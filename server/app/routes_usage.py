"""JWT-scoped usage query API: self for any user, all users for admins."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from . import usage_db
from .deps import AuthContext, get_current_user

router = APIRouter(prefix="/usage")


class EventOut(BaseModel):
    id: int
    created_at: int
    email: str
    iat: int
    endpoint: str
    method: str
    path: str
    status: int
    request_body: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float | None = None
    ttft_ms: float | None = None


class AggregateOut(BaseModel):
    email: str
    endpoint: str | None = None
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    avg_latency_ms: float | None = None
    avg_ttft_ms: float | None = None


def _resolve_email_filter(ctx: AuthContext, email: str | None) -> str | None:
    """Non-admins may only query themselves. Admins may omit email (all) or filter."""
    if ctx.is_admin:
        return email
    if email is not None and email != ctx.email:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot view other users' usage")
    return ctx.email


@router.get("/events", response_model=list[EventOut])
def list_events(
    ctx: AuthContext = Depends(get_current_user),
    email: str | None = None,
    endpoint: str | None = Query(default=None, pattern="^(tab|chat)$"),
    since: int | None = None,
    until: int | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    include_body: bool = False,
):
    target = _resolve_email_filter(ctx, email)
    events = usage_db.list_events(
        email=target,
        endpoint=endpoint,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    out: list[EventOut] = []
    for e in events:
        out.append(
            EventOut(
                id=e.id,
                created_at=e.created_at,
                email=e.email,
                iat=e.iat,
                endpoint=e.endpoint,
                method=e.method,
                path=e.path,
                status=e.status,
                request_body=e.request_body if include_body else None,
                prompt_tokens=e.prompt_tokens,
                completion_tokens=e.completion_tokens,
                latency_ms=e.latency_ms,
                ttft_ms=e.ttft_ms,
            )
        )
    return out


@router.get("/summary", response_model=list[AggregateOut])
def usage_summary(
    ctx: AuthContext = Depends(get_current_user),
    email: str | None = None,
    endpoint: str | None = Query(default=None, pattern="^(tab|chat)$"),
    since: int | None = None,
    until: int | None = None,
    group_by_endpoint: bool = False,
):
    target = _resolve_email_filter(ctx, email)
    rows = usage_db.aggregate_usage(
        email=target,
        endpoint=endpoint,
        since=since,
        until=until,
        group_by_endpoint=group_by_endpoint,
    )
    return [
        AggregateOut(
            email=r.email,
            endpoint=r.endpoint,
            request_count=r.request_count,
            prompt_tokens=r.prompt_tokens,
            completion_tokens=r.completion_tokens,
            avg_latency_ms=r.avg_latency_ms,
            avg_ttft_ms=r.avg_ttft_ms,
        )
        for r in rows
    ]
