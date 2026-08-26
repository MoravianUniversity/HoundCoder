"""Fills the Continue config template with a user's token and server URL."""
import os

from .nginx_config import get_base_url
from .security import encode_jwt

CONTINUE_TEMPLATE_PATH = os.environ.get(
    "CONTINUE_TEMPLATE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "..", "continue-config-template.yaml"),
)


def render_continue_config(email: str, issue_date: int) -> str:
    with open(CONTINUE_TEMPLATE_PATH) as f:
        filled = f.read().replace("<YOUR_API_KEY>", encode_jwt(email, issue_date))
        filled = filled.replace("<SERVER_BASE_URL>", get_base_url())
    return filled
