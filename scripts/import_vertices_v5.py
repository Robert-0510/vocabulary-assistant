"""把 v5 顶点导入数据库（senses_v5.csv + word_senses_v5.csv）。

与旧的 import_sense_graph.py 的区别：
- 输入是重建后的顶点与邻接表，不再读取真题边、不再做合并/人工裁决（这些都已在重建时固化）；
- 不再写 definition_en / merged_into / gloss_raw（迁移 v5 已删掉这些列）；
- 同一中文标签可以对应多个义项顶点（唯一键已删）。

用法：
    python scripts/import_vertices_v5.py --book-id 1 --force
    python scripts/import_vertices_v5.py --dry-run
"""

from __future__ import annotations

import argparse
import csv
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.database import SessionLocal  # noqa: E402
from app.models import AppSetting, Sense, Word, WordBook, WordSense  # noqa: E402
from app.seed import init_db  # noqa: E402
from app.services.scheduler import utcnow_naive  # noqa: E402
from sqlalchemy import delete, func, select  # noqa: E402

DEFAULT_DATA = REPO_ROOT.parent / "data" / "derived"
STATUS_MAP = {"active": "active", "review": "needs_review", "needs_review": "needs_review"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="导入 v5 义项顶点")
    p.add_argument("--book-id", type=int, default=None)
    p.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    p.add_argument("--force", action="store_true", help="先清空该词书的义项图")
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args(argv)


def resolve_book(db, book_id: int | None) -> WordBook:
    if book_id is not None:
        book = db.get(WordBook, book_id)
        if not book:
            raise RuntimeError(f"词书 {book_id} 不存在")
        return book
    active_id = db.scalar(
        select(AppSetting.active_book_id).where(AppSetting.active_book_id.is_not(None))
    )
    if active_id:
        book = db.get(WordBook, active_id)
        if book:
            return book
    book = db.scalar(select(WordBook).order_by(WordBook.id))
    if not book:
        raise RuntimeError("库里没有词书；请先创建词书或用 --book-id 指定")
    return book


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    senses_path = args.data_dir / "senses_v5.csv"
    adj_path = args.data_dir / "word_senses_v5.csv"
    for p in (senses_path, adj_path):
        if not p.exists():
            print(f"[错误] 缺少输入：{p}", file=sys.stderr)
            return 1

    senses = list(csv.DictReader(open(senses_path, encoding="utf-8-sig")))
    members = defaultdict(set)
    for r in csv.DictReader(open(adj_path, encoding="utf-8-sig")):
        members[r["义项ID"]].add(r["词"].strip().lower())

    init_db()
    with SessionLocal() as db:
        try:
            book = resolve_book(db, args.book_id)
            existing = (
                db.scalar(select(func.count()).select_from(Sense).where(Sense.book_id == book.id))
                or 0
            )
            if existing and not args.force:
                print(f"[跳过] 词书「{book.name}」已有 {existing} 个义项；重建请加 --force")
                return 0
            if args.dry_run:
                print(
                    f"[dry-run] 词书「{book.name}」：{len(senses)} 个义项 / "
                    f"{sum(len(v) for v in members.values())} 条成员边"
                )
                return 0
            if existing:
                db.execute(delete(WordSense).where(WordSense.book_id == book.id))
                db.execute(delete(Sense).where(Sense.book_id == book.id))
                db.flush()

            words = {
                w.spelling.lower(): w.id
                for w in db.scalars(select(Word).where(Word.book_id == book.id))
            }
            utcnow_naive()
            stats = Counter()
            for row in senses:
                sid = row["义项ID"]
                status = STATUS_MAP.get((row.get("状态") or "").strip(), "active")
                sense = Sense(
                    book_id=book.id,
                    label_zh=(row.get("中文释义") or row["锚词"])[:120],
                    pos=(row.get("词性") or "adj")[:16],
                    status=status,
                    is_curated=True,
                )
                db.add(sense)
                db.flush()
                stats["senses"] += 1
                stats[f"status_{status}"] += 1
                for w in members.get(sid, ()):
                    wid = words.get(w)
                    if wid is None:
                        stats["skipped"] += 1
                        continue
                    db.add(
                        WordSense(book_id=book.id, word_id=wid, sense_id=sense.id, status="active")
                    )
                    stats["word_senses"] += 1
            db.commit()
            book_name, book_id = book.name, book.id
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            print(f"[错误] 导入失败：{exc}", file=sys.stderr)
            traceback.print_exc()
            return 1

    print(f"词书：{book_name} (id={book_id})")
    print(
        f"  义项：{stats['senses']}（active {stats['status_active']} / needs_review {stats['status_needs_review']}）"
    )
    print(f"  边（word_senses）：{stats['word_senses']}")
    print(f"  词书里找不到、跳过的成员：{stats['skipped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
