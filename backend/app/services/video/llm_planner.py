"""
LLM scene planner — breaks a script into structured scene dicts.

All video renderers call this utility instead of calling LiteLLM directly.
Uses the cheapest capable model (VIDEO_LLM_PLANNER_MODEL, default: gpt-4o-mini)
because scene planning is a structured JSON task that doesn't need a large model.

Returns a list of scene dicts.  The expected schema varies by video type and is
communicated to the LLM via extra_context["scene_schema"].

Note: this module uses the existing AIClient from app.services.ai.client
to ensure all LLM calls are audit-logged and rate-limited consistently.

auto_select_type():
  Used exclusively by AutoRenderer (Step 8).  Asks the LLM to evaluate the
  script + available assets and return the best VIDEO_TYPE slug.
"""
from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING

import structlog

from app.config import settings

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

log = structlog.get_logger(__name__)

# ── Scene schemas ─────────────────────────────────────────────────────────────
# Per-type scene schemas sent to the LLM as a JSON example

_SCENE_SCHEMAS: dict[str, str] = {
    "stockfootage": json.dumps({
        "scenes": [
            {
                "id": 1,
                "title": "Scene title",
                "narration": "Narration text for TTS",
                "search_keywords": ["keyword1", "keyword2"],
                "duration_seconds": 15,
            }
        ]
    }, indent=2),

    "kinetic": json.dumps({
        "phrases": [
            {
                "text": "Short impactful phrase",
                "effect": "fadein",   # fadein | zoomin | slideup | typewriter
                "duration": 3.5,
            }
        ]
    }, indent=2),

    "slideshow": json.dumps({
        "slides": [
            {
                "id": 1,
                "narration": "What to say while showing this image",
                "caption": "Short on-screen text (optional)",
                "ken_burns": "zoom_in",  # zoom_in | zoom_out | pan_left | pan_right
            }
        ]
    }, indent=2),

    "avatar": json.dumps({
        "sections": [
            {
                "id": 1,
                "script": "What the avatar should say in this section",
                "duration_hint": 20,
            }
        ]
    }, indent=2),

    "explainer": json.dumps({
        "scenes": [
            {
                "id": 1,
                "title": "Scene title",
                "body_text": "Supporting text shown on screen",
                "narration": "Narration text",
                "image_prompt": "Detailed DALL-E / SDXL prompt",
                "image_style": "flat illustration",
                "duration_seconds": 15,
            }
        ]
    }, indent=2),

    # Step 7 — ConversationalRenderer: turns between 2-3 characters
    "conversational": json.dumps({
        "turns": [
            {
                "character": "Alex",
                "character_index": 0,
                "position": "left",
                "voice_hint": "female_friendly",
                "text": "What the character says in this turn",
                "duration_seconds": 5,
            },
            {
                "character": "Jamie",
                "character_index": 1,
                "position": "right",
                "voice_hint": "male_calm",
                "text": "The other character's reply",
                "duration_seconds": 4,
            }
        ]
    }, indent=2),
}

# Default schema for types not yet in the map
_DEFAULT_SCHEMA = json.dumps({
    "scenes": [
        {
            "id": 1,
            "title": "Scene title",
            "narration": "Narration text",
            "duration_seconds": 15,
        }
    ]
}, indent=2)

# Video types eligible for auto selection (excludes 'auto' itself and
# types that require special external providers: avatar → HeyGen, screencast → upload)
_AUTO_ELIGIBLE_TYPES: list[str] = [
    "stockfootage", "kinetic", "slideshow", "explainer",
    "whiteboard", "motion", "illustrative", "presentation", "conversational",
]


# ── Public API ────────────────────────────────────────────────────────────────

async def plan_scenes(
    script: str,
    video_type: str,
    settings_dict: dict,
    extra_context: dict,
    session_factory: "async_sessionmaker",
    tenant_id: "uuid.UUID",
) -> list[dict]:
    """
    Call the LLM to break script into structured scenes.

    Returns the list from the top-level array in the JSON response.
    Falls back to a single-scene list if the LLM returns unparseable JSON.
    """
    schema = _SCENE_SCHEMAS.get(video_type, _DEFAULT_SCHEMA)
    duration = settings_dict.get("duration_seconds", 120)
    language = settings_dict.get("language", "en")

    system_prompt = (
        "You are a video production assistant. "
        "Return ONLY valid JSON matching the provided schema — no markdown, no commentary."
    )

    user_prompt = (
        f"Break the following script into scenes for a {video_type} video.\n\n"
        f"Target duration: {duration} seconds\n"
        f"Language: {language}\n"
        f"{_extra_context_block(extra_context)}\n\n"
        f"Required JSON schema:\n{schema}\n\n"
        f"Script:\n{script}"
    )

    client = await _make_client(session_factory, tenant_id)

    try:
        response = await client.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=settings.video_llm_planner_model,
            task_type="video_scene_plan",
        )
    except Exception as exc:  # noqa: BLE001
        log.error(
            "llm_planner_failed",
            video_type=video_type,
            error=str(exc),
        )
        return _fallback_scenes(script, video_type, duration)

    # AIClient.complete() returns litellm.ModelResponse — extract text correctly
    raw = response.choices[0].message.content or ""
    return _parse_response(raw, video_type, script, duration)


