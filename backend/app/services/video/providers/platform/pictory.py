"""
PictoryProvider — full-platform AI video via Pictory.ai.

API reference: https://pictory.ai/developers  (v1)

Pictory takes a text script (or article URL) and produces a fully-edited
video with stock footage, captions, background music, and voice-over.
It is a FullPlatformProvider: we hand it the entire VideoJob and it
handles all creative decisions internally.

Flow:
  1. POST /jobs/storyboard  → { jobId, renderJobId } (storyboard phase)
     Poll GET /jobs/{jobId}  until status == "storyboardReady"
  2. POST /jobs/render       → { jobId, renderJobId } (render phase)
     Poll GET /jobs/{jobId}  until status == "renderComplete"
  3. job.preview.videoURL   — final MP4 URL
  4. Download MP4 to local path

Configuration keys (tenant.config.video):
  api_keys.pictory          : Pictory API key (required)
  pictory_user_id           : Pictory user/account ID (required by their API)
  pictory_brand_logo_url    : (optional) company logo watermark URL
  pictory_voiceover_lang    : BCP-47 locale, default "en"
  pictory_music_volume      : 0.0–1.0, default 0.3
  pictory_highlight_colour  : hex, default "#0072ff"
  pictory_auto_highlight    : bool, default True
  pictory_webhook_url       : (optional) callback URL for async notifications

.env equivalents:
  VIDEO_PICTORY_KEY         : Pictory API key

Polling strategy:
  Storyboard phase: every 5 s, timeout 120 s
  Render phase    : every 10 s, timeout 900 s (Pictory renders can take ~5 min)
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp

from app.services.video.providers.base import FullPlatformProvider, PlatformStatus

if TYPE_CHECKING:
    from app.models.video_job import VideoJob

log = logging.getLogger(__name__)

_API_BASE          = "https://api.pictory.ai/pictoryapis/v1"
_STORYBOARD_EP     = "/jobs/storyboard"
_RENDER_EP         = "/jobs/render"
_TIMEOUT_HTTP      = aiohttp.ClientTimeout(total=60.0)

_STORYBOARD_POLL   = 5.0
_STORYBOARD_WAIT   = 120.0
_RENDER_POLL       = 10.0
_RENDER_WAIT       = 900.0

# Pictory aspect ratios
_ASPECT_MAP = {
    "landscape": "16:9",
    "portrait":  "9:16",
    "square":    "1:1",
}


class PictoryProvider(FullPlatformProvider):
    """
    Submits a VideoJob to Pictory.ai and returns the rendered MP4 URL.

    The job's script text (assembled from LLM plan) is POSTed to Pictory's
    storyboard API, then rendered.  Settings from VideoJob.settings are
    used where possible (aspect_ratio, language, brand colours).
    """

    def __init__(
        self,
        api_key: str,
        user_id: str,
        brand_logo_url: str = "",
        voiceover_lang: str = "en",
        music_volume: float = 0.3,
        highlight_colour: str = "#0072ff",
        auto_highlight: bool = True,
        webhook_url: str = "",
    ) -> None:
        if not api_key:
            raise ValueError("PictoryProvider requires an API key")
        if not user_id:
            raise ValueError(
                "PictoryProvider requires pictory_user_id. "
                "Find it in your Pictory account settings."
            )
        self._api_key          = api_key
        self._user_id          = user_id
        self._brand_logo_url   = brand_logo_url
        self._voiceover_lang   = voiceover_lang
        self._music_volume     = max(0.0, min(1.0, music_volume))
        self._highlight_colour = highlight_colour
        self._auto_highlight   = auto_highlight
        self._webhook_url      = webhook_url

    # ── FullPlatformProvider interface ────────────────────────────────────────

    async def create_video(self, job: "VideoJob") -> str:
        """
        Submit the job to Pictory and run to completion.

        Returns the Pictory render job ID, which can be passed to get_status()
        for external polling.  For convenience, this method also blocks until
        the render is complete and returns the completed render job ID with
        the output_url already populated internally.

        The Celery task is responsible for downloading the final MP4 from the
        URL returned by get_status().output_url.
        """
        headers = self._headers()
        async with aiohttp.ClientSession(
            headers=headers, timeout=_TIMEOUT_HTTP
        ) as session:
            # Phase 1: storyboard
            sb_job_id = await self._storyboard(session, job)
            await self._wait_for_state(
                session, sb_job_id,
                target_status="storyboardReady",
                poll_interval=_STORYBOARD_POLL,
                timeout=_STORYBOARD_WAIT,
                phase="storyboard",
            )
            # Phase 2: render
            render_job_id = await self._render(session, sb_job_id)
            await self._wait_for_state(
                session, render_job_id,
                target_status="renderComplete",
                poll_interval=_RENDER_POLL,
                timeout=_RENDER_WAIT,
                phase="render",
            )

        return render_job_id

    async def get_status(self, platform_job_id: str) -> PlatformStatus:
        """Poll Pictory for current job status."""
        async with aiohttp.ClientSession(
            headers=self._headers(), timeout=_TIMEOUT_HTTP
        ) as session:
            data = await self._get_job(session, platform_job_id)

        status = data.get("status", "")
        if status == "renderComplete":
            output_url = (
                data.get("preview", {}).get("videoURL")
                or data.get("videoURL")
                or ""
            )
            return PlatformStatus(
                status="done",
                output_url=output_url,
            )
        if status in ("failed", "error", "errorOccurred"):
            err = data.get("errorMessage") or data.get("message") or status
            return PlatformStatus(status="failed", error=err)
        if status == "storyboardReady":
            return PlatformStatus(status="processing")
        # queued / processing / etc.
        return PlatformStatus(status="processing")

    # ── Private helpers ───────────────────────────────────────────────────────

    def _headers(self) -> dict[str, str]:
        return {
            "X-Pictory-User-Id": self._user_id,
            "Authorization":     self._api_key,
            "Content-Type":      "application/json",
            "Accept":            "application/json",
        }

    async def _storyboard(
        self,
        session: aiohttp.ClientSession,
        job: "VideoJob",
    ) -> str:
        """POST /jobs/storyboard → returns storyboard job ID."""
        settings: dict = job.settings or {}
        plan:     dict = job.render_plan or {}

        # Assemble full script text from render plan scenes
        script_text = self._build_script(plan, job.title or "")

        aspect_raw  = settings.get("aspect_ratio", "landscape")
        aspect      = _ASPECT_MAP.get(aspect_raw, "16:9")
        language    = job.language or self._voiceover_lang or "en"
        duration    = int(settings.get("duration_seconds", 60))

        body: dict = {
            "videoName":       job.title or "Axis AI Video",
            "videoDescription": job.title or "",
            "language":        language,
            "videoWidth":      1920 if aspect == "16:9" else (1080 if aspect == "1:1" else 1080),
            "videoHeight":     1080 if aspect == "16:9" else (1080 if aspect == "1:1" else 1920),
            "scenes": [
                {
                    "text":     script_text,
                    "durationInSeconds": duration,
                    "keywords": [],
                }
            ],
            "voiceOver": {
                "enabled":  True,
                "language": language,
            },
            "musicVolume":    self._music_volume,
            "autoHighlight":  self._auto_highlight,
            "highlightColor": self._highlight_colour,
        }

        if self._brand_logo_url:
            body["brandLogo"] = {"url": self._brand_logo_url}
        if self._webhook_url:
            body["webhookUrl"] = self._webhook_url

        # Brand colours from settings
        primary_colour = settings.get("brand_colour") or settings.get("colortheme", "")
        if primary_colour:
            body["brandColors"] = [primary_colour]

        async with session.post(f"{_API_BASE}{_STORYBOARD_EP}", json=body) as resp:
            if not resp.ok:
                text = await resp.text()
                raise RuntimeError(
                    f"Pictory storyboard failed ({resp.status}): {text[:400]}"
                )
            data = await resp.json()

        job_id = data.get("jobId") or data.get("renderJobId")
        if not job_id:
            raise RuntimeError(f"Pictory storyboard returned no jobId: {data}")

        log.info("pictory_storyboard_submitted", job_id=job_id)
        return job_id

    async def _render(
        self,
        session: aiohttp.ClientSession,
        storyboard_job_id: str,
    ) -> str:
        """POST /jobs/render → returns render job ID."""
        body = {"jobId": storyboard_job_id}
        async with session.post(f"{_API_BASE}{_RENDER_EP}", json=body) as resp:
            if not resp.ok:
                text = await resp.text()
                raise RuntimeError(
                    f"Pictory render failed ({resp.status}): {text[:400]}"
                )
            data = await resp.json()

        render_id = data.get("renderJobId") or data.get("jobId")
        if not render_id:
            raise RuntimeError(f"Pictory render returned no renderJobId: {data}")

        log.info("pictory_render_submitted", render_id=render_id)
        return render_id

    async def _wait_for_state(
        self,
        session: aiohttp.ClientSession,
        job_id: str,
        target_status: str,
        poll_interval: float,
        timeout: float,
        phase: str,
    ) -> None:
        """Poll until job reaches target_status or timeout/error."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            data   = await self._get_job(session, job_id)
            status = data.get("status", "")
            log.debug("pictory_poll", phase=phase, job_id=job_id, status=status)

            if status == target_status:
                return
            if status in ("failed", "error", "errorOccurred"):
                err = data.get("errorMessage") or data.get("message") or status
                raise RuntimeError(
                    f"Pictory {phase} job {job_id} failed: {err}"
                )
            await asyncio.sleep(poll_interval)

        raise TimeoutError(
            f"Pictory {phase} job {job_id} did not reach '{target_status}' "
            f"within {timeout:.0f} seconds"
        )

    async def _get_job(
        self,
        session: aiohttp.ClientSession,
        job_id: str,
    ) -> dict:
        """GET /jobs/{job_id} → raw response dict."""
        async with session.get(f"{_API_BASE}/jobs/{job_id}") as resp:
            resp.raise_for_status()
            return await resp.json()

    @staticmethod
    def _build_script(plan: dict, title: str) -> str:
        """
        Assemble a single script string from the LLM render plan.
        Handles all scene schema formats (scenes, phrases, slides, turns).
        """
        parts: list[str] = []

        scenes = (
            plan.get("scenes")
            or plan.get("phrases")
            or plan.get("slides")
            or plan.get("sections")
            or []
        )
        for scene in scenes:
            text = (
                scene.get("narration")
                or scene.get("text")
                or scene.get("caption")
                or scene.get("content")
                or scene.get("body")
                or ""
            )
            if text:
                parts.append(text.strip())

        # Conversational turns
        for turn in plan.get("turns", []):
            line = turn.get("line") or turn.get("text") or ""
            if line:
                parts.append(line.strip())

        if not parts:
            parts.append(title or "AI Generated Video")

        return "\n\n".join(parts)
