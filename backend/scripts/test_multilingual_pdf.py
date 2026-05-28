#!/usr/bin/env python3
"""
test_multilingual_pdf.py — Test multilingual PDF ingestion.

Tests three scenarios for the new multilingual pipeline:

  Scenario A — Auto language detection
    Submit a PDF with NO language hint. Verify the pipeline auto-detects
    the language via langdetect and tags the content item correctly.

  Scenario B — Outputs in source language (default)
    Submit a PDF with a known language. Verify AI outputs (summary, glossary)
    are generated in the same language as the content.

  Scenario C — Outputs in different language (output_language override)
    Submit an English PDF but request French output. Verify the AI outputs
    come back in French.

Usage:
    # Run all scenarios (quickest — shares a single ingest per scenario):
    python scripts/test_multilingual_pdf.py --key dev-master-key-change-in-production

    # Run only scenario C (translate English PDF to French):
    python scripts/test_multilingual_pdf.py --key dev-master-key-change-in-production --scenario c

    # Use your own PDF URL:
    python scripts/test_multilingual_pdf.py --key dev-master-key-change-in-production \\
        --url https://example.com/my-document.pdf --scenario b

    # Show full AI output payloads:
    python scripts/test_multilingual_pdf.py --key dev-master-key-change-in-production --verbose

    # Re-check outputs for a content item you already processed:
    python scripts/test_multilingual_pdf.py --key dev-master-key-change-in-production \\
        --content-item-id <UUID>
"""
import argparse
import json
import sys
import time

import httpx

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_API_BASE    = "http://localhost:8000"
DEFAULT_API_KEY     = "dev-master-key-change-in-production"

# A short, clearly English public-domain PDF (~15 pages, W3C PDF accessibility)
PDF_URL_ENGLISH = "https://www.w3.org/WAI/WCAG21/Techniques/pdf/PDF1.pdf"

# An alternative English PDF (the original "Attention is All You Need" paper)
PDF_URL_ARXIV   = "https://arxiv.org/pdf/1706.03762"

POLL_INTERVAL   = 3    # seconds
MAX_WAIT        = 300  # 5 minutes

BASE_CMID = 7100  # unique cmid range so these don't collide with other tests


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


def preview(value, max_len: int = 120) -> str:
    s = str(value)
    return s[:max_len] + "…" if len(s) > max_len else s


# ── API helpers ───────────────────────────────────────────────────────────────

def submit_pdf(
    client: httpx.Client,
    *,
    pdf_url: str,
    cmid: int,
    language: str,
    output_language: str,
    tasks: list[str],
    label: str,
) -> tuple[str, str]:
    """POST /ingest. Returns (content_item_id, job_id)."""
    payload = {
        "source_url": pdf_url,
        "content_type": "pdf",
        "moodle_course_id": 101,
        "moodle_cmid": cmid,
        "title": f"Multilingual PDF Test — {label}",
        "options": {
            "tasks": tasks,
            "language": language,
            "output_language": output_language,
        },
    }

    info(f"Submitting: language={language!r}  output_language={output_language!r}")
    info(f"Tasks: {tasks}")

    r = client.post("/api/v1/ingest", json=payload)
    if r.status_code not in (200, 202):
        err(f"Ingest failed: {r.status_code} — {r.text[:400]}")
        sys.exit(1)

    data = r.json()
    cid  = data["content_item_id"]
    jid  = data["job_id"]
    st   = data["status"]

    ok(f"content_item_id : {cid}")
    ok(f"job_id          : {jid}")
    ok(f"initial status  : {st}")
    return cid, jid


def wait_for_job(client: httpx.Client, job_id: str) -> None:
    """Poll until completed or fail with exit(1)."""
    start        = time.time()
    last_pct     = -1

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


def get_content_detail(client: httpx.Client, cid: str) -> dict:
    r = client.get(f"/api/v1/content/{cid}")
    if r.status_code == 200:
        return r.json()
    return {}


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
    if r.status_code == 200:
        return r.json()
    return []


# ── Scenarios ─────────────────────────────────────────────────────────────────

