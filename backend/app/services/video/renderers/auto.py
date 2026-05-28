"""
AutoRenderer — AI-driven video type selector.

The AutoRenderer is a meta-renderer: it does not produce frames itself.
Instead it:

  1. Calls llm_planner.auto_select_type() to pick the best concrete video
     type for this script + available assets (e.g. "explainer", "kinetic", …).
  2. Looks up the chosen renderer class via ProviderRegistry.get_renderer_class().
  3. Instantiates the chosen renderer with the same (job, providers, tmp_dir,
     session_factory) arguments and runs its render().
  4. Returns the RenderResult unchanged, but appends chosen_type to metadata.

Eligible types (never picks "auto" itself, or "avatar"/"screencast" which
require specialised external assets):
  stockfootage, kinetic, slideshow, explainer, whiteboard, motion,
  illustrative, presentation, conversational

Template settings consumed:
  All settings are passed through to the delegated renderer.
  AutoRenderer itself reads no type-specific settings.
"""
from __future__ import annotations

import structlog

from app.services.video import RenderResult
from app.services.video.base_renderer import BaseVideoRenderer

log = structlog.get_logger(__name__)


class AutoRenderer(BaseVideoRenderer):
    """
    Meta-renderer: asks the LLM to choose the best video type, then delegates.

    Only overrides `render()` — all base-class helpers are available to the
    delegated renderer through its own instance.
    """

    async def render(self) -> RenderResult:
        """
        Entry point called by the Celery render_video task.

        Steps:
          1. Resolve available assets from settings.
          2. Ask LLM for best video_type.
          3. Persist chosen_type to job.settings for audit visibility.
          4. Instantiate and run the chosen renderer.
          5. Append chosen_type to result metadata.
        """
        from app.services.video.registry import ProviderRegistry
        from app.services.video.llm_planner import auto_select_type

        await self._update_progress(5, "Auto: analysing script…")

        # Resolve available assets for the type-selection prompt
        resolved = self.assets  # self.assets set by BaseVideoRenderer.__init__
        available_assets: dict = {
            "character_urls": resolved.get("character_urls", []),
            "image_urls":     resolved.get("image_urls", []),
            "music_url":      resolved.get("music_url"),
        }

        script = self.job.script or self.job.title

        # ── LLM type selection ────────────────────────────────────────────────
        chosen_type = await auto_select_type(
            script=script,
            settings_dict=self.settings,
            available_assets=available_assets,
            session_factory=self._session_factory,
            tenant_id=self.job.tenant_id,
        )

        log.info(
            "auto_renderer_type_chosen",
            job_id=str(self.job.id),
            chosen_type=chosen_type,
        )

        await self._update_progress(10, f"Auto: selected '{chosen_type}' — rendering…")

        # ── Persist chosen type in settings JSONB for audit ───────────────────
        try:
            async with self._session_factory() as session:
                from sqlalchemy import select as sa_select
                from app.models.video_job import VideoJob

                stmt = sa_select(VideoJob).where(VideoJob.id == self.job.id)
                result = await session.execute(stmt)
                job_row = result.scalar_one_or_none()
                if job_row is not None:
                    updated_settings = dict(job_row.settings or {})
                    updated_settings["_auto_chosen_type"] = chosen_type
                    job_row.settings = updated_settings
                    await session.commit()
        except Exception as exc:  # noqa: BLE001
            # Non-fatal: audit write failure must not abort the render
            log.warning("auto_renderer_settings_write_failed", error=str(exc))

        # ── Delegate to chosen renderer ───────────────────────────────────────
        RendererClass = ProviderRegistry.get_renderer_class(chosen_type)

        # Temporarily patch video_type on the in-memory job object so the
        # delegated renderer uses the correct LLM schema and log labels.
        # The DB record retains "auto" as the original requested type.
        original_type = self.job.video_type
        self.job.video_type = chosen_type  # type: ignore[assignment]

        try:
            delegated = RendererClass(
                job=self.job,
                providers=self.providers,
                tmp_dir=self.tmp_dir,
                session_factory=self._session_factory,
            )
            result: RenderResult = await delegated.render()
        finally:
            # Restore so callers can still inspect the original type
            self.job.video_type = original_type  # type: ignore[assignment]

        # ── Enrich result metadata ────────────────────────────────────────────
        enriched_metadata = dict(result.asset_metadata or {})
        enriched_metadata["auto_chosen_type"]    = chosen_type
        enriched_metadata["original_video_type"] = "auto"

        return RenderResult(
            raw_mp4_path=result.raw_mp4_path,
            duration_seconds=result.duration_seconds,
            metadata=enriched_metadata,
        )
