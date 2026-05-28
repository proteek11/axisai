"""
Chat input sanitizer — runs on every user message before any LLM call.

Protections:
  1. Control character stripping — removes null bytes, ESC sequences, etc.
  2. Unicode normalization — prevents homoglyph attacks
  3. Whitespace normalization — collapses excessive spacing/newlines
  4. Length enforcement — hard cap after cleaning
  5. Prompt injection detection — pattern-based heuristics on common attack phrases

Design philosophy:
  - The structured JSON output format is the primary injection defence
    (the LLM can't "escape" into instruction-following mode when we're
    only parsing its JSON output field-by-field). This is the secondary layer.
  - Never block aggressively — false positives hurt real students.
    Flag clear injection attempts (score >= INJECTION_THRESHOLD), warn on suspicious.
  - Never log the raw message after sanitization failure — only log the score.
  - Raise SanitizationError for hard blocks; return cleaned string for soft issues.
"""
from __future__ import annotations

import re
import unicodedata

import structlog

log = structlog.get_logger(__name__)

# Hard limits (post-cleaning)
MAX_MESSAGE_LENGTH = 3000        # Tighter than schema 4000 — extra buffer for prompts
MAX_NEWLINES = 20                # Prevent newline-flooding attacks
MIN_MESSAGE_LENGTH = 1

# Injection detection threshold
INJECTION_THRESHOLD = 3          # Score >= this → block
INJECTION_WARN_THRESHOLD = 1     # Score >= this → log warning but allow

# Regex for control characters (keep printable + standard whitespace)
_CONTROL_CHARS_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]"
)

# Normalise multiple consecutive newlines
_EXCESS_NEWLINES_RE = re.compile(r"\n{4,}")

# Patterns that indicate prompt injection attempts.
# Each pattern carries a weight — total score determines action.
# Weights are intentionally conservative to avoid false positives
# (e.g. a student asking "ignore the previous answer" in a genuine
# follow-up should NOT be blocked).
_INJECTION_PATTERNS: list[tuple[re.Pattern, int, str]] = [
    # Classic direct injection openers
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions?", re.I), 2, "ignore_prev"),
    (re.compile(r"disregard\s+(all\s+)?previous\s+instructions?", re.I), 2, "disregard_prev"),
    (re.compile(r"forget\s+(all\s+)?previous\s+instructions?", re.I), 2, "forget_prev"),
    (re.compile(r"you\s+are\s+now\s+a?\s*\w+\s*(bot|ai|assistant|model)", re.I), 2, "persona_override"),
    (re.compile(r"act\s+as\s+(if\s+you\s+(are|were)\s+)?a?\s*(different|new|another|unrestricted)", re.I), 2, "act_as"),

    # System prompt manipulation
    (re.compile(r"\[system\]|\[INST\]|<<SYS>>|<\|system\|>", re.I), 2, "sys_tag"),
    (re.compile(r"your\s+(system\s+)?prompt\s+is\s+now", re.I), 2, "prompt_override"),
    (re.compile(r"new\s+instructions?\s*:", re.I), 1, "new_instructions"),
    (re.compile(r"override\s+(your\s+)?(instructions?|rules?|guidelines?)", re.I), 2, "override"),

    # Jailbreak patterns
    (re.compile(r"DAN\s+mode|do\s+anything\s+now", re.I), 3, "dan_mode"),
    (re.compile(r"jailbreak|jail\s+break", re.I), 2, "jailbreak"),
    (re.compile(r"without\s+(any\s+)?(restrictions?|limits?|filters?|guidelines?)", re.I), 1, "no_restrictions"),

    # Data exfiltration attempts
    (re.compile(r"(print|output|show|reveal|dump|display)\s+(your\s+)?(system\s+prompt|instructions?|context|guidelines?)", re.I), 2, "exfil_prompt"),
    (re.compile(r"what\s+(are\s+)?your\s+(exact\s+)?(instructions?|system\s+prompt|guidelines?)", re.I), 1, "exfil_soft"),

    # Role confusion
    (re.compile(r"you\s+are\s+not\s+an?\s+(ai|assistant|bot|language\s+model)", re.I), 1, "role_denial"),
    (re.compile(r"pretend\s+(you\s+)?(are|have\s+no)\s+(restrictions?|guidelines?|rules?)", re.I), 2, "pretend"),
]


class SanitizationError(ValueError):
    """Raised when a message is hard-blocked by the sanitizer."""
    def __init__(self, reason: str, score: int):
        super().__init__(reason)
        self.reason = reason
        self.score = score


def sanitize_message(raw: str) -> str:
    """
    Clean and validate a user message.

    Args:
        raw: The raw message string from the user

    Returns:
        Cleaned message string, safe to pass to the LLM pipeline

    Raises:
        SanitizationError: If the message contains hard-blocked content
        ValueError: If the message is empty after cleaning
    """
    if not raw or not isinstance(raw, str):
        raise ValueError("Message must be a non-empty string")

    # ── 1. Unicode normalization (NFKC — canonical decomposition + composition) ──
    # Converts homoglyphs (e.g. Cyrillic 'а' → Latin 'a') and ligatures
    cleaned = unicodedata.normalize("NFKC", raw)

    # ── 2. Strip control characters ──────────────────────────────────────────────
    cleaned = _CONTROL_CHARS_RE.sub("", cleaned)

    # ── 3. Normalize whitespace ───────────────────────────────────────────────────
    # Replace null-byte style separators, tabs → space
    cleaned = cleaned.replace("\t", " ").replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of 4+ newlines → double newline
    cleaned = _EXCESS_NEWLINES_RE.sub("\n\n", cleaned)
    # Collapse runs of 3+ spaces → single space (inside lines)
    cleaned = re.sub(r" {3,}", "  ", cleaned)
    cleaned = cleaned.strip()

    # ── 4. Length checks ──────────────────────────────────────────────────────────
    if len(cleaned) < MIN_MESSAGE_LENGTH:
        raise ValueError("Message is empty after sanitization")

    if len(cleaned) > MAX_MESSAGE_LENGTH:
        # Truncate rather than reject — a very long message might just be a student
        # pasting context. Log it so admins can monitor.
        log.warning("chat_message_truncated", original_len=len(raw), cap=MAX_MESSAGE_LENGTH)
        cleaned = cleaned[:MAX_MESSAGE_LENGTH]

    # ── 5. Prompt injection detection ─────────────────────────────────────────────
    score, triggers = _score_injection(cleaned)

    if score >= INJECTION_THRESHOLD:
        log.warning(
            "chat_injection_blocked",
            score=score,
            triggers=triggers,
            # Never log the actual message content
        )
        raise SanitizationError(
            reason="Message contains content that cannot be processed",
            score=score,
        )

    if score >= INJECTION_WARN_THRESHOLD:
        log.info(
            "chat_injection_suspicious",
            score=score,
            triggers=triggers,
        )
        # Allow through — single-pattern matches are too noisy to block

    return cleaned


def _score_injection(text: str) -> tuple[int, list[str]]:
    """
    Score a message for prompt injection likelihood.

    Returns:
        (total_score, list_of_triggered_pattern_names)
    """
    total = 0
    triggered = []
    for pattern, weight, name in _INJECTION_PATTERNS:
        if pattern.search(text):
            total += weight
            triggered.append(name)
    return total, triggered
