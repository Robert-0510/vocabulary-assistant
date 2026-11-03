"""给「没有义项数据」的历史词书补做义项拆解。

上传接口已经会在导入时拆义项；这个脚本只用于这次改造之前建的老词书。
幂等：只处理完全没有 sense 的词。

用法：
    python scripts/backfill_senses.py [--book-id N] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal  # noqa: E402
from app.models import Word, WordBook, WordSense  # noqa: E402
from app.seed import init_db  # noqa: E402
from app.services.senses import rebuild_word_senses  # noqa: E402
from sqlalchemy import select  # noqa: E402


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-id", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    init_db()
    with SessionLocal() as db:
        books = (
            [db.get(WordBook, args.book_id)]
            if args.book_id
            else list(db.scalars(select(WordBook).order_by(WordBook.id)))
        )
        total_words = total_new = 0
        for book in books:
            if book is None:
                continue
            word_ids = set(db.scalars(select(Word.id).where(Word.book_id == book.id)).all())
            with_sense = set(
                db.scalars(select(WordSense.word_id).where(WordSense.book_id == book.id)).all()
            )
            missing = sorted(word_ids - with_sense)
            total_words += len(missing)
            print(f"词书 {book.id}「{book.name}」：{len(word_ids)} 词，缺义项 {len(missing)}")
            if args.dry_run or not missing:
                continue
            for word in db.scalars(select(Word).where(Word.id.in_(missing))).all():
                rebuild_word_senses(db, book.id, word)
                total_new += 1
            db.commit()
        print(f"完成：新建义项的词 {total_new} 个（dry-run 时只统计 {total_words}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
