"""
DallE3Provider — OpenAI DALL-E 3 image generation (Tier 1+).

API: https://platform.openai.com/docs/api-reference/images/create
Model: dall-e-3  (1024×1024, 1792×1024, 1024×1792 only)
Cost: ~$0.04 per image (standard quality), ~$0.08 (HD quality)

Configuration:
  api_key : VIDEO_OPENAI_TTS_KEY env var OR tenant.config.video.api_keys.openai_tts
            (reuses the same OpenAI key as OpenAI TTS — no separate key needed)

Phase 2 implementation.  Returns NotImplementedError until this file is complete.
"""
from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import httpx
import structlog

from app.services.video.providers.base import ImageGenProvider

log = structlog.get_logger(__name__)

# DALL-E 3 only supports these sizes
_SUPPORTED_SIZES = {
    (1024, 1024): "1024x1024",
    (1792, 1024): "1792x1024",
    (1024, 1792): "1024x1792",
}
_DEFAULT_SIZE = "1792x1024"  # closest to 16:9 landscape

_DALLE3_URL = "https://api.openai.com/v1/images/generations"


class DallE3Provider(ImageGenProvider):
    """
    OpenAI DALL-E 3 image generation.

    Returns high-quality 1792×1024 landscape images by default.
    For video use the image is further scaled/cropped to the target frame size
    by the renderer's Pillow post-processing step.
    """

    def __init__(self, api_key: str, quality: str = "standard") -> None:
        if not api_key:
            raise ValueError("DallE3Provider requires a non-empty api_key")
        self._api_key = api_key
        self._quality = quality  # "standard" | "hd"

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
        Generate one image from prompt and write PNG to output_path.

        style: "flat illustration" | "photorealistic" | "watercolor" | etc.
        width/height: target frame size. DALL-E 3 always outputs 1792×1024 for
                      landscape; the renderer scales it to exact frame dimensions.
        Returns output_path on success.
        Raises httpx.HTTPError or RuntimeError on failure.
        """
        full_prompt = f"{prompt}. Style: {style}. No text overlays." if style else prompt
        size = self._pick_size(width, height)

        log.info(
            "dalle3_generate",
            prompt_preview=full_prompt[:80],
            size=size,
            quality=self._quality,
        )

        payload = {
            "model": "dall-e-3",
            "prompt": full_prompt[:4000],
            "n": 1,
            "size": size,
            "quality": self._quality,
            "response_format": "b64_json",
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(_DALLE3_URL, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()

        b64 = data["data"][0]["b64_json"]
        img_bytes = base64.b64decode(b64)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(img_bytes)

        log.info(
            "dalle3_done",
            size_bytes=len(img_bytes),
            output=str(output_path),
        )
        return output_path

    # ── Private ───────────────────────────────────────────────────────────────

    @staticmethod
    def _pick_size(width: int, height: int) -> str:
        """Pick the DALL-E 3 size closest to the target aspect ratio."""
        aspect = width / max(height, 1)
        if aspect > 1.2:
            return "1792x1024"  # landscape
        if aspect < 0.83:
            return "1024x1792"  # portrait
        return "1024x1024"      # square
