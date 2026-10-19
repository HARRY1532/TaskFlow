import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from pwdlib import PasswordHash
from sqlalchemy.orm import Session

from .db import get_db
from .models import User

load_dotenv()
password_hash = PasswordHash.recommended()
bearer = HTTPBearer()


def jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET_KEY", "")
    if len(secret) < 32 or secret == "replace-with-a-long-random-secret":
        raise RuntimeError("请在 backend/.env 中设置至少 32 字符的 JWT_SECRET_KEY")
    return secret


def create_token(user_id: int) -> str:
    expiry = datetime.now(timezone.utc) + timedelta(hours=12)
    return jwt.encode({"sub": str(user_id), "exp": expiry}, jwt_secret(), algorithm="HS256")


def current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    try:
        payload = jwt.decode(credentials.credentials, jwt_secret(), algorithms=["HS256"])
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise HTTPException(401, "登录已失效") from None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(401, "账号不存在或已停用")
    return user
