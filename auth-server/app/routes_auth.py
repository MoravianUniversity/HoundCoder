"""Public self-service registration via Google OAuth, locked to one email domain."""
import os
import time

import jwt
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from . import db
from .continue_config import render_continue_config
from .nginx_config import get_base_url
from .oauth_client import oauth
from .security import decode_jwt, encode_jwt

router = APIRouter(prefix="/auth")

COOKIE_NAME = "hc_token"

ERROR_MESSAGES = {
    "blocked": "This email address has been blocked by an administrator.",
    "domain_not_allowed": "Sign-in is restricted to accounts on the approved domain.",
}


def _allowed_domain() -> str:
    domain = os.environ.get("ALLOWED_EMAIL_DOMAIN")
    if not domain:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "ALLOWED_EMAIL_DOMAIN is not configured")
    return domain.lower()


def _cookie_is_secure() -> bool:
    return get_base_url().startswith("https://")


def _page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  body {{ font-family: sans-serif; max-width: 700px; margin: 3rem auto; padding: 0 1rem; line-height: 1.5; }}
  code {{ background: #f0f0f0; padding: 0.1rem 0.3rem; border-radius: 3px; }}
  .error {{ color: #b00020; }}
  .button {{ display: inline-block; background: #1a73e8; color: #fff; padding: 0.6rem 1.2rem;
             border-radius: 4px; text-decoration: none; }}
</style>
</head>
<body>
{body}
</body>
</html>""")


@router.get("/info")
def info(error: str | None = None):
    error_html = f'<p class="error">{ERROR_MESSAGES[error]}</p>' if error in ERROR_MESSAGES else ""
    return _page("Hound Coder — Get Access", f"""
<h1>Hound Coder</h1>
<p>Sign in with your Google account to get a personal API token for the
<a href="https://marketplace.visualstudio.com/items?itemName=Continue.continue">Continue</a> extension.</p>
{error_html}
<p><a class="button" href="/auth/google/login">Sign in with Google</a></p>
""")


@router.get("/google/login")
async def google_login(request: Request):
    redirect_uri = f"{get_base_url()}/auth/google/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/google/callback")
async def google_callback(request: Request):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo") or {}

    email = userinfo.get("email")
    if not email or not userinfo.get("email_verified"):
        return RedirectResponse("/auth/info?error=domain_not_allowed")

    email = email.lower()
    domain = email.rsplit("@", 1)[-1]
    if domain != _allowed_domain():
        return RedirectResponse("/auth/info?error=domain_not_allowed")

    if db.is_blocked(email):
        return RedirectResponse("/auth/info?error=blocked")

    now = int(time.time())
    user = db.get_user(email)
    if user is None:
        user = db.create_user(email, is_admin=False, created_at=now)

    token_row = db.get_latest_valid_token(email)
    if token_row is None:
        token_row = db.create_token(email, now)

    jwt_value = encode_jwt(email, token_row.issue_date)
    response = RedirectResponse("/auth/success", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        COOKIE_NAME,
        jwt_value,
        httponly=True,
        secure=_cookie_is_secure(),
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
    email, _ = _auth_from_cookie(request)
    return _page("Hound Coder — Success", f"""
<h1>You're all set, {email}</h1>
<p><a class="button" href="/auth/config">Download Continue Config</a></p>

<h2>Setting up Continue</h2>
<p>Save the downloaded file as <code>config.yaml</code> in your VS Code Continue extension's config directory
(install the extension first if you haven't), replacing its existing configuration. It points Continue at
this server's tab-completion and chat endpoints using your personal token.</p>
""")


@router.get("/config")
def download_config(request: Request):
    email, issue_date = _auth_from_cookie(request)
    filled = render_continue_config(email, issue_date)
    filename = f"hound-coder-continue-config-{email}.yaml"
    return Response(
        content=filled,
        media_type="application/yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
