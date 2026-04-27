"""
contextos.patch — auto-capture and auto-inject memory for Anthropic and OpenAI calls.

Usage:
    import contextos

    contextos.init(api_key="sk-...")   # reads from ~/.contextos/config if omitted
    contextos.set_user("alice")        # set current user

    # Now all Anthropic/OpenAI calls are automatically captured + memory injected
    response = anthropic.Anthropic().messages.create(...)
    response = openai.OpenAI().chat.completions.create(...)
"""
from __future__ import annotations

import json
import threading
from contextvars import ContextVar
from pathlib import Path
from typing import Optional

_CONFIG_PATH = Path.home() / ".contextos" / "config.json"

# Thread/async-safe current user
_current_user: ContextVar[Optional[str]] = ContextVar("current_user", default=None)

_client = None          # ContextOS SDK client
_auto_inject: bool = True
_patched: bool = False


# ── Public API ─────────────────────────────────────────────────────────────

def init(
    api_key: Optional[str] = None,
    url: str = "http://localhost:8000",
    auto_inject: bool = True,
) -> None:
    """
    Initialize ContextOS auto-capture. Call once at app startup.

    If api_key is omitted, reads from ~/.contextos/config.json (written by `contextos init`).

    Args:
        api_key:     Your ContextOS API key (sk-...).
        url:         ContextOS server URL. Default: http://localhost:8000.
        auto_inject: Automatically prepend memory into system prompts. Default: True.
    """
    global _client, _auto_inject, _patched

    if api_key is None:
        api_key = _load_config().get("api_key")
    if not api_key:
        raise ValueError(
            "No API key found. Pass api_key= or run `contextos init` first."
        )

    from .client import ContextOS
    _client = ContextOS(api_key=api_key, base_url=url)
    _auto_inject = auto_inject

    if not _patched:
        _patch_anthropic()
        _patch_openai()
        _patched = True


def set_user(user_id: str) -> None:
    """
    Set the current user. All subsequent LLM calls will capture memory for this user.
    Use contextvars — safe for async and threaded apps.
    """
    _current_user.set(user_id)


def get_user() -> Optional[str]:
    """Return the current user_id, or None if not set."""
    return _current_user.get()


# ── Patching ───────────────────────────────────────────────────────────────

def _patch_anthropic() -> None:
    try:
        from anthropic.resources.messages import Messages

        original_create = Messages.create

        def patched_create(self, *args, **kwargs):
            user_id = _current_user.get()

            # Auto-inject memory into system prompt
            if _auto_inject and user_id and _client:
                messages = kwargs.get("messages", [])
                query = _last_user_message(messages)
                if query:
                    try:
                        mem = _client.query(user_id=user_id, q=query)
                        if mem.prompt_block:
                            existing = kwargs.get("system", "") or ""
                            kwargs["system"] = f"{existing}\n\n{mem.prompt_block}".strip()
                    except Exception:
                        pass  # never block the LLM call

            result = original_create(self, *args, **kwargs)

            # Auto-capture conversation in background
            if user_id and _client:
                messages = kwargs.get("messages", [])
                user_msg = _last_user_message(messages)
                assistant_msg = ""
                if result.content:
                    assistant_msg = getattr(result.content[0], "text", "")
                if user_msg and assistant_msg:
                    _capture_async(user_id, user_msg, assistant_msg, source="anthropic")

            return result

        Messages.create = patched_create

    except ImportError:
        pass  # anthropic not installed — skip silently


def _patch_openai() -> None:
    try:
        from openai.resources.chat.completions import Completions

        original_create = Completions.create

        def patched_create(self, *args, **kwargs):
            user_id = _current_user.get()

            # Auto-inject memory into system prompt
            if _auto_inject and user_id and _client:
                messages = kwargs.get("messages", [])
                query = _last_user_message_openai(messages)
                if query:
                    try:
                        mem = _client.query(user_id=user_id, q=query)
                        if mem.prompt_block:
                            messages = list(messages)
                            # inject as system message at position 0, or append to existing
                            if messages and messages[0].get("role") == "system":
                                messages[0] = {
                                    "role": "system",
                                    "content": f"{messages[0]['content']}\n\n{mem.prompt_block}",
                                }
                            else:
                                messages.insert(0, {"role": "system", "content": mem.prompt_block})
                            kwargs["messages"] = messages
                    except Exception:
                        pass

            result = original_create(self, *args, **kwargs)

            # Auto-capture conversation in background
            if user_id and _client:
                messages = kwargs.get("messages", [])
                user_msg = _last_user_message_openai(messages)
                assistant_msg = ""
                if result.choices:
                    assistant_msg = result.choices[0].message.content or ""
                if user_msg and assistant_msg:
                    _capture_async(user_id, user_msg, assistant_msg, source="openai")

            return result

        Completions.create = patched_create

    except ImportError:
        pass  # openai not installed — skip silently


# ── Helpers ────────────────────────────────────────────────────────────────

def _last_user_message(messages: list) -> str:
    """Extract the last user message text from Anthropic-format messages."""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block.get("text", "")
    return ""


def _last_user_message_openai(messages: list) -> str:
    """Extract the last user message text from OpenAI-format messages."""
    for m in reversed(messages):
        if m.get("role") == "user":
            content = m.get("content", "")
            if isinstance(content, str):
                return content
    return ""


def _capture_async(user_id: str, user_msg: str, assistant_msg: str, source: str) -> None:
    """Fire-and-forget: write conversation to ContextOS in a background thread."""
    conversation = f"User: {user_msg}\nAssistant: {assistant_msg}"

    def _write():
        try:
            _client.write(
                user_id=user_id,
                conversation=conversation,
                source_client=source,
            )
        except Exception:
            pass  # never raise from background thread

    threading.Thread(target=_write, daemon=True).start()


def _load_config() -> dict:
    if _CONFIG_PATH.exists():
        try:
            return json.loads(_CONFIG_PATH.read_text())
        except Exception:
            pass
    return {}
