"""账号：注册 / 登录 / 登出 / 当前用户 / 硬删除注销。"""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_COOKIE,
    clear_session_cookie,
    create_session,
    get_current_user,
    hash_password,
    revoke_all_sessions,
    revoke_session,
    set_session_cookie,
    verify_password,
)
from app.config import config
from app.database import get_db
from app.models import AppSetting, User
from app.schemas import AuthIn, ChangePasswordIn, DeleteAccountIn, UserOut
from app.services.rate_limit import client_ip, enforce

router = APIRouter(prefix="/api/auth", tags=["账号"])


def _clean_username(raw: str) -> str:
    username = raw.strip()
    if not (2 <= len(username) <= 32) or any(ch.isspace() for ch in username):
        raise HTTPException(422, "用户名需为 2–32 个字符且不能包含空白")
    return username


def _clean_password(raw: str) -> str:
    if not (8 <= len(raw) <= 128):
        raise HTTPException(422, "密码长度需为 8–128 个字符")
    return raw


@router.post("/register", response_model=UserOut)
def register(body: AuthIn, request: Request, response: Response, db: Session = Depends(get_db)):
    enforce(f"register:{client_ip(request)}", config.REGISTER_RATE_LIMIT, 3600)
    username = _clean_username(body.username)
    password = _clean_password(body.password)
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "用户名已被注册")

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "用户名已被注册") from exc

    user_id = user.id
    db.add(AppSetting(user_id=user_id))
    db.commit()

    token = create_session(db, user_id)
    set_session_cookie(response, token)
    return UserOut(id=user_id, username=username)


@router.post("/login", response_model=UserOut)
def login(body: AuthIn, request: Request, response: Response, db: Session = Depends(get_db)):
    username = body.username.strip()
    enforce(
        f"login:{client_ip(request)}:{username.lower()}",
        config.LOGIN_RATE_LIMIT,
        60,
    )
    user = db.scalar(select(User).where(User.username == username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")

    token = create_session(db, user.id)
    set_session_cookie(response, token)
    return UserOut(id=user.id, username=user.username)


@router.post("/change-password")
def change_password(
    body: ChangePasswordIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改密码：成功后吊销全部会话，要求使用新密码重新登录。"""
    enforce(f"password:{user.id}", config.PASSWORD_RATE_LIMIT, 600)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "当前密码错误")
    new_password = _clean_password(body.new_password)
    if new_password == body.current_password:
        raise HTTPException(400, "新密码不能与当前密码相同")

    user.password_hash = hash_password(new_password)
    db.commit()
    revoke_all_sessions(db, user.id)
    clear_session_cookie(response)
    return {"ok": True}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    revoke_session(db, request.cookies.get(SESSION_COOKIE))
    clear_session_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username)


@router.post("/delete-account")
def delete_account(
    body: DeleteAccountIn,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """硬删除账号：密码确认后物理删除 users 行，由外键级联清除全部数据。"""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(400, "密码错误，无法注销账号")

    db.execute(delete(User).where(User.id == user.id))
    db.commit()
    clear_session_cookie(response)
    return {"ok": True}