def run_scenario_a(client: httpx.Client, pdf_url: str, verbose: bool) -> None:
    """Scenario A — Auto language detection (no language hint)."""
    hdr("Scenario A: Auto language detection  (language='', output_language='')")

    cid, jid = submit_pdf(
        client,
        pdf_url=pdf_url,
        cmid=BASE_CMID + 1,
        language="",           # ← empty = auto-detect
        output_language="",    # ← empty = same as detected source
        tasks=["summary", "glossary"],
        label="Auto-detect",
    )

    hdr("Polling job…")
    wait_for_job(client, jid)

    hdr("Verifying results — Scenario A")

    # Check content item — language should have been auto-detected and saved
    detail = get_content_detail(client, cid)
    if detail:
        lang = detail.get("language", "?")
        ok(f"content_item.language = '{lang}'  (auto-detected by langdetect)")
        if lang and lang != "?":
            ok("Language detection PASSED — content item language was populated")
        else:
            err("Language field is empty — langdetect may not be installed or text was too short")

    # Check that a summary was generated (in whatever language was detected)
    outputs = list_outputs(client, cid)
    ok(f"AI outputs generated: {[o['output_type'] for o in outputs]}")

    detected_lang = detail.get("language", "en")
    summary = get_output(client, cid, "summary", language=detected_lang)
    if summary:
        payload = summary.get("payload", {})
        ok(f"Summary language tag: {payload.get('language', '?')}")
        if verbose:
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:2000])
        else:
            info(f"Summary preview: {preview(payload.get('summary', ''))}")
    else:
        err("Could not fetch summary output")


def run_scenario_b(client: httpx.Client, pdf_url: str, verbose: bool) -> None:
    """Scenario B — Explicit source language, outputs in same language."""
    hdr("Scenario B: English PDF → outputs in English  (language='en', output_language='')")

    cid, jid = submit_pdf(
        client,
        pdf_url=pdf_url,
        cmid=BASE_CMID + 2,
        language="en",         # ← explicit hint
        output_language="",    # ← empty = same as source = en
        tasks=["summary", "glossary", "flashcards"],
        label="EN-to-EN",
    )

    hdr("Polling job…")
    wait_for_job(client, jid)

    hdr("Verifying results — Scenario B")

    outputs = list_outputs(client, cid)
    ok(f"Generated {len(outputs)} outputs: {[o['output_type'] for o in outputs]}")
    for o in outputs:
        lang = o.get("language", "?")
        ok(f"  {o['output_type']:<14}  language={lang}")
        if lang == "en":
            ok("  → Language tag CORRECT (en)")
        else:
            err(f"  → Expected 'en', got '{lang}'")

    summary = get_output(client, cid, "summary", language="en")
    if summary and verbose:
        print(json.dumps(summary.get("payload", {}), indent=2, ensure_ascii=False)[:2000])

    glossary = get_output(client, cid, "glossary", language="en")
    if glossary:
        terms = glossary.get("payload", {}).get("terms", [])
        ok(f"Glossary terms count: {len(terms)}")
        if terms and verbose:
            print(json.dumps(terms[:3], indent=2, ensure_ascii=False))
        elif terms:
            info(f"First term: {terms[0].get('term')} — {preview(terms[0].get('definition', ''))}")


