"""学习流程：今日任务生成 / 答题提交 / 今日进度。"""

import random
import re
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import PHASE_VALUES, RESULT_VALUES, StudyLog, User, Word, WordBook, WordState
from app.schemas import AnswerIn, AnswerOut, ProgressOut, QuizOut, StudyWordOut, TodayOut
from app.seed import ensure_settings
from app.services.scheduler import apply_answer, to_local_date, utcnow_naive

router = APIRouter(prefix="/api/study", tags=["学习"])


class _OptionPool:
    """一次请求内复用的干扰项候选，避免每个单词都查一次数据库。"""

    def __init__(self, spellings: list[str], definitions: list[str]) -> None:
        self.spellings = tuple(spellings)
        self.definitions = tuple(definitions)


def _unique_nonempty(values) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = (value or "").strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return result


def _book_option_pool(db: Session, book_id: int) -> _OptionPool:
    spellings = db.scalars(select(Word.spelling).where(Word.book_id == book_id)).all()
    definitions = db.scalars(select(Word.definition).where(Word.book_id == book_id)).all()
    return _OptionPool(_unique_nonempty(spellings), _unique_nonempty(definitions))


def _sample_others(values: tuple[str, ...] | list[str], correct: str, n: int = 3) -> list[str]:
    """从候选池随机取 n 个不同于正确项的值（有界重试 + 线性兜底）。"""
    if not values:
        return []
    blocked = {correct.strip().lower()}
    picked: list[str] = []
    for _ in range(max(20, n * 10)):
        value = random.choice(values)
        key = value.strip().lower()
        if key in blocked:
            continue
        blocked.add(key)
        picked.append(value)
        if len(picked) == n:
            return picked
    for value in values:
        key = value.strip().lower()
        if key in blocked:
            continue
        blocked.add(key)
        picked.append(value)
        if len(picked) == n:
            break
    return picked


def _random_others(db: Session, book_id: int, exclude_id: int, column, n: int = 3) -> list[str]:
    """兼容路径：没有预取候选池时按需查询（测试/单题调用）。"""
    vals = db.scalars(
        select(column)
        .where(Word.book_id == book_id, Word.id != exclude_id)
        .order_by(func.rand())
        .limit(n + 2)  # 多取几个，去掉重复释义后仍有 3 个干扰项
    ).all()
    return _unique_nonempty(vals)


def _inflection_forms(spelling: str) -> list[str]:
    """生成常见屈折形式（复数 / 过去式 / 进行式等），用于例句挖空。"""
    s = spelling.lower()
    forms = {s, s + "s", s + "es", s + "ed", s + "d", s + "ing"}
    if s.endswith("e"):
        forms.add(s[:-1] + "ing")  # analyze → analyzing
    if s.endswith("y"):
        forms.add(s[:-1] + "ied")  # carry → carried
        forms.add(s[:-1] + "ies")  # carry → carries
    if len(s) >= 3 and s[-1] not in "aeiou" and s[-2] in "aeiou" and s[-3] not in "aeiou":
        forms.add(s + s[-1] + "ing")  # run → running
        forms.add(s + s[-1] + "ed")
    return sorted(forms, key=len, reverse=True)


def _pack_options(correct: str, others: list[str]) -> dict:
    """生成 4 个选项（含正确项）并打乱。"""
    options, seen = [], {correct.strip().lower()}
    for o in others:
        key = o.strip().lower()
        if key and key not in seen:
            seen.add(key)
            options.append(o)
        if len(options) == 3:
            break
    options.append(correct)
    random.shuffle(options)
    return {"options": options, "answer_index": options.index(correct)}


def build_quiz(
    db: Session,
    word: Word,
    mode: str | None = None,
    pool: _OptionPool | None = None,
) -> QuizOut | None:
    """为单词生成测试题：en2cn 看英选中 / cn2en 看中选英 / cloze 例句挖空。

    传入 pool 时从预取候选池取干扰项（O(1) 次查询）；否则保留按需查询的兼容路径。
    """
    if mode is None:
        mode = random.choice(["en2cn", "cn2en"])

    if mode == "cloze" and word.example_en:
        forms = _inflection_forms(word.spelling)
        pattern = r"\b(?:" + "|".join(re.escape(f) for f in forms) + r")\b"
        sentence = re.sub(pattern, "____", word.example_en, count=1, flags=re.IGNORECASE)
        if "____" in sentence:
            others = (
                _sample_others(pool.spellings, word.spelling)
                if pool is not None
                else _random_others(db, word.book_id, word.id, Word.spelling)
            )
            packed = _pack_options(word.spelling, others)
            return QuizOut(type="cloze", question=sentence, **packed)
        mode = "en2cn"  # 例句里挖不出该词，退化为看英选中

    if mode == "en2cn":
        others = (
            _sample_others(pool.definitions, word.definition)
            if pool is not None
            else _random_others(db, word.book_id, word.id, Word.definition)
        )
        packed = _pack_options(word.definition, others)
        return QuizOut(type="en2cn", question=word.spelling, **packed)

    others = (
        _sample_others(pool.spellings, word.spelling)
        if pool is not None
        else _random_others(db, word.book_id, word.id, Word.spelling)
    )
    packed = _pack_options(word.spelling, others)
    return QuizOut(type="cn2en", question=word.definition, **packed)


