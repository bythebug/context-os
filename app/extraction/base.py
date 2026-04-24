from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

FragmentType = Literal["fact", "preference", "decision", "event", "project"]

EXTRACTION_SYSTEM_PROMPT = """You are a memory extraction engine. Given a conversation, extract discrete, self-contained memory fragments that would be useful context for future conversations with this user.

Return a JSON array. Each element must have exactly these fields:
- content: string — a single, specific, self-contained fact (no pronouns like "they" or "the user"; write as if read in isolation)
- type: one of "fact" | "preference" | "decision" | "event" | "project"
- importance: integer 1-5 (1=trivial, 3=useful, 5=critical)

Rules:
- Extract only concrete, specific information. Skip pleasantries and filler.
- Each fragment must stand alone without surrounding context.
- Prefer fewer, high-quality fragments over many vague ones.
- If nothing meaningful can be extracted, return an empty array [].

Example output:
[
  {"content": "User is building a FastAPI service deployed on Fly.io", "type": "project", "importance": 4},
  {"content": "User prefers async Python over sync", "type": "preference", "importance": 3},
  {"content": "User decided to use pgvector instead of Pinecone for cost reasons", "type": "decision", "importance": 4}
]"""


@dataclass
class RawFragment:
    content: str
    type: FragmentType
    importance: int


class BaseExtractor(ABC):
    @abstractmethod
    async def extract(self, conversation: str) -> list[RawFragment]:
        """Extract memory fragments from raw conversation text."""
        ...
