#!/usr/bin/env python3
"""
test_page.py — End-to-end test for the Moodle Page content pipeline.

The page extractor accepts raw HTML from Moodle, strips it to plain text,
detects embedded YouTube / Vimeo iframes, fetches their transcripts, and
merges everything into one unified document for chunking and RAG.

Usage:
    # Plain text page (default):
    python scripts/test_page.py --key axai_YOUR_KEY

    # Page with embedded YouTube video (3Blue1Brown — Neural Networks):
    python scripts/test_page.py --key axai_YOUR_KEY --with-youtube

    # Page with embedded Vimeo video:
    python scripts/test_page.py --key axai_YOUR_KEY --with-vimeo

    # Page with BOTH types of embedded video:
    python scripts/test_page.py --key axai_YOUR_KEY --with-youtube --with-vimeo

    # Custom HTML (paste or pipe your own content):
    python scripts/test_page.py --key axai_YOUR_KEY --html "<h2>My topic</h2><p>...</p>"

    # Full output payloads:
    python scripts/test_page.py --key axai_YOUR_KEY --verbose

    # Skip ingest, poll an existing job:
    python scripts/test_page.py --key axai_YOUR_KEY --job-id <UUID>

    # Skip ingest+poll, fetch outputs only:
    python scripts/test_page.py --key axai_YOUR_KEY --content-item-id <UUID>
"""
import argparse
import json
import sys
import time

import httpx

BASE_URL = "http://localhost:8000/api/v1"
POLL_INTERVAL = 3    # seconds between status checks
MAX_WAIT = 300       # max seconds to wait (page with video can take a while)

# ── Sample HTML payloads ────────────────────────────────────────────────────

SAMPLE_TEXT_ONLY = """
<h2>Introduction to Machine Learning</h2>
<p>Machine learning is a subset of artificial intelligence that enables systems
to learn and improve from experience without being explicitly programmed.</p>
<h3>Key Concepts</h3>
<ul>
  <li><strong>Supervised Learning:</strong> The algorithm is trained on labelled data
      where inputs and expected outputs are both provided.</li>
  <li><strong>Unsupervised Learning:</strong> The algorithm discovers patterns and
      structure in unlabelled data without guidance.</li>
  <li><strong>Reinforcement Learning:</strong> An agent learns optimal behaviour by
      receiving rewards or penalties based on its actions.</li>
</ul>
<p>The most common supervised learning algorithms include linear regression,
logistic regression, decision trees, random forests, support vector machines,
and neural networks. Each has trade-offs in interpretability, performance,
and data requirements.</p>
<h3>Applications</h3>
<p>Machine learning is widely used in image recognition, natural language processing,
recommendation systems, fraud detection, medical diagnosis, and autonomous vehicles.
Understanding the fundamentals is essential before exploring deep learning.</p>
"""

SAMPLE_WITH_YOUTUBE = """
<h2>Understanding Neural Networks</h2>
<p>Neural networks are computing systems loosely inspired by the biological neural
networks in animal brains. They form the foundation of modern deep learning.</p>
<p>Watch the video below for a visual, intuitive explanation of how neural networks
learn from data using gradient descent and backpropagation:</p>
<p>
  <iframe
    width="560" height="315"
    src="https://www.youtube.com/embed/aircAruvnKk"
    title="But what is a neural network? | Chapter 1, Deep learning"
    frameborder="0"
    allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
    allowfullscreen>
  </iframe>
</p>
<p>After watching, reflect on how the network adjusts weights during training and
why more layers allow the model to learn increasingly abstract representations.</p>
"""

SAMPLE_WITH_VIMEO = """
<h2>Data Structures: Arrays and Linked Lists</h2>
<p>This module compares two fundamental data structures used throughout computer science.</p>
<p>
  <iframe
    src="https://player.vimeo.com/video/76979871"
    width="640" height="360"
    frameborder="0"
    allow="autoplay; fullscreen; picture-in-picture"
    allowfullscreen>
  </iframe>
</p>
<p>Key trade-offs to remember:</p>
<ul>
  <li><strong>Arrays</strong> — O(1) random access, O(n) insertion/deletion in the middle,
      contiguous memory allocation.</li>
  <li><strong>Linked Lists</strong> — O(1) head insertion, O(n) access by index,
      non-contiguous memory with pointer overhead.</li>
</ul>
<p>Choose arrays when you need fast indexed reads. Choose linked lists when you need
frequent insertions at the front and rarely access by index.</p>
"""