def _to_study_word(
    db: Session,
    state: WordState,
    quiz_mode: str | None = None,
    pool: _OptionPool | None = None,
) -> StudyWordOut:
    w = state.word
    quiz = build_quiz(db, w, quiz_mode, pool)
    return StudyWordOut(
        id=w.id,
        spelling=w.spelling,
        phonetic=w.phonetic,
        definition=w.definition,
        example_en=w.example_en,
        example_cn=w.example_cn,
        status=state.status,
        quiz=quiz,
    )


@router.get("/today", response_model=TodayOut)
def today_task(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    setting = ensure_settings(db, user.id)
    if not setting.active_book_id:
        raise HTTPException(400, "还没有选择词书，请先在「词书管理」上传并选择词书")
    owned = db.scalar(
        select(WordBook.id).where(
            WordBook.id == setting.active_book_id, WordBook.user_id == user.id
        )
    )
    if owned is None:
        raise HTTPException(400, "当前词书不存在，请重新选择词书")
    book_id = setting.active_book_id
    now = utcnow_naive()
    pool = _book_option_pool(db, book_id)

    # 复习池：已学习的到期词，按到期时间升序、遗忘次数降序
    review_states = db.scalars(
        select(WordState)
        .options(selectinload(WordState.word))
        .where(
            WordState.book_id == book_id,
            WordState.stability.is_not(None),
            WordState.due <= now,
        )
        .order_by(WordState.due.asc(), WordState.lapses.desc())
        .limit(setting.review_per_day)
    ).all()

    # 新词池：stability 为 NULL 表示尚未学习，按词书原序
    new_states = db.scalars(
        select(WordState)
        .options(selectinload(WordState.word))
        .where(WordState.book_id == book_id, WordState.stability.is_(None))
        .join(Word, Word.id == WordState.word_id)
        .order_by(Word.seq.asc())
        .limit(setting.new_per_day)
    ).all()

    return TodayOut(
        new_words=[_to_study_word(db, s, "cloze", pool) for s in new_states],
        review_words=[_to_study_word(db, s, None, pool) for s in review_states],
        new_target=min(setting.new_per_day, len(new_states)),
        review_target=min(setting.review_per_day, len(review_states)),
    )


@router.post("/answer", response_model=AnswerOut)
def submit_answer(
    body: AnswerIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.phase not in PHASE_VALUES or body.result not in RESULT_VALUES:
        raise HTTPException(400, "phase 或 result 取值非法")

    # 只能作答当前账号自己词书里的单词
    state = db.scalar(
        select(WordState)
        .join(Word, Word.id == WordState.word_id)
        .join(WordBook, WordBook.id == Word.book_id)
        .where(WordState.word_id == body.word_id, WordBook.user_id == user.id)
    )
    if not state:
        raise HTTPException(404, "单词不存在")

    apply_answer(state, body.result)
    db.add(
        StudyLog(
            user_id=user.id,
            word_id=body.word_id,
            phase=body.phase,
            result=body.result,
        )
    )
    db.commit()
    return AnswerOut(
        status=state.status,
        stability=state.stability,
        difficulty=state.difficulty,
        due_date=to_local_date(state.due),
    )


@router.get("/progress", response_model=ProgressOut)
def today_progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    setting = ensure_settings(db, user.id)
    day_start = datetime.combine(date.today(), time.min)

    logs = db.execute(
        select(StudyLog.word_id, StudyLog.phase).where(
            StudyLog.user_id == user.id,
            StudyLog.studied_at >= day_start,
        )
    ).all()
    new_done = len({w for w, p in logs if p in ("new_first", "new_quiz")})
    review_done = len({w for w, p in logs if p in ("review", "relearn")})

    new_target, review_target = setting.new_per_day, setting.review_per_day
    owns_active_book = setting.active_book_id is not None and db.scalar(
        select(WordBook.id).where(
            WordBook.id == setting.active_book_id, WordBook.user_id == user.id
        )
    )
    if owns_active_book:
        now = utcnow_naive()
        remaining_new = (
            db.scalar(
                select(func.count())
                .select_from(WordState)
                .where(
                    WordState.book_id == setting.active_book_id,
                    WordState.stability.is_(None),
                )
            )
            or 0
        )
        remaining_due = (
            db.scalar(
                select(func.count())
                .select_from(WordState)
                .where(
                    WordState.book_id == setting.active_book_id,
                    WordState.stability.is_not(None),
                    WordState.due <= now,
                )
            )
            or 0
        )
        new_target = min(new_target, new_done + int(remaining_new))
        review_target = min(review_target, review_done + int(remaining_due))

    return ProgressOut(
        new_target=new_target,
        review_target=review_target,
        new_done=new_done,
        review_done=review_done,
    )
