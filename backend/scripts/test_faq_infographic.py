#!/usr/bin/env python3
"""
test_faq_infographic.py — Dedicated smoke-test for the FAQ and Infographic generators.

HOW TO TEST
-----------

1.  Start the stack
    ---------------
    docker compose up -d
    # or: uvicorn app.main:app --reload  +  celery -A app.celery_app worker -l info

2.  Quick test against a fresh video URL (e.g. a YouTube link)
    -----------------------------------------------------------
    python scripts/test_faq_infographic.py \\
        --key  "your-api-key" \\
        --url  "https://www.youtube.com/watch?v=dQw4w9WgXcQ" \\
        --content-type video_link

    This will:
      • POST /ingest  with tasks ["faq", "infographic"]
      • Poll GET /jobs/{job_id} until the job completes (or fails)
      • Print the full FAQ (Q&A, topic, difficulty)
      • Fetch the Infographic JSON (prints metadata)
      • Save the HTML to /tmp/infographic_<id>.html   ← open in browser!
      • Hit /infographic/html to verify the raw HTML endpoint

3.  Test against an existing content item (skip re-ingest)
    -------------------------------------------------------
    python scripts/test_faq_infographic.py \\
        --key  "your-api-key" \\
        --content-item-id "uuid-of-existing-item"

    This triggers POST /content/{id}/generate with tasks faq+infographic,
    then polls the returned job_id until done.

4.  Test a PDF or SCORM page instead of a video
    ---------------------------------------------
    python scripts/test_faq_infographic.py \\
        --key  "your-api-key" \\
        --url  "https://example.com/lesson.pdf" \\
        --content-type pdf_link

5.  Flags
    ------
    --base-url      API base URL       (default: http://localhost:8000/api/v1)
    --poll-interval Seconds between polls (default: 4)
    --poll-timeout  Give up after N seconds (default: 300)
    --faq-count     Number of FAQ items to request (default: 8)
    --save-dir      Directory to save the HTML file (default: /tmp)
    --no-html-check Skip the raw /infographic/html endpoint check

WHAT TO LOOK FOR
----------------
  FAQ
    ✔  A numbered list of Q&A pairs printed to the terminal
    ✔  Each entry shows topic tag and difficulty level (beginner/intermediate/advanced)
    ✔  Count matches (or is close to) --faq-count

  Infographic
    ✔  JSON metadata printed: title, sections list, colour_palette
    ✔  "Saved HTML to /tmp/infographic_<id>.html — open in a browser!"
    ✔  Opening that file in a browser renders a styled, self-contained page
    ✔  The /infographic/html endpoint returns 200 with Content-Type: text/html
"""

import argparse
import json
import sys
import time
from pathlib import Path

try:
    import httpx
except ImportError:
    print("ERROR: httpx not installed.  Run:  pip install httpx")
    sys.exit(1)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Smoke-test the FAQ and Infographic endpoints",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--base-url", default="http://localhost:8000/api/v1",
                   help="API base URL (default: http://localhost:8000/api/v1)")
    p.add_argument("--key", required=False, default="",
                   help="API key / bearer token (if auth is enabled)")

    # Ingest path
    ingest_g = p.add_argument_group("ingest (required unless --content-item-id is given)")
    ingest_g.add_argument("--url", help="Content URL to ingest (YouTube, Vimeo, PDF, etc.)")
    ingest_g.add_argument("--content-type", default="video_link",
                          choices=["video_link", "vimeo_link", "youtube_link",
                                   "peertube_link", "pdf_link", "scorm_link",
                                   "html_page"],
                          help="Content type (default: video_link)")
    ingest_g.add_argument("--course-id", default="1", help="Moodle course ID (default: 1)")
    ingest_g.add_argument("--cmid", default="1", help="Moodle cmid (default: 1)")
    ingest_g.add_argument("--tenant-id", default="default",
                          help="Tenant ID (default: default)")

    # Skip-ingest path
    p.add_argument("--content-item-id",
                   help="Existing content item UUID — skip ingest, trigger generate directly")

    # Polling
    p.add_argument("--poll-interval", type=float, default=4,
                   help="Seconds between status polls (default: 4)")
    p.add_argument("--poll-timeout", type=float, default=300,
                   help="Give up polling after N seconds (default: 300)")

    # Generator options
    p.add_argument("--faq-count", type=int, default=8,
                   help="Number of FAQ items to request (default: 8)")
    p.add_argument("--language", default="en",
                   help="Output language code (default: en)")

    # Output
    p.add_argument("--save-dir", default="/tmp",
                   help="Directory to save infographic HTML (default: /tmp)")
    p.add_argument("--no-html-check", action="store_true",
                   help="Skip the raw /infographic/html endpoint check")

    args = p.parse_args()
    if not args.content_item_id and not args.url:
        p.error("Either --url or --content-item-id is required")
    return args


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def make_client(base_url: str, key: str) -> httpx.Client:
    headers = {}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    # httpx base_url must end with "/" and paths must NOT start with "/"
    # so that URL joining keeps the full prefix (e.g. /api/v1/content/...)
    if not base_url.endswith("/"):
        base_url = base_url + "/"
    return httpx.Client(base_url=base_url, headers=headers, timeout=30)


