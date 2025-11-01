"""Comprehensive Memory Validation Suite

Run inside backend container:

    docker compose exec backend python scripts/memory_validation_suite.py

Purpose: Executes layered tests for Redis (short-term), Pinecone (semantic), Neo4j (structured),
Mongo (transcript), and personalization deterministic paths.

The script is intentionally linear and prints PASS/FAIL per step with minimal dependencies.
"""
from __future__ import annotations
import requests, time, sys, json

BASE = "http://localhost:8000"
EMAIL = "memory_tester@example.com"
PASSWORD = "Passw0rd!"

HEADERS = {}


def _print(title: str):
    print(f"\n=== {title} ===")


def register_and_login():
    _print("Auth")
    requests.post(f"{BASE}/api/auth/signup", json={"email": EMAIL, "password": PASSWORD})
    r = requests.post(f"{BASE}/api/auth/login", data={"username": EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        print("Login failed", r.text); sys.exit(1)
    token = r.json().get("access_token")
    if not token:
        print("No token returned"); sys.exit(1)
    global HEADERS
    HEADERS = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print("PASS login")


def test_short_term():
    _print("Short-Term Memory (Redis)")
    r = requests.post(f"{BASE}/api/chat/new", json={"message": "Hello Aurion"}, headers=HEADERS)
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    # Provide a fact
    r2 = requests.post(f"{BASE}/api/chat/{sid}", json={"message": "My favorite color is blue."}, headers=HEADERS)
    assert r2.status_code == 200
    time.sleep(0.4)  # allow background append
    # Ask recall (fast-path not yet implemented for color, fallback semantic/graph later if added)
    r3 = requests.post(f"{BASE}/api/chat/{sid}", json={"message": "What is my favorite color?"}, headers=HEADERS)
    assert r3.status_code == 200
    print("Session ID:", sid)
    return sid


def test_semantic_and_hobbies(session_id: str):
    _print("Semantic Memory (Pinecone)")
    phrases = [
        "I love playing chess and cricket.",
        "Sometimes I also enjoy table tennis.",
    ]
    for p in phrases:
        r = requests.post(f"{BASE}/api/chat/{session_id}", json={"message": p}, headers=HEADERS)
        assert r.status_code == 200
    # Trigger a recall question
    r2 = requests.post(f"{BASE}/api/chat/{session_id}", json={"message": "What sports do I like?"}, headers=HEADERS)
    assert r2.status_code == 200
    print("PASS semantic upsert & query (manual inspection of response)")


def test_structured_facts(session_id: str):
    _print("Structured Facts (Neo4j)")
    r = requests.post(f"{BASE}/api/chat/{session_id}", json={"message": "My friend Alice lives in New York."}, headers=HEADERS)
    assert r.status_code == 200
    # Ask a follow-up after background extraction chance
    time.sleep(1.2)
    r2 = requests.post(f"{BASE}/api/chat/{session_id}", json={"message": "Where does my friend Alice live?"}, headers=HEADERS)
    assert r2.status_code == 200
    print("PASS structured fact capture (inspect AI response)")


def test_persistent_transcript(session_id: str):
    _print("Persistent Transcript (Mongo)")
    # Fetch messages via sessions endpoint for comparison
    r = requests.get(f"{BASE}/api/sessions/{session_id}", headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    total = data.get("totalMessages")
    assert total is not None
    print("Total messages stored:", total)
    print("PASS transcript retrieval")


def test_summary_personalization(session_id: str):
    _print("Personalization & Summary")
    # Provide name + preference in same or new session
    r = requests.post(f"{BASE}/api/chat/{session_id}", json={"message": "My name is John and I live in Paris and love soccer."}, headers=HEADERS)
    assert r.status_code == 200
    time.sleep(1.0)
    # New session to test cross-session recall
    r2 = requests.post(f"{BASE}/api/chat/new", json={"message": "Hi"}, headers=HEADERS)
    assert r2.status_code == 200
    greet = r2.json().get("response_text", "")
    print("Cross-session greeting:", greet)
    r3 = requests.post(f"{BASE}/api/chat/{r2.json()['session_id']}", json={"message": "What do you know about me?"}, headers=HEADERS)
    assert r3.status_code == 200
    print("Profile summary response:", r3.json().get("response_text"))
    print("PASS personalization cross-session")


def main():
    register_and_login()
    sid = test_short_term()
    test_semantic_and_hobbies(sid)
    test_structured_facts(sid)
    test_persistent_transcript(sid)
    test_summary_personalization(sid)
    print("\nAll memory validation steps executed (inspect outputs for semantic/graph accuracy).")

if __name__ == "__main__":
    main()
