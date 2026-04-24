import json

import anthropic
import structlog

from app.config import settings
from app.extraction.base import EXTRACTION_SYSTEM_PROMPT, BaseExtractor, RawFragment

logger = structlog.get_logger(__name__)

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


class AnthropicExtractor(BaseExtractor):
    async def extract(self, conversation: str) -> list[RawFragment]:
        client = _get_client()
        try:
            message = await client.messages.create(
                model=settings.anthropic_extraction_model,
                max_tokens=2048,
                system=EXTRACTION_SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": f"Extract memory fragments from this conversation:\n\n{conversation}",
                    }
                ],
            )
            block = message.content[0]
            if not isinstance(block, anthropic.types.TextBlock):
                logger.warning("extraction.unexpected_block_type", block_type=type(block).__name__)
                return []
            raw = block.text.strip()
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(raw)
            return [
                RawFragment(
                    content=item["content"],
                    type=item["type"],
                    importance=max(1, min(5, int(item["importance"]))),
                )
                for item in data
                if item.get("content") and item.get("type")
            ]
        except Exception:
            logger.exception("extraction.anthropic_failed")
            return []
