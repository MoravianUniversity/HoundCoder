"""JWT encoding/decoding and signing-secret management."""
import os
import stat

import jwt

DATA_DIR = os.environ.get("AUTH_DATA_DIR", "/opt/hound-coder/auth")
SECRET_PATH = os.path.join(DATA_DIR, "jwt_secret.key")
ALGORITHM = "HS256"


def _load_or_create_secret() -> str:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(SECRET_PATH):
        with open(SECRET_PATH, "r") as f:
            return f.read().strip()
    secret = os.urandom(32).hex()
    fd = os.open(SECRET_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "w") as f:
        f.write(secret)
    return secret


_secret = None


def get_secret() -> str:
    global _secret
    if _secret is None:
        _secret = _load_or_create_secret()
    return _secret


def encode_jwt(email: str, issue_date: int) -> str:
    payload = {"email": email, "iat": issue_date}
    return jwt.encode(payload, get_secret(), algorithm=ALGORITHM)


def decode_jwt(token: str) -> dict:
    """Verify signature and required claims; raises jwt.PyJWTError on failure."""
    return jwt.decode(
        token,
        get_secret(),
        algorithms=[ALGORITHM],
        options={"require": ["email", "iat"], "verify_exp": False},
    )
