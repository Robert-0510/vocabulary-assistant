"""数据导出 / 导入备份（版本化 JSON，包含词书、记忆状态与学习流水）。"""

import json
import logging
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.config import config
from app.database import get_db
from app.models import (
    PHASE_VALUES,
    RESULT_VALUES,
    AppSetting,
    StudyLog,
    User,
    Word,
    WordBook,
    WordState,
)
from app.schemas import (
    BackupBook,
    BackupLog,
    BackupPayload,
    BackupWord,
    BackupWordState,
    ImportResult,
)
from app.services.scheduler import derive_status, utcnow_naive
from app.version import __version__

logger = logging.getLogger("app.backup")
router = APIRouter(prefix="/api", tags=["备份"])

BACKUP_FORMAT = "vocab-assistant-backup"
BACKUP_VERSION = 1
MAX_IMPORT_BOOKS = 200
MAX_IMPORT_WORDS = 100_000
MAX_IMPORT_LOGS = 500_000


def _naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _unique_book_name(base: str, existing: set[str]) -> str:
    base = (base or "").strip()[:100] or "导入词书"
    candidate = base
    index = 2
    while candidate in existing:
        suffix = f"({index})"
        candidate = f"{base[: 100 - len(suffix)]}{suffix}"
        index += 1
    existing.add(candidate)
    return candidate


