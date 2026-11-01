"""学习流程：今日任务生成 / 答题提交 / 今日进度。

题型分层：
- meaning_multi：看英文单词，多选全部释义（义项），词级卡 word_states 计分；
- equiv_group：看锚词，多选同义组成员，义项卡 sense_states 计分，选项词不写状态；
- en2cn / cn2en / cloze：词书没有义项数据时的兜底题型（旧契约）。
多选判分在服务端完成，今日任务响应不包含正确集合。
"""

import random
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    PHASE_VALUES,
    RESULT_VALUES,
    Sense,
    SenseState,
    StudyLog,
    User,
    Word,
    WordBook,
    WordSense,
    WordState,
)
from app.schemas import (
    AnswerIn,
    AnswerOut,
    LegacyQuizOut,
    MultiQuizOut,
    ProgressOut,
    QuizOptionOut,
    StudyWordOut,
    TodayOut,
)
from app.seed import ensure_settings
from app.services.scheduler import apply_answer, to_local_date, utcnow_naive

router = APIRouter(prefix="/api/study", tags=["学习"])


class _OptionPool:
    """一次请求内复用的单词表：干扰项、音标、拼写都从这里取。"""

    def __init__(self, words: list[Word]) -> None:
        self.words = words
        self.by_id = {word.id: word for word in words}
        self.spellings = tuple(_unique_nonempty(word.spelling for word in words))
        self.definitions = tuple(_unique_nonempty(word.definition for word in words))


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
    words = db.scalars(
        select(Word).where(Word.book_id == book_id).order_by(Word.seq.asc(), Word.id.asc())
    ).all()
    return _OptionPool(list(words))


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
) -> LegacyQuizOut | None:
    """旧题型兜底：en2cn 看英选中 / cn2en 看中选英 / cloze 例句挖空。"""
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
            return LegacyQuizOut(type="cloze", question=sentence, **packed)
        mode = "en2cn"  # 例句里挖不出该词，退化为看英选中

    if mode == "en2cn":
        others = (
            _sample_others(pool.definitions, word.definition)
            if pool is not None
            else _random_others(db, word.book_id, word.id, Word.definition)
        )
        packed = _pack_options(word.definition, others)
        return LegacyQuizOut(type="en2cn", question=word.spelling, **packed)

    others = (
        _sample_others(pool.spellings, word.spelling)
        if pool is not None
        else _random_others(db, word.book_id, word.id, Word.spelling)
    )
    packed = _pack_options(word.spelling, others)
    return LegacyQuizOut(type="cn2en", question=word.definition, **packed)


class _SenseIndex:
    """一本书的义项图：词→义项、义项→成员、义项名。"""

    def __init__(self, rows) -> None:
        self.word_to_senses: dict[int, set[int]] = defaultdict(set)
        self.sense_to_words: dict[int, set[int]] = defaultdict(set)
        self.label_by_sense: dict[int, str] = {}
        self.pos_by_sense: dict[int, str] = {}
        for word_id, sense_id, label, pos in rows:
            self.word_to_senses[int(word_id)].add(int(sense_id))
            self.sense_to_words[int(sense_id)].add(int(word_id))
            self.label_by_sense[int(sense_id)] = label
            self.pos_by_sense[int(sense_id)] = pos

    def __bool__(self) -> bool:
        return bool(self.label_by_sense)


def _load_sense_index(db: Session, book_id: int) -> _SenseIndex:
    rows = db.execute(
        select(WordSense.word_id, WordSense.sense_id, Sense.label_zh, Sense.pos)
        .join(Sense, Sense.id == WordSense.sense_id)
        .where(
            WordSense.book_id == book_id,
            WordSense.status == "active",
            Sense.status == "active",
        )
    ).all()
    return _SenseIndex(rows)


def _pick_anchor(members: set[int], index: _SenseIndex) -> int:
    """等价组代表词：图内度=1（叶子）优先，其次按词 ID 稳定排序。"""
    return min(members, key=lambda word_id: (len(index.word_to_senses.get(word_id, ())), word_id))


