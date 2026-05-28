"""
PexelsProvider — Pexels free stock video & image search.

Pexels API v1 documentation: https://www.pexels.com/api/documentation/

Rate limits (free tier):
  - 200 requests/hour, 20,000 requests/month
  - No commercial use restriction for video embeds

API key: VIDEO_PEXELS_API_KEY in .env  OR  tenant.config.video.api_keys.pexels

Video search endpoint  : GET https://api.pexels.com/videos/search
Image search endpoint  : GET https://api.pexels.com/v1/search
"""
from __future__ import annotations

from pathlib import Path

import httpx
import structlog

from app.services.video.providers.base import StockClip, StockImage, StockProvider

log = structlog.get_logger(__name__)

_VIDEOS_BASE = "https://api.pexels.com/videos/search"
_IMAGES_BASE = "https://api.pexels.com/v1/search"

# Preferred video file qualities, in order of preference
_VIDEO_QUALITY_ORDER = ("hd", "fhd", "sd")

# Target resolution thresholds for clip selection (width pixels)
_RES_THRESHOLD = {
    "4k":    3840,
    "1080p": 1920,
    "720p":  1280,
}


class PexelsProvider(StockProvider):
    """
    Pexels free stock library — videos and images.

    Instantiated by ProviderRegistry with the resolved API key.
    Pass api_key="" to run without a key — Pexels returns 401; we return [].
    """

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        if not api_key:
            log.warning(
                "pexels_no_api_key",
                msg="Pexels requests will fail (401). Set VIDEO_PEXELS_API_KEY in .env.",
            )

    # ── StockProvider interface ───────────────────────────────────────────────

    async def search_videos(
        self,
        query: str,
        count: int = 5,
        min_duration_sec: int = 5,
        max_duration_sec: int = 30,
    ) -> list[StockClip]:
        """
        Search Pexels for video clips.

        Fetches up to min(count * 2, 30) results then filters by duration,
        ensuring we return enough clips even if some don't meet the duration
        constraint.

        Returns up to `count` StockClip objects, best quality first.
        Returns [] on API error (logged as warning — renderer handles empty list).
        """
        if not self._api_key:
            return []

        fetch_count = min(count * 3, 30)  # over-fetch then filter

        params = {
            "query": query,
            "per_page": fetch_count,
            "min_duration": min_duration_sec,
            "max_duration": max_duration_sec,
        }

        try:
            data = await self._get(_VIDEOS_BASE, params)
        except Exception as exc:  # noqa: BLE001
            log.warning("pexels_video_search_failed", query=query, error=str(exc))
            return []

        clips: list[StockClip] = []
        for video in data.get("videos", []):
            clip = self._parse_video(video)
            if clip:
                clips.append(clip)
            if len(clips) >= count:
                break

        log.debug(
            "pexels_video_search",
            query=query,
            found=len(data.get("videos", [])),
            returned=len(clips),
        )
        return clips

    async def search_images(
        self,
        query: str,
        count: int = 3,
        orientation: str = "landscape",
    ) -> list[StockImage]:
        """
        Search Pexels for photos.

        orientation: "landscape" | "portrait" | "square"
        Returns up to `count` StockImage objects.
        Returns [] on API error.
        """
        if not self._api_key:
            return []

        params = {
            "query": query,
            "per_page": count,
            "orientation": orientation,
        }

        try:
            data = await self._get(_IMAGES_BASE, params)
        except Exception as exc:  # noqa: BLE001
            log.warning("pexels_image_search_failed", query=query, error=str(exc))
            return []

        images: list[StockImage] = []
        for photo in data.get("photos", []):
            img = self._parse_image(photo, orientation)
            if img:
                images.append(img)

        log.debug(
            "pexels_image_search",
            query=query,
            found=len(data.get("photos", [])),
            returned=len(images),
        )
        return images

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get(self, url: str, params: dict) -> dict:
        """Make an authenticated GET request and return parsed JSON."""
        headers = {"Authorization": self._api_key}
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _parse_video(video: dict) -> StockClip | None:
        """
        Extract the best-quality video file from a Pexels video object.

        Pexels returns multiple "video_files" per clip at different resolutions.
        We pick the highest resolution file that fits within typical 1080p.
        Falls back to the first file if quality tags are missing.
        """
        files: list[dict] = video.get("video_files", [])
        if not files:
            return None

        # Sort by width descending, cap at 1920 for bandwidth sanity
        usable = [
            f for f in files
            if f.get("width") and f.get("link")
            and f.get("width", 0) <= 3840
        ]
        if not usable:
            usable = files  # Use whatever is available

        # Prefer quality tag ordering, then width
        def _sort_key(f: dict) -> tuple[int, int]:
            q = f.get("quality", "")
            order_map = {"fhd": 0, "hd": 1, "sd": 2}
            return (order_map.get(q, 3), -(f.get("width") or 0))

        usable.sort(key=_sort_key)
        best = usable[0]

        user = video.get("user", {})
        attribution = (
            f"{user.get('name', 'Pexels')} via pexels.com"
            if user.get("name") else "Pexels"
        )

        return StockClip(
            url=best["link"],
            duration_sec=float(video.get("duration", 0)),
            width=best.get("width", 1280),
            height=best.get("height", 720),
            attribution=attribution,
        )

    @staticmethod
    def _parse_image(photo: dict, orientation: str) -> StockImage | None:
        """Extract the best image URL from a Pexels photo object."""
        src: dict = photo.get("src", {})
        if not src:
            return None

        # Pick the URL matching orientation; fall back to "original"
        _ORIENT_KEY = {
            "landscape": "landscape",
            "portrait":  "portrait",
            "square":    "square",
        }
        url = src.get(_ORIENT_KEY.get(orientation, "landscape")) or src.get("original", "")
        if not url:
            return None

        photographer = photo.get("photographer", "Pexels")
        attribution = f"{photographer} via pexels.com"

        return StockImage(
            url=url,
            width=photo.get("width", 1280),
            height=photo.get("height", 720),
            attribution=attribution,
        )
