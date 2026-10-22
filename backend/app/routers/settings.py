"""设置：每日任务量 / 当前词书（按账号隔离）。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User, WordBook
from app.schemas import SettingsIn, SettingsOut
from app.seed import ensure_settings

router = APIRouter(prefix="/api/settings", tags=["设置"])


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    s = ensure_settings(db, user.id)
    return SettingsOut(
        new_per_day=s.new_per_day,
        review_per_day=s.review_per_day,
        active_book_id=s.active_book_id,
    )


@router.put("", response_model=SettingsOut)
def update_settings(
    body: SettingsIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = ensure_settings(db, user.id)
    s.new_per_day = body.new_per_day
    s.review_per_day = body.review_per_day
    if body.active_book_id is not None:
        owned = db.scalar(
            select(WordBook.id).where(
                WordBook.id == body.active_book_id, WordBook.user_id == user.id
            )
        )
        if owned is None:
            raise HTTPException(404, "词书不存在")
        s.active_book_id = body.active_book_id
    db.commit()
    return SettingsOut(
        new_per_day=s.new_per_day,
        review_per_day=s.review_per_day,
        active_book_id=s.active_book_id,
    )
