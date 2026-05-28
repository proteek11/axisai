#!/usr/bin/env python3
"""
test_multilingual_vimeo.py — Test multilingual Vimeo transcript pipeline.

Tests four scenarios:

  Scenario A — Multi-track transcript storage
    Submit a Vimeo video that has multiple caption tracks (EN + other languages).
    Verify ALL tracks are stored as separate Transcript rows.

  Scenario B — Single-language video + AI in same language
    Submit a video. Verify outputs are generated in the detected/source language.

  Scenario C — Translate outputs to a different language
    Submit an English video but set output_language=fr.
    Verify all AI outputs (summary, flashcards, etc.) come back in French.

  Scenario D — Whisper fallback language detection
    Submit a video with NO captions (Whisper will be used).
    Verify the auto-detected audio language is stored on the content item.

Usage:
    # Run all scenarios:
    python scripts/test_multilingual_vimeo.py --key dev-master-key-change-in-production

    # Use a specific Vimeo video (with token for private):
    python scripts/test_multilingual_vimeo.py --key dev-master-key-change-in-production \\
        --url "https://vimeo.com/YOUR_VIDEO_ID" --vimeo-token YOUR_TOKEN

    # Only run scenario C (translate to French):
    python scripts/test_multilingual_vimeo.py --key dev-master-key-change-in-production \\
        --url "https://vimeo.com/76979871" --scenario c --output-lang fr

    # Full verbose output:
    python scripts/test_multilingual_vimeo.py --key dev-master-key-change-in-production --verbose

    # Re-check transcripts for an already-processed content item:
    python scripts/test_multilingual_vimeo.py --key dev-master-key-change-in-production \\
        --content-item-id <UUID> --scenario a
"""
import argparse
import json
import sys
import time

import httpx

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_API_BASE    = "http://localhost:8000"
DEFAULT_API_KEY     = "dev-master-key-change-in-production"

# Public Vimeo video — well-known, has English captions
# Replace with a video that has multi-language captions to test Scenario A
DEFAULT_VIMEO_URL   = "https://vimeo.com/76979871"

POLL_INTERVAL   = 5    # seconds (video is slower than PDF — transcription)
MAX_WAIT        = 600  # 10 minutes (Whisper can be slow)
BASE_CMID       = 7200  # unique cmid range for these tests


# ── Helpers ───────────────────────────────────────────────────────────────────

def hdr(title: str) -> None:
    print(f"\n{'━' * 64}")
    print(f"  {title}")
    print(f"{'━' * 64}")


def ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def info(msg: str) -> None:
    print(f"  ·  {msg}")


def err(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"  ⚠  {msg}")


def preview(value, max_len: int = 120) -> str:
    s = str(value)
    return s[:max_len] + "…" if len(s) > max_len else s


# ── API helpers ───────────────────────────────────────────────────────────────

def submit_video(
    client: httpx.Client,
    *,
    video_url: str,
    cmid: int,
    content_type: str = "vimeo",
    language: str = "",
    output_language: str = "",
    tasks: list[str],
    vimeo_token: str | None = None,
    label: str,
) -> tuple[str, str]:
    """POST /ingest. Returns (content_item_id, job_id)."""
    metadata: dict = {}
    if vimeo_token:
        metadata["vimeo_token"] = vimeo_token

    payload = {
        "source_url": video_url,
        "content_type": content_type,
        "moodle_course_id": 101,
        "moodle_cmid": cmid,
        "title": f"Multilingual Video Test — {label}",
        "options": {
            "tasks": tasks,
            "language": language,
            "output_language": output_language,
        },
        "metadata": metadata,
    }

    info(f"Submitting: language={language!r}  output_language={output_language!r}")
    info(f"Tasks: {tasks}")
    if vimeo_token:
        info(f"Vimeo token: {vimeo_token[:10]}… (truncated)")

    r = client.post("/api/v1/ingest", json=payload)
    if r.status_code not in (200, 202):
        err(f"Ingest failed: {r.status_code} — {r.text[:400]}")
        sys.exit(1)

    data = r.json()
    cid  = data["content_item_id"]
    jid  = data.get("job_id", "")
    st   = data.get("status", "?")

    ok(f"content_item_id : {cid}")
    ok(f"job_id          : {jid}")
    ok(f"initial status  : {st}")
    return cid, jid


