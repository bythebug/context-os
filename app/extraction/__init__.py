from app.config import settings
from app.extraction.base import BaseExtractor


def get_extractor() -> BaseExtractor:
    if settings.extraction_provider == "openai":
        from app.extraction.openai import OpenAIExtractor
        return OpenAIExtractor()
    if settings.extraction_provider == "mock":
        from app.extraction.mock import MockExtractor
        return MockExtractor()
    from app.extraction.anthropic import AnthropicExtractor
    return AnthropicExtractor()
