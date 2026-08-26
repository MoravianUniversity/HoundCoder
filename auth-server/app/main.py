"""FastAPI app assembly: routers + static admin page."""
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from . import db
from . import routes_admin
from . import routes_auth
from . import routes_validate
from .nginx_config import get_base_url
from .security import get_or_create_session_secret

app = FastAPI(title="Hound Coder Auth Server")


@app.on_event("startup")
def on_startup():
    db.init_db()


app.add_middleware(
    SessionMiddleware,
    secret_key=get_or_create_session_secret(),
    same_site="lax",
    https_only=get_base_url().startswith("https://"),
)

app.include_router(routes_validate.router)
app.include_router(routes_admin.router)
app.include_router(routes_auth.router)

_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/admin", StaticFiles(directory=_static_dir, html=True), name="admin-ui")