async def auto_select_type(
    script: str,
    settings_dict: dict,
    available_assets: dict,
    session_factory: "async_sessionmaker",
    tenant_id: "uuid.UUID",
) -> str:
    """
    Ask the LLM to choose the best video_type for this script + assets.

    Returns a string from _AUTO_ELIGIBLE_TYPES.
    Falls back to "stockfootage" if the LLM returns an unrecognised value or fails.

    Called by AutoRenderer before delegating to the chosen renderer class.
    """
    asset_summary_parts: list[str] = []
    if available_assets.get("character_urls"):
        n = len(available_assets["character_urls"])
        asset_summary_parts.append(f"{n} character image(s) available")
    if available_assets.get("image_urls"):
        n = len(available_assets["image_urls"])
        asset_summary_parts.append(f"{n} background/slide image(s) available")
    if available_assets.get("music_url"):
        asset_summary_parts.append("background music available")
    asset_summary = ", ".join(asset_summary_parts) or "no pre-uploaded assets"

    duration = settings_dict.get("duration_seconds", 120)

    eligible_str = ", ".join(_AUTO_ELIGIBLE_TYPES)
    system_prompt = (
        "You are a video type selector. "
        "Return ONLY a single JSON object with one key 'video_type' "
        "whose value is one of the eligible types. No other text."
    )
    user_prompt = (
        f"Choose the single best video type for the following script.\n\n"
        f"Eligible types: {eligible_str}\n"
        f"Target duration: {duration} seconds\n"
        f"Available assets: {asset_summary}\n\n"
        f"Guidelines:\n"
        f"  - conversational → if script has dialogue or 2+ distinct speakers\n"
        f"  - kinetic         → if script is a short motivational / key-message piece\n"
        f"  - explainer       → if script explains a concept or process step-by-step\n"
        f"  - slideshow       → if image_urls are available and content suits gallery style\n"
        f"  - illustrative    → if character images available and story/narrative tone\n"
        f"  - presentation    → if script has clear headings / sections\n"
        f"  - whiteboard      → if script is educational, sketching ideas\n"
        f"  - motion          → if script suits bold brand / marketing style\n"
        f"  - stockfootage    → default for documentary, product, or general content\n\n"
        f"Script:\n{script[:1500]}"   # cap at 1500 chars to keep cost low
    )

    client = await _make_client(session_factory, tenant_id)
    fallback = "stockfootage"

    try:
        response = await client.complete(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            model=settings.video_llm_planner_model,
            task_type="video_type_selection",
        )
        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)
        chosen = data.get("video_type", "").strip().lower()
    except Exception as exc:  # noqa: BLE001
        log.warning("auto_select_type_failed", error=str(exc))
        return fallback

    if chosen not in _AUTO_ELIGIBLE_TYPES:
        log.warning(
            "auto_select_type_invalid_choice",
            chosen=chosen,
            fallback=fallback,
        )
        return fallback

    log.info("auto_select_type_chosen", video_type=chosen, tenant_id=str(tenant_id))
    return chosen


# ── Private helpers ───────────────────────────────────────────────────────────

def _parse_response(
    raw: str,
    video_type: str,
    script: str,
    duration: int,
) -> list[dict]:
    """Parse JSON from LLM response; fall back on failure."""
    try:
        data = json.loads(raw.strip())
        # Return whichever top-level list key is present
        for key in ("scenes", "phrases", "slides", "sections", "turns"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # If root is already a list
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError) as exc:
        log.warning("llm_planner_json_parse_failed", error=str(exc), raw=raw[:200])

    return _fallback_scenes(script, video_type, duration)


def _fallback_scenes(script: str, video_type: str, duration: int) -> list[dict]:
    """
    Single-scene fallback when LLM returns bad JSON.

    Returns a correctly-keyed dict for the specific video_type so renderers
    can access their expected fields without producing empty/crashed output.
    """
    log.warning("llm_planner_using_fallback_single_scene", video_type=video_type)

    if video_type == "kinetic":
        # KineticRenderer reads: text, effect, duration
        return [{"text": script, "effect": "fadein", "duration": max(5, duration // 10)}]

    if video_type == "avatar":
        # AvatarRenderer reads: script, duration_hint
        return [{"id": 1, "script": script, "duration_hint": duration}]

    if video_type == "slideshow":
        # SlideshowRenderer reads: narration, caption, ken_burns
        return [{"id": 1, "narration": script, "caption": "", "ken_burns": "zoom_in"}]

    if video_type == "conversational":
        # ConversationalRenderer reads: character, character_index, text, duration_seconds
        half = max(5, duration // 2)
        return [
            {
                "character": "Alex",
                "character_index": 0,
                "text": script,
                "duration_seconds": half,
            },
            {
                "character": "Jamie",
                "character_index": 1,
                "text": "That's a great point!",
                "duration_seconds": 3,
            },
        ]

    if video_type == "auto":
        # AutoRenderer delegates to another renderer; if planning fails before
        # delegation we return a stockfootage-compatible fallback so the render
        # does not produce an empty result.
        return [{
            "id": 1,
            "title": "Main",
            "narration": script,
            "search_keywords": [script[:40].strip()],
            "duration_seconds": duration,
        }]

    # stockfootage, explainer, whiteboard, motion, illustrative, presentation, screencast
    # All read: title, narration, search_keywords, duration_seconds (at minimum)
    return [{
        "id": 1,
        "title": "Main",
        "narration": script,
        "search_keywords": [script[:40].strip()],
        "duration_seconds": duration,
    }]


async def _make_client(session_factory: "async_sessionmaker", tenant_id: "uuid.UUID"):
    """Shared AIClient factory for this module."""
    from app.services.ai.client import AIClient
    from app.core.redis import get_redis

    redis = await get_redis()
    return AIClient(
        session_factory=session_factory,
        redis=redis,
        tenant_id=str(tenant_id),
        content_item_id=None,
        job_id=None,
    )


def _extra_context_block(extra: dict) -> str:
    if not extra:
        return ""
    lines = ["Additional context:"]
    for k, v in extra.items():
        lines.append(f"  {k}: {v}")
    return "\n".join(lines)
