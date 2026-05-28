#!/usr/bin/env python3
"""
End-to-end PDF pipeline test.

Tests the complete flow:
  1. POST /api/v1/ingest          → submit PDF URL
  2. GET  /api/v1/jobs/{job_id}   → poll until complete
  3. GET  /api/v1/content/{id}/summary   → verify output
  4. GET  /api/v1/content/{id}/flashcards
  5. GET  /api/v1/content/{id}/outputs   → list all outputs

Usage:
    # Make sure the API is running first:
    docker compose up -d

    # Basic test with a public PDF:
    python scripts/test_pdf.py --key axai_YOUR_KEY_HERE

    # Test specific tasks:
    python scripts/test_pdf.py --key axai_... --tasks summary,quiz,glossary

    # Use a custom PDF URL:
    python scripts/test_pdf.py --key axai_... --url https://example.com/doc.pdf

    # Verbose mode shows full JSON payloads:
    python scripts/test_pdf.py --key axai_... --verbose
"""
import argparse
import json
import sys
import time
from typing import Any

import httpx

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_API_BASE = "http://localhost:8000"

# Public domain PDF — a short accessible paper (~15 pages)
DEFAULT_PDF_URL = (
    "https://www.w3.org/WAI/WCAG21/Techniques/pdf/PDF1.pdf"
)

# Small ArXiv paper as an alternative
ALT_PDF_URL = (
    "https://arxiv.org/pdf/1706.03762"  # "Attention is All You Need"
)

POLL_INTERVAL_INITIAL = 2   # seconds between polls for first 30s
POLL_INTERVAL_SLOW = 10     # seconds between polls after 30s
MAX_WAIT_SECONDS = 300      # 5 minutes max


# ── Helpers ───────────────────────────────────────────────────────────────────

def print_section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def print_ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def print_err(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)


def print_info(msg: str) -> None:
    print(f"  ·  {msg}")


def truncate(text: str, max_len: int = 200) -> str:
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


def dump(data: Any, verbose: bool) -> None:
    if verbose:
        print(json.dumps(data, indent=2, default=str))
    else:
        # Just show a taste
        if isinstance(data, dict):
            for k, v in list(data.items())[:5]:
                print(f"     {k}: {truncate(str(v))}")


# ── Test steps ────────────────────────────────────────────────────────────────

def test_health(client: httpx.Client) -> bool:
    print_section("Step 0: Health check")
    try:
        r = client.get("/api/v1/health")
        if r.status_code == 200:
            print_ok(f"API healthy — {r.json()}")
            return True
        else:
            print_err(f"Health check failed: {r.status_code} {r.text}")
            return False
    except httpx.ConnectError:
        print_err(
            "Cannot connect to API. Is 'docker compose up -d' running?\n"
            "       Make sure the api service is up on localhost:8000"
        )
        return False


def ingest_pdf(
    client: httpx.Client,
    pdf_url: str,
    tasks: list[str],
    verbose: bool,
) -> tuple[str, str] | None:
    """POST /ingest. Returns (content_item_id, job_id) or None on failure."""
    print_section(f"Step 1: Ingest PDF")
    print_info(f"URL   : {pdf_url}")
    print_info(f"Tasks : {tasks}")

    payload = {
        "source_url": pdf_url,
        "content_type": "pdf",
        "moodle_course_id": 1,
        "moodle_cmid": 1001,
        "moodle_user_id": 2,
        "title": "Test PDF Document",
        "options": {
            "tasks": tasks,
            "language": "en",
            "chunk_size": 800,
            "chunk_overlap": 100,
        },
        "metadata": {"test_run": True},
    }

    r = client.post("/api/v1/ingest", json=payload)
    print_info(f"Status: {r.status_code}")

    if r.status_code not in (200, 202):
        print_err(f"Ingest failed: {r.status_code}")
        print(r.text)
        return None

    data = r.json()
    dump(data, verbose)

    content_item_id = data.get("content_item_id")
    job_id = data.get("job_id")
    status = data.get("status")

    print_ok(f"content_item_id : {content_item_id}")
    print_ok(f"job_id          : {job_id}")
    print_ok(f"status          : {status}")

    if status == "ready":
        print_info("Content already processed — skipping poll step")
        return content_item_id, ""

    return content_item_id, job_id


def poll_job(
    client: httpx.Client,
    job_id: str,
    verbose: bool,
) -> bool:
    """Poll /jobs/{job_id} until complete or failed. Returns True on success."""
    if not job_id:
        return True  # Already ready

    print_section(f"Step 2: Poll job {job_id[:8]}…")

    start = time.time()
    last_progress = -1

    while True:
        elapsed = time.time() - start
        if elapsed > MAX_WAIT_SECONDS:
            print_err(f"Timed out after {MAX_WAIT_SECONDS}s")
            return False

        r = client.get(f"/api/v1/jobs/{job_id}")
        if r.status_code != 200:
            print_err(f"Job poll failed: {r.status_code} {r.text}")
            return False

        data = r.json()
        status = data.get("status")
        progress = data.get("progress", 0)
        message = data.get("progress_message", "")

        if progress != last_progress:
            print_info(f"[{elapsed:5.0f}s] {progress:3d}%  {status:<12}  {message}")
            last_progress = progress

        if verbose and status in ("completed", "failed"):
            dump(data, verbose)

        if status == "completed":
            print_ok(f"Job completed in {elapsed:.1f}s")
            return True

        if status == "failed":
            print_err(f"Job FAILED: {data.get('error_message')}")
            if verbose:
                print(data.get("error_traceback", ""))
            return False

        interval = POLL_INTERVAL_INITIAL if elapsed < 30 else POLL_INTERVAL_SLOW
        time.sleep(interval)


