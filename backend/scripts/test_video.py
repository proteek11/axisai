#!/usr/bin/env python3
"""
test_video.py — End-to-end test for the YouTube, Vimeo, and PeerTube video pipeline.

Usage:
    # YouTube (public video with captions):
    python scripts/test_video.py --key axai_YOUR_KEY --url "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    # YouTube with chapters:
    python scripts/test_video.py --key axai_YOUR_KEY \\
        --url "https://youtu.be/dQw4w9WgXcQ" \\
        --tasks summary,flashcards,chapters

    # Vimeo (public video, no token):
    python scripts/test_video.py --key axai_YOUR_KEY \\
        --url "https://vimeo.com/76979871"

    # Vimeo with token (private/unlisted video + native chapter support):
    python scripts/test_video.py --key axai_YOUR_KEY \\
        --url "https://vimeo.com/76979871" \\
        --vimeo-token YOUR_VIMEO_TOKEN \\
        --tasks summary,chapters

    # PeerTube (public video):
    python scripts/test_video.py --key axai_YOUR_KEY \\
        --url "https://peertube.example.com/w/abc123" \\
        --tasks summary,chapters

    # PeerTube (private video with token):
    python scripts/test_video.py --key axai_YOUR_KEY \\
        --url "https://peertube.example.com/w/abc123" \\
        --peertube-token YOUR_OAUTH_TOKEN \\
        --tasks summary,chapters

    # Poll only (if you already have a job_id):
    python scripts/test_video.py --key axai_YOUR_KEY --job-id <UUID>

    # Verbose output (print full payload):
    python scripts/test_video.py --key axai_YOUR_KEY --url "..." --verbose

Available tasks:
    summary, flashcards, glossary, quiz, mindmap, objectives, blooms, chapters, faq, infographic
"""
import argparse
import json
import sys
import time
from typing import Any

import httpx

BASE_URL = "http://localhost:8000/api/v1"
POLL_INTERVAL = 3   # seconds between status checks
MAX_WAIT = 600      # max seconds to wait for pipeline (video can be slow)


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}


