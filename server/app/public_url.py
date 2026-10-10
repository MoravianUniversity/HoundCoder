"""Public base URL from the incoming request (Host + trusted X-Forwarded-Proto)."""
from fastapi import Request


def base_url_from_request(request: Request) -> str:
    return str(request.base_url).rstrip("/")
