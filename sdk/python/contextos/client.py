"""ContextOS Python SDK."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Optional

import httpx


class ContextOSError(Exception):
    """Raised when the ContextOS API returns an error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"ContextOS API error {status_code}: {detail}")


@dataclass
class Fragment:
    id: str
    content: str
    type: str
    importance: int
    score: float
    source_client: Optional[str]
    created_at: datetime

    @classmethod
    def _from_dict(cls, d: dict[str, Any]) -> "Fragment":
        return cls(
            id=d["id"],
            content=d["content"],
            type=d["type"],
            importance=d["importance"],
            score=d["score"],
            source_client=d.get("source_client"),
            created_at=datetime.fromisoformat(d["created_at"]),
        )


@dataclass
class MemoryResponse:
    user_id: str
    fragments: list[Fragment]
    prompt_block: str
    total_fragments: int
    query_ms: int

    @classmethod
    def _from_dict(cls, d: dict[str, Any]) -> "MemoryResponse":
        return cls(
            user_id=d["user_id"],
            fragments=[Fragment._from_dict(f) for f in d["fragments"]],
            prompt_block=d["prompt_block"],
            total_fragments=d["meta"]["total_fragments"],
            query_ms=d["meta"]["query_ms"],
        )


class ContextOS:
    """
    ContextOS client.

    Usage::

        client = ContextOS(base_url="https://your-app.fly.dev", api_key="sk-...")

        # After a conversation
        client.write(user_id="alice", conversation="User: I prefer async Python\\nAssistant: Got it.")

        # Before an LLM call
        memory = client.query(user_id="alice", q=user_message)
        system_prompt = f"You are a helpful assistant.\\n\\n{memory.prompt_block}"
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "http://localhost:8000",
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout

    # ------------------------------------------------------------------
    # Sync interface
    # ------------------------------------------------------------------

    def write(
        self,
        user_id: str,
        conversation: str,
        source_client: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        Ingest a conversation. Extraction runs in the background on the server.
        Returns the session_id.
        """
        payload: dict[str, Any] = {
            "user_id": user_id,
            "conversation": conversation,
        }
        if source_client:
            payload["source_client"] = source_client
        if metadata:
            payload["metadata"] = metadata

        resp = httpx.post(
            f"{self._base_url}/sessions",
            json=payload,
            headers=self._headers,
            timeout=self._timeout,
        )
        _raise_for_status(resp)
        return resp.json()["session_id"]

    def query(
        self,
        user_id: str,
        q: str,
        top_k: Optional[int] = None,
        scope: Literal["global", "app"] = "global",
        type: Optional[str] = None,
    ) -> MemoryResponse:
        """
        Retrieve relevant memory fragments for a user.
        Returns a MemoryResponse with fragments and a ready-to-inject prompt_block.
        """
        params: dict[str, Any] = {"user_id": user_id, "q": q, "scope": scope}
        if top_k is not None:
            params["top_k"] = top_k
        if type is not None:
            params["type"] = type

        resp = httpx.get(
            f"{self._base_url}/memory",
            params=params,
            headers=self._headers,
            timeout=self._timeout,
        )
        _raise_for_status(resp)
        return MemoryResponse._from_dict(resp.json())

    def delete(self, fragment_id: str) -> None:
        """Delete a fragment by ID. Only fragments created by this app can be deleted."""
        resp = httpx.delete(
            f"{self._base_url}/memory/{fragment_id}",
            headers=self._headers,
            timeout=self._timeout,
        )
        _raise_for_status(resp)

    # ------------------------------------------------------------------
    # Async interface
    # ------------------------------------------------------------------

    async def awrite(
        self,
        user_id: str,
        conversation: str,
        source_client: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """Async version of write()."""
        payload: dict[str, Any] = {
            "user_id": user_id,
            "conversation": conversation,
        }
        if source_client:
            payload["source_client"] = source_client
        if metadata:
            payload["metadata"] = metadata

        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            resp = await client.post(f"{self._base_url}/sessions", json=payload)
        _raise_for_status(resp)
        return resp.json()["session_id"]

    async def aquery(
        self,
        user_id: str,
        q: str,
        top_k: Optional[int] = None,
        scope: Literal["global", "app"] = "global",
        type: Optional[str] = None,
    ) -> MemoryResponse:
        """Async version of query()."""
        params: dict[str, Any] = {"user_id": user_id, "q": q, "scope": scope}
        if top_k is not None:
            params["top_k"] = top_k
        if type is not None:
            params["type"] = type

        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            resp = await client.get(f"{self._base_url}/memory", params=params)
        _raise_for_status(resp)
        return MemoryResponse._from_dict(resp.json())

    async def adelete(self, fragment_id: str) -> None:
        """Async version of delete()."""
        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            resp = await client.delete(f"{self._base_url}/memory/{fragment_id}")
        _raise_for_status(resp)


def _raise_for_status(resp: httpx.Response) -> None:
    if resp.is_error:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise ContextOSError(status_code=resp.status_code, detail=detail)
