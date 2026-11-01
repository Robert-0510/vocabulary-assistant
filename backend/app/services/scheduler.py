"""FSRS 间隔重复调度（基于官方 py-fsrs 实现，取代原 SM-2 变体）。

评分映射（应用交互 → FSRS Rating）：
- 不认识 / 答错 / 全错 → Again（遗忘，未毕业，当日重学）
- 认识 / 答对 / 全对   → Good（毕业进入复习）
- 部分正确（多选漏选但未全错） → Hard（义项级 / 多选首次启用的档位）
- 熟知          → Easy（更长的复习间隔）

学习/重学步进设为单步 1 分钟：让「不认识 / 答错」的卡片保持未毕业状态、
由前端会话内队列当日重学，答对即毕业进入 Review。day 级间隔由 FSRS
根据记忆稳定性（stability）与难度（difficulty）计算。

时间约定：`due` / `last_review` 以 UTC 存储（MySQL DATETIME 为 naive），
只在进入 FSRS 时附加 UTC 时区、落库时剥离；查询比较统一用 naive UTC。
"""

from datetime import UTC, datetime, timedelta

from fsrs import Card, Rating, Scheduler, State

MASTERED_THRESHOLD = 90.0  # 记忆稳定性 ≥ 90 天视为「已掌握」

RESULT_TO_RATING: dict[str, Rating] = {
    "unknown": Rating.Again,
    "wrong": Rating.Again,
    "know": Rating.Good,
    "correct": Rating.Good,
    "partial": Rating.Hard,
    "master": Rating.Easy,
}

_scheduler = Scheduler(
    learning_steps=(timedelta(minutes=1),),
    relearning_steps=(timedelta(minutes=1),),
    enable_fuzzing=False,
)


def utcnow() -> datetime:
    """带时区的当前 UTC 时间（传给 FSRS）。"""
    return datetime.now(UTC)


def utcnow_naive() -> datetime:
    """无时区的当前 UTC 时间（与落库的 due 比较）。"""
    return datetime.now(UTC).replace(tzinfo=None)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _naive(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.astimezone(UTC).replace(tzinfo=None)


def to_local_date(dt: datetime | None):
    """UTC（naive）转本地日期，仅用于展示「到期日」。"""
    if dt is None:
        return None
    return _aware(dt).astimezone().date()


def to_card(state) -> Card:
    """由 WordState 重建 FSRS Card；stability 为 NULL 表示尚未学习的新词。"""
    if state.stability is None:
        return Card()
    return Card(
        state=State(state.state),
        step=state.step,
        stability=float(state.stability),
        difficulty=float(state.difficulty),
        due=_aware(state.due),
        last_review=_aware(state.last_review),
    )


def derive_status(state_value: int, stability) -> str:
    if stability is None:
        return "new"
    if state_value in (State.Learning.value, State.Relearning.value):
        return "learning"
    if float(stability) >= MASTERED_THRESHOLD:
        return "mastered"
    return "reviewing"


def apply_answer(state, result: str, now: datetime | None = None) -> None:
    """按 FSRS 就地更新 WordState（等价于旧的 SM-2 apply_answer）。"""
    now = now or utcnow()
    rating = RESULT_TO_RATING[result]
    card = to_card(state)
    card, _log = _scheduler.review_card(card, rating, now)

    state.state = int(card.state)
    state.step = card.step
    state.stability = float(card.stability) if card.stability is not None else None
    state.difficulty = float(card.difficulty) if card.difficulty is not None else None
    state.due = _naive(card.due)
    state.last_review = _naive(card.last_review)

    if rating == Rating.Again:
        state.lapses += 1
        state.reps = 0
    else:
        state.reps += 1

    state.status = derive_status(state.state, state.stability)
