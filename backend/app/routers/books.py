"""词书管理：上传解析 / 列表 / 词表 / 删除 / 激活。"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.config import config
from app.database import get_db
from app.models import StudyLog, User, Word, WordBook, WordState
from app.schemas import BookCounts, BookOut, UploadResult, WordOut, WordPage, WordUpdateIn
from app.seed import ensure_settings
from app.services.md_parser import (
    MAX_BOOK_NAME,
    MAX_DEFINITION,
    MAX_EXAMPLE_CN,
    MAX_EXAMPLE_EN,
    MAX_PHONETIC,
    MAX_SPELLING,
    parse_markdown,
)
from app.services.scheduler import to_local_date

router = APIRouter(prefix="/api/books", tags=["词书"])


class ActivateOut(BaseModel):
    ok: bool
    active_book_id: int


def _scheduled_days(state) -> int:
    """下次复习的间隔天数（词表「间隔(天)」列展示用）。"""
    if state.due and state.last_review:
        return max(0, (state.due - state.last_review).days)
    return 0


def _owned_book(db: Session, book_id: int, user: User) -> WordBook:
    book = db.scalar(select(WordBook).where(WordBook.id == book_id, WordBook.user_id == user.id))
    if book is None:
        raise HTTPException(404, "词书不存在")
    return book


@router.post("/upload", response_model=UploadResult)
async def upload_book(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not file.filename or not file.filename.lower().endswith((".md", ".markdown", ".txt")):
        raise HTTPException(400, "仅支持上传 .md / .markdown / .txt 文件")

    max_bytes = config.MAX_UPLOAD_MB * 1024 * 1024
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise HTTPException(400, "Content-Length 不合法") from exc
        # multipart 边界与头部开销留 1MB 余量
        if declared > max_bytes + 1024 * 1024:
            raise HTTPException(413, f"文件过大，最大支持 {config.MAX_UPLOAD_MB} MB")
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(413, f"文件过大，最大支持 {config.MAX_UPLOAD_MB} MB")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = raw.decode("gbk", errors="replace")

    name, words, skipped = parse_markdown(content)
    name = (name or Path(file.filename).stem)[:MAX_BOOK_NAME]
    if not words:
        raise HTTPException(400, "未解析到有效单词，请检查表格格式（至少需要：单词 | 音标 | 释义）")
    if len(words) > config.MAX_WORDS_PER_BOOK:
        raise HTTPException(
            422,
            f"单词数量超过上限（{config.MAX_WORDS_PER_BOOK}），请拆分后上传",
        )

    existing = set(db.scalars(select(WordBook.name).where(WordBook.user_id == user.id)).all())
    base, i = name, 2
    while name in existing:
        name = f"{base}({i})"
        i += 1

    book = WordBook(user_id=user.id, name=name, word_count=len(words))
    db.add(book)
    db.flush()
    word_objs = [Word(book_id=book.id, **w) for w in words]
    db.add_all(word_objs)
    db.flush()
    db.add_all([WordState(word_id=w.id, book_id=book.id) for w in word_objs])

    setting = ensure_settings(db, user.id)
    if setting.active_book_id is None:
        setting.active_book_id = book.id
    db.commit()
    return UploadResult(book_id=book.id, name=name, imported=len(word_objs), skipped=skipped)


@router.get("", response_model=list[BookOut])
def list_books(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    books = db.scalars(
        select(WordBook).where(WordBook.user_id == user.id).order_by(WordBook.created_at.desc())
    ).all()
    rows = db.execute(
        select(WordState.book_id, WordState.status, func.count())
        .join(WordBook, WordBook.id == WordState.book_id)
        .where(WordBook.user_id == user.id)
        .group_by(WordState.book_id, WordState.status)
    ).all()
    counts: dict[int, dict[str, int]] = {}
    for book_id, status, cnt in rows:
        counts.setdefault(book_id, {})[status] = int(cnt)
    active_id = ensure_settings(db, user.id).active_book_id

    return [
        BookOut(
            id=b.id,
            name=b.name,
            description=b.description,
            word_count=b.word_count,
            created_at=b.created_at,
            is_active=b.id == active_id,
            counts=BookCounts(
                **{
                    s: counts.get(b.id, {}).get(s, 0)
                    for s in ("new", "learning", "reviewing", "mastered")
                }
            ),
        )
        for b in books
    ]


@router.get("/{book_id}/words", response_model=WordPage)
def book_words(
    book_id: int,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _owned_book(db, book_id, user)
    page = max(1, page)
    page_size = min(100, max(1, page_size))

    q = (
        select(Word, WordState)
        .join(WordState, WordState.word_id == Word.id)
        .where(Word.book_id == book_id)
    )
    if keyword.strip():
        kw = f"%{keyword.strip()}%"
        q = q.where((Word.spelling.like(kw)) | (Word.definition.like(kw)))
    if status in ("new", "learning", "reviewing", "mastered"):
        q = q.where(WordState.status == status)

    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    rows = db.execute(
        q.order_by(Word.seq.asc()).offset((page - 1) * page_size).limit(page_size)
    ).all()

    items = [
        WordOut(
            id=w.id,
            spelling=w.spelling,
            phonetic=w.phonetic,
            definition=w.definition,
            example_en=w.example_en,
            example_cn=w.example_cn,
            seq=w.seq,
            status=st.status,
            interval_days=float(_scheduled_days(st)),
            stability=float(st.stability) if st.stability is not None else None,
            difficulty=float(st.difficulty) if st.difficulty is not None else None,
            reps=st.reps,
            lapses=st.lapses,
            due_date=to_local_date(st.due),
        )
        for w, st in rows
    ]
    return WordPage(total=int(total), items=items)


@router.delete("/{book_id}")
def delete_book(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    book = _owned_book(db, book_id, user)
    setting = ensure_settings(db, user.id)
    if setting.active_book_id == book_id:
        # 自动回退到剩余最近创建的一本，避免用户卡在「未选择词书」
        next_book_id = db.scalar(
            select(WordBook.id)
            .where(WordBook.user_id == user.id, WordBook.id != book_id)
            .order_by(WordBook.created_at.desc(), WordBook.id.desc())
            .limit(1)
        )
        setting.active_book_id = next_book_id
    db.delete(book)  # 物理删除；外键级联删除 words / word_states / study_logs
    db.commit()
    return {"ok": True}


@router.post("/{book_id}/reset")
def reset_book_progress(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    """把词书内所有单词重置为新词，并删除当前账号在这本书上的学习流水。"""
    _owned_book(db, book_id, user)
    word_ids = select(Word.id).where(Word.book_id == book_id)
    deleted = db.execute(
        delete(StudyLog).where(
            StudyLog.user_id == user.id,
            StudyLog.word_id.in_(word_ids),
        )
    ).rowcount
    db.execute(
        update(WordState)
        .where(WordState.book_id == book_id)
        .values(
            state=1,
            step=None,
            stability=None,
            difficulty=None,
            due=None,
            last_review=None,
            reps=0,
            lapses=0,
            status="new",
        )
    )
    db.commit()
    return {"ok": True, "deleted_logs": int(deleted or 0)}


@router.put("/{book_id}/words/{word_id}")
def update_word(
    book_id: int,
    word_id: int,
    body: WordUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """词表纠错：只更新显式传入的字段。"""
    _owned_book(db, book_id, user)
    word = db.scalar(select(Word).where(Word.id == word_id, Word.book_id == book_id))
    if word is None:
        raise HTTPException(404, "单词不存在")

    fields = body.model_dump(exclude_unset=True)

    if "spelling" in fields:
        spelling = (fields["spelling"] or "").strip()[:MAX_SPELLING]
        if not spelling:
            raise HTTPException(422, "单词不能为空")
        duplicate = db.scalar(
            select(Word.id).where(
                Word.book_id == book_id,
                func.lower(Word.spelling) == spelling.lower(),
                Word.id != word_id,
            )
        )
        if duplicate is not None:
            raise HTTPException(409, "该词书内已存在同名单词")
        word.spelling = spelling

    if "definition" in fields:
        definition = (fields["definition"] or "").strip()[:MAX_DEFINITION]
        if not definition:
            raise HTTPException(422, "释义不能为空")
        word.definition = definition

    if "phonetic" in fields:
        word.phonetic = (fields["phonetic"] or "").strip()[:MAX_PHONETIC]

    if "example_en" in fields:
        value = (fields["example_en"] or "").strip()[:MAX_EXAMPLE_EN]
        word.example_en = value or None

    if "example_cn" in fields:
        value = (fields["example_cn"] or "").strip()[:MAX_EXAMPLE_CN]
        word.example_cn = value or None

    db.commit()
    return {"ok": True}


@router.put("/{book_id}/activate", response_model=ActivateOut)
def activate_book(
    book_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)
):
    _owned_book(db, book_id, user)
    setting = ensure_settings(db, user.id)
    setting.active_book_id = book_id
    db.commit()
    return ActivateOut(ok=True, active_book_id=book_id)