SAMPLE_MIXED = """
<h2>Deep Learning: Theory and Practice</h2>
<p>This week we explore the mathematical foundations of deep learning and see
how modern frameworks implement these ideas efficiently.</p>
<h3>Part 1 — The intuition (YouTube)</h3>
<p>
  <iframe
    width="560" height="315"
    src="https://www.youtube.com/embed/aircAruvnKk"
    title="Neural Networks Intro"
    frameborder="0" allowfullscreen>
  </iframe>
</p>
<h3>Part 2 — A worked example (Vimeo)</h3>
<p>
  <iframe
    src="https://player.vimeo.com/video/76979871"
    width="640" height="360"
    frameborder="0" allowfullscreen>
  </iframe>
</p>
<p>Complete both videos before attempting the quiz below. Focus on gradient descent
and how backpropagation flows errors backwards through each layer.</p>
"""


# ── API helpers ─────────────────────────────────────────────────────────────

def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def ingest_page(
    api_key: str,
    page_url: str,
    html_content: str,
    cmid: int,
    course_id: int,
    tasks: list[str],
    title: str,
    language: str,
    vimeo_token: str | None,
) -> dict:
    """Submit a Moodle page HTML body for processing."""
    metadata: dict = {"html_content": html_content}
    if vimeo_token:
        metadata["vimeo_token"] = vimeo_token

    payload = {
        "source_url": page_url,
        "content_type": "page",
        "moodle_course_id": course_id,
        "moodle_cmid": cmid,
        "title": title,
        "options": {
            "tasks": tasks,
            "language": language,
        },
        "metadata": metadata,
    }

    print(f"\n[1/4] Submitting Moodle page for processing...")
    print(f"      URL   : {page_url}")
    print(f"      Title : {title}")
    print(f"      HTML  : {len(html_content):,} chars")
    print(f"      Tasks : {', '.join(tasks)}")
    if vimeo_token:
        print(f"      Vimeo token: {vimeo_token[:8]}... (truncated)")

    r = httpx.post(
        f"{BASE_URL}/ingest",
        headers=_headers(api_key),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def poll_job(api_key: str, job_id: str) -> dict:
    """Poll job status until completed or failed."""
    print(f"\n[2/4] Polling job {job_id} ...")
    started = time.time()
    last_progress = -1

    while True:
        elapsed = time.time() - started
        if elapsed > MAX_WAIT:
            print(f"\n✗ Timed out after {MAX_WAIT}s waiting for job {job_id}")
            sys.exit(1)

        r = httpx.get(
            f"{BASE_URL}/jobs/{job_id}",
            headers=_headers(api_key),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        status = data.get("status", "unknown")
        progress = data.get("progress", 0)
        message = data.get("progress_message", "")

        if progress != last_progress:
            print(f"      [{elapsed:5.0f}s] {progress:3d}% — {message}")
            last_progress = progress

        if status == "completed":
            print(f"\n✓ Job completed in {elapsed:.1f}s")
            return data
        elif status == "failed":
            error = data.get("error_message", "unknown error")
            print(f"\n✗ Job failed: {error}")
            if data.get("error_traceback"):
                print("\nTraceback:")
                print(data["error_traceback"][-2000:])
            sys.exit(1)

        time.sleep(POLL_INTERVAL)


def fetch_outputs(api_key: str, content_item_id: str, verbose: bool) -> None:
    """Fetch and display all generated AI outputs."""
    print(f"\n[3/4] Fetching outputs for content_item {content_item_id} ...")

    r = httpx.get(
        f"{BASE_URL}/content/{content_item_id}/outputs",
        headers=_headers(api_key),
        timeout=10,
    )
    r.raise_for_status()
    outputs = r.json()

    print(f"      Found {len(outputs)} output(s):")
    for out in outputs:
        out_type = out.get("output_type", "?")
        out_status = out.get("status", "?")
        model = out.get("model", "?")
        print(f"      ✓ {out_type:12s}  status={out_status}  model={model}")

        if verbose:
            payload = out.get("payload", {})
            print(f"\n{'─'*60}")
            print(f"OUTPUT TYPE: {out_type.upper()}")
            print(f"{'─'*60}")
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])
            print()


