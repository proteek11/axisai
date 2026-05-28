"""
MoviePyRenderer — VideoRenderProvider backed by MoviePy.

This is a stub for Phase 1.  Individual renderers (KineticRenderer,
SlideshowRenderer, StockFootageRenderer, AvatarRenderer) compose their own
MoviePy clips and return a RenderResult directly; they do NOT call this
provider.

MoviePyRenderer is used only by the ProviderRegistry as the default
render provider when no platform provider (e.g. HeyGen) is configured.
Concrete functionality is wired in Step 6 (Phase 1 renderers).

Registered in registry._build_render("moviepy").
"""
from __future__ import annotations

from pathlib import Path

from app.services.video.providers.base import VideoRenderProvider


class MoviePyRenderer(VideoRenderProvider):
    """
    Thin wrapper around MoviePy for low-level scene assembly.

    Phase 1 renderers (kinetic, slideshow, stockfootage, avatar) import
    MoviePy directly inside their own render() methods for full control.
    This class exists to satisfy the ProviderRegistry contract and will be
    fleshed out in Step 6 if a shared scene-assembly pipeline is desired.
    """

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or {}

    async def render_scenes(
        self,
        scenes: list[dict],
        settings: dict,
        output_path: Path,
    ) -> float:
        """
        Assemble a list of scene dicts into a single MP4 using MoviePy.

        Not yet implemented — Phase 1 renderers handle their own assembly.
        This will be implemented in Step 6.

        Returns video duration in seconds.
        """
        raise NotImplementedError(
            "MoviePyRenderer.render_scenes() is not yet implemented. "
            "Phase 1 renderers (kinetic, slideshow, stockfootage, avatar) "
            "perform their own MoviePy assembly internally."
        )