def _build_meaning_quiz(word: Word, index: _SenseIndex) -> MultiQuizOut | None:
    """多选释义：单义词 4 选 1；多义词 max(5, n+2) 选 n。"""
    sense_ids = sorted(index.word_to_senses.get(word.id, ()))
    if not sense_ids:
        return None

    raw_texts = [index.label_by_sense[sense_id] for sense_id in sense_ids]
    duplicated = {text for text, count in Counter(raw_texts).items() if count > 1}

    def display(sense_id: int) -> str:
        text = index.label_by_sense[sense_id]
        # 同一个词的两个义项展示名相同（例如仅词性不同）时，用词性消歧
        if text in duplicated:
            return f"{text}（{index.pos_by_sense.get(sense_id, '')}）"
        return text

    correct_texts = [display(sense_id) for sense_id in sense_ids]
    if len({text.lower() for text in correct_texts}) != len(correct_texts):
        return None

    option_count = 4 if len(sense_ids) == 1 else max(5, len(sense_ids) + 2)
    used_texts = {text.lower() for text in correct_texts}
    distractor_pool: list[int] = []
    for sense_id, label in index.label_by_sense.items():
        if sense_id in index.word_to_senses[word.id] or label.lower() in used_texts:
            continue
        distractor_pool.append(sense_id)
        used_texts.add(label.lower())
    needed = option_count - len(sense_ids)
    if len(distractor_pool) < needed:
        return None
    picks = random.sample(distractor_pool, needed)

    options = [QuizOptionOut(id=sense_id, text=display(sense_id)) for sense_id in sense_ids]
    options += [
        QuizOptionOut(id=sense_id, text=index.label_by_sense[sense_id]) for sense_id in picks
    ]
    random.shuffle(options)
    return MultiQuizOut(
        type="meaning_multi",
        question=word.spelling,
        options=options,
        option_count=len(options),
    )


def _build_equiv_quiz(
    sense_id: int, index: _SenseIndex, pool: _OptionPool
) -> tuple[MultiQuizOut, int] | None:
    """等价组：锚词 + 星内成员 + 2 个星外干扰词；正确项 = 星内除锚词外的全部。"""
    members = index.sense_to_words.get(sense_id, set())
    if len(members) < 2:
        return None
    anchor_id = _pick_anchor(members, index)
    anchor = pool.by_id.get(anchor_id)
    if anchor is None:
        return None

    correct_ids = members - {anchor_id}
    correct_words = [
        pool.by_id[word_id] for word_id in sorted(correct_ids) if word_id in pool.by_id
    ]
    if not correct_words:
        return None

    blocked_ids = {word.id for word in correct_words} | {anchor_id}
    blocked_spellings = {word.spelling.lower() for word in correct_words} | {
        anchor.spelling.lower()
    }
    candidates = [
        word
        for word in pool.words
        if word.id not in blocked_ids and word.spelling.lower() not in blocked_spellings
    ]
    if len(candidates) < 2:
        return None
    distractors = random.sample(candidates, 2)

    options = [
        QuizOptionOut(id=word.id, text=word.spelling) for word in correct_words + distractors
    ]
    random.shuffle(options)
    return (
        MultiQuizOut(
            type="equiv_group",
            question=anchor.spelling,
            options=options,
            option_count=len(options),
        ),
        anchor_id,
    )


def _to_study_word(
    db: Session,
    state: WordState,
    quiz_mode: str | None = None,
    pool: _OptionPool | None = None,
    index: _SenseIndex | None = None,
) -> StudyWordOut:
    w = state.word
    quiz = _build_meaning_quiz(w, index) if index and index else None
    if quiz is None:
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


def _to_sense_item(
    state: SenseState, sense: Sense, index: _SenseIndex, pool: _OptionPool
) -> StudyWordOut | None:
    built = _build_equiv_quiz(sense.id, index, pool)
    if built is None:
        return None
    quiz, anchor_id = built
    anchor = pool.by_id[anchor_id]
    return StudyWordOut(
        id=sense.id,
        spelling=anchor.spelling,
        phonetic=anchor.phonetic,
        definition=sense.label_zh,
        status=state.status,
        quiz=quiz,
    )


def _grade_selection(selected: set[int], correct: set[int]) -> tuple[str, int]:
    """全对 → correct；有交集但漏选/错选 → partial；一个没中 → wrong。"""
    hit = len(selected & correct)
    if selected == correct:
        return "correct", hit
    if hit == 0:
        return "wrong", 0
    return "partial", hit


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
    index = _load_sense_index(db, book_id)

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

    # 义项卡：到期的 sense_states，生成 equiv_group
    sense_rows = db.execute(
        select(SenseState, Sense)
        .join(Sense, Sense.id == SenseState.sense_id)
        .where(
            SenseState.book_id == book_id,
            SenseState.due <= now,
            Sense.status == "active",
        )
        .order_by(SenseState.due.asc(), SenseState.lapses.desc(), SenseState.id.asc())
        .limit(setting.review_per_day)
    ).all()
    sense_items: list[StudyWordOut] = []
    for sense_state, sense in sense_rows:
        item = _to_sense_item(sense_state, sense, index, pool)
        if item is not None:
            sense_items.append(item)

    return TodayOut(
        new_words=[_to_study_word(db, s, "cloze", pool, index) for s in new_states],
        review_words=[_to_study_word(db, s, None, pool, index) for s in review_states],
        sense_items=sense_items,
        sense_target=len(sense_items),
        new_target=min(setting.new_per_day, len(new_states)),
        review_target=min(setting.review_per_day, len(review_states)),
    )


