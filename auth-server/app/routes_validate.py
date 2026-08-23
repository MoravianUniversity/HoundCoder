"""Internal endpoint used by nginx auth_request to validate bearer tokens."""
from fastapi import APIRouter, Depends, Response

from .deps import AuthContext, get_current_user

router = APIRouter()


@router.get("/validate")
def validate(response: Response, ctx: AuthContext = Depends(get_current_user)):
    # Surfaced via auth_request_set in nginx so access logs can record who made each request.
    response.headers["X-Auth-Email"] = ctx.email
    response.headers["X-Auth-Iat"] = str(ctx.issue_date)
    return {"email": ctx.email}
