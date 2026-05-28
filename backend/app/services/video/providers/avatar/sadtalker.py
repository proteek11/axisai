"""
SadTalkerProvider — local GPU lip-sync via the SadTalker REST API.

SadTalker (https://github.com/OpenTalker/SadTalker) must be running as a
local HTTP server.  A minimal FastAPI wrapper is typical:

    POST /generate
    Body (multipart/form-data):
      source_image : PNG/JPEG portrait
      driven_audio : WAV/MP3 audio
      preprocess   : "crop" | "resize" | "full"
      still_mode   : bool (less head motion)
      use_enhancer : bool (GFPGAN face enhance)
      batch_size   : int  (default 1)
    Response: { "video_path": "/tmp/result.mp4" }   OR streamed MP4

Alternatively, many deployments serve the raw MP4 directly.
This provider handles both patterns:
  - If Content-Type is video/*  → write body directly to output_path
  - Otherwise                  → parse JSON and fetch the video_path URL

Configuration keys (tenant.config.video):
  sadtalker_url         : base URL, e.g. "http://localhost:7860"  (required)
  sadtalker_preprocess  : "crop" | "resize" | "full"  (default "crop")
  sadtalker_still       : bool (default False — natural head movement)
  sadtalker_enhancer    : bool (default True — GFPGAN quality boost)
  sadtalker_batch_size  : int  (default 1)

Since SadTalker is a local GPU process it does NOT use a cloud API key.
The source portrait image is pulled from:
  avatar_id → treated as a local file path OR an HTTP URL.
  Falls back to sadtalker_default_portrait if avatar_id is empty.

TTS audio is expected to already exist as a WAV/MP3 file — the path is
passed in via voice_id (treated as audio file path when using SadTalker).
If voice_id is empty the caller must pre-synthesise and pass the audio path.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import aiohttp

from app.services.video.providers.base import AvatarInfo, AvatarProvider

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT   = 600.0   # SadTalker GPU can be slow — 10 minutes
_GENERATE_ENDPOINT = "/generate"


class SadTalkerProvider(AvatarProvider):
    """
    Lip-sync avatar using locally-hosted SadTalker.

    Requires:
      - SadTalker REST server running at sadtalker_url
      - GPU with VRAM ≥ 4 GB (8 GB+ recommended for enhancer)

    IMPORTANT: SadTalker does not perform TTS internally.
    The AvatarRenderer detects requires_pre_tts=True and synthesises
    audio first, then passes the audio file path as voice_id.
    """

    # Signals to AvatarRenderer that TTS must be run before calling create_video()
    # and the resulting audio file path passed as voice_id.
    requires_pre_tts: bool = True

    def __init__(
        self,
        base_url: str,
        preprocess: str = "crop",
        still_mode: bool = False,
        use_enhancer: bool = True,
        batch_size: int = 1,
        default_portrait: str = "",
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        if not base_url:
            raise ValueError(
                "SadTalkerProvider requires sadtalker_url. "
                "Set tenant.config.video.sadtalker_url to the local server address."
            )
        self._base_url         = base_url.rstrip("/")
        self._preprocess       = preprocess
        self._still_mode       = still_mode
        self._use_enhancer     = use_enhancer
        self._batch_size       = batch_size
        self._default_portrait = default_portrait
        self._timeout          = timeout

    # ── AvatarProvider interface ──────────────────────────────────────────────

    async def create_video(
        self,
        script: str,
        avatar_id: str,
        voice_id: str,
        language: str,
        output_path: Path,
        **kwargs,                # absorb renderer template settings not used by SadTalker
    ) -> float:
        """
        Generate a lip-synced video using SadTalker.

        avatar_id : Path (absolute or relative) OR http URL to a portrait image.
                    Falls back to self._default_portrait if empty.
        voice_id  : Path to pre-synthesised WAV/MP3 audio file.
                    IMPORTANT: SadTalker does NOT do TTS — the audio must
                    already exist.  The renderer pipeline is responsible for
                    running the TTS step first and passing the audio path here.
        script    : Not used by SadTalker directly (TTS is handled upstream).
        language  : Not used by SadTalker (no TTS).
        """
        portrait_src = avatar_id or self._default_portrait
        if not portrait_src:
            raise ValueError(
                "SadTalkerProvider: no portrait source. "
                "Pass avatar_id or set sadtalker_default_portrait in tenant config."
            )
        if not voice_id:
            raise ValueError(
                "SadTalkerProvider: voice_id must be the path to a pre-synthesised "
                "audio file (WAV/MP3).  Run TTS first, then pass the audio path."
            )

        audio_path = Path(voice_id)
        if not audio_path.exists():
            raise FileNotFoundError(
                f"SadTalker audio file not found: {audio_path}"
            )

        timeout = aiohttp.ClientTimeout(total=self._timeout)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Get portrait bytes
            portrait_bytes, portrait_name = await self._load_portrait(
                session, portrait_src
            )
            # POST to SadTalker
            video_bytes = await self._call_sadtalker(
                session, portrait_bytes, portrait_name, audio_path
            )

        # Write output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(video_bytes)

        return await self._measure_duration(output_path)

    async def list_avatars(self) -> list[AvatarInfo]:
        """
        SadTalker does not have a managed avatar library — portraits are
        arbitrary image files.  Returns an empty list; callers should
        enumerate portrait files themselves.
        """
        return []

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _load_portrait(
        self,
        session: aiohttp.ClientSession,
        src: str,
    ) -> tuple[bytes, str]:
        """Load portrait bytes from a local path or HTTP URL."""
        if src.startswith("http://") or src.startswith("https://"):
            async with session.get(src) as resp:
                resp.raise_for_status()
                data = await resp.read()
            name = src.rsplit("/", 1)[-1] or "portrait.jpg"
            return data, name

        p = Path(src)
        if not p.exists():
            raise FileNotFoundError(f"Portrait file not found: {p}")
        return p.read_bytes(), p.name

    async def _call_sadtalker(
        self,
        session: aiohttp.ClientSession,
        portrait_bytes: bytes,
        portrait_name: str,
        audio_path: Path,
    ) -> bytes:
        """POST to SadTalker /generate and return the MP4 bytes."""
        form = aiohttp.FormData()
        form.add_field(
            "source_image",
            portrait_bytes,
            filename=portrait_name,
            content_type="image/jpeg",
        )
        form.add_field(
            "driven_audio",
            audio_path.read_bytes(),
            filename=audio_path.name,
            content_type="audio/mpeg",
        )
        form.add_field("preprocess",   self._preprocess)
        form.add_field("still_mode",   str(self._still_mode).lower())
        form.add_field("use_enhancer", str(self._use_enhancer).lower())
        form.add_field("batch_size",   str(self._batch_size))

        url = f"{self._base_url}{_GENERATE_ENDPOINT}"
        log.info("sadtalker_request", url=url, audio=str(audio_path))

        async with session.post(url, data=form) as resp:
            if not resp.ok:
                text = await resp.text()
                raise RuntimeError(
                    f"SadTalker /generate failed ({resp.status}): {text[:400]}"
                )
            content_type = resp.headers.get("Content-Type", "")
            if content_type.startswith("video/"):
                # Server streams raw MP4
                return await resp.read()
            # JSON response with path or URL
            data = await resp.json()

        video_ref = data.get("video_path") or data.get("video_url") or ""
        if not video_ref:
            raise RuntimeError(
                f"SadTalker response missing video_path/video_url: {data}"
            )

        # Fetch the referenced video
        if video_ref.startswith("http"):
            async with session.get(video_ref) as fetch_resp:
                fetch_resp.raise_for_status()
                return await fetch_resp.read()

        # Local path on the SadTalker server — try to fetch via /file endpoint
        fetch_url = f"{self._base_url}/file={video_ref}"
        async with session.get(fetch_url) as fetch_resp:
            if fetch_resp.ok:
                return await fetch_resp.read()
            raise RuntimeError(
                f"Cannot fetch SadTalker result from {fetch_url} "
                f"({fetch_resp.status})"
            )

    @staticmethod
    async def _measure_duration(path: Path) -> float:
        """Return video duration in seconds via ffprobe, or rough estimate."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10.0)
            return float(stdout.decode().strip())
        except Exception:
            size = path.stat().st_size
            # Rough estimate: ~1 MB ≈ 8 s at 1 Mbps
            return size / (1024 * 1024 / 8.0)
