import json
import logging

from openai import AsyncOpenAI

from app.config import settings
from app.extraction.base import EXTRACTION_SYSTEM_PROMPT, BaseExtractor, RawFragment

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client


class OpenAIExtractor(BaseExtractor):
    async def extract(self, conversation: str) -> list[RawFragment]:
        client = _get_client()
        try:
            response = await client.chat.completions.create(
                model=settings.openai_extraction_model,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Extract memory fragments from this conversation:\n\n{conversation}",
                    },
                ],
                max_tokens=2048,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            # OpenAI json_object mode wraps arrays; unwrap if needed
            parsed = json.loads(raw)
            data = parsed if isinstance(parsed, list) else parsed.get("fragments", parsed.get("items", []))
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
            logger.exception("OpenAI extraction failed")
            return []
