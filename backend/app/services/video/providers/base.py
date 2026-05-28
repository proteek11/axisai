"""
Abstract provider interfaces for the video creation pipeline.

Six capability groups:
  TTSProvider          — text-to-speech synthesis
  AvatarProvider       — lip-synced talking-head video
  ImageGenProvider     — AI image generation
  StockProvider        — stock video / image search
  VideoRenderProvider  — video assembly (scene list → MP4)
  FullPlatformProvider — complete script-to-MP4 delegation (Synthesia, Pictory, etc.)

Design rule: renderers NEVER import vendor SDKs directly.
They call these abstract interfaces.  The concrete implementation is
resolved at runtime from the tenant's config by ProviderRegistry.

Adding a new vendor = add one new class implementing the right interface.
No renderer code changes needed.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.video_job import VideoJob


# ── Shared data classes ───────────────────────────────────────────────────────

@dataclass
class VoiceInfo:
    voice_id: str
    name: str
    language: str
    gender: str | None = None
    preview_url: str | None = None


@dataclass
class AvatarInfo:
    avatar_id: str
    name: str
    thumbnail_url: str | None = None
    gender: str | None = None


@dataclass
class StockClip:
    url: str            # Direct download URL for the video clip
    duration_sec: float
    width: int
    height: int
    attribution: str | None = None


@dataclass
class StockImage:
    url: str            # Direct download URL for the image
    width: int
    height: int
    attribution: str | None = None


@dataclass
class PlatformStatus:
    status: str         # "queued" | "processing" | "done" | "failed"
    output_url: str | None = None
    error: str | None = None


# ── Provider interfaces ───────────────────────────────────────────────────────

class TTSProvider(ABC):
    """
    Text-to-speech synthesis.

    Implementations: EdgeTTSProvider, OpenAITTSProvider,
                     ElevenLabsProvider, AzureTTSProvider, GTTSProvider
    """

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        voice: str,
        language: str,
        output_path: Path,
    ) -> float:
        """
        Synthesize text to an audio file at output_path.

        Returns audio duration in seconds.
        output_path is created (or overwritten) by the implementation.
        The file format must be WAV or MP3 (MoviePy-compatible).
        """

    @abstractmethod
    async def list_voices(self, language: str) -> list[VoiceInfo]:
        """Return available voices for the given language code (e.g. 'en', 'hi')."""

    async def clone_voice(self, audio_sample: Path, name: str) -> str:
        """
        Clone a voice from a sample audio file and return a voice_id.
        Only supported by ElevenLabs (Tier 2+). Others raise NotImplementedError.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support voice cloning."
        )


class AvatarProvider(ABC):
    """
    Talking-head / lip-synced avatar video generation.

    Implementations: HeyGenProvider, DIDProvider, SynthesiaProvider,
                     SadTalkerProvider (local GPU)
    """

    @abstractmethod
    async def create_video(
        self,
        script: str,
        avatar_id: str,
        voice_id: str,
        language: str,
        output_path: Path,
    ) -> float:
        """
        Generate a lip-synced avatar video from script text.

        Returns video duration in seconds.
        output_path is written by the implementation (MP4 format).
        """

    @abstractmethod
    async def list_avatars(self) -> list[AvatarInfo]:
        """Return available avatars for this provider / account."""


class ImageGenProvider(ABC):
    """
    AI image generation from text prompts.

    Implementations: SDXLLocalProvider, DallE3Provider,
                     FluxProvider, MidjourneyProvider
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        style: str,
        width: int,
        height: int,
        output_path: Path,
    ) -> Path:
        """
        Generate an image from prompt and write it to output_path (PNG).
        Returns the output_path.
        """

    async def generate_batch(
        self,
        prompts: list[str],
        style: str,
        width: int,
        height: int,
        output_dir: Path,
    ) -> list[Path]:
        """
        Generate multiple images concurrently.
        Default implementation calls generate() sequentially.
        Override for providers that support native batch APIs.
        """
        results = []
        for i, prompt in enumerate(prompts):
            out = output_dir / f"img_{i:03d}.png"
            results.append(await self.generate(prompt, style, width, height, out))
        return results


class StockProvider(ABC):
    """
    Stock video clip and image search.

    Implementations: PexelsProvider (free), PixabayProvider (free),
                     ShutterstockProvider (paid), GettyProvider (paid)
    """

    @abstractmethod
    async def search_videos(
        self,
        query: str,
        count: int = 5,
        min_duration_sec: int = 5,
        max_duration_sec: int = 30,
    ) -> list[StockClip]:
        """
        Search for stock video clips matching query.
        Returns up to `count` clips sorted by relevance.
        """

    @abstractmethod
    async def search_images(
        self,
        query: str,
        count: int = 3,
        orientation: str = "landscape",
    ) -> list[StockImage]:
        """
        Search for stock images matching query.
        orientation: "landscape" | "portrait" | "square"
        """


class VideoRenderProvider(ABC):
    """
    Video assembly: combines scenes (images/clips + audio) into an MP4.

    Implementations: MoviePyRenderer (default, local),
                     ShotstackProvider, CreatomateProvider
    """

    @abstractmethod
    async def render_scenes(
        self,
        scenes: list[dict],
        settings: dict,
        output_path: Path,
    ) -> float:
        """
        Assemble a list of scene dicts into a video at output_path.

        Each scene dict structure is renderer-dependent (set by the caller).
        Returns video duration in seconds.
        output_path is written by the implementation (raw MP4, pre-FFmpeg gate).
        """


class FullPlatformProvider(ABC):
    """
    Complete script-to-MP4 platforms that handle the entire pipeline internally.

    Short-circuits all individual providers — if a tenant has a platform provider
    configured, render_video skips TTS / image gen / stock / render steps entirely
    and delegates the whole job here.

    Implementations: SynthesiaProvider, PictoryProvider, VeedProvider,
                     DescriptProvider, InVideoProvider, HeyGenStudiosProvider
    """

    @abstractmethod
    async def create_video(self, job: "VideoJob") -> str:
        """
        Submit the entire job to the platform.

        Returns a platform-specific job ID that can be passed to get_status().
        """

    @abstractmethod
    async def get_status(self, platform_job_id: str) -> PlatformStatus:
        """
        Poll the platform for job status.

        When status == "done", PlatformStatus.output_url contains the MP4 URL.
        The Celery task downloads this URL to a local temp file before the
        FFmpeg quality gate runs.
        """