def ingest_video(
    api_key: str,
    url: str,
    content_type: str,
    cmid: int,
    course_id: int,
    tasks: list[str],
    vimeo_token: str | None,
    peertube_token: str | None,
    language: str,
) -> dict:
    """Submit a video URL for processing."""
    metadata: dict[str, Any] = {}
    if vimeo_token:
        metadata["vimeo_token"] = vimeo_token
    if peertube_token:
        metadata["peertube_token"] = peertube_token

    payload = {
        "source_url": url,
        "content_type": content_type,
        "moodle_course_id": course_id,
        "moodle_cmid": cmid,
        "title": f"Test video ({content_type})",
        "options": {
            "tasks": tasks,
            "language": language,
        },
        "metadata": metadata,
    }

    print(f"\n[1/7] Submitting {content_type} video for processing...")
    print(f"      URL: {url}")
    if vimeo_token:
        print(f"      Vimeo token: {vimeo_token[:8]}... (truncated)")
    if peertube_token:
        print(f"      PeerTube token: {peertube_token[:8]}... (truncated)")
    print(f"      Tasks: {', '.join(tasks)}")

    r = httpx.post(
        f"{BASE_URL}/ingest",
        headers=_headers(api_key),
        json=payload,
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def poll_job(api_key: str, job_id: str) -> dict:
    """Poll until job completes or fails."""
    print(f"\n[2/7] Polling job {job_id} ...")
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
    """Fetch and display all generated outputs."""
    print(f"\n[3/7] Fetching outputs for content_item {content_item_id} ...")

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
        status = out.get("status", "?")
        model = out.get("model", "?")
        print(f"      ✓ {out_type:18s}  status={status}  model={model}")

        if verbose and out_type != "chapters":  # chapters has its own pretty printer
            payload = out.get("payload", {})
            print(f"\n{'─'*60}")
            print(f"OUTPUT TYPE: {out_type.upper()}")
            print(f"{'─'*60}")
            print(json.dumps(payload, indent=2, ensure_ascii=False)[:3000])
            print()


def fetch_chapters(
    api_key: str,
    content_item_id: str,
    language: str,
    verbose: bool,
) -> None:
    """
    Fetch and display video chapters.

    Shows a formatted seek table — each row shows the timestamp, title, and
    optional summary so you can verify the chapters make sense at a glance.
    """
    print(f"\n[4/7] Fetching chapters for content_item {content_item_id} ...")

    r = httpx.get(
        f"{BASE_URL}/content/{content_item_id}/chapters",
        headers=_headers(api_key),
        params={"language": language},
        timeout=15,
    )

    if r.status_code == 404:
        print("      (no chapters found — was 'chapters' included in --tasks?)")
        return

    r.raise_for_status()
    data = r.json()

    chapters = data.get("chapters", [])
    chapter_count = data.get("chapter_count", 0)
    total_duration = data.get("total_duration_sec", 0.0)
    chapters_source = data.get("chapters_source", "unknown")
    model = data.get("model") or "—"

    source_badge = {
        "platform_api": "📺 native (platform API)",
        "ai_generated": "🤖 AI-generated",
        "none":         "⚠️  none",
    }.get(chapters_source, chapters_source)

    print(f"      Chapters : {chapter_count}")
    print(f"      Duration : {_fmt_duration(total_duration)}")
    print(f"      Source   : {source_badge}")
    if chapters_source == "ai_generated":
        print(f"      Model    : {model}")

    if not chapters:
        note = data.get("note", "")
        if note:
            print(f"      Note     : {note}")
        return

    # ── Seek table ────────────────────────────────────────────────────────────
    print()
    print(f"      {'#':>3}  {'Timestamp':>9}  {'Duration':>9}  Title")
    print(f"      {'─'*3}  {'─'*9}  {'─'*9}  {'─'*40}")

    for i, ch in enumerate(chapters, start=1):
        start = ch.get("start_sec", 0.0)
        end = ch.get("end_sec", 0.0)
        duration = max(0.0, end - start)
        title = ch.get("title", "")
        # Truncate long titles for the table
        title_display = title[:48] + "…" if len(title) > 49 else title
        print(
            f"      {i:>3}  {_fmt_time(start):>9}  {_fmt_duration(duration):>9}  {title_display}"
        )

    if verbose:
        print(f"\n{'─'*60}")
        print("CHAPTERS FULL PAYLOAD")
        print(f"{'─'*60}")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print()


def fetch_faq(
    api_key: str,
    content_item_id: str,
    language: str,
    verbose: bool,
) -> None:
    """Fetch and display the FAQ list."""
    print(f"\n[5/7] Fetching FAQ for content_item {content_item_id} ...")

    r = httpx.get(
        f"{BASE_URL}/content/{content_item_id}/faq",
        headers=_headers(api_key),
        params={"language": language},
        timeout=15,
    )

    if r.status_code == 404:
        print("      (no FAQ found — was 'faq' included in --tasks?)")
        return

    r.raise_for_status()
    data = r.json()

    faqs = data.get("faqs", [])
    print(f"      FAQ count : {data.get('faq_count', 0)}")

    for i, faq in enumerate(faqs, start=1):
        diff = faq.get("difficulty", "?")
        topic = faq.get("topic", "")
        question = faq.get("question", "")
        answer = faq.get("answer", "")
        topic_str = f"  [{topic}]" if topic else ""
        print(f"\n      Q{i}{topic_str} ({diff}): {question}")
        if verbose:
            print(f"         A: {answer}")
        else:
            # Short preview of the answer
            preview = answer[:120] + "…" if len(answer) > 120 else answer
            print(f"         A: {preview}")


def fetch_infographic(
    api_key: str,
    content_item_id: str,
    language: str,
    verbose: bool,
) -> None:
    """Fetch and display infographic metadata, optionally save the HTML to disk."""
    print(f"\n[6/7] Fetching infographic for content_item {content_item_id} ...")

    r = httpx.get(
        f"{BASE_URL}/content/{content_item_id}/infographic",
        headers=_headers(api_key),
        params={"language": language},
        timeout=30,
    )

    if r.status_code == 404:
        print("      (no infographic found — was 'infographic' included in --tasks?)")
        return

    r.raise_for_status()
    data = r.json()

    title = data.get("title", "—")
    sections = data.get("sections", [])
    html_chars = data.get("html_char_count", 0)
    palette = data.get("colour_palette", {})
    model = data.get("model") or "—"

    print(f"      Title    : {title}")
    print(f"      Sections : {', '.join(sections) if sections else '—'}")
    print(f"      HTML size: {html_chars:,} chars")
    print(f"      Palette  : primary={palette.get('primary','?')}  accent={palette.get('accent1','?')}")
    print(f"      Model    : {model}")

    # Save HTML to a local file for inspection
    html = data.get("html", "")
    if html:
        out_path = f"/tmp/infographic_{content_item_id[:8]}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n      ✓ HTML saved to: {out_path}  (open in browser to preview)")

    if verbose:
        print(f"\n{'─'*60}")
        print("INFOGRAPHIC HTML (first 1000 chars)")
        print(f"{'─'*60}")
        print(html[:1000])
        print("...")


