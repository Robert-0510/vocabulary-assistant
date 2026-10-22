"""公开发布前新增的账号、边界与词书生命周期测试。"""

import json
import uuid

SAMPLE_BOOK = """# 测试词书

| 单词 | 音标 | 释义 | 例句 |
|---|---|---|---|
| abandon | /əˈbændən/ | v. 放弃 | He abandoned it. 他放弃了。 |
| benefit | /ˈbenɪfɪt/ | n. 好处 | |
| crucial | /ˈkruːʃl/ | adj. 至关重要的 | |
| emerge | /ɪˈmɜːdʒ/ | v. 出现 | |
"""

PASSWORD = "password123"


def unique(prefix="u"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def register(client, username, password=PASSWORD):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def upload(client, content=SAMPLE_BOOK, filename="book.md"):
    return client.post(
        "/api/books/upload",
        files={"file": (filename, content.encode("utf-8"), "text/markdown")},
    )


def test_change_password_revokes_sessions(api_client):
    api_client.cookies.clear()
    name = unique()
    assert register(api_client, name).status_code == 200

    assert (
        api_client.post(
            "/api/auth/change-password",
            json={"current_password": "wrong-pass", "new_password": "newpassword123"},
        ).status_code
        == 400
    )
    assert (
        api_client.post(
            "/api/auth/change-password",
            json={"current_password": PASSWORD, "new_password": "short"},
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/auth/change-password",
            json={"current_password": PASSWORD, "new_password": PASSWORD},
        ).status_code
        == 400
    )

    changed = api_client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "newpassword123"},
    )
    assert changed.status_code == 200
    # 当前会话也被吊销
    assert api_client.get("/api/auth/me").status_code == 401

    assert (
        api_client.post(
            "/api/auth/login", json={"username": name, "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        api_client.post(
            "/api/auth/login",
            json={"username": name, "password": "newpassword123"},
        ).status_code
        == 200
    )
    api_client.cookies.clear()


def test_upload_rejects_oversized_file(auth_client, monkeypatch):
    from app.config import config

    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    resp = upload(auth_client)
    assert resp.status_code == 413


def test_upload_clips_long_fields_and_book_name(auth_client):
    long_name = "长" * 150
    long_phonetic = "/" + "a" * 300 + "/"
    long_definition = "释义" * 600  # 1200 字符
    long_cn = "中文" * 400  # 800 字符
    md = (
        f"# {long_name}\n\n"
        "| 单词 | 音标 | 释义 | 例句 |\n"
        "|---|---|---|---|\n"
        f"| truncated | {long_phonetic} | {long_definition} | Example. {long_cn} |\n"
    )
    resp = upload(auth_client, md, "long.md")
    assert resp.status_code == 200, resp.text
    book = next(
        b for b in auth_client.get("/api/books").json() if b["id"] == resp.json()["book_id"]
    )
    assert len(book["name"]) == 100

    words = auth_client.get(f"/api/books/{book['id']}/words").json()["items"]
    assert len(words) == 1
    word = words[0]
    assert word["spelling"] == "truncated"
    assert len(word["phonetic"]) == 200
    assert len(word["definition"]) == 1000


def test_reset_book_progress(auth_client):
    book_id = upload(auth_client).json()["book_id"]
    word_id = auth_client.get("/api/study/today").json()["new_words"][0]["id"]
    auth_client.post(
        "/api/study/answer",
        json={"word_id": word_id, "phase": "new_first", "result": "know"},
    )
    before = auth_client.get(f"/api/books/{book_id}/words").json()["items"]
    assert any(w["id"] == word_id and w["status"] == "reviewing" for w in before)

    resp = auth_client.post(f"/api/books/{book_id}/reset")
    assert resp.status_code == 200
    after = auth_client.get(f"/api/books/{book_id}/words").json()["items"]
    target = next(w for w in after if w["id"] == word_id)
    assert target["status"] == "new"
    assert target["stability"] is None
    assert target["reps"] == 0
    assert auth_client.get("/api/study/today").status_code == 200


def test_edit_word_and_duplicate_check(api_client):
    api_client.cookies.clear()
    assert register(api_client, unique()).status_code == 200
    book_id = upload(api_client).json()["book_id"]
    items = api_client.get(f"/api/books/{book_id}/words").json()["items"]
    first, second = items[0], items[1]

    resp = api_client.put(
        f"/api/books/{book_id}/words/{first['id']}",
        json={"spelling": "abandoned", "definition": "v. 已放弃"},
    )
    assert resp.status_code == 200
    edited = api_client.get(f"/api/books/{book_id}/words", params={"keyword": "abandoned"}).json()[
        "items"
    ]
    assert edited[0]["definition"] == "v. 已放弃"

    duplicate = api_client.put(
        f"/api/books/{book_id}/words/{second['id']}",
        json={"spelling": "abandoned"},
    )
    assert duplicate.status_code == 409

    # 另一账号不能编辑
    other_book = api_client.post("/api/auth/logout")  # noqa: F841 - 仅确保会话清理
    assert register(api_client, unique()).status_code == 200
    forbidden = api_client.put(
        f"/api/books/{book_id}/words/{first['id']}", json={"spelling": "hacked"}
    )
    assert forbidden.status_code == 404
    api_client.cookies.clear()


def test_delete_active_book_falls_back(api_client):
    api_client.cookies.clear()
    assert register(api_client, unique()).status_code == 200
    first_id = upload(api_client).json()["book_id"]
    second_id = upload(api_client, SAMPLE_BOOK.replace("abandon", "zzz"), "b2.md").json()["book_id"]
    assert api_client.put(f"/api/books/{second_id}/activate").status_code == 200
    assert api_client.get("/api/settings").json()["active_book_id"] == second_id

    assert api_client.delete(f"/api/books/{second_id}").status_code == 200
    assert api_client.get("/api/settings").json()["active_book_id"] == first_id
    assert api_client.get("/api/study/today").status_code == 200
    api_client.cookies.clear()


def test_export_import_roundtrip(api_client):
    api_client.cookies.clear()
    assert register(api_client, unique()).status_code == 200
    assert upload(api_client).status_code == 200
    api_client.put("/api/settings", json={"new_per_day": 60, "review_per_day": 120})
    word_id = api_client.get("/api/study/today").json()["new_words"][0]["id"]
    api_client.post(
        "/api/study/answer",
        json={"word_id": word_id, "phase": "new_first", "result": "know"},
    )

    export = api_client.get("/api/export")
    assert export.status_code == 200
    assert "attachment" in export.headers["content-disposition"]
    payload = export.json()
    assert payload["format"] == "vocab-assistant-backup"
    assert payload["version"] == 1
    assert payload["app_version"]
    assert payload["books"][0]["words"][0]["logs"]
    assert "password" not in json.dumps(payload).lower()

    # 导入到另一个账号
    api_client.post("/api/auth/logout")
    api_client.cookies.clear()
    assert register(api_client, unique()).status_code == 200
    assert api_client.get("/api/books").json() == []

    imported = api_client.post(
        "/api/import",
        files={
            "file": (
                "backup.json",
                json.dumps(payload).encode("utf-8"),
                "application/json",
            )
        },
    )
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["books_imported"] == 1
    assert result["words_imported"] == 4

    books = api_client.get("/api/books").json()
    assert len(books) == 1 and books[0]["name"] == payload["books"][0]["name"]
    assert api_client.get("/api/settings").json()["new_per_day"] == 60
    states = api_client.get(f"/api/books/{books[0]['id']}/words").json()["items"]
    assert any(s["status"] == "reviewing" for s in states)
    assert api_client.get("/api/stats/overview").json()["total_days"] >= 1
    api_client.cookies.clear()


def test_today_task_does_not_issue_per_word_queries(auth_client):
    """40 个新词的今日任务不应按词查询干扰项。"""
    lines = ["# 大词书", "", "| 单词 | 音标 | 释义 | 例句 |", "|---|---|---|---|"]
    for index in range(40):
        lines.append(f"| word{index:03d} | /w{index}/ | 释义 {index} | |")
    book_id = upload(auth_client, "\n".join(lines), "big.md").json()["book_id"]
    auth_client.put("/api/settings", json={"new_per_day": 40, "review_per_day": 50})

    from app.database import engine
    from sqlalchemy import event

    statements: list[str] = []

    def before_cursor_execute(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        resp = auth_client.get("/api/study/today")
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["new_words"]) == 40
    assert all(len(word["quiz"]["options"]) == 4 for word in body["new_words"])
    assert len(statements) <= 15, f"查询数过多：{len(statements)}"
    assert book_id


def test_import_rejects_invalid_backups(api_client):
    api_client.cookies.clear()
    assert register(api_client, unique()).status_code == 200

    bad_format = api_client.post(
        "/api/import",
        files={
            "file": (
                "backup.json",
                json.dumps({"format": "other", "version": 1, "books": []}).encode(),
                "application/json",
            )
        },
    )
    assert bad_format.status_code == 400

    bad_version = api_client.post(
        "/api/import",
        files={
            "file": (
                "backup.json",
                json.dumps(
                    {"format": "vocab-assistant-backup", "version": 99, "books": []}
                ).encode(),
                "application/json",
            )
        },
    )
    assert bad_version.status_code == 422

    bad_json = api_client.post(
        "/api/import",
        files={"file": ("backup.json", b"not json", "application/json")},
    )
    assert bad_json.status_code == 400
    api_client.cookies.clear()
