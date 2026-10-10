"""Public self-service registration via Google OAuth, locked to one email domain."""
import json
import os
import time

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from . import db
from . import settings
from .oauth_client import oauth
from .public_url import base_url_from_request
from .security import decode_jwt, encode_jwt
from .setup_sections import build_placeholders, load_sections

router = APIRouter(prefix="/register")

COOKIE_NAME = "hc_token"
TOKEN_PREFIX_LEN = 20

_templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_templates_dir)


def _allowed_domain() -> str:
    domain = settings.allowed_email_domain()
    if not domain:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "ALLOWED_EMAIL_DOMAIN is not configured")
    return domain


def _cookie_is_secure(request: Request) -> bool:
    return request.url.scheme == "https"


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = f"{base_url_from_request(request)}/register/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}

    email = userinfo.get("email")
    if not email or not userinfo.get("email_verified"):
        return RedirectResponse("/?error=domain_not_allowed")

    email = email.lower()
    domain = email.rsplit("@", 1)[-1]
    if domain != _allowed_domain():
        return RedirectResponse("/?error=domain_not_allowed")

    if db.is_blocked(email):
        return RedirectResponse("/?error=blocked")

    now = int(time.time())
    user = db.get_user(email)
    if user is None:
        user = db.create_user(email, is_admin=False, created_at=now)

    token_row = db.get_latest_valid_token(email)
    if token_row is None:
        token_row = db.create_token(email, now)

    jwt_value = encode_jwt(email, token_row.issue_date)
    response = RedirectResponse("/register/success", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        COOKIE_NAME,
        jwt_value,
        httponly=True,
        secure=_cookie_is_secure(request),
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return response


def _auth_from_cookie(request: Request) -> tuple[str, int]:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    try:
        payload = decode_jwt(raw)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session")

    email = payload["email"]
    issue_date = payload["iat"]

    if db.get_user(email) is None or db.is_blocked(email):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Access revoked")

    token_row = db.get_token(email, issue_date)
    if token_row is None or token_row.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")

    return email, issue_date


@router.get("/success")
def success(request: Request):
    email, issue_date = _auth_from_cookie(request)
    jwt_value = encode_jwt(email, issue_date)
    placeholders = build_placeholders(request, api_key=jwt_value)
    sections = load_sections(placeholders)
    masked = jwt_value[:TOKEN_PREFIX_LEN] + "…"
    return templates.TemplateResponse(
        request,
        "success.html",
        {
            "service_name": settings.service_name(),
            "email": email,
            "token_masked": masked,
            "token_json": json.dumps(jwt_value),
            "sections": sections,
        },
    )
