# -*- coding: utf-8 -*-
"""初始化默认账号 + 词书，并导入 v5 顶点。

只在本机开发库上跑一次；重复执行会复用已有账号/词书，加 --force 重建义项图。

用法：
    python scripts/setup_default_book.py --username admin --password <口令> [--force]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import func, select  # noqa: E402

from app.auth import hash_password  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import AppSetting, Sense, User, Word, WordBook, WordSense, WordState  # noqa: E402
from app.seed import ensure_settings, init_db  # noqa: E402

DATA = REPO_ROOT.parent / "data" / "derived"
BOOK_NAME = "GRE 等价词义项"


def _user_exists(username: str) -> bool:
    with SessionLocal() as db:
        return db.scalar(select(User.id).where(User.username == username)) is not None


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--username", default="admin")
    ap.add_argument("--password", default=None, help="创建新账号时必填；复用已有账号可省略")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    if args.password is None and not _user_exists(args.username):
        ap.error("创建新账号必须提供 --password")

    vocab = {e["word"]: e for e in json.loads((DATA / "jjci_words.json").read_text(encoding="utf-8"))}
    dict_cn = json.loads((DATA / "dict_cn.json").read_text(encoding="utf-8")) if (DATA / "dict_cn.json").exists() else {}
    members = [r for r in csv.DictReader(open(DATA / "word_senses_v5.csv", encoding="utf-8-sig"))]
    words = sorted({r["词"] for r in members})

    init_db()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == args.username))
        if not user:
            user = User(username=args.username, password_hash=hash_password(args.password))
            db.add(user)
            db.flush()
            print(f"新建账号：{args.username}")
        else:
            print(f"复用账号：{args.username}")

        book = db.scalar(select(WordBook).where(WordBook.user_id == user.id, WordBook.name == BOOK_NAME))
        if not book:
            book = WordBook(user_id=user.id, name=BOOK_NAME, description="GRE 等价词二部图（v5）", word_count=0)
            db.add(book)
            db.flush()
            print("新建词书")

        existing = {w.spelling.lower() for w in db.scalars(select(Word).where(Word.book_id == book.id))}
        to_add = []
        for i, w in enumerate(words):
            if w in existing:
                continue
            e = vocab.get(w)
            zh = ""
            if e:
                zh = "".join(re.findall(r"[\u4e00-\u9fff]+", e["meaning"] or ""))
            if not zh and w in dict_cn and dict_cn[w].get("explain"):
                zh = "".join(re.findall(r"[\u4e00-\u9fff]+", dict_cn[w]["explain"]))
            to_add.append(Word(book_id=book.id, spelling=w, definition=(zh or w)[:1000], seq=i))
        if to_add:
            db.add_all(to_add)
            db.flush()
            print(f"新增单词：{len(to_add)}")
        # 词级 FSRS 状态：上传词书时引擎会给每个词建一行，这里补齐
        have_state = {s.word_id for s in db.scalars(select(WordState).where(WordState.book_id == book.id))}
        missing = [w for w in db.scalars(select(Word).where(Word.book_id == book.id)) if w.id not in have_state]
        if missing:
            db.add_all([WordState(word_id=w.id, book_id=book.id) for w in missing])
            db.flush()
            print(f"新增词状态：{len(missing)}")
        book.word_count = db.scalar(select(func.count()).select_from(Word).where(Word.book_id == book.id))
        setting = ensure_settings(db, user.id)
        setting.active_book_id = book.id
        db.commit()
        print(f"词书 id={book.id}，词数={book.word_count}，已设为当前词书")
        book_id = book.id

    # 导入顶点
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import import_vertices_v5  # noqa: E402

    rc = import_vertices_v5.main(["--book-id", str(book_id)] + (["--force"] if args.force else []))
    if rc != 0:
        return rc

    with SessionLocal() as db:
        print("库内：义项", db.scalar(select(func.count()).select_from(Sense)),
              "边", db.scalar(select(func.count()).select_from(WordSense)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


