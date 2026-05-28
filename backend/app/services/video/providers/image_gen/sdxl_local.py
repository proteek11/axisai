"""
SDXLLocalProvider — Stable Diffusion XL via local Automatic1111 API (Tier 0).

Requires a running Automatic1111 WebUI instance with SDXL model loaded.
API: http://localhost:7860 (or VIDEO_SDXL_LOCAL_URL)
Endpoint: POST /sdapi/v1/txt2img

Configuration:
  VIDEO_IMAGE_GEN=sdxl_local
  VIDEO_SDXL_LOCAL_URL=http://localhost:7860   (or wherever A1111 is running)

Cost: $0 (local GPU compute)
GPU: Requires NVIDIA GPU with 6GB+ VRAM for SDXL.

If the API is unreachable, generate() raises RuntimeError so the renderer
can fall back to a Pexels image or solid color.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import httpx
import structlog

from app.services.video.providers.base import ImageGenProvider

log = structlog.get_logger(__name__)

_DEFAULT_STEPS = 20
_DEFAULT_CFG   = 7.0


class SDXLLocalProvider(ImageGenProvider):
    """
    Stable Diffusion XL via local Automatic1111 WebUI API.

    Generates images locally at zero API cost, requires GPU.
    """

    def __init__(self, api_url: str) -> None:
        self._api_url = api_url.rstrip("/")

    # ── ImageGenProvider interface ────────────────────────────────────────────

    async def generate(
        self,
        prompt: str,
        style: str,
        width: int,
        height: int,
        output_path: Path,
    ) -> Path:
        """
        Generate one image via Automatic1111's txt2img endpoint.

        Maps style hint to a negative prompt / style suffix.
        width/height are clamped to multiples of 64 (SDXL requirement).
        Returns output_path on success.
        Raises RuntimeError if the local API is unreachable.
        """
        style_suffix = _STYLE_PROMPTS.get(style.lower() if style else "", "")
        full_prompt = f"{prompt}, {style_suffix}" if style_suffix else prompt

        # SDXL requires dimensions divisible by 64
        gen_w = max(512, (min(width, 1920) // 64) * 64)
        gen_h = max(512, (min(height, 1080) // 64) * 64)

        log.info(
            "sdxl_generate",
            prompt_preview=full_prompt[:80],
            size=f"{gen_w}x{gen_h}",
        )

        payload = {
            "prompt": full_prompt[:2000],
            "negative_prompt": (
                "blurry, low quality, watermark, text, logo, "
                "deformed, ugly, extra limbs"
            ),
            "steps": _DEFAULT_STEPS,
            "cfg_scale": _DEFAULT_CFG,
            "width": gen_w,
            "height": gen_h,
            "sampler_name": "DPM++ 2M Karras",
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self._api_url}/sdapi/v1/txt2img",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise RuntimeError(
                f"SDXL local API unreachable at {self._api_url}: {exc}"
            ) from exc

        b64 = data["images"][0]
        img_bytes = base64.b64decode(b64)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(img_bytes)

        log.info("sdxl_done", size_bytes=len(img_bytes), output=str(output_path))
        return output_path


# Style prompt suffixes keyed by style name
_STYLE_PROMPTS: dict[str, str] = {
    "flat illustration":  "flat vector illustration, minimal, clean lines, pastel colors",
    "photorealistic":     "photorealistic, 8k uhd, professional photography, sharp focus",
    "watercolor":         "watercolor painting, soft edges, artistic, hand-painted",
    "cartoon":            "cartoon style, bold outlines, bright colors, playful",
    "3d render":          "3d render, octane render, studio lighting, glossy materials",
    "sketch":             "pencil sketch, hand-drawn, detailed line art, monochrome",
    "infographic":        "clean infographic style, flat design, data visualization",
    "corporate":          "professional corporate photography, clean background, business",
}