def _legacy_answer(body: AnswerIn, db: Session, user: User) -> AnswerOut:
    """旧契约：word_id + result，前端判分；保留以兼容旧客户端与旧测试。"""
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
        result=body.result,
    )


def _answer_word(body: AnswerIn, db: Session, user: User) -> AnswerOut:
    """词级多选：正确集合 = 该词当前全部 active 义项。"""
    state = db.scalar(
        select(WordState)
        .join(Word, Word.id == WordState.word_id)
        .join(WordBook, WordBook.id == Word.book_id)
        .where(WordState.word_id == body.target_id, WordBook.user_id == user.id)
    )
    if not state:
        raise HTTPException(404, "单词不存在")

    correct = {
        int(sense_id)
        for sense_id in db.scalars(
            select(WordSense.sense_id)
            .join(Sense, Sense.id == WordSense.sense_id)
            .where(
                WordSense.word_id == body.target_id,
                WordSense.status == "active",
                Sense.status == "active",
            )
        ).all()
    }
    if not correct:
        raise HTTPException(400, "该词没有可判分的义项")

    selected = {int(value) for value in body.selected_ids}
    result, hit = _grade_selection(selected, correct)
    phase = body.phase or "meaning"
    apply_answer(state, result)
    db.add(StudyLog(user_id=user.id, word_id=body.target_id, phase=phase, result=result))
    db.commit()
    return AnswerOut(
        status=state.status,
        stability=state.stability,
        difficulty=state.difficulty,
        due_date=to_local_date(state.due),
        result=result,
        selected_correct=hit,
        correct_total=len(correct),
        correct_ids=sorted(correct),
    )


def _answer_sense(body: AnswerIn, db: Session, user: User) -> AnswerOut:
    """义项级多选：只更新 sense_states，选项词（含锚词）的 word_states 不变。"""
    row = db.execute(
        select(Sense, SenseState)
        .join(WordBook, WordBook.id == Sense.book_id)
        .outerjoin(SenseState, SenseState.sense_id == Sense.id)
        .where(Sense.id == body.target_id, WordBook.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(404, "义项不存在")
    sense, state = row
    if sense.status != "active":
        raise HTTPException(400, "该义项尚未启用")

    index = _load_sense_index(db, sense.book_id)
    members = set(index.sense_to_words.get(sense.id, ()))
    if len(members) < 2:
        raise HTTPException(400, "该义项没有可考的同义成员")
    anchor_id = _pick_anchor(members, index)
    correct = members - {anchor_id}

    if state is None:
        state = SenseState(
            sense_id=sense.id,
            book_id=sense.book_id,
            due=utcnow_naive() - timedelta(seconds=1),
        )
        db.add(state)
        db.flush()

    selected = {int(value) for value in body.selected_ids}
    result, hit = _grade_selection(selected, correct)
    phase = body.phase or "group"
    apply_answer(state, result)
    db.add(StudyLog(user_id=user.id, word_id=anchor_id, phase=phase, result=result))
    db.commit()
    return AnswerOut(
        status=state.status,
        stability=state.stability,
        difficulty=state.difficulty,
        due_date=to_local_date(state.due),
        result=result,
        selected_correct=hit,
        correct_total=len(correct),
        correct_ids=sorted(correct),
    )


@router.post("/answer", response_model=AnswerOut)
def submit_answer(
    body: AnswerIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # 旧契约优先：word_id + result 同时出现时按旧路径处理
    if body.word_id is not None and body.result is not None:
        return _legacy_answer(body, db, user)
    if body.target_id is None:
        raise HTTPException(422, "缺少 target_id")
    if body.phase is not None and body.phase not in PHASE_VALUES:
        raise HTTPException(400, "phase 取值非法")
    if body.kind == "sense":
        return _answer_sense(body, db, user)
    return _answer_word(body, db, user)


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