def fetch_output(
    client: httpx.Client,
    content_item_id: str,
    output_type: str,
    verbose: bool,
) -> bool:
    """GET /content/{id}/{output_type}. Returns True on success."""
    r = client.get(f"/api/v1/content/{content_item_id}/{output_type}")
    if r.status_code == 200:
        data = r.json()
        payload = data.get("payload", {})
        model = data.get("model", "?")
        ptok = data.get("prompt_tokens", 0)
        ctok = data.get("completion_tokens", 0)
        print_ok(
            f"{output_type:<12} model={model}  "
            f"tokens={ptok}+{ctok}"
        )
        if verbose:
            dump(payload, verbose)
        else:
            # Show a small preview of the payload
            if isinstance(payload, dict):
                first_key = next(iter(payload), None)
                if first_key:
                    val = payload[first_key]
                    print(f"     └── {first_key}: {truncate(str(val), 120)}")
        return True
    elif r.status_code == 404:
        detail = r.json().get("detail", "not found")
        print_info(f"{output_type:<12} 404 — {detail}")
        return False
    else:
        print_err(f"{output_type:<12} {r.status_code} — {r.text[:200]}")
        return False


def fetch_all_outputs(
    client: httpx.Client,
    content_item_id: str,
    requested_tasks: list[str],
    verbose: bool,
) -> None:
    print_section("Step 3: Fetch outputs")
    success_count = 0
    for task in requested_tasks:
        ok = fetch_output(client, content_item_id, task, verbose)
        if ok:
            success_count += 1

    print()
    print_ok(f"{success_count}/{len(requested_tasks)} outputs retrieved successfully")


def list_all_outputs(
    client: httpx.Client,
    content_item_id: str,
    verbose: bool,
) -> None:
    print_section("Step 4: List all outputs (/outputs)")
    r = client.get(f"/api/v1/content/{content_item_id}/outputs")
    if r.status_code != 200:
        print_err(f"List failed: {r.status_code} {r.text}")
        return

    outputs = r.json()
    print_ok(f"Found {len(outputs)} active output(s)")
    for o in outputs:
        otype = o.get("output_type", "?")
        lang = o.get("language", "?")
        model = o.get("model", "?")
        ptok = o.get("prompt_tokens", 0)
        ctok = o.get("completion_tokens", 0)
        print(f"     {otype:<16} lang={lang}  model={model}  tokens={ptok}+{ctok}")

    if verbose:
        dump(outputs, verbose)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="End-to-end PDF pipeline test for axis-ai"
    )
    parser.add_argument(
        "--key",
        required=True,
        help="API key (e.g. axai_xxxxxxxxxxxxxxxx)",
    )
    parser.add_argument(
        "--url",
        default=DEFAULT_PDF_URL,
        help=f"PDF URL to test (default: W3C PDF accessibility doc)",
    )
    parser.add_argument(
        "--alt",
        action="store_true",
        help="Use the alternative PDF URL (ArXiv 'Attention is All You Need')",
    )
    parser.add_argument(
        "--tasks",
        default="summary,flashcards,glossary",
        help="Comma-separated tasks (default: summary,flashcards,glossary)",
    )
    parser.add_argument(
        "--base",
        default=DEFAULT_API_BASE,
        help=f"API base URL (default: {DEFAULT_API_BASE})",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full JSON payloads",
    )
    args = parser.parse_args()

    pdf_url = ALT_PDF_URL if args.alt else args.url
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]

    headers = {"Authorization": f"Bearer {args.key}"}

    print()
    print("=" * 60)
    print("  axis-ai  —  End-to-End PDF Test")
    print("=" * 60)
    print(f"  API base : {args.base}")
    print(f"  PDF URL  : {pdf_url}")
    print(f"  Tasks    : {tasks}")
    print()

    with httpx.Client(base_url=args.base, headers=headers, timeout=30) as client:
        # Step 0: health
        if not test_health(client):
            sys.exit(1)

        # Step 1: ingest
        result = ingest_pdf(client, pdf_url, tasks, args.verbose)
        if not result:
            sys.exit(1)
        content_item_id, job_id = result

        # Step 2: poll
        if not poll_job(client, job_id, args.verbose):
            sys.exit(1)

        # Step 3: fetch each requested output
        fetch_all_outputs(client, content_item_id, tasks, args.verbose)

        # Step 4: list all outputs
        list_all_outputs(client, content_item_id, args.verbose)

    print()
    print("=" * 60)
    print("  Test complete")
    print("=" * 60)
    print()


if __name__ == "__main__":
    main()
