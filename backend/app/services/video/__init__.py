"""
Video creation service package.

Top-level exports:
  ProviderBundle  — resolved set of providers for one render job
  RenderResult    — raw output from a renderer (before FFmpeg gate)

Import paths:
  from app.services.video import ProviderBundle, RenderResult
  from app.services.video.registry import ProviderRegistry
  from app.services.video.base_renderer import BaseVideoRenderer
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.video.providers.base import (
        AvatarProvider,
        FullPlatformProvider,
        ImageGenProvider,
        StockProvider,
        TTSProvider,
        VideoRenderProvider,
    )


@dataclass
class ProviderBundle:
    """
    Resolved concrete providers for a single render job.

    Created by ProviderRegistry.get_providers(tenant) and injected into
    every renderer.  Renderers access capabilities only through this bundle —
    never by importing vendor SDKs directly.

    Optional providers (avatar, image_gen, platform) are None when not
    configured for the tenant's quality tier.
    """
    tts: "TTSProvider"
    stock: "StockProvider"
    render: "VideoRenderProvider"
    avatar: "AvatarProvider | None" = None
    image_gen: "ImageGenProvider | None" = None
    platform: "FullPlatformProvider | None" = None

    # Snapshot of the tenant video config used to build this bundle
    # — stored on the VideoJob.provider_used column for audit
    provider_names: dict = field(default_factory=dict)


@dataclass
class RenderResult:
    """
    Raw output from a renderer's render() call.

    raw_mp4_path  — path to the assembled video BEFORE the FFmpeg quality gate.
                    The Celery task pipes this through ffmpeg_gate.encode() and
                    then discards the raw file.
    duration_seconds — approximate duration in seconds (from TTS / MoviePy).
    metadata      — optional extra info (scene count, images used, etc.)
    """
    raw_mp4_path: Path
    duration_seconds: float
    metadata: dict = field(default_factory=dict)
