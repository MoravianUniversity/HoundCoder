"""Token validation endpoint (JWT check against the auth DB)."""
from fastapi import APIRouter, Depends, Response

from .deps import AuthContext, get_current_user

router = APIRouter()


@router.get("/validate")
def validate(response: Response, ctx: AuthContext = Depends(get_current_user)):
    # Kept for direct checks / tooling; inference paths validate inside the proxy.
    response.headers["X-Auth-Email"] = ctx.email
    response.headers["X-Auth-Iat"] = str(ctx.issue_date)
    return {"email": ctx.email}
