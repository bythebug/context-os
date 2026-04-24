"""
Smoke test: write a session → query memory → verify prompt_block is injectable.

Requires a running ContextOS stack (docker-compose up) and a seeded API key.
Run with:
    CONTEXTOS_API_KEY=<key> pytest tests/test_smoke.py -v
"""
import os
import time

import httpx
import pytest

BASE_URL = os.getenv("CONTEXTOS_BASE_URL", "http://localhost:8000")
API_KEY = os.getenv("CONTEXTOS_API_KEY", "")


@pytest.fixture(scope="module")
def headers():
    assert API_KEY, "Set CONTEXTOS_API_KEY env var before running smoke tests"
    return {"Authorization": f"Bearer {API_KEY}"}


def test_health():
    r = httpx.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["postgres"] == "ok"
    assert data["redis"] == "ok"


def test_write_session(headers):
    payload = {
        "user_id": "smoke-test-user",
        "conversation": (
            "User: I'm building a FastAPI service that stores embeddings in pgvector. "
            "I prefer async Python and want the API to follow the OpenAI key format. "
            "I decided to use Fly.io for deployment because it's the cheapest option for small services."
        ),
        "source_client": "smoke-test",
        "metadata": {"test_run": True},
    }
    r = httpx.post(f"{BASE_URL}/sessions", json=payload, headers=headers)
    assert r.status_code == 202
    data = r.json()
    assert data["status"] == "accepted"
    assert data["user_id"] == "smoke-test-user"


def test_query_memory(headers):
    # Give the background extraction task time to complete
    time.sleep(15)

    r = httpx.get(
        f"{BASE_URL}/memory",
        params={"user_id": "smoke-test-user", "q": "deployment and infrastructure preferences"},
        headers=headers,
        timeout=60.0,
    )
    assert r.status_code == 200
    data = r.json()

    assert data["user_id"] == "smoke-test-user"
    assert isinstance(data["fragments"], list)
    assert len(data["fragments"]) > 0
    assert "prompt_block" in data
    assert len(data["prompt_block"]) > 0
    assert "meta" in data
    assert data["meta"]["total_fragments"] > 0

    # Verify prompt_block is injectable — starts with context header
    assert data["prompt_block"].startswith("Relevant context about this user:")

    # Verify each fragment has required fields
    for frag in data["fragments"]:
        assert "id" in frag
        assert "content" in frag
        assert "type" in frag
        assert frag["type"] in ("fact", "preference", "decision", "event", "project")
        assert 1 <= frag["importance"] <= 5
        assert 0.0 <= frag["score"] <= 1.0


def test_query_memory_scope_app(headers):
    r = httpx.get(
        f"{BASE_URL}/memory",
        params={"user_id": "smoke-test-user", "q": "python async", "scope": "app"},
        headers=headers,
    )
    assert r.status_code == 200


def test_query_memory_type_filter(headers):
    r = httpx.get(
        f"{BASE_URL}/memory",
        params={"user_id": "smoke-test-user", "q": "deployment", "type": "decision"},
        headers=headers,
    )
    assert r.status_code == 200
    data = r.json()
    for frag in data["fragments"]:
        assert frag["type"] == "decision"
