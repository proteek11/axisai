#!/usr/bin/env python3
"""
Phase 2c — Pool-based outputs + Teacher Management API test.

Tests all new endpoints added in Phase 2c:
  - GET  /content/{id}/summary          → SummaryResponse (with edit provenance)
  - PUT  /content/{id}/summary          → teacher edit summary
  - GET  /content/{id}/flashcards       → FlashcardPoolResponse (pool stats + items)
  - POST /content/{id}/flashcards       → manually add a card
  - PUT  /content/{id}/flashcards/{fid} → edit a card
  - DEL  /content/{id}/flashcards/{fid} → delete a card
  - POST /content/{id}/flashcards/regenerate → grow the pool
  - GET  /content/{id}/quiz-questions       → QuizPoolResponse
  - POST /content/{id}/quiz-questions       → manually add a question
  - POST /content/{id}/quiz-questions/regenerate
  - GET  /content/{id}/glossary         → GlossaryPoolResponse
  - POST /content/{id}/glossary/terms   → manually add a term
  - PUT  /content/{id}/glossary/terms/{tid}
  - DEL  /content/{id}/glossary/terms/{tid}

Usage:
    # Run migration first:
    docker compose exec api alembic upgrade head

    # Option A — fresh ingest (will ingest PDF, wait for pipeline, then test):
    python scripts/test_phase2c.py --key axai_YOUR_KEY

    # Option B — use existing content_item from a previous test run:
    python scripts/test_phase2c.py --key axai_YOUR_KEY --content-id <uuid>

    # Verbose (show full JSON responses):
    python scripts/test_phase2c.py --key axai_YOUR_KEY --verbose
"""
import argparse
import json
import random
import sys
import time
from typing import Any

import httpx

DEFAULT_API_BASE = "http://localhost:8000"
DEFAULT_PDF_URL = "https://grow.lmsatwork.com/coursesample/brazil.pdf"
POLL_INTERVAL = 3
MAX_WAIT = 300

MOODLE_USER_ID = 42   # Simulated teacher user ID


# ── Print helpers ─────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{'─' * 65}")
    print(f"  {title}")
    print(f"{'─' * 65}")


def ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def err(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)


def info(msg: str) -> None:
    print(f"  ·  {msg}")


def dump(data: Any, verbose: bool, max_items: int = 3) -> None:
    if verbose:
        print(json.dumps(data, indent=2, default=str))
    elif isinstance(data, dict):
        for k, v in list(data.items())[:4]:
            v_str = str(v)
            if len(v_str) > 120:
                v_str = v_str[:120] + "…"
            print(f"     {k}: {v_str}")


# ── Ingest + poll (reused from test_pdf.py) ───────────────────────────────────

def ingest_and_wait(
    client: httpx.Client,
    pdf_url: str,
    verbose: bool,
) -> str | None:
    """Ingest PDF with all pool-based tasks and wait for completion. Returns content_item_id."""
    section("Step 0: Ingest PDF (flashcards + quiz + glossary + summary)")
    info(f"URL: {pdf_url}")

    # Use a random cmid so each fresh test run creates a new content item
    # (avoids reusing stuck/failed items from previous runs)
    test_cmid = random.randint(90000, 99999)
    info(f"Using test cmid: {test_cmid}")

    r = client.post("/api/v1/ingest", json={
        "source_url": pdf_url,
        "content_type": "pdf",
        "moodle_course_id": 1,
        "moodle_cmid": test_cmid,
        "moodle_user_id": MOODLE_USER_ID,
        "title": "Phase 2c Test Document",
        "options": {
            "tasks": ["summary", "flashcards", "quiz", "glossary"],
            "language": "en",
            "count": 5,   # Generate 5 items (small for fast testing)
        },
    })

    if r.status_code not in (200, 202):
        err(f"Ingest failed: {r.status_code} {r.text}")
        return None

    data = r.json()
    info(f"Ingest response: {data}")   # debug
    content_item_id = data["content_item_id"]
    job_id = data.get("job_id") or data.get("task_id") or data.get("id") or ""
    ok(f"content_item_id = {content_item_id}")
    ok(f"job_id          = {job_id}")

    if data.get("status") == "ready" or not job_id:
        ok("Content already ready — skipping poll")
        return content_item_id

    # Poll
    info("Polling for completion…")
    start = time.time()
    last_pct = -1
    while True:
        elapsed = time.time() - start
        if elapsed > MAX_WAIT:
            err(f"Timed out after {MAX_WAIT}s")
            return None

        r = client.get(f"/api/v1/jobs/{job_id}")
        data = r.json()
        status = data.get("status") or "unknown"
        pct = data.get("progress") or 0
        msg = data.get("progress_message") or data.get("message") or ""

        if pct != last_pct:
            print(f"     [{elapsed:5.0f}s] {int(pct):3d}%  {status:<12}  {msg}")
            last_pct = pct

        if status == "completed":
            ok(f"Pipeline completed in {elapsed:.1f}s")
            return content_item_id
        if status == "failed":
            err(f"Pipeline FAILED: {data.get('error_message')}")
            return None

        time.sleep(POLL_INTERVAL)


