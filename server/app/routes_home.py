"""Public welcome page (templated from SERVICE_NAME / ALLOWED_EMAIL_DOMAIN)."""
import os

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from . import settings

router = APIRouter()

_templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
templates = Jinja2Templates(directory=_templates_dir)


@router.get("/")
def welcome(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "service_name": settings.service_name(),
            "allowed_domain": settings.allowed_email_domain(),
        },
    )