def show_extraction_info(api_key: str, content_item_id: str) -> None:
    """Show item status and extraction metadata (videos found, words extracted, etc.)."""
    print(f"\n[4/4] Extraction info ...")
    r = httpx.get(
        f"{BASE_URL}/content/{content_item_id}",
        headers=_headers(api_key),
        timeout=10,
    )
    if r.status_code == 404:
        print("      (no /content/{id} detail endpoint yet — skipping)")
        return
    if r.status_code == 200:
        data = r.json()
        print(f"      status      : {data.get('status')}")
        print(f"      word_count  : {data.get('word_count')}")
        print(f"      chunk_count : {data.get('chunk_count')}")


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test the Axis AI Moodle Page content pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--key", required=True, help="Axis AI API key (axai_...)")

    # HTML content selection — mutually exclusive flags
    content_group = parser.add_argument_group("HTML content (choose one, or combine --with-youtube and --with-vimeo)")
    content_group.add_argument(
        "--with-youtube",
        action="store_true",
        help="Include a sample embedded YouTube video in the page",
    )
    content_group.add_argument(
        "--with-vimeo",
        action="store_true",
        help="Include a sample embedded Vimeo video in the page",
    )
    content_group.add_argument(
        "--html",
        default=None,
        help="Custom raw HTML string to use as page body",
    )

    parser.add_argument(
        "--page-url",
        default="https://moodle.example.com/mod/page/view.php?id=1001",
        help="Moodle page URL (stored as reference metadata; content is NOT fetched from it)",
    )
    parser.add_argument(
        "--tasks",
        default="summary,flashcards",
        help="Comma-separated output types to generate (default: summary,flashcards)",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Content language code (default: en)",
    )
    parser.add_argument(
        "--cmid",
        type=int,
        default=8001,
        help="Moodle course module ID (default: 8001)",
    )
    parser.add_argument(
        "--course-id",
        type=int,
        default=801,
        help="Moodle course ID (default: 801)",
    )
    parser.add_argument(
        "--vimeo-token",
        default=None,
        help="Vimeo access token (for private videos embedded in the page)",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Skip ingest and poll an existing job ID",
    )
    parser.add_argument(
        "--content-item-id",
        default=None,
        help="Skip ingest+poll and fetch outputs for this content item ID",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full output payloads",
    )

    args = parser.parse_args()
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]

    # ── Choose HTML content ────────────────────────────────────────────────
    if args.html:
        html_content = args.html
        title = "Custom Page Content"
    elif args.with_youtube and args.with_vimeo:
        html_content = SAMPLE_MIXED
        title = "Deep Learning: Theory and Practice (YouTube + Vimeo)"
    elif args.with_youtube:
        html_content = SAMPLE_WITH_YOUTUBE
        title = "Understanding Neural Networks (with YouTube)"
    elif args.with_vimeo:
        html_content = SAMPLE_WITH_VIMEO
        title = "Data Structures (with Vimeo)"
    else:
        html_content = SAMPLE_TEXT_ONLY
        title = "Introduction to Machine Learning"

    content_item_id = args.content_item_id
    job_id = args.job_id

    # ── Submit ─────────────────────────────────────────────────────────────
    if content_item_id:
        print(f"  Skipping ingest — using content_item_id={content_item_id}")
    elif job_id:
        print(f"  Skipping ingest — using job_id={job_id}")
    else:
        result = ingest_page(
            api_key=args.key,
            page_url=args.page_url,
            html_content=html_content,
            cmid=args.cmid,
            course_id=args.course_id,
            tasks=tasks,
            title=title,
            language=args.language,
            vimeo_token=args.vimeo_token,
        )
        print(f"      content_item_id : {result['content_item_id']}")
        print(f"      job_id          : {result['job_id']}")
        print(f"      status          : {result['status']}")

        if result["status"] == "ready":
            print("\n  Content already processed. Fetching existing outputs...")
            content_item_id = result["content_item_id"]
        elif result["job_id"]:
            job_id = result["job_id"]
            content_item_id = result["content_item_id"]
        else:
            print(f"\n  {result['message']}")
            sys.exit(0)

    # ── Poll ───────────────────────────────────────────────────────────────
    if job_id and not content_item_id:
        r = httpx.get(
            f"{BASE_URL}/jobs/{job_id}",
            headers={"Authorization": f"Bearer {args.key}"},
            timeout=10,
        )
        r.raise_for_status()
        content_item_id = r.json().get("content_item_id")

    if job_id:
        poll_job(api_key=args.key, job_id=job_id)

    # ── Results ────────────────────────────────────────────────────────────
    if content_item_id:
        fetch_outputs(api_key=args.key, content_item_id=content_item_id, verbose=args.verbose)
        show_extraction_info(api_key=args.key, content_item_id=content_item_id)

    print("\n✓ Done.\n")


if __name__ == "__main__":
    main()