def wait_for_job(client: httpx.Client, job_id: str) -> None:
    start     = time.time()
    last_pct  = -1

    while True:
        elapsed = time.time() - start
        if elapsed > MAX_WAIT:
            err(f"Timed out after {MAX_WAIT}s")
            sys.exit(1)

        r = client.get(f"/api/v1/jobs/{job_id}")
        r.raise_for_status()
        d = r.json()

        pct = d.get("progress", 0)
        msg = d.get("progress_message", "")
        st  = d.get("status", "unknown")

        if pct != last_pct:
            print(f"  [{elapsed:5.0f}s] {pct:3d}%  {msg}")
            last_pct = pct

        if st == "completed":
            ok(f"Completed in {elapsed:.1f}s")
            return
        if st == "failed":
            err(f"Job failed: {d.get('error_message')}")
            print(d.get("error_traceback", "")[-2000:])
            sys.exit(1)

        time.sleep(POLL_INTERVAL)


def get_transcript(
    client: httpx.Client,
    cid: str,
    language: str = "en",
) -> dict | None:
    r = client.get(
        f"/api/v1/content/{cid}/transcript",
        params={"language": language},
    )
    if r.status_code == 200:
        return r.json()
    if r.status_code == 404:
        detail = r.json().get("detail", "not found")
        warn(f"No transcript for language='{language}': {detail}")
        return None
    err(f"Transcript fetch error: {r.status_code} — {r.text[:200]}")
    return None


def get_output(
    client: httpx.Client,
    cid: str,
    output_type: str,
    language: str = "en",
) -> dict | None:
    r = client.get(
        f"/api/v1/content/{cid}/{output_type}",
        params={"language": language},
    )
    if r.status_code == 200:
        return r.json()
    return None


def list_outputs(client: httpx.Client, cid: str) -> list[dict]:
    r = client.get(f"/api/v1/content/{cid}/outputs")
    return r.json() if r.status_code == 200 else []


def get_content_detail(client: httpx.Client, cid: str) -> dict:
    r = client.get(f"/api/v1/content/{cid}")
    return r.json() if r.status_code == 200 else {}


# ── Scenarios ─────────────────────────────────────────────────────────────────

def run_scenario_a(
    client: httpx.Client,
    video_url: str,
    vimeo_token: str | None,
    verbose: bool,
) -> None:
    """Scenario A — Multi-track transcript storage."""
    hdr("Scenario A: Multi-track transcript storage")
    info("If the video has captions in multiple languages, each should")
    info("be stored as a separate Transcript row in the DB.")
    info("Use a video with multi-language subs for the best test.")

    cid, jid = submit_video(
        client,
        video_url=video_url,
        cmid=BASE_CMID + 1,
        language="",          # auto — let extractor find all tracks
        output_language="",
        tasks=["summary"],    # minimal tasks — focus on transcript storage
        vimeo_token=vimeo_token,
        label="Multi-track",
    )

    hdr("Polling job…")
    wait_for_job(client, jid)

    hdr("Verifying results — Scenario A")

    # Check content item language
    detail = get_content_detail(client, cid)
    lang = detail.get("language", "?")
    ok(f"content_item.language = '{lang}'")

    # Fetch the primary (English) transcript
    transcript_en = get_transcript(client, cid, language="en")
    if transcript_en:
        seg_count = len(transcript_en.get("segments", []))
        word_count = transcript_en.get("word_count", 0)
        source = transcript_en.get("source", "?")
        ok(f"EN transcript: {seg_count} segments, {word_count} words, source={source}")
        if verbose and transcript_en.get("segments"):
            print("\n  First 3 segments:")
            for seg in transcript_en["segments"][:3]:
                print(f"    [{seg.get('start_sec', 0):.1f}s → {seg.get('end_sec', 0):.1f}s] "
                      f"{seg.get('text', '').strip()}")
    else:
        info("No English transcript — video may not have EN captions")
        info("If captions were available in another language, check that language directly")

    # Try to fetch any other language tracks that might exist
    # (common ones: es, fr, de, pt, it, zh, ja, ar)
    other_langs = ["fr", "es", "de", "pt", "it", "zh-Hans", "zh-Hant", "ja", "ar", "nl"]
    found_extra = []
    for lang_code in other_langs:
        r = client.get(
            f"/api/v1/content/{cid}/transcript",
            params={"language": lang_code},
        )
        if r.status_code == 200:
            d = r.json()
            found_extra.append(lang_code)
            ok(f"Found transcript in '{lang_code}': {len(d.get('segments', []))} segments")

    if found_extra:
        ok(f"Multi-track PASSED — found {len(found_extra)} extra language(s): {found_extra}")
    else:
        info("No extra language tracks found. Either the video has only one language,")
        info("or it had no API captions (Whisper fallback gives only one track).")
        info("Try a video with official multi-language subtitles for Scenario A.")

    # DB verification hint
    print()
    info(f"DB check: SELECT language, source, word_count, segment_count")
    info(f"  FROM transcripts WHERE content_item_id = '{cid}';")


