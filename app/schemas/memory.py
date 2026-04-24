import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class FragmentOut(BaseModel):
    id: uuid.UUID
    content: str
    type: str
    importance: int
    source_client: str | None
    score: float = Field(..., description="Cosine similarity score from retrieval (0-1)")
    created_at: datetime

    model_config = {"from_attributes": True}


class MemoryMeta(BaseModel):
    total_fragments: int
    query_ms: int


class MemoryResponse(BaseModel):
    user_id: str
    fragments: list[FragmentOut]
    prompt_block: str = Field(..., description="Ready-to-inject system prompt block")
    meta: MemoryMeta