# ── Test: Summary ─────────────────────────────────────────────────────────────

def test_summary(client: httpx.Client, cid: str, verbose: bool) -> bool:
    section("TEST: Summary GET + Teacher Edit")
    failures = 0

    # 1. GET summary
    r = client.get(f"/api/v1/content/{cid}/summary")
    if r.status_code == 200:
        data = r.json()
        ok(f"GET summary → 200  (is_teacher_edited={data.get('is_teacher_edited')})")
        original_summary = data.get("payload", {}).get("summary", "")
        info(f"Summary preview: {str(original_summary)[:120]}…")
        if verbose:
            dump(data, verbose)
    else:
        err(f"GET summary → {r.status_code}: {r.text[:200]}")
        failures += 1
        return False

    # 2. PUT summary (teacher edit)
    edited_text = "This is the teacher-edited summary. It has been manually improved."
    r = client.put(f"/api/v1/content/{cid}/summary", json={
        "summary": edited_text,
        "key_points": ["Point 1 — manually added", "Point 2 — manually added"],
        "moodle_user_id": MOODLE_USER_ID,
    })
    if r.status_code == 200:
        data = r.json()
        ok(f"PUT summary → 200  (is_teacher_edited={data.get('is_teacher_edited')}, edited_by={data.get('last_edited_by')})")
        returned_text = data.get("payload", {}).get("summary", "")
        if returned_text == edited_text:
            ok("Edited text matches what was sent ✓")
        else:
            err(f"Edit mismatch: got '{returned_text[:60]}'")
            failures += 1
    else:
        err(f"PUT summary → {r.status_code}: {r.text[:200]}")
        failures += 1

    # 3. GET again — should return edited version
    r = client.get(f"/api/v1/content/{cid}/summary")
    if r.status_code == 200:
        data = r.json()
        if data.get("is_teacher_edited") and data["payload"].get("summary") == edited_text:
            ok("GET after edit → returns teacher-edited version ✓")
        else:
            err(f"GET after edit — unexpected payload: {data.get('payload', {}).get('summary', '')[:60]}")
            failures += 1
    else:
        err(f"GET summary after edit → {r.status_code}")
        failures += 1

    return failures == 0


# ── Test: Flashcard pool ───────────────────────────────────────────────────────