@router.get("/export")
def export_backup(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """导出当前账号的全部词书、记忆状态与学习流水。"""
    setting = db.get(AppSetting, user.id)
    books = db.scalars(
        select(WordBook)
        .where(WordBook.user_id == user.id)
        .order_by(WordBook.created_at.asc(), WordBook.id.asc())
    ).all()

    logs_by_word: dict[int, list[StudyLog]] = {}
    for log in db.scalars(
        select(StudyLog)
        .where(StudyLog.user_id == user.id)
        .order_by(StudyLog.studied_at.asc(), StudyLog.id.asc())
    ).all():
        logs_by_word.setdefault(log.word_id, []).append(log)

    payload_books: list[BackupBook] = []
    for book in books:
        words = db.scalars(
            select(Word)
            .options(selectinload(Word.state))
            .where(Word.book_id == book.id)
            .order_by(Word.seq.asc(), Word.id.asc())
        ).all()
        backup_words: list[BackupWord] = []
        for word in words:
            state = word.state
            backup_words.append(
                BackupWord(
                    spelling=word.spelling,
                    phonetic=word.phonetic or "",
                    definition=word.definition,
                    example_en=word.example_en,
                    example_cn=word.example_cn,
                    seq=word.seq,
                    state=(
                        BackupWordState(
                            state=state.state,
                            step=state.step,
                            stability=(
                                float(state.stability) if state.stability is not None else None
                            ),
                            difficulty=(
                                float(state.difficulty) if state.difficulty is not None else None
                            ),
                            due=state.due,
                            last_review=state.last_review,
                            reps=state.reps,
                            lapses=state.lapses,
                            status=state.status,
                        )
                        if state is not None
                        else None
                    ),
                    logs=[
                        BackupLog(
                            phase=log.phase,
                            result=log.result,
                            studied_at=log.studied_at,
                        )
                        for log in logs_by_word.get(word.id, [])
                    ],
                )
            )
        payload_books.append(
            BackupBook(
                name=book.name,
                description=book.description,
                words=backup_words,
            )
        )

    active_name = None
    if setting and setting.active_book_id:
        active_name = db.scalar(
            select(WordBook.name).where(
                WordBook.id == setting.active_book_id,
                WordBook.user_id == user.id,
            )
        )

    payload = BackupPayload(
        format=BACKUP_FORMAT,
        version=BACKUP_VERSION,
        app_version=__version__,
        exported_at=datetime.now(UTC),
        settings=(
            {
                "new_per_day": setting.new_per_day,
                "review_per_day": setting.review_per_day,
            }
            if setting
            else None
        ),
        active_book_name=active_name,
        books=payload_books,
    )
    filename = f"vocab-assistant-backup-{date.today().isoformat()}.json"
    return JSONResponse(
        content=payload.model_dump(mode="json"),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def _make_state(backup: BackupWordState | None) -> dict:
    """把导入的状态规范化，保证 FSRS 重建时字段自洽。"""
    if backup is None or backup.stability is None:
        return {
            "state": 1,
            "step": None,
            "stability": None,
            "difficulty": None,
            "due": None,
            "last_review": None,
            "reps": 0,
            "lapses": 0,
            "status": "new",
        }

    state_value = backup.state if backup.state in (1, 2, 3) else 1
    stability = max(0.0, float(backup.stability))
    difficulty = (
        min(10.0, max(1.0, float(backup.difficulty))) if backup.difficulty is not None else 5.0
    )
    now = utcnow_naive()
    due = _naive_utc(backup.due) or now
    last_review = _naive_utc(backup.last_review) or due
    return {
        "state": state_value,
        "step": (
            max(0, int(backup.step)) if state_value != 2 and backup.step is not None else None
        ),
        "stability": stability,
        "difficulty": difficulty,
        "due": due,
        "last_review": last_review,
        "reps": max(0, int(backup.reps or 0)),
        "lapses": max(0, int(backup.lapses or 0)),
        "status": derive_status(state_value, stability),
    }


@router.post("/import", response_model=ImportResult)
async def import_backup(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """合并导入备份：同名词书自动改名，不清空现有数据。"""
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(400, "仅支持导入 .json 备份文件")

    max_bytes = config.MAX_IMPORT_MB * 1024 * 1024
    raw = await file.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise HTTPException(413, f"备份文件过大，最大支持 {config.MAX_IMPORT_MB} MB")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(400, "备份文件不是有效的 UTF-8 JSON") from exc

    try:
        payload = BackupPayload.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0] if exc.errors() else {}
        raise HTTPException(422, f"备份格式不正确：{first.get('msg', '字段校验失败')}") from exc

    if payload.format != BACKUP_FORMAT:
        raise HTTPException(400, "不是背单词助手的备份文件")
    if payload.version != BACKUP_VERSION:
        raise HTTPException(422, f"不支持的备份版本：{payload.version}")
    if len(payload.books) > MAX_IMPORT_BOOKS:
        raise HTTPException(422, f"词书数量超过上限（{MAX_IMPORT_BOOKS}）")

    total_words = sum(len(book.words) for book in payload.books)
    total_logs = sum(len(word.logs) for book in payload.books for word in book.words)
    if total_words > MAX_IMPORT_WORDS:
        raise HTTPException(422, f"单词数量超过上限（{MAX_IMPORT_WORDS}）")
    if total_logs > MAX_IMPORT_LOGS:
        raise HTTPException(422, f"学习记录数量超过上限（{MAX_IMPORT_LOGS}）")

    existing_names = set(db.scalars(select(WordBook.name).where(WordBook.user_id == user.id)).all())
    imported_ids: list[int] = []
    first_id_by_name: dict[str, int] = {}
    books_imported = 0
    words_imported = 0
    skipped = 0

    try:
        for book in payload.books:
            name = _unique_book_name(book.name, existing_names)
            book_obj = WordBook(
                user_id=user.id,
                name=name,
                description=book.description,
                word_count=0,
            )
            db.add(book_obj)
            db.flush()

            seen: set[str] = set()
            pairs: list[tuple[Word, BackupWord]] = []
            for item in book.words:
                spelling = item.spelling.strip()[:100]
                definition = item.definition.strip()[:1000]
                if not spelling or not definition:
                    skipped += 1
                    continue
                key = spelling.lower()
                if key in seen:
                    skipped += 1
                    continue
                seen.add(key)
                word = Word(
                    book_id=book_obj.id,
                    spelling=spelling,
                    phonetic=(item.phonetic or "").strip()[:200],
                    definition=definition,
                    example_en=(item.example_en or "").strip()[:2000] or None,
                    example_cn=(item.example_cn or "").strip()[:500] or None,
                    seq=len(pairs),
                )
                pairs.append((word, item))
            if not pairs:
                db.delete(book_obj)
                db.flush()
                continue

            db.add_all([word for word, _ in pairs])
            db.flush()
            book_obj.word_count = len(pairs)

            states: list[WordState] = []
            logs: list[StudyLog] = []
            seen_logs: set[tuple[str, str, str, datetime | None]] = set()
            for word, item in pairs:
                states.append(
                    WordState(
                        word_id=word.id,
                        book_id=book_obj.id,
                        **_make_state(item.state),
                    )
                )
                for log in item.logs:
                    if log.phase not in PHASE_VALUES or log.result not in RESULT_VALUES:
                        skipped += 1
                        continue
                    studied_at = _naive_utc(log.studied_at) or utcnow_naive()
                    log_key = (word.spelling.lower(), log.phase, log.result, studied_at)
                    if log_key in seen_logs:
                        skipped += 1
                        continue
                    seen_logs.add(log_key)
                    logs.append(
                        StudyLog(
                            user_id=user.id,
                            word_id=word.id,
                            phase=log.phase,
                            result=log.result,
                            studied_at=studied_at,
                        )
                    )
            db.add_all(states)
            db.add_all(logs)

            books_imported += 1
            words_imported += len(pairs)
            imported_ids.append(book_obj.id)
            first_id_by_name.setdefault(book.name.strip()[:100], book_obj.id)

        setting = db.get(AppSetting, user.id)
        if setting is None:
            setting = AppSetting(user_id=user.id)
            db.add(setting)
            db.flush()
        if payload.settings is not None:
            setting.new_per_day = min(300, max(5, payload.settings.new_per_day))
            setting.review_per_day = min(600, max(10, payload.settings.review_per_day))
        if setting.active_book_id is None:
            candidate = (
                first_id_by_name.get(payload.active_book_name or "")
                if payload.active_book_name
                else None
            )
            setting.active_book_id = candidate or (imported_ids[0] if imported_ids else None)

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:  # noqa: BLE001 - 导入需要整体回滚并返回友好错误
        db.rollback()
        logger.exception("backup import failed")
        raise HTTPException(500, "导入失败，数据已回滚") from exc

    return ImportResult(
        books_imported=books_imported,
        words_imported=words_imported,
        skipped=skipped,
    )