def run_scenario_c(
    client: httpx.Client,
    pdf_url: str,
    output_lang: str,
    verbose: bool,
) -> None:
    """Scenario C — English PDF, outputs in a different language."""
    hdr(f"Scenario C: English PDF → outputs in '{output_lang}'  (output_language='{output_lang}')")
    info("This calls the AI generators with the target language instruction.")
    info("The summary, glossary, and flashcards should come back in the target language.")

    cid, jid = submit_pdf(
        client,
        pdf_url=pdf_url,
        cmid=BASE_CMID + 3,
        language="en",
        output_language=output_lang,  # ← override: translate outputs to this language
        tasks=["summary", "glossary", "flashcards"],
        label=f"EN-to-{output_lang.upper()}",
    )

    hdr("Polling job…")
    wait_for_job(client, jid)

    hdr(f"Verifying results — Scenario C (expected language: {output_lang})")

    # Outputs should be tagged with output_lang and content should be in that language
    outputs = list_outputs(client, cid)
    ok(f"Generated {len(outputs)} outputs")

    for o in outputs:
        lang = o.get("language", "?")
        otype = o.get("output_type", "?")
        status = "CORRECT" if lang == output_lang else f"WRONG (expected {output_lang})"
        ok(f"  {otype:<14}  language={lang}  [{status}]")

    summary = get_output(client, cid, "summary", language=output_lang)
    if summary:
        payload = summary.get("payload", {})
        summary_text = payload.get("summary", "")
        ok(f"Summary language={payload.get('language')}:")
        if verbose:
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])
        else:
            info(f"  First 300 chars: {summary_text[:300]}")

        # Simple heuristic check: if output_lang is 'fr', look for French words
        if output_lang == "fr" and summary_text:
            french_hints = ["le ", "la ", "les ", "de ", "du ", "des ", "un ", "une ", "et ", "en "]
            found = [w for w in french_hints if w in summary_text.lower()]
            if found:
                ok(f"French word check PASSED (found: {', '.join(found[:5])})")
            else:
                err("French word check FAILED — output may not be in French")

    glossary = get_output(client, cid, "glossary", language=output_lang)
    if glossary:
        terms = glossary.get("payload", {}).get("terms", [])
        ok(f"Glossary terms: {len(terms)}")
        if terms:
            t = terms[0]
            info(f"  First term: {t.get('term')} — {preview(t.get('definition', ''))}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Multilingual PDF pipeline test for axis-ai",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--key",     default=DEFAULT_API_KEY, help="API key")
    parser.add_argument("--base",    default=DEFAULT_API_BASE, help="API base URL")
    parser.add_argument("--url",     default=PDF_URL_ENGLISH, help="PDF URL to use")
    parser.add_argument("--arxiv",   action="store_true", help="Use ArXiv PDF instead")
    parser.add_argument(
        "--scenario",
        choices=["a", "b", "c", "all"],
        default="all",
        help="Which scenario to run (default: all)",
    )
    parser.add_argument(
        "--output-lang",
        default="fr",
        help="Target output language for scenario C (default: fr)",
    )
    parser.add_argument(
        "--content-item-id",
        help="Skip ingest and just re-check outputs for an existing content item",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    pdf_url = PDF_URL_ARXIV if args.arxiv else args.url

    print()
    print("=" * 64)
    print("  axis-ai  —  Multilingual PDF Pipeline Test")
    print("=" * 64)
    print(f"  API  : {args.base}")
    print(f"  PDF  : {pdf_url}")
    print(f"  Scenario: {args.scenario}")
    print()

    headers = {"Authorization": f"Bearer {args.key}"}

    with httpx.Client(
        base_url=args.base,
        headers=headers,
        timeout=60,
    ) as client:
        # Quick health check
        r = client.get("/api/v1/health")
        if r.status_code != 200:
            err("API is not reachable — is docker compose up?")
            sys.exit(1)
        ok(f"API healthy: {r.json()}")

        scenario = args.scenario.lower()

        if scenario in ("a", "all"):
            run_scenario_a(client, pdf_url, args.verbose)
        if scenario in ("b", "all"):
            run_scenario_b(client, pdf_url, args.verbose)
        if scenario in ("c", "all"):
            run_scenario_c(client, pdf_url, args.output_lang, args.verbose)

    print()
    print("=" * 64)
    print("  All selected scenarios complete.")
    print("=" * 64)
    print()
    print("  TIP — To verify in the DB directly:")
    print("  psql postgresql://axis:axisdev@localhost:5432/axis_ai -c \\")
    print("    \"SELECT id, title, language, status FROM content_items ORDER BY created_at DESC LIMIT 5;\"")
    print()
    print("  psql postgresql://axis:axisdev@localhost:5432/axis_ai -c \\")
    print("    \"SELECT output_type, language, status FROM ai_outputs ORDER BY created_at DESC LIMIT 10;\"")
    print()


if __name__ == "__main__":
    main()
