"""FastAPI app assembly: routers + static admin page."""
import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import db
from . import routes_admin
from . import routes_validate

app = FastAPI(title="Hound Coder Auth Server")


@app.on_event("startup")
def on_startup():
    db.init_db()


app.include_router(routes_validate.router)
app.include_router(routes_admin.router)

_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
app.mount("/admin", StaticFiles(directory=_static_dir, html=True), name="admin-ui")