def run_scenario_b(
    client: httpx.Client,
    video_url: str,
    vimeo_token: str | None,
    verbose: bool,
) -> None:
    """Scenario B — Video with explicit source language, outputs in same language."""
    hdr("Scenario B: English video → AI outputs in English")

    cid, jid = submit_video(
        client,
        video_url=video_url,
        cmid=BASE_CMID + 2,
        language="en",
        output_language="",   # same as source
        tasks=["summary", "flashcards", "glossary"],
        vimeo_token=vimeo_token,
        label="EN-to-EN",
    )

    hdr("Polling job…")
    wait_for_job(client, jid)

    hdr("Verifying results — Scenario B")

    outputs = list_outputs(client, cid)
    ok(f"Generated {len(outputs)} outputs")

    all_correct = True
    for o in outputs:
        lang = o.get("language", "?")
        otype = o.get("output_type", "?")
        correct = lang == "en"
        status_str = "CORRECT" if correct else f"WRONG — expected 'en'"
        ok(f"  {otype:<14}  language={lang}  [{status_str}]")
        if not correct:
            all_correct = False

    if all_correct:
        ok("Language tagging PASSED — all outputs tagged 'en'")

    # Verify transcript saved
    transcript = get_transcript(client, cid, "en")
    if transcript:
        segs = transcript.get("segments", [])
        ok(f"Transcript saved: {len(segs)} segments")
        if verbose and segs:
            print("\n  Sample segments:")
            for seg in segs[:5]:
                print(f"    [{seg.get('start_sec', 0):.1f}s] {seg.get('text', '').strip()}")

    # Quick summary preview
    summary = get_output(client, cid, "summary", language="en")
    if summary:
        text = summary.get("payload", {}).get("summary", "")
        info(f"Summary preview: {preview(text)}")
        if verbose:
            print(json.dumps(summary.get("payload", {}), indent=2, ensure_ascii=False)[:2000])


def run_scenario_c(
    client: httpx.Client,
    video_url: str,
    vimeo_token: str | None,
    output_lang: str,
    verbose: bool,
) -> None:
    """Scenario C — English video, AI outputs in a different language."""
    hdr(f"Scenario C: English video → AI outputs in '{output_lang}'")
    info(f"The transcript stays in the original language.")
    info(f"All AI-generated text (summary, flashcards, etc.) is translated to {output_lang!r}.")

    cid, jid = submit_video(
        client,
        video_url=video_url,
        cmid=BASE_CMID + 3,
        language="en",
        output_language=output_lang,   # ← override
        tasks=["summary", "flashcards", "glossary"],
        vimeo_token=vimeo_token,
        label=f"EN-to-{output_lang.upper()}",
    )

    hdr("Polling job…")
    wait_for_job(client, jid)

    hdr(f"Verifying results — Scenario C (target: {output_lang})")

    outputs = list_outputs(client, cid)
    ok(f"Generated {len(outputs)} outputs")

    all_correct = True
    for o in outputs:
        lang  = o.get("language", "?")
        otype = o.get("output_type", "?")
        correct = lang == output_lang
        status_str = "CORRECT" if correct else f"WRONG — expected '{output_lang}'"
        ok(f"  {otype:<14}  language={lang}  [{status_str}]")
        if not correct:
            all_correct = False

    if all_correct:
        ok(f"Output language tagging PASSED — all outputs tagged '{output_lang}'")
    else:
        err(f"Output language MISMATCH — check that output_language was threaded correctly")

    # Verify the transcript was still saved in the original language (not translated)
    transcript = get_transcript(client, cid, "en")
    if transcript:
        segs = transcript.get("segments", [])
        ok(f"Original EN transcript preserved: {len(segs)} segments")
    else:
        info("No EN transcript (may have used Whisper or no captions found)")

    # Fetch the translated summary
    summary = get_output(client, cid, "summary", language=output_lang)
    if summary:
        payload = summary.get("payload", {})
        text    = payload.get("summary", "")
        ok(f"Summary (language={payload.get('language', '?')}):")
        if verbose:
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])
        else:
            info(f"  First 300 chars: {text[:300]}")

        # Simple French sanity check
        if output_lang == "fr" and text:
            fr_words = ["le ", "la ", "les ", "de ", "du ", "des ", "un ", "une ", "et ", "en ", "pour "]
            found = [w for w in fr_words if w in text.lower()]
            if found:
                ok(f"French vocabulary check PASSED (found: {', '.join(found[:5])})")
            else:
                warn("French vocabulary check inconclusive — output may still be correct, check manually")

    # Fetch flashcards in target language
    flashcards = get_output(client, cid, "flashcards", language=output_lang)
    if flashcards:
        cards = flashcards.get("payload", {}).get("cards", [])
        ok(f"Flashcards: {len(cards)} cards in '{output_lang}'")
        if cards:
            c = cards[0]
            info(f"  First card front: {preview(c.get('front', ''))}")
            info(f"  First card back : {preview(c.get('back', ''))}")