def test_flashcards(client: httpx.Client, cid: str, verbose: bool) -> bool:
    section("TEST: Flashcard Pool (GET / Add / Edit / Delete / Regenerate)")
    failures = 0

    # 1. GET pool
    r = client.get(f"/api/v1/content/{cid}/flashcards")
    if r.status_code == 200:
        data = r.json()
        pool = data.get("pool", {})
        items = data.get("items", [])
        ok(f"GET flashcards → {len(items)} items  (total={pool.get('total')}, max={pool.get('pool_max')})")
        info(f"Source breakdown: {pool.get('source_breakdown')}")
        if verbose:
            dump(data, verbose)
        if not items:
            info("No flashcards yet — pipeline may not have run flashcards task")
    else:
        err(f"GET flashcards → {r.status_code}: {r.text[:200]}")
        failures += 1

    # 2. Manually add a card
    r = client.post(f"/api/v1/content/{cid}/flashcards", json={
        "front": "What is the purpose of this test?",
        "back": "To verify the teacher management API works correctly.",
        "hint": "Think about QA",
        "card_type": "application",
        "difficulty": "easy",
        "topic": "Testing",
        "moodle_user_id": MOODLE_USER_ID,
    })
    if r.status_code == 201:
        card = r.json()
        card_id = card["id"]
        ok(f"POST flashcard → 201  id={card_id}  source={card.get('source')}")
        if card.get("source") != "manual":
            err("Expected source='manual' for manually added card")
            failures += 1
    else:
        err(f"POST flashcard → {r.status_code}: {r.text[:200]}")
        failures += 1
        card_id = None

    if card_id:
        # 3. Edit the card
        r = client.put(f"/api/v1/content/{cid}/flashcards/{card_id}", json={
            "front": "What is the PURPOSE of this test? (edited)",
            "difficulty": "medium",
            "moodle_user_id": MOODLE_USER_ID,
        })
        if r.status_code == 200:
            card = r.json()
            ok(f"PUT flashcard → 200  front='{card.get('front')[:50]}'")
        else:
            err(f"PUT flashcard → {r.status_code}: {r.text[:200]}")
            failures += 1

        # 4. Deactivate (toggle is_active)
        r = client.put(f"/api/v1/content/{cid}/flashcards/{card_id}", json={
            "is_active": False,
            "moodle_user_id": MOODLE_USER_ID,
        })
        if r.status_code == 200:
            ok(f"PUT flashcard is_active=False → 200")
        else:
            err(f"PUT flashcard deactivate → {r.status_code}: {r.text[:200]}")
            failures += 1

        # 5. Delete the card
        r = client.delete(f"/api/v1/content/{cid}/flashcards/{card_id}")
        if r.status_code == 204:
            ok("DELETE flashcard → 204 ✓")
        else:
            err(f"DELETE flashcard → {r.status_code}: {r.text[:200]}")
            failures += 1

    # 6. Regenerate (add 3 more cards to pool)
    info("Testing regenerate (adding 3 more cards)…")
    r = client.post(f"/api/v1/content/{cid}/flashcards/regenerate?count=3")
    if r.status_code == 200:
        result = r.json()
        ok(
            f"POST regenerate → 200  "
            f"added={result.get('added')}  "
            f"skipped_dedup={result.get('skipped_dedup')}  "
            f"pool_total={result.get('pool_total')}  "
            f"batch={result.get('generation_batch')}"
        )
    else:
        err(f"POST regenerate → {r.status_code}: {r.text[:200]}")
        failures += 1

    # 7. GET pool again to verify count changed
    r = client.get(f"/api/v1/content/{cid}/flashcards")
    if r.status_code == 200:
        data = r.json()
        pool = data.get("pool", {})
        ok(f"GET flashcards after regen → {pool.get('total')} total  batches={pool.get('batch_count')}")
    else:
        err(f"GET flashcards after regen → {r.status_code}")
        failures += 1

    return failures == 0


# ── Test: Quiz question pool ───────────────────────────────────────────────────

