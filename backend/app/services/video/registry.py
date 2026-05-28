"""
ProviderRegistry — resolves concrete providers from a tenant's config.

Reads tenant.config["video"] JSONB and instantiates the right provider class
for each capability (TTS, stock, avatar, image_gen, render, platform).

Priority order for each capability:
  1. Per-tenant setting in tenant.config["video"]["providers"]
  2. Global .env default (settings.video_tts_provider, etc.)
  3. Tier 0 fallback (edge_tts, pexels, moviepy)

API key lookup priority:
  1. Per-tenant key in tenant.config["video"]["api_keys"][provider]
  2. Global .env key (settings.video_heygen_key, etc.)

Phase 1 supported providers:
  TTS   : edge_tts
  Stock : pexels
  Avatar: heygen
  Render: moviepy (stub — full implementation in Step 6)
  Other providers raise NotImplementedError until their Step is complete.
"""
from __future__ import annotations

import base64
import os

import structlog
from typing import TYPE_CHECKING

from app.config import settings
from app.services.video import ProviderBundle
from app.services.video.providers.base import (
    AvatarProvider,
    FullPlatformProvider,
    ImageGenProvider,
    StockProvider,
    TTSProvider,
    VideoRenderProvider,
)

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)


class ProviderRegistry:
    """
    Resolves providers and renderer classes for a given tenant.

    Usage (inside Celery task):
        registry = ProviderRegistry(tenant)
        bundle   = registry.get_providers()
        RendererClass = ProviderRegistry.get_renderer_class(job.video_type)
        renderer = RendererClass(job, bundle, tmp_dir, session_factory)
        result   = await renderer.render()
    """

    def __init__(self, tenant: "Tenant") -> None:
        self._tenant = tenant
        self._video_cfg: dict = (tenant.config or {}).get("video", {})

    # ── Public API ────────────────────────────────────────────────────────────

    def get_providers(self) -> ProviderBundle:
        """Build and return the ProviderBundle for this tenant."""
        tts_name    = self._resolve_name("tts",      settings.video_tts_provider)
        stock_name  = self._resolve_name("stock",    "pexels")
        avatar_name = self._resolve_name("avatar",   None)
        render_name = self._resolve_name("render",   "moviepy")
        plat_name   = self._resolve_name("platform", None)
        img_name    = self._resolve_name(
            "image_gen",
            settings.video_image_gen if settings.video_image_gen != "none" else None,
        )

        tts       = self._build_tts(tts_name)
        stock     = self._build_stock(stock_name)
        render    = self._build_render(render_name)
        avatar    = self._build_avatar(avatar_name) if avatar_name else None
        image_gen = self._build_image_gen(img_name) if img_name else None
        platform  = self._build_platform(plat_name) if plat_name else None

        provider_names = {
            "tts":       tts_name,
            "stock":     stock_name,
            "avatar":    avatar_name,
            "image_gen": img_name,
            "render":    render_name,
            "platform":  plat_name,
        }

        log.debug(
            "provider_bundle_resolved",
            tenant_id=str(self._tenant.id),
            providers=provider_names,
        )

        return ProviderBundle(
            tts=tts,
            stock=stock,
            render=render,
            avatar=avatar,
            image_gen=image_gen,
            platform=platform,
            provider_names=provider_names,
        )

    @staticmethod
    def get_renderer_class(video_type: str) -> type["BaseVideoRenderer"]:
        """
        Return the renderer class for the given video_type.
        Lazy imports keep startup time fast and let renderers be added
        incrementally without touching this registry.
        """
        # Phase 1 renderers (Steps 6a-6d)
        _MAP: dict[str, str] = {
            "kinetic":      "app.services.video.renderers.kinetic.KineticRenderer",
            "slideshow":    "app.services.video.renderers.slideshow.SlideshowRenderer",
            "stockfootage": "app.services.video.renderers.stockfootage.StockFootageRenderer",
            "avatar":       "app.services.video.renderers.avatar.AvatarRenderer",
            # Phase 2 renderers (Steps later)
            "explainer":    "app.services.video.renderers.explainer.ExplainerRenderer",
            "whiteboard":   "app.services.video.renderers.whiteboard.WhiteboardRenderer",
            "motion":       "app.services.video.renderers.motion.MotionRenderer",
            "illustrative": "app.services.video.renderers.illustrative.IllustrativeRenderer",
            "presentation": "app.services.video.renderers.presentation.PresentationRenderer",
            "screencast":   "app.services.video.renderers.screencast.ScreencastRenderer",
            # Step 7 — 2-3 character dialogue
            "conversational": "app.services.video.renderers.conversational.ConversationalRenderer",
            # Step 8 — AI picks best type and delegates
            "auto":         "app.services.video.renderers.auto.AutoRenderer",
        }

        if video_type not in _MAP:
            raise ValueError(f"No renderer registered for video_type='{video_type}'")

        module_path, class_name = _MAP[video_type].rsplit(".", 1)
        try:
            import importlib
            mod = importlib.import_module(module_path)
        except ImportError as exc:
            raise NotImplementedError(
                f"Cannot import renderer module '{module_path}' for video_type="
                f"'{video_type}'. Check for missing dependencies or syntax errors. "
                f"Original error: {exc}"
            ) from exc
        try:
            return getattr(mod, class_name)
        except AttributeError as exc:
            raise NotImplementedError(
                f"Module '{module_path}' has no class '{class_name}' "
                f"(video_type='{video_type}'). Original error: {exc}"
            ) from exc

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_name(self, capability: str, default: str | None) -> str | None:
        """Read provider name from tenant config, falling back to default."""
        return self._video_cfg.get("providers", {}).get(capability) or default

    def _get_api_key(self, provider_name: str) -> str | None:
        """
        Fetch API key for a provider.

        Priority:
          1. Per-tenant key in tenant.config["video"]["api_keys"][provider]
             - If key starts with "enc::" it is AES-256 (Fernet) encrypted and
               will be decrypted using settings.video_encryption_key.
          2. Global .env / settings fallback.

        Storing encrypted keys:
          from cryptography.fernet import Fernet
          key = settings.video_encryption_key.encode()  # 32-byte hex → Fernet key
          token = Fernet(base64.urlsafe_b64encode(bytes.fromhex(key))).encrypt(api_key.encode())
          stored_value = "enc::" + token.decode()
        """
        tenant_key = self._video_cfg.get("api_keys", {}).get(provider_name)
        if tenant_key:
            if isinstance(tenant_key, str) and tenant_key.startswith("enc::"):
                return self._decrypt(tenant_key[5:])  # strip "enc::" prefix
            return tenant_key

        # Global .env fallbacks
        _ENV_KEYS: dict[str, str] = {
            "heygen":     settings.video_heygen_key,
            "elevenlabs": settings.video_elevenlabs_key,
            "openai_tts": settings.video_openai_tts_key,
            "pexels":     settings.video_pexels_api_key,
            "d_id":       getattr(settings, "video_d_id_key", ""),
            "pictory":    getattr(settings, "video_pictory_key", ""),
        }
        return _ENV_KEYS.get(provider_name) or None

    @staticmethod
    def _decrypt(token: str) -> str:
        """
        Decrypt a Fernet token using settings.video_encryption_key.

        The encryption key must be a 32-byte hex string (64 hex chars).
        It is converted to URL-safe base64 as required by Fernet.

        Raises:
            ValueError  — if video_encryption_key is not set or wrong length.
            cryptography.fernet.InvalidToken — if decryption fails.
        """
        raw_key = settings.video_encryption_key
        if not raw_key:
            raise ValueError(
                "Cannot decrypt tenant API key: VIDEO_ENCRYPTION_KEY is not set in .env. "
                "Generate one with: openssl rand -hex 32"
            )
        if len(raw_key) != 64:
            raise ValueError(
                f"VIDEO_ENCRYPTION_KEY must be 64 hex chars (32 bytes). "
                f"Got {len(raw_key)} chars."
            )
        try:
            key_bytes   = bytes.fromhex(raw_key)
        except ValueError as exc:
            raise ValueError(
                f"VIDEO_ENCRYPTION_KEY is not valid hex: {exc}"
            ) from exc

        # Fernet requires URL-safe base64-encoded 32-byte key
        fernet_key = base64.urlsafe_b64encode(key_bytes)

        try:
            from cryptography.fernet import Fernet
            return Fernet(fernet_key).decrypt(token.encode()).decode()
        except Exception as exc:
            raise ValueError(
                f"Failed to decrypt tenant API key (wrong encryption key?): {exc}"
            ) from exc

    # ── Provider builders ─────────────────────────────────────────────────────

    def _build_tts(self, name: str) -> TTSProvider:
        if name == "edge_tts":
            from app.services.video.providers.tts.edge_tts import EdgeTTSProvider
            return EdgeTTSProvider()
        if name == "openai":
            api_key = self._get_api_key("openai_tts") or ""
            if not api_key:
                raise ValueError(
                    "OpenAI TTS requires an API key. "
                    "Set VIDEO_OPENAI_TTS_KEY in .env or "
                    "tenant.config.video.api_keys.openai_tts"
                )
            model         = self._video_cfg.get("openai_tts_model", "tts-1")
            default_voice = self._video_cfg.get("openai_tts_voice", "alloy")
            from app.services.video.providers.tts.openai_tts import OpenAITTSProvider
            return OpenAITTSProvider(
                api_key=api_key,
                model=model,
                default_voice=default_voice,
            )
        if name == "elevenlabs":
            api_key = self._get_api_key("elevenlabs") or ""
            if not api_key:
                raise ValueError(
                    "ElevenLabs requires an API key. "
                    "Set VIDEO_ELEVENLABS_KEY in .env or "
                    "tenant.config.video.api_keys.elevenlabs"
                )
            default_voice = self._video_cfg.get("elevenlabs_default_voice", "")
            model         = self._video_cfg.get("elevenlabs_model", "eleven_multilingual_v2")
            from app.services.video.providers.tts.elevenlabs import ElevenLabsProvider
            return ElevenLabsProvider(
                api_key=api_key,
                default_voice_id=default_voice or None,
                model=model,
            )
        raise ValueError(f"Unknown TTS provider: '{name}'")

    def _build_stock(self, name: str) -> StockProvider:
        if name == "pexels":
            api_key = self._get_api_key("pexels")
            from app.services.video.providers.stock.pexels import PexelsProvider
            return PexelsProvider(api_key=api_key or "")
        raise ValueError(f"Unknown stock provider: '{name}'")

    def _build_avatar(self, name: str) -> AvatarProvider:
        if name == "heygen":
            api_key = self._get_api_key("heygen")
            if not api_key:
                raise ValueError(
                    "HeyGen API key not configured. "
                    "Set VIDEO_HEYGEN_KEY in .env or in tenant.config.video.api_keys.heygen"
                )
            avatar_id = self._video_cfg.get("heygen_avatar_id", "")
            voice_id  = self._video_cfg.get("heygen_voice_id", "")
            from app.services.video.providers.avatar.heygen import HeyGenProvider
            return HeyGenProvider(
                api_key=api_key,
                default_avatar_id=avatar_id,
                default_voice_id=voice_id,
            )
        if name == "d_id":
            api_key = self._get_api_key("d_id") or ""
            if not api_key:
                raise ValueError(
                    "D-ID requires an API key. "
                    "Set VIDEO_D_ID_KEY in .env or "
                    "tenant.config.video.api_keys.d_id"
                )
            presenter_id = self._video_cfg.get("d_id_presenter_id", "")
            driver_id    = self._video_cfg.get("d_id_driver_id", "")
            stitch       = bool(self._video_cfg.get("d_id_stitch", True))
            fluent       = bool(self._video_cfg.get("d_id_fluent", False))
            pad_audio    = float(self._video_cfg.get("d_id_pad_audio", 0.0))
            crop_type    = self._video_cfg.get("d_id_crop_type", "wide")
            from app.services.video.providers.avatar.d_id import DIDProvider
            return DIDProvider(
                api_key=api_key,
                default_presenter_id=presenter_id,
                driver_id=driver_id,
                stitch=stitch,
                fluent=fluent,
                pad_audio=pad_audio,
                crop_type=crop_type,
            )
        if name == "sadtalker":
            base_url    = self._video_cfg.get("sadtalker_url", "") or ""
            preprocess  = self._video_cfg.get("sadtalker_preprocess", "crop")
            still       = bool(self._video_cfg.get("sadtalker_still", False))
            enhancer    = bool(self._video_cfg.get("sadtalker_enhancer", True))
            batch_size  = int(self._video_cfg.get("sadtalker_batch_size", 1))
            portrait    = self._video_cfg.get("sadtalker_default_portrait", "")
            from app.services.video.providers.avatar.sadtalker import SadTalkerProvider
            return SadTalkerProvider(
                base_url=base_url,
                preprocess=preprocess,
                still_mode=still,
                use_enhancer=enhancer,
                batch_size=batch_size,
                default_portrait=portrait,
            )
        raise ValueError(f"Unknown avatar provider: '{name}'")

    def _build_image_gen(self, name: str) -> "ImageGenProvider":
        if name == "dalle3":
            api_key = self._get_api_key("openai_tts") or ""
            if not api_key:
                raise ValueError(
                    "DALL-E 3 requires an OpenAI API key. "
                    "Set VIDEO_OPENAI_TTS_KEY in .env or "
                    "tenant.config.video.api_keys.openai_tts"
                )
            quality = self._video_cfg.get("dalle3_quality", "standard")
            from app.services.video.providers.image_gen.dalle3 import DallE3Provider
            return DallE3Provider(api_key=api_key, quality=quality)

        if name == "sdxl_local":
            api_url = self._video_cfg.get("sdxl_local_url", "") or settings.video_sdxl_local_url
            from app.services.video.providers.image_gen.sdxl_local import SDXLLocalProvider
            return SDXLLocalProvider(api_url=api_url)

        raise ValueError(f"Unknown image_gen provider: '{name}'")

    def _build_render(self, name: str) -> VideoRenderProvider:
        if name == "moviepy":
            from app.services.video.providers.render.moviepy_renderer import MoviePyRenderer
            return MoviePyRenderer()
        raise ValueError(f"Unknown render provider: '{name}'")

    def _build_platform(self, name: str) -> FullPlatformProvider:
        if name == "pictory":
            api_key = self._get_api_key("pictory") or ""
            if not api_key:
                raise ValueError(
                    "Pictory requires an API key. "
                    "Set VIDEO_PICTORY_KEY in .env or "
                    "tenant.config.video.api_keys.pictory"
                )
            user_id          = self._video_cfg.get("pictory_user_id", "")
            if not user_id:
                raise ValueError(
                    "Pictory requires pictory_user_id. "
                    "Set tenant.config.video.pictory_user_id"
                )
            brand_logo       = self._video_cfg.get("pictory_brand_logo_url", "")
            lang             = self._video_cfg.get("pictory_voiceover_lang", "en")
            music_vol        = float(self._video_cfg.get("pictory_music_volume", 0.3))
            highlight_colour = self._video_cfg.get("pictory_highlight_colour", "#0072ff")
            auto_highlight   = bool(self._video_cfg.get("pictory_auto_highlight", True))
            webhook_url      = self._video_cfg.get("pictory_webhook_url", "")
            from app.services.video.providers.platform.pictory import PictoryProvider
            return PictoryProvider(
                api_key=api_key,
                user_id=user_id,
                brand_logo_url=brand_logo,
                voiceover_lang=lang,
                music_volume=music_vol,
                highlight_colour=highlight_colour,
                auto_highlight=auto_highlight,
                webhook_url=webhook_url,
            )
        raise NotImplementedError(
            f"Full-platform provider '{name}' is not yet wired. "
            f"Supported: pictory"
        )
