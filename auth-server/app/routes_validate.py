"""Internal endpoint used by nginx auth_request to validate bearer tokens."""
from fastapi import APIRouter, Depends

from .db import User
from .deps import get_current_user

router = APIRouter()


@router.get("/validate")
def validate(user: User = Depends(get_current_user)):
    return {"email": user.email}
