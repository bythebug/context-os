from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    user_id: str = Field(..., description="Caller-supplied opaque user identifier")
    conversation: str = Field(..., description="Raw conversation text to extract memory from")
    source_client: str | None = Field(None, description="Identifier for the calling tool, e.g. 'claude-terminal'")
    metadata: dict = Field(default_factory=dict, description="Arbitrary metadata (session_id, model, etc.)")


class SessionResponse(BaseModel):
    session_id: str
    user_id: str
    status: str  # "accepted" — extraction runs async
    message: str
