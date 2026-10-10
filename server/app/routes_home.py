"""Public welcome page (templated from SERVICE_NAME / ALLOWED_EMAIL_DOMAIN)."""
import os

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from . import settings

router = APIRouter()

_templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_templates_dir)


def _error_message(error: str | None, domain: str | None) -> str | None:
    if error == "blocked":
        return "This email address has been blocked by an administrator."
    if error == "domain_not_allowed":
        if domain:
            return f"Sign-in is restricted to Google accounts on @{domain}."
        return "Sign-in is restricted to allowed Google accounts."
    return None


@router.get("/")
def welcome(request: Request, error: str | None = None):
    domain = settings.allowed_email_domain()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "service_name": settings.service_name(),
            "allowed_domain": domain,
            "error_message": _error_message(error, domain),
        },
    )
