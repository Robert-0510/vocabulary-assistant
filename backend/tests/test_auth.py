import uuid

from sqlalchemy import func, select

SAMPLE_BOOK = """# 测试词书

| 单词 | 音标 | 释义 | 例句 |
|---|---|---|---|
| abandon | /əˈbændən/ | v. 放弃 | He abandoned it. 他放弃了。 |
| benefit | /ˈbenɪfɪt/ | n. 好处 | |
"""

PASSWORD = "password123"


def unique(prefix="u"):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def register(client, username, password=PASSWORD):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def upload(client):
    return client.post(
        "/api/books/upload",
        files={"file": ("book.md", SAMPLE_BOOK.encode("utf-8"), "text/markdown")},
    )


def test_register_login_me_logout(api_client):
    api_client.cookies.clear()
    name = unique()
    assert register(api_client, name).status_code == 200

    me = api_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == name

    assert api_client.post("/api/auth/logout").status_code == 200
    assert api_client.get("/api/auth/me").status_code == 401
    assert api_client.get("/api/books").status_code == 401

    # 错误密码
    assert (
        api_client.post(
            "/api/auth/login", json={"username": name, "password": "wrong-pass"}
        ).status_code
        == 401
    )
    # 正确密码
    assert (
        api_client.post(
            "/api/auth/login", json={"username": name, "password": PASSWORD}
        ).status_code
        == 200
    )
    assert api_client.get("/api/auth/me").status_code == 200
    api_client.cookies.clear()


def test_duplicate_username_and_short_password(api_client):
    api_client.cookies.clear()
    name = unique()
    assert register(api_client, name).status_code == 200
    assert register(api_client, name).status_code == 409
    assert register(api_client, unique(), "short").status_code == 422
    assert register(api_client, "bad name", PASSWORD).status_code == 422
    api_client.cookies.clear()


def test_user_data_isolation(api_client):
    api_client.cookies.clear()
    name_a, name_b = unique("a"), unique("b")

    # 账号 A：上传词书、修改设置
    assert register(api_client, name_a).status_code == 200
    book_id = upload(api_client).json()["book_id"]
    assert len(api_client.get("/api/books").json()) == 1
    api_client.put("/api/settings", json={"new_per_day": 50, "review_per_day": 100})
    assert api_client.post("/api/auth/logout").status_code == 200

    # 账号 B：看不到 A 的词书与设置，也不能越权操作
    assert register(api_client, name_b).status_code == 200
    assert api_client.get("/api/books").json() == []
    assert api_client.get("/api/settings").json()["new_per_day"] == 25
    assert api_client.get(f"/api/books/{book_id}/words").status_code == 404
    assert api_client.put(f"/api/books/{book_id}/activate").status_code == 404
    assert api_client.delete(f"/api/books/{book_id}").status_code == 404
    # 同名词书在不同账号下允许存在
    assert upload(api_client).status_code == 200
    assert api_client.post("/api/auth/logout").status_code == 200

    # 重新登录 A，数据仍在
    assert (
        api_client.post(
            "/api/auth/login", json={"username": name_a, "password": PASSWORD}
        ).status_code
        == 200
    )
    books = api_client.get("/api/books").json()
    assert len(books) == 1 and books[0]["id"] == book_id
    assert api_client.get("/api/settings").json()["new_per_day"] == 50
    api_client.cookies.clear()


def test_book_delete_is_hard(api_client):
    api_client.cookies.clear()
    assert register(api_client, unique()).status_code == 200
    user_id = api_client.get("/api/auth/me").json()["id"]
    book_id = upload(api_client).json()["book_id"]

    word_id = api_client.get("/api/study/today").json()["new_words"][0]["id"]
    api_client.post(
        "/api/study/answer",
        json={"word_id": word_id, "phase": "new_first", "result": "know"},
    )

    assert api_client.delete(f"/api/books/{book_id}").status_code == 200

    from app.database import SessionLocal  # 夹具设置临时库后再解析
    from app.models import StudyLog, Word, WordState

    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Word).where(Word.book_id == book_id)) == 0
        assert (
            db.scalar(
                select(func.count()).select_from(WordState).where(WordState.book_id == book_id)
            )
            == 0
        )
        assert (
            db.scalar(select(func.count()).select_from(StudyLog).where(StudyLog.user_id == user_id))
            == 0
        )
    api_client.cookies.clear()


def test_delete_account_hard_deletes_all_data(api_client):
    api_client.cookies.clear()
    name = unique()
    reg = register(api_client, name)
    assert reg.status_code == 200
    user_id = reg.json()["id"]
    book_id = upload(api_client).json()["book_id"]
    word_id = api_client.get("/api/study/today").json()["new_words"][0]["id"]
    api_client.post(
        "/api/study/answer",
        json={"word_id": word_id, "phase": "new_first", "result": "know"},
    )

    # 密码错误不能注销
    assert (
        api_client.post(
            "/api/auth/delete-account", json={"password": "not-the-password"}
        ).status_code
        == 400
    )
    assert api_client.get("/api/auth/me").status_code == 200

    # 密码正确 → 物理删除
    assert (
        api_client.post("/api/auth/delete-account", json={"password": PASSWORD}).status_code == 200
    )
    assert api_client.get("/api/auth/me").status_code == 401
    assert api_client.get("/api/books").status_code == 401

    from app.database import SessionLocal
    from app.models import (
        AppSetting,
        StudyLog,
        User,
        UserSession,
        Word,
        WordBook,
        WordState,
    )

    with SessionLocal() as db:
        assert db.get(User, user_id) is None
        assert (
            db.scalar(
                select(func.count()).select_from(UserSession).where(UserSession.user_id == user_id)
            )
            == 0
        )
        assert (
            db.scalar(
                select(func.count()).select_from(AppSetting).where(AppSetting.user_id == user_id)
            )
            == 0
        )
        assert (
            db.scalar(select(func.count()).select_from(WordBook).where(WordBook.user_id == user_id))
            == 0
        )
        assert (
            db.scalar(select(func.count()).select_from(StudyLog).where(StudyLog.user_id == user_id))
            == 0
        )
        assert db.scalar(select(func.count()).select_from(Word).where(Word.book_id == book_id)) == 0
        assert (
            db.scalar(
                select(func.count()).select_from(WordState).where(WordState.book_id == book_id)
            )
            == 0
        )

    # 注销后用户名可重新注册
    assert register(api_client, name).status_code == 200
    api_client.post("/api/auth/logout")
    api_client.cookies.clear()