def check(resp: httpx.Response, label: str):
    if resp.status_code >= 400:
        print(f"\n✗  {label} — HTTP {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text[:500])
        sys.exit(1)


# ---------------------------------------------------------------------------
# Step 1a — Ingest (fresh URL)
# ---------------------------------------------------------------------------

def ingest(client: httpx.Client, args: argparse.Namespace) -> tuple[str, str]:
    """Submit a fresh ingest job. Returns (content_item_id, job_id)."""
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("STEP 1/4 — Ingest content")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    payload = {
        "source_url": args.url,
        "content_type": args.content_type,
        "moodle_course_id": int(args.course_id),
        "moodle_cmid": int(args.cmid),
        "options": {
            "tasks": ["faq", "infographic"],
            "language": args.language,
            "count": args.faq_count,
        },
    }

    print(f"  URL          : {args.url}")
    print(f"  content_type : {args.content_type}")
    print(f"  tasks        : faq, infographic")
    print(f"  faq_count    : {args.faq_count}")

    resp = client.post("ingest", json=payload)
    check(resp, "POST /ingest")

    data = resp.json()
    content_item_id = data.get("content_item_id") or data.get("id")
    job_id = data.get("job_id") or data.get("task_id")

    print(f"\n  ✔  content_item_id : {content_item_id}")
    print(f"  ✔  job_id          : {job_id}")
    return content_item_id, job_id


# ---------------------------------------------------------------------------
# Step 1b — Generate outputs for existing content item
# ---------------------------------------------------------------------------

def trigger_generate(client: httpx.Client, content_item_id: str,
                     args: argparse.Namespace) -> str:
    """Trigger POST /content/{id}/generate. Returns job_id."""
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("STEP 1/4 — Trigger generation on existing item")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  content_item_id : {content_item_id}")
    print(f"  tasks           : faq, infographic")

    payload = {
        "tasks": ["faq", "infographic"],
        "language": args.language,
        "count": args.faq_count,
        "force_regenerate": False,
    }

    resp = client.post(f"content/{content_item_id}/generate", json=payload)
    check(resp, f"POST /content/{content_item_id}/generate")

    data = resp.json()
    job_id = data.get("job_id") or data.get("task_id")

    print(f"\n  ✔  job_id : {job_id}")
    return job_id


# ---------------------------------------------------------------------------
# Step 2 — Poll job status until complete
# ---------------------------------------------------------------------------

def poll_job(client: httpx.Client, job_id: str, args: argparse.Namespace):
    """Poll GET /jobs/{job_id} until status == completed (or failed)."""
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("STEP 2/4 — Wait for pipeline to finish")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  Polling /jobs/{job_id} every {args.poll_interval}s …\n")

    deadline = time.time() + args.poll_timeout
    elapsed = 0

    while time.time() < deadline:
        resp = client.get(f"jobs/{job_id}")
        check(resp, f"GET /jobs/{job_id}")
        data = resp.json()
        status = str(data.get("status") or "unknown")
        progress = int(data.get("progress") or 0)
        msg = str(data.get("progress_message") or "")

        print(f"\r  [{elapsed:>4.0f}s]  {status:12s}  {progress:3d}%  {msg[:50]}   ",
              end="", flush=True)

        if status == "completed":
            print(f"\n\n  ✔  Job complete")
            return data.get("content_item_id", "")

        if status in ("failed", "error"):
            print(f"\n\n  ✗  Job failed — status: {status}")
            err = data.get("error_message", "(no error message)")
            print(f"  Error: {err}")
            sys.exit(1)

        elapsed += args.poll_interval
        time.sleep(args.poll_interval)

    print(f"\n\n  ✗  Timed out after {args.poll_timeout}s waiting for job {job_id}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Step 3 — Fetch and display FAQ
# ---------------------------------------------------------------------------

def fetch_faq(client: httpx.Client, content_item_id: str, language: str):
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("STEP 3/4 — Fetch FAQ")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    resp = client.get(f"content/{content_item_id}/faq",
                      params={"language": language})
    check(resp, f"GET /content/{content_item_id}/faq")
    data = resp.json()

    faqs = data.get("faqs", [])
    faq_count = data.get("faq_count", len(faqs))
    lang = data.get("language", "?")
    content_type = data.get("content_type", "?")
    model = data.get("model", "?")
    is_edited = data.get("is_teacher_edited", False)

    print(f"\n  content_item_id : {content_item_id}")
    print(f"  content_type    : {content_type}")
    print(f"  language        : {lang}")
    print(f"  faq_count       : {faq_count}")
    print(f"  model           : {model}")
    print(f"  teacher_edited  : {is_edited}")

    if not faqs:
        print("\n  ⚠  No FAQ items returned — check generator logs")
        return

    DIFF_ICONS = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}

    print(f"\n  ─── FAQ Items ({faq_count}) ───\n")
    for i, item in enumerate(faqs, 1):
        diff = item.get("difficulty", "beginner")
        icon = DIFF_ICONS.get(diff, "⚪")
        topic = item.get("topic", "")
        q = item.get("question", "(no question)")
        a = item.get("answer", "(no answer)")

        print(f"  {i:2d}. {icon} [{diff.upper()}]  {f'#{topic}' if topic else ''}")
        print(f"      Q: {q}")
        print(f"      A: {a}")
        print()

    print(f"  ✔  FAQ fetched — {faq_count} items")


# ---------------------------------------------------------------------------
# Step 4 — Fetch and display Infographic
# ---------------------------------------------------------------------------

def fetch_infographic(client: httpx.Client, content_item_id: str,
                      language: str, save_dir: str, skip_html_check: bool):
    print("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("STEP 4/4 — Fetch Infographic")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # --- 4a: JSON endpoint ---
    resp = client.get(f"content/{content_item_id}/infographic",
                      params={"language": language})
    check(resp, f"GET /content/{content_item_id}/infographic")
    data = resp.json()

    title = data.get("title", "(no title)")
    sections = data.get("sections", [])
    palette = data.get("colour_palette", {})
    html = data.get("html", "")
    html_char_count = data.get("html_char_count", len(html))
    model = data.get("model", "?")
    content_type = data.get("content_type", "?")
    lang = data.get("language", "?")

    print(f"\n  content_item_id : {content_item_id}")
    print(f"  content_type    : {content_type}")
    print(f"  language        : {lang}")
    print(f"  model           : {model}")
    print(f"  title           : {title}")
    print(f"  sections        : {', '.join(sections) if sections else '(none listed)'}")
    print(f"  colour_palette  : primary={palette.get('primary','?')}  "
          f"accent1={palette.get('accent1','?')}  accent2={palette.get('accent2','?')}")
    print(f"  html_char_count : {html_char_count:,}")

    if not html:
        print("\n  ⚠  No HTML content returned — check generator logs")
        return

    # Sanity: check it looks like HTML
    html_lower = html.strip().lower()
    if not html_lower.startswith("<!doctype") and not html_lower.startswith("<html"):
        print(f"  ⚠  HTML doesn't start with <!DOCTYPE> — first 120 chars:")
        print(f"     {html[:120]!r}")
    else:
        print(f"  ✔  HTML starts correctly with: {html[:40].strip()!r}")

    # --- Save to disk ---
    short_id = content_item_id[:8]
    save_path = Path(save_dir) / f"infographic_{short_id}.html"
    try:
        save_path.write_text(html, encoding="utf-8")
        print(f"\n  💾  Saved HTML to {save_path}")
        print(f"  🌐  Open in browser:  file://{save_path.resolve()}")
    except OSError as exc:
        print(f"  ⚠  Could not save HTML: {exc}")

    # --- 4b: Raw HTML endpoint ---
    if not skip_html_check:
        print(f"\n  ─── Checking /infographic/html (raw text/html) ───")
        resp_html = client.get(f"content/{content_item_id}/infographic/html",
                               params={"language": language})
        check(resp_html, f"GET /content/{content_item_id}/infographic/html")

        ct = resp_html.headers.get("content-type", "")
        raw = resp_html.text

        if "text/html" in ct:
            print(f"  ✔  Content-Type: {ct}")
        else:
            print(f"  ⚠  Unexpected Content-Type: {ct!r}")

        if raw.strip().lower().startswith("<!doctype"):
            print(f"  ✔  Raw HTML endpoint returns valid HTML ({len(raw):,} chars)")
        else:
            print(f"  ⚠  Raw HTML response doesn't start with <!DOCTYPE>")
            print(f"     First 200 chars: {raw[:200]!r}")

    print(f"\n  ✔  Infographic fetched — {html_char_count:,} chars of HTML")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    client = make_client(args.base_url, args.key)

    print("=" * 51)
    print("  axis-ai FAQ + Infographic smoke-test")
    print("=" * 51)
    print(f"  base_url : {args.base_url}")
    print(f"  auth     : {'yes' if args.key else 'no'}")

    # --- Resolve content_item_id + job_id ---
    if args.content_item_id:
        # Skip ingest — trigger generation on existing item
        content_item_id = args.content_item_id
        job_id = trigger_generate(client, content_item_id, args)
    else:
        # Fresh ingest
        content_item_id, job_id = ingest(client, args)

    # --- Poll job to completion ---
    # (poll_job returns content_item_id from job response, but we already have it)
    poll_job(client, job_id, args)

    # --- Fetch outputs ---
    fetch_faq(client, content_item_id, args.language)
    fetch_infographic(client, content_item_id, args.language,
                      args.save_dir, args.no_html_check)

    print("\n" + "=" * 51)
    print("  All checks passed ✔")
    print("=" * 51)


if __name__ == "__main__":
    main()
