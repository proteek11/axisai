"""
DIDProvider — D-ID AI talking-head avatar video generation.

API reference: https://docs.d-id.com/reference/create-a-talk

Flow:
  1. POST /talks          → returns { id: "tlk_xxx" }
  2. Poll GET /talks/{id} until status == "done" or "error"
  3. Download result_url  → MP4 file

Supported presenter types:
  - "image"   : still-image presenter (default; upload or URL)
  - "clip"    : D-ID Studio clip presenters

Configuration keys (tenant.config.video):
  api_keys.d_id           : D-ID API key (Basic auth username; password = "")
  d_id_presenter_id       : D-ID presenter image URL or presenter_id
  d_id_driver_id          : (optional) D-ID driver clip ID for mouth movement style
  d_id_stitch             : bool, default True (auto-crop + align head)
  d_id_fluent             : bool, default False (smoother but slower)
  d_id_pad_audio          : float seconds of silence to pad start (default 0.0)
  d_id_crop_type          : "wide" | "square" | "vertical"  (default "wide")

.env equivalents:
  VIDEO_D_ID_KEY          : D-ID API key
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from pathlib import Path

import aiohttp

from app.services.video.providers.base import AvatarInfo, AvatarProvider

log = logging.getLogger(__name__)

_BASE_URL      = "https://api.d-id.com"
_POLL_INTERVAL = 5.0   # seconds between status checks
_POLL_TIMEOUT  = 600.0  # 10 minutes max
_TIMEOUT_SEC   = 60.0


class DIDProvider(AvatarProvider):
    """
    D-ID talking-head avatar via the D-ID Talks API.

    The D-ID API uses HTTP Basic auth where the API key is the username
    and the password is an empty string.
    """

    def __init__(
        self,
        api_key: str,
        default_presenter_id: str = "",
        driver_id: str = "",
        stitch: bool = True,
        fluent: bool = False,
        pad_audio: float = 0.0,
        crop_type: str = "wide",
    ) -> None:
        if not api_key:
            raise ValueError("DIDProvider requires an API key")
        # D-ID uses Basic auth: base64(key + ":")
        credentials   = base64.b64encode(f"{api_key}:".encode()).decode()
        self._auth     = f"Basic {credentials}"
        self._presenter_id  = default_presenter_id
        self._driver_id     = driver_id
        self._stitch        = stitch
        self._fluent        = fluent
        self._pad_audio     = pad_audio
        self._crop_type     = crop_type

    # ── AvatarProvider interface ──────────────────────────────────────────────

    async def create_video(
        self,
        script: str,
        avatar_id: str,
        voice_id: str,
        language: str,
        output_path: Path,
        **kwargs,                # absorb renderer template settings not used by D-ID
    ) -> float:
        """
        Generate a lip-synced talking-head video via D-ID.

        avatar_id : D-ID presenter image URL  OR  a D-ID presenter_id string.
                    Falls back to self._presenter_id if empty.
        voice_id  : TTS voice identifier — passed through to D-ID's built-in
                    TTS engine.  Format: "microsoft|en-US-JennyNeural"
                    (provider|voice_name).  If blank, D-ID uses its default.
        language  : BCP-47 locale code, e.g. "en-US".
        """
        presenter = avatar_id or self._presenter_id
        if not presenter:
            raise ValueError(
                "DIDProvider: no presenter specified. "
                "Pass avatar_id or set d_id_presenter_id in tenant config."
            )

        timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SEC)
        async with aiohttp.ClientSession(
            headers={
                "Authorization": self._auth,
                "Content-Type":  "application/json",
                "Accept":        "application/json",
            },
            timeout=timeout,
        ) as session:
            talk_id = await self._create_talk(
                session, presenter, script, voice_id, language
            )
            output_url = await self._poll_until_done(session, talk_id)
            duration   = await self._download(session, output_url, output_path)

        return duration

    async def list_avatars(self) -> list[AvatarInfo]:
        """Return available D-ID presenter clips on this account."""
        timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SEC)
        async with aiohttp.ClientSession(
            headers={
                "Authorization": self._auth,
                "Accept":        "application/json",
            },
            timeout=timeout,
        ) as session:
            async with session.get(f"{_BASE_URL}/clips") as resp:
                if resp.status == 404:
                    # Clips endpoint may not be available on all plans
                    return []
                resp.raise_for_status()
                data = await resp.json()

        clips = data.get("clips", [])
        return [
            AvatarInfo(
                avatar_id=c.get("id", ""),
                name=c.get("name", c.get("id", "")),
                thumbnail_url=c.get("thumbnail_url"),
            )
            for c in clips
        ]

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _create_talk(
        self,
        session: aiohttp.ClientSession,
        presenter: str,
        script: str,
        voice_id: str,
        language: str,
    ) -> str:
        """POST /talks and return the talk_id."""
        # Determine if presenter is a URL or a clips presenter_id
        source_url: str | None     = None
        presenter_id_val: str | None = None
        if presenter.startswith("http://") or presenter.startswith("https://"):
            source_url = presenter
        else:
            presenter_id_val = presenter

        # Build the script payload
        script_payload: dict = {
            "type":       "text",
            "input":      script,
            "provider":   self._build_tts_provider(voice_id, language),
        }
        if self._pad_audio > 0:
            script_payload["ssml"] = False  # pad_audio handled server-side only
            script_payload["audio_silence_dutation"] = int(self._pad_audio * 1000)

        # Build the config payload
        config_payload: dict = {
            "stitch":     self._stitch,
            "fluent":     self._fluent,
            "crop_type":  self._crop_type,
        }
        if self._driver_id:
            config_payload["driver_id"] = self._driver_id

        # Assemble the full request body
        body: dict = {
            "script": script_payload,
            "config": config_payload,
        }
        if source_url:
            body["source_url"] = source_url
        if presenter_id_val:
            body["presenter_id"] = presenter_id_val

        async with session.post(f"{_BASE_URL}/talks", json=body) as resp:
            if not resp.ok:
                text = await resp.text()
                raise RuntimeError(
                    f"D-ID /talks failed ({resp.status}): {text[:400]}"
                )
            data = await resp.json()

        talk_id = data.get("id")
        if not talk_id:
            raise RuntimeError(f"D-ID /talks returned no id: {data}")
        log.info("d_id_talk_created", talk_id=talk_id)
        return talk_id

    async def _poll_until_done(
        self, session: aiohttp.ClientSession, talk_id: str
    ) -> str:
        """Poll GET /talks/{id} until status == 'done'. Returns result_url."""
        deadline = time.monotonic() + _POLL_TIMEOUT
        while time.monotonic() < deadline:
            async with session.get(f"{_BASE_URL}/talks/{talk_id}") as resp:
                resp.raise_for_status()
                data = await resp.json()

            status = data.get("status", "")
            log.debug("d_id_poll", talk_id=talk_id, status=status)

            if status == "done":
                result_url = data.get("result_url")
                if not result_url:
                    raise RuntimeError(
                        f"D-ID talk {talk_id} done but result_url missing"
                    )
                return result_url

            if status == "error":
                error_detail = data.get("error", {})
                raise RuntimeError(
                    f"D-ID talk {talk_id} failed: {error_detail}"
                )

            await asyncio.sleep(_POLL_INTERVAL)

        raise TimeoutError(
            f"D-ID talk {talk_id} did not complete within "
            f"{_POLL_TIMEOUT:.0f} seconds"
        )

    @staticmethod
    async def _download(
        session: aiohttp.ClientSession,
        url: str,
        output_path: Path,
    ) -> float:
        """Download MP4 from result_url and return duration via file size estimate."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        async with session.get(url) as resp:
            resp.raise_for_status()
            data = await resp.read()

        output_path.write_bytes(data)

        # Try to get precise duration via ffprobe
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            return float(stdout.decode().strip())
        except Exception:
            # Rough estimate: ~1 MB ≈ 8 s at 1 Mbps
            return len(data) / (1024 * 1024 / 8.0)

    @staticmethod
    def _build_tts_provider(voice_id: str, language: str) -> dict:
        """
        Build the D-ID TTS provider dict from a voice_id string.

        Supported formats:
          "microsoft|en-US-JennyNeural"   → {type:"microsoft", voice_id:"..."}
          "amazon|Joanna"                  → {type:"amazon", voice_id:"..."}
          ""                               → {type:"microsoft"} (D-ID default)
        """
        if "|" in voice_id:
            provider_type, vid = voice_id.split("|", 1)
            return {"type": provider_type.strip(), "voice_id": vid.strip()}
        # Fallback: pick Microsoft Neural by language
        _LANG_MAP = {
            "en": "en-US-JennyNeural",
            "hi": "hi-IN-SwaraNeural",
            "es": "es-ES-ElviraNeural",
            "fr": "fr-FR-DeniseNeural",
            "de": "de-DE-KatjaNeural",
            "ar": "ar-SA-ZariyahNeural",
            "zh": "zh-CN-XiaoxiaoNeural",
            "pt": "pt-BR-FranciscaNeural",
            "ja": "ja-JP-NanamiNeural",
            "ko": "ko-KR-SunHiNeural",
        }
        lang_prefix = (language or "en").split("-")[0].lower()
        voice       = _LANG_MAP.get(lang_prefix, "en-US-JennyNeural")
        return {"type": "microsoft", "voice_id": voice}
