"""
ContextOS cross-app memory demo.

Shows two separate AI apps — a "Claude app" and a "GPT app" — sharing
one memory store through ContextOS. Alice tells one app her preferences.
The other app already knows them without Alice re-introducing herself.

Usage:
    # 1. Start ContextOS
    contextos start

    # 2. Create an API key
    contextos keys create --app-name demo \\
      --database-url postgresql://contextos:contextos@localhost:5433/contextos

    # 3. Run this demo
    CONTEXTOS_API_KEY=sk-... python demo/cross_app_demo.py
"""

import os
import time
import httpx

BASE_URL = os.getenv("CONTEXTOS_URL", "http://localhost:8000")
API_KEY = os.getenv("CONTEXTOS_API_KEY")

if not API_KEY:
    raise SystemExit("Set CONTEXTOS_API_KEY=sk-... before running this demo.")


def _headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def divider(label: str):
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print('─' * 60)


# ── APP 1: Claude app writes Alice's memory ────────────────────────────────

divider("APP 1 (Claude app) — Alice has a conversation")

conversation_in_claude = (
    "User: Hey, I'm Alice. I'm building a SaaS called Buildly. "
    "I always use async Python and deploy everything on Fly.io. I hate AWS.\n"
    "Assistant: Great to meet you Alice! Noted — async Python on Fly.io for Buildly."
)

print(f"\nConversation:\n{conversation_in_claude}\n")

resp = httpx.post(
    f"{BASE_URL}/sessions",
    headers=_headers(),
    json={
        "user_id": "alice",
        "conversation": conversation_in_claude,
        "source_client": "claude-app",
    },
)
resp.raise_for_status()
print(f"Written to ContextOS: session_id={resp.json()['session_id']}")
print("Waiting for background extraction...")
time.sleep(4)

# ── APP 2: GPT app queries — without Alice saying anything ────────────────

divider("APP 2 (GPT app) — Alice starts a new conversation, says nothing yet")

print("\nQuerying ContextOS for alice's context before the first message...")

resp = httpx.get(
    f"{BASE_URL}/memory",
    headers=_headers(),
    params={"user_id": "alice", "q": "what is alice building and what stack does she use?"},
)
resp.raise_for_status()
data = resp.json()

print(f"\nFragments retrieved ({data['meta']['total_fragments']} total):")
for f in data["fragments"]:
    print(f"  [{f['type']}] {f['content']}  (source: {f['source_client']}, score: {f['score']:.2f})")

print(f"\nprompt_block (inject this into your system prompt):")
print(f"\n  {data['prompt_block']}\n")

divider("Result")
print("""
  Alice's Claude app wrote her preferences.
  Alice's GPT app read them — without Alice saying a word.

  Same user_id. Same ContextOS server. One brain.

  This is cross-app personal memory.
""")
