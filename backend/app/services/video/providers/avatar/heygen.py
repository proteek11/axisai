"""
HeyGenProvider — AI talking-head avatar video via HeyGen API v2.

HeyGen turns a text script into a lip-synced avatar video using one of their
photorealistic or illustrated avatars.  The result is an HD MP4 download URL.

API reference:
  POST https://api.heygen.com/v2/video/generate   — submit job
  GET  https://api.heygen.com/v1/video_status.get — poll status
  GET  https://api.heygen.com/v2/avatars           — list avatars
  GET  https://api.heygen.com/v2/voices            — list TTS voices

Configuration:
  api_key         : VIDEO_HEYGEN_KEY env var  OR  tenant.config.video.api_keys.heygen
  default_avatar_id : tenant.config.video.heygen_avatar_id  (optional)
  default_voice_id  : tenant.config.video.heygen_voice_id   (optional)

create_video() contract:
  Submits the job and polls synchronously (with configurable timeout).
  Downloads the finished MP4 to output_path.
  Returns video duration in seconds.

Polling:
  HeyGen takes 1-5 minutes per clip.  We poll every POLL_INTERVAL_SEC up to
  POLL_TIMEOUT_SEC.  The Celery task wraps this in a 30-min overall timeout.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

import httpx
import structlog

from app.services.video.providers.base import AvatarInfo, AvatarProvider

log = structlog.get_logger(__name__)

_API_BASE    = "https://api.heygen.com"
_GENERATE    = f"{_API_BASE}/v2/video/generate"
_STATUS      = f"{_API_BASE}/v1/video_status.get"
_LIST_AVATARS= f"{_API_BASE}/v2/avatars"
_LIST_VOICES = f"{_API_BASE}/v2/voices"

POLL_INTERVAL_SEC = 10
POLL_TIMEOUT_SEC  = 1800   # 30 minutes — hard cap

# HeyGen status values
_STATUS_PENDING    = "pending"
_STATUS_PROCESSING = "processing"
_STATUS_COMPLETED  = "completed"
_STATUS_FAILED     = "failed"
_TERMINAL_STATUSES = {_STATUS_COMPLETED, _STATUS_FAILED}


class HeyGenProvider(AvatarProvider):
    """
    HeyGen API v2 — photorealistic & illustrated avatar video generation.

    Single instance is reused across calls.  The httpx.AsyncClient is
    created fresh per call so there are no connection-lifetime issues.
    """

    def __init__(
        self,
        api_key: str,
        default_avatar_id: str = "",
        default_voice_id: str = "",
    ) -> None:
        if not api_key:
            raise ValueError("HeyGenProvider requires a non-empty api_key")
        self._api_key         = api_key
        self._default_avatar  = default_avatar_id
        self._default_voice   = default_voice_id

    # ── AvatarProvider interface ──────────────────────────────────────────────

    async def create_video(
        self,
        script: str,
        avatar_id: str,
        voice_id: str,
        language: str,
        output_path: Path,
        # Template settings passed through from AvatarRenderer
        avatar_style: str = "normal",
        avatar_position: str = "center",
        voice_speed: float = 1.0,
        voice_emotion: str | None = None,
        background_type: str = "color",
        background_value: str | None = None,
        show_captions: bool = False,
        **kwargs,
    ) -> float:
        """
        Submit script to HeyGen, poll until done, download MP4 to output_path.

        avatar_id      : HeyGen avatar ID (e.g. "josh_lite3_20230714").
                         Falls back to default_avatar_id from config.
        voice_id       : HeyGen voice ID.  Falls back to default_voice_id.
        avatar_style   : "normal" | "closeUp" | "circle"
        avatar_position: "left" | "right" | "center"  (used as background_color shorthand)
        voice_speed    : 0.5 – 2.0  (HeyGen v2 supports speed parameter)
        voice_emotion  : "excited" | "friendly" | "serious" | "soothing" | "broadcaster"
        background_type: "color" | "image" | "video"
        background_value: hex colour string or asset URL, depending on background_type
        show_captions  : (reserved — HeyGen caption setting, not yet in v2 API)

        Returns video duration in seconds.
        Raises RuntimeError if the job fails or times out.
        """
        resolved_avatar = avatar_id or self._default_avatar
        resolved_voice  = voice_id  or self._default_voice

        if not resolved_avatar:
            raise ValueError(
                "No HeyGen avatar_id provided and no default configured. "
                "Set heygen_avatar_id in tenant.config.video or in the job settings."
            )

        # ── Submit job ────────────────────────────────────────────────────────
        log.info(
            "heygen_submit",
            avatar_id=resolved_avatar,
            voice_id=resolved_voice,
            script_chars=len(script),
        )

        video_id = await self._submit(
            script=script,
            avatar_id=resolved_avatar,
            voice_id=resolved_voice,
            avatar_style=avatar_style,
            voice_speed=voice_speed,
            voice_emotion=voice_emotion,
            background_type=background_type,
            background_value=background_value,
        )

        log.info("heygen_job_submitted", video_id=video_id)

        # ── Poll for completion ───────────────────────────────────────────────
        mp4_url = await self._poll_until_done(video_id)

        # ── Download MP4 ──────────────────────────────────────────────────────
        output_path.parent.mkdir(parents=True, exist_ok=True)
        await self._download(mp4_url, output_path)

        duration = await self._measure_duration(output_path)
        log.info(
            "heygen_video_ready",
            video_id=video_id,
            duration_sec=round(duration, 1),
            output=str(output_path),
        )
        return duration

    async def list_avatars(self) -> list[AvatarInfo]:
        """Return all HeyGen avatars available on this account."""
        try:
            data = await self._get(_LIST_AVATARS)
        except Exception as exc:  # noqa: BLE001
            log.warning("heygen_list_avatars_failed", error=str(exc))
            return []

        avatars: list[AvatarInfo] = []
        for item in data.get("data", {}).get("avatars", []):
            avatars.append(
                AvatarInfo(
                    avatar_id=item.get("avatar_id", ""),
                    name=item.get("avatar_name", item.get("avatar_id", "")),
                    thumbnail_url=item.get("preview_image_url"),
                    gender=item.get("gender"),
                )
            )
        return avatars

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _submit(
        self,
        script: str,
        avatar_id: str,
        voice_id: str,
        avatar_style: str = "normal",
        voice_speed: float = 1.0,
        voice_emotion: str | None = None,
        background_type: str = "color",
        background_value: str | None = None,
    ) -> str:
        """
        POST to HeyGen /v2/video/generate.
        Returns the HeyGen video_id string.
        """
        # ── Voice block ───────────────────────────────────────────────────────
        voice_block: dict = {
            "type":       "text",
            "input_text": script,
        }
        if voice_id:
            voice_block["voice_id"] = voice_id
        # Clamp speed to HeyGen accepted range 0.5–2.0
        speed = max(0.5, min(2.0, float(voice_speed)))
        if speed != 1.0:
            voice_block["speed"] = speed
        if voice_emotion:
            # HeyGen v2 emotion values: excited friendly serious soothing broadcaster
            voice_block["emotion"] = voice_emotion

        # ── Background block ──────────────────────────────────────────────────
        bg_type = background_type or "color"
        if bg_type == "color":
            bg_block: dict = {
                "type":  "color",
                "value": background_value or "#ffffff",
            }
        elif bg_type == "image":
            bg_block = {
                "type":       "image",
                "url":        background_value or "",
                "fit":        "cover",
            }
        elif bg_type == "video":
            bg_block = {
                "type":  "video",
                "url":   background_value or "",
                "play_style": "loop",
                "fit":   "cover",
            }
        else:
            bg_block = {"type": "color", "value": "#ffffff"}

        payload: dict = {
            "video_inputs": [
                {
                    "character": {
                        "type":         "avatar",
                        "avatar_id":    avatar_id,
                        "avatar_style": avatar_style or "normal",
                    },
                    "voice":      voice_block,
                    "background": bg_block,
                }
            ],
            "dimension": {"width": 1280, "height": 720},
            "test": False,
        }

        data = await self._post(_GENERATE, payload)
        video_id: str | None = data.get("data", {}).get("video_id")
        if not video_id:
            raise RuntimeError(
                f"HeyGen submit returned no video_id. Response: {data}"
            )
        return video_id

    async def _poll_until_done(self, video_id: str) -> str:
        """
        Poll _STATUS endpoint until status is completed or failed.

        Returns the MP4 download URL on success.
        Raises RuntimeError on failure or timeout.
        """
        deadline = time.monotonic() + POLL_TIMEOUT_SEC
        attempts = 0

        while time.monotonic() < deadline:
            attempts += 1
            await asyncio.sleep(POLL_INTERVAL_SEC)

            try:
                data = await self._get(_STATUS, params={"video_id": video_id})
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "heygen_poll_error",
                    video_id=video_id,
                    attempt=attempts,
                    error=str(exc),
                )
                continue

            status_data: dict = data.get("data", {})
            current_status: str = status_data.get("status", "")
            log.debug(
                "heygen_poll",
                video_id=video_id,
                status=current_status,
                attempt=attempts,
            )

            if current_status == _STATUS_COMPLETED:
                mp4_url: str = status_data.get("video_url", "")
                if not mp4_url:
                    raise RuntimeError(
                        f"HeyGen job {video_id} completed but video_url is empty"
                    )
                return mp4_url

            if current_status == _STATUS_FAILED:
                error_msg = status_data.get("error", "Unknown HeyGen error")
                raise RuntimeError(
                    f"HeyGen job {video_id} failed: {error_msg}"
                )

        raise RuntimeError(
            f"HeyGen job {video_id} timed out after {POLL_TIMEOUT_SEC // 60} minutes "
            f"({attempts} poll attempts)"
        )

    async def _download(self, url: str, dest: Path) -> None:
        """Stream-download the MP4 from HeyGen's CDN to dest."""
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with dest.open("wb") as f:
                    async for chunk in response.aiter_bytes(65_536):
                        f.write(chunk)
        log.debug("heygen_download_done", dest=str(dest), size=dest.stat().st_size)

    async def _get(self, url: str, params: dict | None = None) -> dict:
        headers = {
            "X-Api-Key": self._api_key,
            "Accept": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            response = await client.get(url, params=params or {})
            response.raise_for_status()
            return response.json()

    async def _post(self, url: str, payload: dict) -> dict:
        headers = {
            "X-Api-Key": self._api_key,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30.0, headers=headers) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    @staticmethod
    async def _measure_duration(mp4_path: Path) -> float:
        """
        Measure duration of the downloaded MP4 using moviepy (async-safe).
        Falls back to 0.0 if moviepy is unavailable.
        """
        def _blocking() -> float:
            try:
                from moviepy import VideoFileClip
                with VideoFileClip(str(mp4_path)) as clip:
                    return float(clip.duration)
            except Exception as exc:  # noqa: BLE001
                log.warning("heygen_duration_measure_failed", error=str(exc))
                return 0.0

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _blocking)
