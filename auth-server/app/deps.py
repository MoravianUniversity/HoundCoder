"""FastAPI dependencies for validating bearer tokens and admin access."""
from fastapi import Depends, Header, HTTPException, status
import jwt

from . import db
from .security import decode_jwt


def get_current_user(authorization: str | None = Header(default=None)) -> db.User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    token = authorization.split(" ", 1)[1]

    try:
        payload = decode_jwt(token)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    email = payload["email"]
    issue_date = payload["iat"]

    user = db.get_user(email)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")

    token_row = db.get_token(email, issue_date)
    if token_row is None or token_row.revoked:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token revoked")

    return user


def require_admin(user: db.User = Depends(get_current_user)) -> db.User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user