def fetch_transcript(api_key: str, content_item_id: str, language: str, verbose: bool) -> None:
    """Fetch the stored transcript for the video."""
    print(f"\n[7/7] Fetching transcript for content_item {content_item_id} ...")

    r = httpx.get(
        f"{BASE_URL}/content/{content_item_id}/transcript",
        headers=_headers(api_key),
        params={"language": language},
        timeout=10,
    )

    if r.status_code == 404:
        detail = r.json().get("detail", "no transcript found")
        print(f"      (404) {detail}")
        return

    r.raise_for_status()
    data = r.json()

    print(f"      language      : {data.get('language')}")
    print(f"      source        : {data.get('source')}")
    print(f"      word_count    : {data.get('word_count')}")
    print(f"      segment_count : {data.get('segment_count')}")

    if verbose:
        segments = data.get("segments", [])
        print(f"\n      First 5 segments:")
        for seg in segments[:5]:
            start = seg.get("start_sec", 0)
            text = seg.get("text", "")[:80]
            print(f"        [{_fmt_time(start)}] {text}")


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _fmt_time(seconds: float) -> str:
    """Format seconds as MM:SS or H:MM:SS."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def _fmt_duration(seconds: float) -> str:
    """Human-readable duration, e.g. '1h 23m' or '4m 30s'."""
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    parts: list[str] = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if sec or not parts:
        parts.append(f"{sec}s")
    return " ".join(parts)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test the Axis AI video pipeline (YouTube / Vimeo / PeerTube)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--key", required=True, help="Axis AI API key (axai_...)")
    parser.add_argument("--url", help="Video URL to process")
    parser.add_argument(
        "--content-type",
        choices=["youtube", "vimeo", "peertube"],
        help="Force content type (auto-detected from URL if omitted)",
    )
    parser.add_argument(
        "--tasks",
        default="summary,flashcards,chapters,faq,infographic",
        help=(
            "Comma-separated list of output types to generate "
            "(default: summary,flashcards,chapters,faq,infographic). "
            "Available: summary,flashcards,glossary,quiz,mindmap,objectives,blooms,chapters,faq,infographic"
        ),
    )
    parser.add_argument(
        "--vimeo-token",
        default=None,
        help="Vimeo personal access token (for private/unlisted videos + native chapters API)",
    )
    parser.add_argument(
        "--peertube-token",
        default=None,
        help="PeerTube OAuth access token (for private/restricted videos)",
    )
    parser.add_argument(
        "--language",
        default="en",
        help="Preferred transcript / output language code (default: en)",
    )
    parser.add_argument(
        "--cmid",
        type=int,
        default=9001,
        help="Moodle course module ID (default: 9001)",
    )
    parser.add_argument(
        "--course-id",
        type=int,
        default=901,
        help="Moodle course ID (default: 901)",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        help="Skip ingest and poll an existing job ID",
    )
    parser.add_argument(
        "--content-item-id",
        default=None,
        help="Skip ingest+poll and just fetch outputs for this content item ID",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Print full output payloads",
    )

    args = parser.parse_args()
    tasks = [t.strip() for t in args.tasks.split(",") if t.strip()]

    # ── Determine content type from URL if not forced ──────────────────────
    content_type = args.content_type
    if not content_type and args.url:
        if "youtube.com" in args.url or "youtu.be" in args.url:
            content_type = "youtube"
        elif "vimeo.com" in args.url:
            content_type = "vimeo"
        elif args.url.startswith("http"):
            # Best-effort PeerTube detection (watch/w path pattern)
            if "/videos/watch/" in args.url or "/w/" in args.url:
                content_type = "peertube"
            else:
                print(f"✗ Cannot determine content type from URL: {args.url}")
                print("  Use --content-type youtube|vimeo|peertube to force it.")
                sys.exit(1)
        else:
            print(f"✗ Cannot determine content type from URL: {args.url}")
            sys.exit(1)

    content_item_id = args.content_item_id
    job_id = args.job_id

    # ── Submit (unless we already have IDs) ───────────────────────────────
    if content_item_id:
        print(f"  Skipping ingest — using content_item_id={content_item_id}")
    elif job_id:
        print(f"  Skipping ingest — using job_id={job_id}")
    else:
        if not args.url:
            print("✗ --url is required unless --job-id or --content-item-id is provided")
            sys.exit(1)

        result = ingest_video(
            api_key=args.key,
            url=args.url,
            content_type=content_type,
            cmid=args.cmid,
            course_id=args.course_id,
            tasks=tasks,
            vimeo_token=args.vimeo_token,
            peertube_token=args.peertube_token,
            language=args.language,
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

    # ── Poll ──────────────────────────────────────────────────────────────
    if job_id and not content_item_id:
        r = httpx.get(
            f"{BASE_URL}/jobs/{job_id}",
            headers=_headers(args.key),
            timeout=10,
        )
        r.raise_for_status()
        content_item_id = r.json().get("content_item_id")

    if job_id:
        poll_job(api_key=args.key, job_id=job_id)

    # ── Fetch outputs, chapters, faq, infographic, transcript ────────────────
    if content_item_id:
        fetch_outputs(
            api_key=args.key,
            content_item_id=content_item_id,
            verbose=args.verbose,
        )
        fetch_chapters(
            api_key=args.key,
            content_item_id=content_item_id,
            language=args.language,
            verbose=args.verbose,
        )
        fetch_faq(
            api_key=args.key,
            content_item_id=content_item_id,
            language=args.language,
            verbose=args.verbose,
        )
        fetch_infographic(
            api_key=args.key,
            content_item_id=content_item_id,
            language=args.language,
            verbose=args.verbose,
        )
        fetch_transcript(
            api_key=args.key,
            content_item_id=content_item_id,
            language=args.language,
            verbose=args.verbose,
        )

    print("\n✓ Done.\n")


if __name__ == "__main__":
    main()
