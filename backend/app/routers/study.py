"""学习流程：今日任务生成 / 答题提交 / 今日进度。

题型分层：
- meaning_multi：看英文单词，多选全部释义（义项），词级卡 word_states 计分；
- equiv_group：看代表词，多选同义组成员，更新代表词词卡，选项词不写状态；
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
    Sense,
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


class _SenseIndex:
    """一本书的义项图：词→义项、义项→成员、义项名、是否精选。"""

    def __init__(self, rows) -> None:
        self.word_to_senses: dict[int, set[int]] = defaultdict(set)
        self.sense_to_words: dict[int, set[int]] = defaultdict(set)
        self.label_by_sense: dict[int, str] = {}
        self.pos_by_sense: dict[int, str] = {}
        self.curated_senses: set[int] = set()
        for word_id, sense_id, label, pos, is_curated in rows:
            self.word_to_senses[int(word_id)].add(int(sense_id))
            self.sense_to_words[int(sense_id)].add(int(word_id))
            self.label_by_sense[int(sense_id)] = label
            self.pos_by_sense[int(sense_id)] = pos
            if is_curated:
                self.curated_senses.add(int(sense_id))

    def __bool__(self) -> bool:
        return bool(self.label_by_sense)


def _load_sense_index(db: Session, book_id: int) -> _SenseIndex:
    rows = db.execute(
        select(
            WordSense.word_id,
            WordSense.sense_id,
            Sense.label_zh,
            Sense.pos,
            Sense.is_curated,
        )
        .join(Sense, Sense.id == WordSense.sense_id)
        .where(
            WordSense.book_id == book_id,
            WordSense.status == "active",
            Sense.status == "active",
        )
    ).all()
    return _SenseIndex(rows)


MAX_ANCHOR_SENSES = 3


def _pick_anchor(members: set[int], index: _SenseIndex) -> int | None:
    """代表词：义项数最少的成员；义项数 >3 的词不能当代表词。"""
    if not members:
        return None
    best = min(members, key=lambda word_id: (len(index.word_to_senses.get(word_id, ())), word_id))
    if len(index.word_to_senses.get(best, ())) > MAX_ANCHOR_SENSES:
        return None
    return best


def _is_representative(word_id: int, index: _SenseIndex) -> bool:
    """该词是否至少是一个可考等价组的代表词（只看精选义项）。"""
    for sense_id in index.word_to_senses.get(word_id, ()):
        if sense_id not in index.curated_senses:
            continue
        members = index.sense_to_words.get(sense_id, set())
        if len(members) >= 2 and _pick_anchor(members, index) == word_id:
            return True
    return False


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
    # 小词书的义项池可能不够凑满标准选项数：有多少用多少，至少保证 1 个干扰项
    if not distractor_pool:
        return None
    picks = random.sample(distractor_pool, min(needed, len(distractor_pool)))

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
    """等价组：代表词 + 星内其它成员 + 2 个多义词干扰项；正确项 = 星内除代表词外的全部。"""
    members = index.sense_to_words.get(sense_id, set())
    if len(members) < 2 or sense_id not in index.curated_senses:
        return None
    anchor_id = _pick_anchor(members, index)
    if anchor_id is None:
        return None
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
    # 干扰项优先从多义词里抽：它们的义项多，作为「等价」候选更有迷惑性
    candidates = [
        word
        for word in pool.words
        if word.id not in blocked_ids
        and word.spelling.lower() not in blocked_spellings
        and len(index.word_to_senses.get(word.id, ())) > 1
    ]
    if len(candidates) < 2:
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
            owner_word_id=anchor_id,
        ),
        anchor_id,
    )


def _to_study_word(state: WordState, index: _SenseIndex) -> StudyWordOut:
    """词题：始终是「不定项选择释义」，不再回退旧题型。"""
    w = state.word
    return StudyWordOut(
        id=w.id,
        spelling=w.spelling,
        phonetic=w.phonetic,
        definition=w.definition,
        example_en=w.example_en,
        example_cn=w.example_cn,
        status=state.status,
        quiz=_build_meaning_quiz(w, index),
    )


def _to_group_item(
    state: WordState, sense_id: int, index: _SenseIndex, pool: _OptionPool
) -> StudyWordOut | None:
    """等价组题：挂靠代表词的词卡，id 仍用 sense_id（答题时用来定位这一组）。"""
    built = _build_equiv_quiz(sense_id, index, pool)
    if built is None:
        return None
    quiz, anchor_id = built
    anchor = pool.by_id[anchor_id]
    return StudyWordOut(
        id=sense_id,
        spelling=anchor.spelling,
        phonetic=anchor.phonetic,
        definition=quiz.question,
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

    # 等价组题：只为「代表词」（义项数 ≤3 且是该组代表）生成，挂在该词的词卡上
    sense_items: list[StudyWordOut] = []
    used_senses: set[int] = set()
    for state in list(new_states) + list(review_states):
        if not _is_representative(state.word_id, index):
            continue
        candidates = [
            sense_id
            for sense_id in sorted(index.word_to_senses.get(state.word_id, ()))
            if sense_id not in used_senses
            and len(index.sense_to_words.get(sense_id, set())) >= 2
            and _pick_anchor(index.sense_to_words[sense_id], index) == state.word_id
        ]
        if not candidates:
            continue
        item = _to_group_item(state, candidates[0], index, pool)
        if item is not None:
            sense_items.append(item)
            used_senses.add(candidates[0])

    return TodayOut(
        new_words=[_to_study_word(s, index) for s in new_states],
        review_words=[_to_study_word(s, index) for s in review_states],
        sense_items=sense_items,
        sense_target=len(sense_items),
        new_target=min(setting.new_per_day, len(new_states)),
        review_target=min(setting.review_per_day, len(review_states)),
    )


def _answer_word(body: AnswerIn, db: Session, user: User) -> AnswerOut:
    """词级多选：正确集合 = 该词当前全部 active 义项。

    代表词（义项数 ≤3 且有等价组）的词题只是「先背一遍」的热身，不写 FSRS；
    该词的记忆由紧接着的等价组题记分（见 _answer_sense）。
    """
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

    index = _load_sense_index(db, state.book_id)
    scheduled = not _is_representative(body.target_id, index)

    selected = {int(value) for value in body.selected_ids}
    result, hit = _grade_selection(selected, correct)
    phase = body.phase or "meaning"
    if scheduled:
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
    """等价组多选：更新**代表词的词卡**，不给选项词写任何状态。"""
    sense = db.scalar(
        select(Sense)
        .join(WordBook, WordBook.id == Sense.book_id)
        .where(Sense.id == body.target_id, WordBook.user_id == user.id)
    )
    if sense is None:
        raise HTTPException(404, "义项不存在")
    if sense.status != "active":
        raise HTTPException(400, "该义项尚未启用")
    if not sense.is_curated:
        raise HTTPException(400, "该义项来自上传词书，只用于单词语义题")

    index = _load_sense_index(db, sense.book_id)
    members = set(index.sense_to_words.get(sense.id, ()))
    if len(members) < 2:
        raise HTTPException(400, "该义项没有可考的同义成员")
    anchor_id = _pick_anchor(members, index)
    if anchor_id is None:
        raise HTTPException(400, "该组没有合格的代表词（义项数超过 3）")
    correct = members - {anchor_id}

    state = db.scalar(
        select(WordState).where(
            WordState.word_id == anchor_id, WordState.book_id == sense.book_id
        )
    )
    if state is None:
        state = WordState(word_id=anchor_id, book_id=sense.book_id)
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
    # 旧契约（word_id + result）已下线：所有题型都走服务端判分的多选
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
    # 词级进度：新词自评/挖空 + 多选释义（meaning）
    new_done = len({w for w, p in logs if p in ("new_first", "new_quiz", "meaning")})
    review_done = len({w for w, p in logs if p in ("review", "relearn")})
    # 义项卡进度（equiv_group）：按义项去重，与词级进度分开统计
    sense_done = len({w for w, p in logs if p == "group"})

    new_target, review_target = setting.new_per_day, setting.review_per_day
    sense_target = sense_done
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
        # 等价组题由代表词的词卡派生：统计今日还没出过的组题
        index = _load_sense_index(db, setting.active_book_id)
        candidates = db.scalars(
            select(WordState).where(
                WordState.book_id == setting.active_book_id,
                (WordState.stability.is_(None)) | (WordState.due <= now),
            )
        ).all()
        remaining_sense = sum(1 for s in candidates if _is_representative(s.word_id, index))
        sense_target = sense_done + int(remaining_sense)

    return ProgressOut(
        new_target=new_target,
        review_target=review_target,
        new_done=new_done,
        review_done=review_done,
        sense_target=sense_target,
        sense_done=sense_done,
    )

