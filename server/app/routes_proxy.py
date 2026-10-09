"""Authenticated streaming proxy from /tab and /chat to local vLLM OpenAI servers."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import StreamingResponse

from . import metrics, usage_db
from .deps import AuthContext, get_current_user

logger = logging.getLogger(__name__)

TAB_UPSTREAM = os.environ.get("TAB_UPSTREAM", "http://127.0.0.1:8001/v1")
CHAT_UPSTREAM = os.environ.get("CHAT_UPSTREAM", "http://127.0.0.1:8002/v1")

# Hop-by-hop / framing headers that must not be forwarded.
_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}

router = APIRouter()

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=3600.0, write=60.0, pool=10.0),
            follow_redirects=False,
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def _upstream_base(endpoint: str) -> str:
    return TAB_UPSTREAM if endpoint == "tab" else CHAT_UPSTREAM


def _filter_request_headers(headers: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        lk = key.lower()
        if lk in _HOP_BY_HOP or lk == "authorization":
            continue
        out[key] = value
    return out


def _filter_response_headers(headers: httpx.Headers) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in _HOP_BY_HOP:
            continue
        out[key] = value
    return out


def _prepare_body(raw: bytes, content_type: str | None) -> tuple[bytes, bool]:
    """Return (body, is_streaming). Inject stream_options.include_usage when streaming."""
    if not raw:
        return raw, False
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct not in ("application/json", "text/json"):
        return raw, False
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return raw, False
    if not isinstance(payload, dict):
        return raw, False
    streaming = bool(payload.get("stream"))
    if streaming:
        opts = payload.get("stream_options")
        if not isinstance(opts, dict):
            opts = {}
        opts = {**opts, "include_usage": True}
        payload["stream_options"] = opts
        return json.dumps(payload).encode("utf-8"), True
    return raw, False


def _usage_from_obj(obj: object) -> tuple[int | None, int | None]:
    if not isinstance(obj, dict):
        return None, None
    usage = obj.get("usage")
    if not isinstance(usage, dict):
        return None, None
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")
    return (
        int(prompt) if isinstance(prompt, int) else None,
        int(completion) if isinstance(completion, int) else None,
    )


def _parse_sse_usage(buffer: str) -> tuple[int | None, int | None]:
    """Scan SSE text for the last data payload that includes usage."""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    for line in buffer.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        p, c = _usage_from_obj(obj)
        if p is not None or c is not None:
            prompt_tokens, completion_tokens = p, c
    return prompt_tokens, completion_tokens


def _record(
    *,
    ctx: AuthContext,
    endpoint: str,
    method: str,
    path: str,
    status: int,
    request_body: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    latency_s: float,
    ttft_s: float | None,
) -> None:
    metrics.record_request(
        endpoint=endpoint,
        email=ctx.email,
        status=status,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_s=latency_s,
        ttft_s=ttft_s,
    )
    try:
        usage_db.insert_event(
            email=ctx.email,
            iat=ctx.issue_date,
            endpoint=endpoint,
            method=method,
            path=path,
            status=status,
            request_body=request_body,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_s * 1000.0,
            ttft_ms=(ttft_s * 1000.0) if ttft_s is not None else None,
        )
    except Exception:
        logger.exception("Failed to persist request_event for %s", ctx.email)


async def _proxy(endpoint: str, path: str, request: Request, ctx: AuthContext) -> Response:
    raw_body = await request.body()
    body, _ = _prepare_body(raw_body, request.headers.get("content-type"))
    try:
        request_body_text = raw_body.decode("utf-8") if raw_body else None
    except UnicodeDecodeError:
        request_body_text = None

    upstream_url = f"{_upstream_base(endpoint).rstrip('/')}/{path.lstrip('/')}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    headers = _filter_request_headers(dict(request.headers))
    if body and "content-type" not in {k.lower() for k in headers}:
        headers["content-type"] = "application/json"

    client = get_http_client()
    t0 = time.perf_counter()
    method = request.method.upper()

    try:
        upstream_req = client.build_request(
            method,
            upstream_url,
            headers=headers,
            content=body if method not in ("GET", "HEAD") else None,
        )
        upstream = await client.send(upstream_req, stream=True)
    except httpx.RequestError as exc:
        latency_s = time.perf_counter() - t0
        _record(
            ctx=ctx,
            endpoint=endpoint,
            method=method,
            path=f"/{endpoint}/{path}",
            status=502,
            request_body=request_body_text,
            prompt_tokens=None,
            completion_tokens=None,
            latency_s=latency_s,
            ttft_s=None,
        )
        return Response(content=f"Upstream error: {exc}", status_code=502)

    content_type = upstream.headers.get("content-type", "")
    is_sse = "text/event-stream" in content_type
    resp_headers = _filter_response_headers(upstream.headers)
    log_path = f"/{endpoint}/{path}"

    if is_sse:
        async def event_stream() -> AsyncIterator[bytes]:
            ttft_s: float | None = None
            sse_buf = ""
            prompt_tokens: int | None = None
            completion_tokens: int | None = None
            status = upstream.status_code
            try:
                async for chunk in upstream.aiter_bytes():
                    if ttft_s is None:
                        ttft_s = time.perf_counter() - t0
                    try:
                        sse_buf += chunk.decode("utf-8", errors="replace")
                        # Keep a bounded tail so we still see the final usage chunk.
                        if len(sse_buf) > 65536:
                            sse_buf = sse_buf[-65536:]
                    except Exception:
                        pass
                    yield chunk
                prompt_tokens, completion_tokens = _parse_sse_usage(sse_buf)
            finally:
                await upstream.aclose()
                latency_s = time.perf_counter() - t0
                _record(
                    ctx=ctx,
                    endpoint=endpoint,
                    method=method,
                    path=log_path,
                    status=status,
                    request_body=request_body_text,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    latency_s=latency_s,
                    ttft_s=ttft_s,
                )

        return StreamingResponse(
            event_stream(),
            status_code=upstream.status_code,
            headers=resp_headers,
            media_type=content_type or None,
        )

    # Non-streaming: buffer body to extract usage, then return.
    try:
        raw = await upstream.aread()
    finally:
        await upstream.aclose()
    latency_s = time.perf_counter() - t0
    ttft_s = latency_s
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    try:
        obj = json.loads(raw)
        prompt_tokens, completion_tokens = _usage_from_obj(obj)
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass
    _record(
        ctx=ctx,
        endpoint=endpoint,
        method=method,
        path=log_path,
        status=upstream.status_code,
        request_body=request_body_text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        latency_s=latency_s,
        ttft_s=ttft_s,
    )
    return Response(
        content=raw,
        status_code=upstream.status_code,
        headers=resp_headers,
        media_type=content_type or None,
    )


@router.api_route("/tab/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_tab(path: str, request: Request, ctx: AuthContext = Depends(get_current_user)):
    return await _proxy("tab", path, request, ctx)


@router.api_route("/chat/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
async def proxy_chat(path: str, request: Request, ctx: AuthContext = Depends(get_current_user)):
    return await _proxy("chat", path, request, ctx)
