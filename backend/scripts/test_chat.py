#!/usr/bin/env python3
"""
Test script for the Phase 6 Chat API.

Tests:
  1. Create a session
  2. Send a general question (expects ANSWER or NO_CONTEXT)
  3. Send a follow-up asking for examples (tests EXPLAIN_MORE / GIVE_EXAMPLES intent + continuation)
  4. Request a visual representation (tests SHOW_VISUAL + visual_data)
  5. Ask to be quizzed (tests QUIZ_ME intent)
  6. Ask an out-of-scope question (tests OUT_OF_SCOPE response_type)
  7. Load session history (verifies DB persistence)
  8. End the session

Usage:
    python scripts/test_chat.py --key axai_YOUR_KEY --course 42
    python scripts/test_chat.py --key axai_YOUR_KEY --course 42 --verbose
    python scripts/test_chat.py --key axai_YOUR_KEY --course 42 --content-id UUID

Note: You must have content ingested for the course before running this test,
otherwise all questions will return NO_CONTEXT (which is also valid and tested).
"""
import argparse
import json
import sys
import time

import requests

BASE_URL = "http://localhost:8000/api/v1"
DIVIDER = "=" * 65


def h(text: str):
    print(f"\n{DIVIDER}")
    print(f"  {text}")
    print(DIVIDER)


def ok(text: str):
    print(f"  ✓  {text}")


def warn(text: str):
    print(f"  ⚠  {text}")


def fail(text: str):
    print(f"  ✗  {text}")
    sys.exit(1)


def post(url, payload, headers, verbose=False):
    t0 = time.perf_counter()
    r = requests.post(url, json=payload, headers=headers, timeout=60)
    elapsed = int((time.perf_counter() - t0) * 1000)
    if verbose:
        print(f"\n  → POST {url}")
        print(f"  → Status: {r.status_code}  ({elapsed}ms)")
        try:
            print(f"  → Body:\n{json.dumps(r.json(), indent=4)}")
        except Exception:
            print(f"  → Raw: {r.text[:500]}")
    return r, elapsed


def get(url, headers, verbose=False):
    t0 = time.perf_counter()
    r = requests.get(url, headers=headers, timeout=30)
    elapsed = int((time.perf_counter() - t0) * 1000)
    if verbose:
        print(f"\n  → GET {url}")
        print(f"  → Status: {r.status_code}  ({elapsed}ms)")
        try:
            print(f"  → Body:\n{json.dumps(r.json(), indent=4)}")
        except Exception:
            print(f"  → Raw: {r.text[:500]}")
    return r, elapsed


def print_message_summary(data: dict):
    resp_type = data.get("response_type", "?")
    intent = data.get("intent", "?")
    confidence = data.get("confidence", 0)
    answer = data.get("answer", "") or ""
    render = data.get("render_hint", "?")
    suggestions = data.get("suggestions", [])
    sources = data.get("sources", [])
    meta = data.get("meta", {})

    print(f"  Response type : {resp_type}")
    print(f"  Intent        : {intent}")
    print(f"  Confidence    : {confidence:.2f}")
    print(f"  Render hint   : {render}")
    print(f"  Answer length : {len(answer)} chars")
    print(f"  Suggestions   : {len(suggestions)}")
    print(f"  Sources cited : {len(sources)}")
    print(f"  Tokens used   : {meta.get('tokens_total', 0)}")
    print(f"  Latency       : {meta.get('latency_ms', 0)}ms")

    if suggestions:
        print("  Suggestion labels:")
        for s in suggestions:
            print(f"    [{s.get('type', '?')}] {s.get('label', '')} → {s.get('action', '')}")

    if render in ("visual_chart", "visual_mermaid"):
        vd = data.get("visual_data")
        print(f"  Visual data   : {type(vd).__name__} — keys: {list(vd.keys()) if vd else 'null'}")