def run_scenario_d(
    client: httpx.Client,
    video_url: str,
    vimeo_token: str | None,
    verbose: bool,
) -> None:
    """Scenario D — Whisper fallback + language auto-detection."""
    hdr("Scenario D: Whisper language detection")
    info("This scenario works best with a video that has NO API captions.")
    info("Whisper will transcribe the audio and detect the language.")
    info("The detected language should be saved on content_item.language.")
    info("Using the same URL as other scenarios — results depend on whether")
    info("API captions are available.")

    cid, jid = submit_video(
        client,
        video_url=video_url,
        cmid=BASE_CMID + 4,
        language="",          # no hint — force auto detection path
        output_language="",
        tasks=["summary"],
        vimeo_token=vimeo_token,
        label="Whisper-detect",
    )

    hdr("Polling job…")
    wait_for_job(client, jid)

    hdr("Verifying results — Scenario D")

    detail = get_content_detail(client, cid)
    lang = detail.get("language", "?")
    ok(f"content_item.language (after pipeline): '{lang}'")

    if lang and lang not in ("?", ""):
        ok("Language detection PASSED — content item has a language tag")
    else:
        warn("content_item.language is empty — Whisper may have used API captions")
        info("If the video had API captions, detected_source_language from Whisper is not used")

    transcript = get_transcript(client, cid, language=lang if lang not in ("?", "") else "en")
    if transcript:
        source = transcript.get("source", "?")
        segs   = transcript.get("segments", [])
        ok(f"Transcript source: '{source}'  ({len(segs)} segments)")
        if source == "whisper_local":
            ok("Whisper fallback confirmed — captions came from audio transcription")
        elif source == "api_captions":
            info("API captions were found — Whisper was NOT used (video has captions)")
        if verbose and segs:
            print("\n  First 3 segments:")
            for seg in segs[:3]:
                print(f"    [{seg.get('start_sec', 0):.1f}s] {seg.get('text', '').strip()}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multilingual Vimeo pipeline test for axis-ai",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--key",          default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--base",         default=DEFAULT_API_BASE, help="API base URL")
    parser.add_argument("--url",          default=DEFAULT_VIMEO_URL, help="Vimeo video URL")
    parser.add_argument("--vimeo-token",  default=None, help="Vimeo personal access token")
    parser.add_argument(
        "--scenario",
        choices=["a", "b", "c", "d", "all"],
        default="b",
        help="Which scenario to run (default: b — quickest meaningful test)",
    )
    parser.add_argument(
        "--output-lang",
        default="fr",
        help="Target output language for scenario C (default: fr)",
    )
    parser.add_argument(
        "--content-item-id",
        help="Skip ingest and re-check outputs for this content item",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print()
    print("=" * 64)
    print("  axis-ai  —  Multilingual Vimeo Pipeline Test")
    print("=" * 64)
    print(f"  API      : {args.base}")
    print(f"  Video    : {args.url}")
    print(f"  Scenario : {args.scenario}")
    print()

    headers = {"Authorization": f"Bearer {args.key}"}

    with httpx.Client(
        base_url=args.base,
        headers=headers,
        timeout=60,
    ) as client:
        r = client.get("/api/v1/health")
        if r.status_code != 200:
            err("API not reachable — is docker compose up?")
            sys.exit(1)
        ok(f"API healthy: {r.json()}")

        sc = args.scenario.lower()
        vt = args.vimeo_token

        if sc in ("a", "all"):
            run_scenario_a(client, args.url, vt, args.verbose)
        if sc in ("b", "all"):
            run_scenario_b(client, args.url, vt, args.verbose)
        if sc in ("c", "all"):
            run_scenario_c(client, args.url, vt, args.output_lang, args.verbose)
        if sc in ("d", "all"):
            run_scenario_d(client, args.url, vt, args.verbose)

    print()
    print("=" * 64)
    print("  All selected scenarios complete.")
    print("=" * 64)
    print()
    print("  DB check — transcripts (all languages stored):")
    print("  psql postgresql://axis:axisdev@localhost:5432/axis_ai -c \\")
    print("    \"SELECT content_item_id, language, source, word_count")
    print("     FROM transcripts ORDER BY created_at DESC LIMIT 10;\"")
    print()
    print("  DB check — AI output languages:")
    print("  psql postgresql://axis:axisdev@localhost:5432/axis_ai -c \\")
    print("    \"SELECT output_type, language, status FROM ai_outputs ORDER BY created_at DESC LIMIT 15;\"")
    print()


if __name__ == "__main__":
    main()