def test_quiz_questions(client: httpx.Client, cid: str, verbose: bool) -> bool:
    section("TEST: Quiz Question Pool (GET / Add / Edit / Delete / Regenerate)")
    failures = 0

    # 1. GET pool
    r = client.get(f"/api/v1/content/{cid}/quiz-questions")
    if r.status_code == 200:
        data = r.json()
        pool = data.get("pool", {})
        items = data.get("items", [])
        ok(f"GET quiz-questions → {len(items)} items  (total={pool.get('total')}, max={pool.get('pool_max')})")
        if verbose:
            dump(items[:2] if items else [], verbose)
    else:
        err(f"GET quiz-questions → {r.status_code}: {r.text[:200]}")
        failures += 1

    # 2. Filter by blooms level
    r = client.get(f"/api/v1/content/{cid}/quiz-questions?blooms_level=remember")
    if r.status_code == 200:
        items = r.json().get("items", [])
        ok(f"GET quiz-questions?blooms_level=remember → {len(items)} items")
    else:
        err(f"GET quiz-questions filtered → {r.status_code}")
        failures += 1

    # 3. Manually add a question
    r = client.post(f"/api/v1/content/{cid}/quiz-questions", json={
        "question_type": "multichoice",
        "question_text": "Which of the following best describes the main purpose of this document?",
        "options": [
            {"text": "To test the API", "is_correct": True, "feedback": "Correct!"},
            {"text": "To train models", "is_correct": False, "feedback": "Incorrect"},
            {"text": "To generate PDFs", "is_correct": False, "feedback": "Incorrect"},
            {"text": "To manage tenants", "is_correct": False, "feedback": "Incorrect"},
        ],
        "correct_answer": None,
        "explanation": "This is a manually added test question.",
        "blooms_level": "understand",
        "difficulty": "easy",
        "topic_primary": "Testing",
        "moodle_user_id": MOODLE_USER_ID,
    })
    if r.status_code == 201:
        q = r.json()
        q_id = q["id"]
        ok(f"POST quiz-question → 201  id={q_id}  source={q.get('source')}")
    else:
        err(f"POST quiz-question → {r.status_code}: {r.text[:200]}")
        failures += 1
        q_id = None

    if q_id:
        # 4. Edit it
        r = client.put(f"/api/v1/content/{cid}/quiz-questions/{q_id}", json={
            "explanation": "Updated explanation — this question was manually edited.",
            "blooms_level": "apply",
            "moodle_user_id": MOODLE_USER_ID,
        })
        if r.status_code == 200:
            q = r.json()
            ok(f"PUT quiz-question → 200  blooms={q.get('blooms_level')}")
        else:
            err(f"PUT quiz-question → {r.status_code}: {r.text[:200]}")
            failures += 1

        # 5. Delete it
        r = client.delete(f"/api/v1/content/{cid}/quiz-questions/{q_id}")
        if r.status_code == 204:
            ok("DELETE quiz-question → 204 ✓")
        else:
            err(f"DELETE quiz-question → {r.status_code}: {r.text[:200]}")
            failures += 1

    # 6. Regenerate
    info("Testing quiz regenerate (adding 3 more questions)…")
    r = client.post(f"/api/v1/content/{cid}/quiz-questions/regenerate?count=3")
    if r.status_code == 200:
        result = r.json()
        ok(
            f"POST quiz regenerate → 200  "
            f"added={result.get('added')}  "
            f"skipped_dedup={result.get('skipped_dedup')}  "
            f"pool_total={result.get('pool_total')}  "
            f"batch={result.get('generation_batch')}"
        )
    else:
        err(f"POST quiz regenerate → {r.status_code}: {r.text[:200]}")
        failures += 1

    return failures == 0


# ── Test: Glossary pool ────────────────────────────────────────────────────────

