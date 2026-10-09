"""Runtime settings from environment (loaded via dotenv in main)."""
import os


def service_name() -> str:
    return os.environ.get("SERVICE_NAME", "Hound Coder").strip() or "Hound Coder"


def allowed_email_domain() -> str | None:
    domain = os.environ.get("ALLOWED_EMAIL_DOMAIN", "").strip()
    return domain.lower() if domain else None
