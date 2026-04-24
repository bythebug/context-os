import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------

class AppCreate(BaseModel):
    name: str


class AppOut(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# API keys
# ---------------------------------------------------------------------------

class ApiKeyOut(BaseModel):
    id: uuid.UUID
    app_id: uuid.UUID
    created_at: datetime
    # raw key only returned on creation, never again
    key: Optional[str] = None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

class AppUsage(BaseModel):
    app_id: uuid.UUID
    app_name: str
    total_fragments: int
    total_dead_letters: int
    unique_users: int
    last_active: Optional[datetime]