def test_glossary(client: httpx.Client, cid: str, verbose: bool) -> bool:
    section("TEST: Glossary Pool (GET / Add / Edit / Delete)")
    failures = 0

    # 1. GET pool
    r = client.get(f"/api/v1/content/{cid}/glossary")
    if r.status_code == 200:
        data = r.json()
        pool = data.get("pool", {})
        items = data.get("items", [])
        ok(f"GET glossary → {len(items)} terms  (total={pool.get('total')}, max={pool.get('pool_max')})")
        if verbose:
            dump(items[:2] if items else [], verbose)
    else:
        err(f"GET glossary → {r.status_code}: {r.text[:200]}")
        failures += 1

    # 2. Add a manual term
    r = client.post(f"/api/v1/content/{cid}/glossary/terms", json={
        "term": "API (Application Programming Interface)",
        "definition": "A set of rules and protocols for building and interacting with software applications.",
        "context": "The API allows Moodle to communicate with the axis-ai service.",
        "related_terms": ["REST", "HTTP", "endpoint"],
        "category": "concept",
        "moodle_user_id": MOODLE_USER_ID,
    })
    if r.status_code == 201:
        term = r.json()
        term_id = term["id"]
        ok(f"POST glossary term → 201  id={term_id}  term='{term.get('term')}'  source={term.get('source')}")
    else:
        err(f"POST glossary term → {r.status_code}: {r.text[:200]}")
        failures += 1
        term_id = None

    if term_id:
        # 3. Edit it
        r = client.put(f"/api/v1/content/{cid}/glossary/terms/{term_id}", json={
            "definition": "Updated definition — a contract between software components.",
            "category": "tool",
            "moodle_user_id": MOODLE_USER_ID,
        })
        if r.status_code == 200:
            term = r.json()
            ok(f"PUT glossary term → 200  definition='{term.get('definition')[:50]}'")
        else:
            err(f"PUT glossary term → {r.status_code}: {r.text[:200]}")
            failures += 1

        # 4. Delete it
        r = client.delete(f"/api/v1/content/{cid}/glossary/terms/{term_id}")
        if r.status_code == 204:
            ok("DELETE glossary term → 204 ✓")
        else:
            err(f"DELETE glossary term → {r.status_code}: {r.text[:200]}")
            failures += 1

    # 5. GET with include_inactive
    r = client.get(f"/api/v1/content/{cid}/glossary?include_inactive=true")
    if r.status_code == 200:
        data = r.json()
        ok(f"GET glossary?include_inactive=true → {len(data.get('items', []))} terms")
    else:
        err(f"GET glossary include_inactive → {r.status_code}")
        failures += 1

    return failures == 0


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2c teacher management API test")
    parser.add_argument("--key", required=True, help="API key (axai_...)")
    parser.add_argument("--content-id", default=None,
                        help="Skip ingest and use this existing content_item_id UUID")
    parser.add_argument("--url", default=DEFAULT_PDF_URL, help="PDF URL for fresh ingest")
    parser.add_argument("--base", default=DEFAULT_API_BASE, help="API base URL")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show full JSON responses")
    parser.add_argument("--test", default="all",
                        help="Comma-separated tests to run: summary,flashcards,quiz,glossary (default: all)")
    args = parser.parse_args()

    tests_to_run = (
        {"summary", "flashcards", "quiz", "glossary"}
        if args.test == "all"
        else {t.strip() for t in args.test.split(",")}
    )

    headers = {"Authorization": f"Bearer {args.key}"}

    print()
    print("=" * 65)
    print("  axis-ai  —  Phase 2c Teacher Management API Test")
    print("=" * 65)
    print(f"  API base : {args.base}")
    print(f"  Tests    : {', '.join(sorted(tests_to_run))}")
    if args.content_id:
        print(f"  Content  : {args.content_id}  (skipping ingest)")
    print()

    with httpx.Client(base_url=args.base, headers=headers, timeout=60) as client:

        # Health check
        r = client.get("/api/v1/health")
        if r.status_code != 200:
            err(f"API not healthy: {r.status_code}")
            sys.exit(1)
        ok(f"API healthy")

        # Get or create content_item
        if args.content_id:
            cid = args.content_id
            info(f"Using existing content_item_id: {cid}")
        else:
            cid = ingest_and_wait(client, args.url, args.verbose)
            if not cid:
                err("Failed to get content item — aborting")
                sys.exit(1)

        print(f"\n  content_item_id = {cid}")

        # Run selected tests
        results = {}

        if "summary" in tests_to_run:
            results["summary"] = test_summary(client, cid, args.verbose)

        if "flashcards" in tests_to_run:
            results["flashcards"] = test_flashcards(client, cid, args.verbose)

        if "quiz" in tests_to_run:
            results["quiz"] = test_quiz_questions(client, cid, args.verbose)

        if "glossary" in tests_to_run:
            results["glossary"] = test_glossary(client, cid, args.verbose)

    # Summary
    print()
    print("=" * 65)
    print("  RESULTS")
    print("=" * 65)
    all_passed = True
    for test_name, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {test_name}")
        if not passed:
            all_passed = False
    print()

    if all_passed:
        print("  All tests passed ✓")
    else:
        print("  Some tests failed — check output above", file=sys.stderr)
        sys.exit(1)

    print("=" * 65)
    print()


if __name__ == "__main__":
    main()