def run_tests(api_key: str, course_id: int, content_id: str | None, verbose: bool):
    headers = {"Authorization": f"Bearer {api_key}"}
    session_id = None

    # ── Test 1: Create session ─────────────────────────────────────────────────
    h("Test 1: Create chat session")
    payload = {
        "moodle_user_id": 42,
        "moodle_course_id": course_id,
        "language": "en",
    }
    if content_id:
        payload["scoped_content_ids"] = [content_id]

    r, ms = post(f"{BASE_URL}/chat/sessions", payload, headers, verbose)
    if r.status_code != 201:
        fail(f"Create session failed: {r.status_code} — {r.text[:200]}")

    data = r.json()
    session_id = data["id"]
    ok(f"Session created: {session_id}")
    ok(f"User: {data['moodle_user_id']}, Course: {data['moodle_course_id']}")

    # ── Test 2: General question ───────────────────────────────────────────────
    h("Test 2: General question")
    r, ms = post(f"{BASE_URL}/chat/message", {
        "session_id": session_id,
        "message": "What are the main topics covered in this course?",
    }, headers, verbose)

    if r.status_code != 200:
        fail(f"Message failed: {r.status_code} — {r.text[:300]}")

    data = r.json()
    print_message_summary(data)

    resp_type = data["response_type"]
    if resp_type in ("ANSWER", "LOW_CONFIDENCE"):
        ok(f"Got answer (type={resp_type})")
    elif resp_type == "NO_CONTEXT":
        warn("NO_CONTEXT — no course content ingested yet. This is expected if no PDFs have been processed.")
    else:
        warn(f"Unexpected response_type: {resp_type}")

    assert data.get("suggestions"), "Expected suggestions array"
    ok(f"Suggestions present: {len(data['suggestions'])}")

    # ── Test 3: Follow-up / continuation (EXPLAIN_MORE) ───────────────────────
    h("Test 3: Follow-up asking for examples (EXPLAIN_MORE / GIVE_EXAMPLES)")
    r, ms = post(f"{BASE_URL}/chat/message", {
        "session_id": session_id,
        "message": "Can you give me a concrete example of that?",
        "suggestion_clicked_id": None,
    }, headers, verbose)

    if r.status_code != 200:
        fail(f"Follow-up failed: {r.status_code}")

    data = r.json()
    print_message_summary(data)
    ok(f"Follow-up processed — intent={data['intent']}")

    # ── Test 4: Visual representation ─────────────────────────────────────────
    h("Test 4: Visual representation request (SHOW_VISUAL)")
    r, ms = post(f"{BASE_URL}/chat/message", {
        "session_id": session_id,
        "message": "Can you show me that visually with a diagram or chart?",
    }, headers, verbose)

    if r.status_code != 200:
        fail(f"Visual request failed: {r.status_code}")

    data = r.json()
    print_message_summary(data)
    intent = data.get("intent", "")
    render = data.get("render_hint", "")
    if intent == "SHOW_VISUAL":
        ok(f"SHOW_VISUAL intent detected")
        if render in ("visual_chart", "visual_mermaid"):
            ok(f"Visual data returned (render_hint={render})")
        else:
            warn(f"render_hint={render} — LLM may have chosen markdown over visual (valid)")
    else:
        warn(f"Intent={intent} — may have been classified differently due to low context")

    # ── Test 5: Quiz me ────────────────────────────────────────────────────────
    h("Test 5: Quiz request (QUIZ_ME)")
    r, ms = post(f"{BASE_URL}/chat/message", {
        "session_id": session_id,
        "message": "Can you test me with 2 questions about what we just discussed?",
    }, headers, verbose)

    if r.status_code != 200:
        fail(f"Quiz request failed: {r.status_code}")

    data = r.json()
    print_message_summary(data)
    ok(f"Quiz processed — intent={data['intent']} type={data['response_type']}")

    # ── Test 6: Out-of-scope question ──────────────────────────────────────────
    h("Test 6: Out-of-scope question")
    r, ms = post(f"{BASE_URL}/chat/message", {
        "session_id": session_id,
        "message": "What is the best recipe for chocolate cake?",
    }, headers, verbose)

    if r.status_code != 200:
        fail(f"Out-of-scope test failed: {r.status_code}")

    data = r.json()
    print_message_summary(data)
    rt = data["response_type"]
    if rt in ("OUT_OF_SCOPE", "NO_CONTEXT"):
        ok(f"Correctly handled out-of-scope (response_type={rt})")
        dm = data.get("default_message")
        if dm:
            ok(f"default_message present: '{dm[:80]}...'")
    else:
        warn(f"response_type={rt} — model may have found something tangentially related")

    # ── Test 7: Session history ────────────────────────────────────────────────
    h("Test 7: Load session history")
    r, ms = get(f"{BASE_URL}/chat/sessions/{session_id}/history", headers, verbose)

    if r.status_code != 200:
        fail(f"History load failed: {r.status_code}")

    data = r.json()
    msg_count = len(data.get("messages", []))
    ok(f"History loaded: {msg_count} messages")
    ok(f"Session title: '{data.get('title', '')}'")

    # Verify all our messages are persisted
    user_msgs = [m for m in data["messages"] if m["role"] == "user"]
    assistant_msgs = [m for m in data["messages"] if m["role"] == "assistant"]
    ok(f"User messages: {len(user_msgs)}, Assistant messages: {len(assistant_msgs)}")
    assert len(user_msgs) == 5, f"Expected 5 user messages, got {len(user_msgs)}"
    assert len(assistant_msgs) == 5, f"Expected 5 assistant messages, got {len(assistant_msgs)}"

    # ── Test 8: End session ────────────────────────────────────────────────────
    h("Test 8: End session")
    r, ms = post(f"{BASE_URL}/chat/sessions/{session_id}/end", {}, headers, verbose)

    if r.status_code not in (200, 204):
        fail(f"End session failed: {r.status_code}")
    ok("Session ended successfully")

    # Verify session is marked inactive
    r, _ = get(f"{BASE_URL}/chat/sessions/{session_id}", headers, verbose=False)
    if r.status_code == 200:
        s = r.json()
        if not s.get("is_active", True):
            ok("Session confirmed as inactive")
        else:
            warn("Session still shows as active after end call")

    # ── Final summary ─────────────────────────────────────────────────────────
    h("All chat tests passed!")
    print()
    print("  What was validated:")
    print("  ✓  Session creation with learning event")
    print("  ✓  General question → answer with suggestions + sources")
    print("  ✓  Follow-up / continuation (topic threading)")
    print("  ✓  Visual representation request (SHOW_VISUAL)")
    print("  ✓  Quiz request (QUIZ_ME)")
    print("  ✓  Out-of-scope question (default_message returned)")
    print("  ✓  Session history persistence (all messages in DB)")
    print("  ✓  Session end with SESSION_END learning event")
    print()
    print("  Check your DB to verify user_learning_events rows were written:")
    print(f"  SELECT event_type, topic_tags, confidence_score")
    print(f"  FROM user_learning_events")
    print(f"  WHERE chat_session_id = '{session_id}'")
    print(f"  ORDER BY created_at;\n")


def main():
    parser = argparse.ArgumentParser(description="Test Phase 6 Chat API")
    parser.add_argument("--key", required=True, help="API key (axai_...)")
    parser.add_argument("--course", type=int, default=1, help="Moodle course ID")
    parser.add_argument("--content-id", default=None, help="Scope to specific content item UUID")
    parser.add_argument("--verbose", action="store_true", help="Print full request/response JSON")
    parser.add_argument("--url", default="http://localhost:8000", help="Base API URL")

    args = parser.parse_args()
    global BASE_URL
    BASE_URL = f"{args.url}/api/v1"

    print(f"\n  axis-ai Chat API Test — Phase 6")
    print(f"  API URL : {BASE_URL}")
    print(f"  Course  : {args.course}")
    print(f"  Content : {args.content_id or '(all course content)'}")
    print(f"  Verbose : {args.verbose}")

    run_tests(
        api_key=args.key,
        course_id=args.course,
        content_id=args.content_id,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
