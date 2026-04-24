from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_by_api_key(request: Request) -> str:
    """Rate limit by API key if present, fall back to IP."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_key_by_api_key)
