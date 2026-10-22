"""账号鉴权：PBKDF2 密码哈希、服务端会话、当前用户依赖。

会话采用「随机 token + 服务端存储哈希」：
- Cookie 里是原始 token（HttpOnly）；
- 数据库只保存 SHA-256，泄库也无法直接复用；
- 会话 30 天过期，登出/注销时物理删除。
"""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import config
from app.database import get_db
from app.models import User, UserSession

SESSION_COOKIE = "va_session"
SESSION_TTL = timedelta(days=config.SESSION_TTL_DAYS)
_PBKDF2_ITERATIONS = 260_000


def utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user_id: int) -> str:
    """签发新会话，并顺手清理已过期的会话。"""
    token = secrets.token_urlsafe(32)
    now = utcnow_naive()
    db.execute(delete(UserSession).where(UserSession.expires_at <= now))
    db.add(
        UserSession(
            token_hash=_token_hash(token),
            user_id=user_id,
            expires_at=now + SESSION_TTL,
        )
    )
    db.commit()
    return token


def revoke_session(db: Session, token: str | None) -> None:
    if not token:
        return
    db.execute(delete(UserSession).where(UserSession.token_hash == _token_hash(token)))
    db.commit()


def revoke_all_sessions(db: Session, user_id: int) -> None:
    """吊销某个账号的全部会话（修改密码后强制重新登录）。"""
    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
    db.commit()


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=int(SESSION_TTL.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=config.COOKIE_SECURE,  # 本地 HTTP 为 false；HTTPS 部署改为 true
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(401, "请先登录")
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == _token_hash(token),
            UserSession.expires_at > utcnow_naive(),
        )
    )
    if session is None:
        raise HTTPException(401, "登录已过期，请重新登录")
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(401, "请先登录")
    return user
