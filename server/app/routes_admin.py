"""Admin-only API for managing allowed users and their tokens."""
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel

from . import db
from .continue_config import render_continue_config
from .deps import require_admin
from .security import encode_jwt

router = APIRouter(prefix="/admin/api", dependencies=[Depends(require_admin)])


class NewUser(BaseModel):
    email: str
    is_admin: bool = False


class AdminUpdate(BaseModel):
    is_admin: bool


class TokenOut(BaseModel):
    issue_date: int
    revoked: bool
    token: str


class UserOut(BaseModel):
    email: str
    is_admin: bool
    blocked: bool
    tokens: list[TokenOut]


class BlockEntry(BaseModel):
    email: str
    reason: str | None = None


class BlockedOut(BaseModel):
    email: str
    blocked_at: int
    reason: str | None


def _user_out(user: db.User) -> UserOut:
    tokens = [
        TokenOut(issue_date=t.issue_date, revoked=t.revoked, token=encode_jwt(user.email, t.issue_date))
        for t in db.list_tokens(user.email)
    ]
    return UserOut(email=user.email, is_admin=user.is_admin, blocked=db.is_blocked(user.email), tokens=tokens)


@router.get("/users", response_model=list[UserOut])
def list_users():
    return [_user_out(u) for u in db.list_users()]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def add_user(new_user: NewUser):
    if db.get_user(new_user.email) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "User already exists")
    now = int(time.time())
    user = db.create_user(new_user.email, new_user.is_admin, now)
    db.create_token(new_user.email, now)
    return _user_out(user)


@router.patch("/users/{email}", response_model=UserOut)
def update_admin_status(email: str, update: AdminUpdate):
    user = db.get_user(email)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    db.set_admin(email, update.is_admin)
    return _user_out(db.get_user(email))


@router.delete("/users/{email}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(email: str):
    if db.get_user(email) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    db.delete_user(email)


@router.post("/users/{email}/tokens", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def issue_token(email: str):
    if db.get_user(email) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    now = int(time.time())
    token_row = db.create_token(email, now)
    return TokenOut(issue_date=token_row.issue_date, revoked=token_row.revoked, token=encode_jwt(email, now))


@router.get("/users/{email}/tokens/{issue_date}", response_model=TokenOut)
def get_token(email: str, issue_date: int):
    token_row = db.get_token(email, issue_date)
    if token_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    return TokenOut(issue_date=token_row.issue_date, revoked=token_row.revoked, token=encode_jwt(email, issue_date))


@router.post("/users/{email}/tokens/{issue_date}/revoke", response_model=TokenOut)
def revoke_token(email: str, issue_date: int):
    token_row = db.get_token(email, issue_date)
    if token_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    db.revoke_token(email, issue_date)
    return TokenOut(issue_date=issue_date, revoked=True, token=encode_jwt(email, issue_date))


@router.get("/users/{email}/tokens/{issue_date}/continue-config")
def download_continue_config(email: str, issue_date: int):
    token_row = db.get_token(email, issue_date)
    if token_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    filled = render_continue_config(email, issue_date)
    filename = f"hound-coder-continue-config-{email}.yaml"
    return Response(
        content=filled,
        media_type="application/yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/blocklist", response_model=list[BlockedOut])
def list_blocklist():
    return [BlockedOut(email=b.email, blocked_at=b.blocked_at, reason=b.reason) for b in db.list_blocked()]


@router.post("/blocklist", response_model=BlockedOut, status_code=status.HTTP_201_CREATED)
def block_email(entry: BlockEntry):
    now = int(time.time())
    db.block_email(entry.email, entry.reason, now)
    db.revoke_all_tokens(entry.email)
    return BlockedOut(email=entry.email, blocked_at=now, reason=entry.reason)


@router.delete("/blocklist/{email}", status_code=status.HTTP_204_NO_CONTENT)
def unblock_email(email: str):
    db.unblock_email(email)
