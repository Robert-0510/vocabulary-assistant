"""统计：总览 / 打卡日历 / 近 N 天曲线。"""

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import STATUS_VALUES, StudyLog, User, WordBook, WordState
from app.schemas import CalendarDay, RecentDay, StatsOverview

router = APIRouter(prefix="/api/stats", tags=["统计"])


def _month_days(year: int, month: int) -> list[date]:
    d = date(year, month, 1)
    if month == 12:
        nxt = date(year + 1, 1, 1)
    else:
        nxt = date(year, month + 1, 1)
    days = []
    while d < nxt:
        days.append(d)
        d += timedelta(days=1)
    return days


@router.get("/overview", response_model=StatsOverview)
def overview(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    counts = dict(
        db.execute(
            select(WordState.status, func.count())
            .join(WordBook, WordBook.id == WordState.book_id)
            .where(WordBook.user_id == user.id)
            .group_by(WordState.status)
        ).all()
    )
    counts = {s: int(counts.get(s, 0)) for s in STATUS_VALUES}

    dates = sorted(
        {
            d
            for (d,) in db.execute(
                select(func.distinct(func.date(StudyLog.studied_at))).where(
                    StudyLog.user_id == user.id
                )
            ).all()
        },
        reverse=True,
    )
    streak = 0
    if dates:
        cursor = date.today() if dates[0] == date.today() else date.today() - timedelta(days=1)
        for d in dates:
            if d == cursor:
                streak += 1
                cursor -= timedelta(days=1)
            else:
                break

    day_start = datetime.combine(date.today(), time.min)
    learned_today = len(
        set(
            db.scalars(
                select(StudyLog.word_id).where(
                    StudyLog.user_id == user.id,
                    StudyLog.studied_at >= day_start,
                )
            ).all()
        )
    )
    return StatsOverview(
        total_words=sum(counts.values()),
        **counts,
        streak_days=streak,
        total_days=len(dates),
        learned_today=learned_today,
    )


@router.get("/calendar", response_model=list[CalendarDay])
def calendar(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        year, mon = map(int, month.split("-"))
        start = date(year, mon, 1)
    except ValueError as exc:
        raise HTTPException(400, "month 格式应为 YYYY-MM") from exc

    end = _month_days(year, mon)[-1]
    rows = db.execute(
        select(func.date(StudyLog.studied_at), StudyLog.word_id).where(
            StudyLog.user_id == user.id,
            StudyLog.studied_at >= datetime.combine(start, time.min),
            StudyLog.studied_at < datetime.combine(end + timedelta(days=1), time.min),
        )
    ).all()
    per_day: dict[str, set[int]] = {}
    for d, word_id in rows:
        per_day.setdefault(str(d), set()).add(word_id)

    return [
        CalendarDay(date=str(d), count=len(per_day.get(str(d), ()))) for d in _month_days(year, mon)
    ]


@router.get("/recent", response_model=list[RecentDay])
def recent(
    days: int = Query(30, ge=1, le=120),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    start = date.today() - timedelta(days=days - 1)
    rows = db.execute(
        select(func.date(StudyLog.studied_at), StudyLog.phase, StudyLog.word_id).where(
            StudyLog.user_id == user.id,
            StudyLog.studied_at >= datetime.combine(start, time.min),
        )
    ).all()
    per_day: dict[str, dict[str, set[int]]] = {}
    for d, phase, word_id in rows:
        bucket = per_day.setdefault(str(d), {"new": set(), "review": set()})
        if phase in ("new_first", "new_quiz"):
            bucket["new"].add(word_id)
        else:
            bucket["review"].add(word_id)

    result = []
    cur = start
    while cur <= date.today():
        b = per_day.get(str(cur), {})
        result.append(
            RecentDay(
                date=str(cur),
                new_count=len(b.get("new", ())),
                review_count=len(b.get("review", ())),
            )
        )
        cur += timedelta(days=1)
    return result
