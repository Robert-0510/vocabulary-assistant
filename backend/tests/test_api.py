SAMPLE_BOOK = """# 测试词书

| 单词 | 音标 | 释义 | 例句 |
|---|---|---|---|
| abandon | /əˈbændən/ | v. 放弃 | He abandoned it. 他放弃了。 |
| benefit | /ˈbenɪfɪt/ | n. 好处 | |
| crucial | /ˈkruːʃl/ | adj. 至关重要的 | |
| emerge | /ɪˈmɜːdʒ/ | v. 出现 | |
| manifest | /ˈmænɪfest/ | adj. 明显的 v. 显示 | His relief was manifest. |
"""


def _sense_ids(book_id: int, word_id: int) -> list[int]:
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import WordSense

    with SessionLocal() as db:
        return sorted(
            db.scalars(select(WordSense.sense_id).where(WordSense.word_id == word_id)).all()
        )


def test_health(api_client):
    resp = api_client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["db"] == "ok"
    assert body["version"]
    assert resp.headers.get("X-Request-ID")


def test_requires_login(api_client):
    api_client.cookies.clear()
    assert api_client.get("/api/books").status_code == 401
    assert api_client.get("/api/study/today").status_code == 401
    assert api_client.get("/api/stats/overview").status_code == 401
    assert api_client.get("/api/settings").status_code == 401


def test_full_study_flow(auth_client):
    api_client = auth_client
    # 上传并自动激活
    resp = api_client.post(
        "/api/books/upload",
        files={"file": ("sample.md", SAMPLE_BOOK.encode("utf-8"), "text/markdown")},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["imported"] == 5

    books = api_client.get("/api/books").json()
    assert len(books) == 1 and books[0]["is_active"] is True
    book_id = books[0]["id"]

    # 今日任务：4 个新词，均带 4 选项的不定项选择（服务端判分）
    today = api_client.get("/api/study/today").json()
    assert len(today["new_words"]) == 5
    assert all(w["quiz"] and w["quiz"]["type"] == "meaning_multi" for w in today["new_words"])
    assert all(w["quiz"]["option_count"] == len(w["quiz"]["options"]) for w in today["new_words"])
    word_id = today["new_words"][0]["id"]
    correct = _sense_ids(book_id, word_id)

    # 全选正确 → 毕业（reviewing），有稳定性与难度
    resp = api_client.post(
        "/api/study/answer",
        json={"kind": "word", "target_id": word_id, "phase": "meaning", "selected_ids": correct},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["result"] == "correct"
    assert body["status"] == "reviewing"
    assert body["stability"] > 0
    assert 1.0 <= body["difficulty"] <= 10.0

    # 进度：该词已计入新词完成
    progress = api_client.get("/api/study/progress").json()
    assert progress["new_done"] == 1
    assert progress["new_target"] == 5

    # 多义词漏选 → partial（Hard），不重置 reps
    second_id = next(w["id"] for w in today["new_words"] if w["spelling"] == "manifest")
    second_correct = _sense_ids(book_id, second_id)
    partial = api_client.post(
        "/api/study/answer",
        json={
            "kind": "word",
            "target_id": second_id,
            "phase": "meaning",
            "selected_ids": [second_correct[0]],
        },
    ).json()
    assert partial["result"] == "partial"
    assert partial["selected_correct"] == 1

    # 一个都不选 → wrong
    wrong = api_client.post(
        "/api/study/answer",
        json={"kind": "word", "target_id": second_id, "phase": "review", "selected_ids": []},
    ).json()
    assert wrong["result"] == "wrong"

    # 参数校验
    assert (
        api_client.post(
            "/api/study/answer",
            json={"kind": "word", "phase": "meaning", "selected_ids": []},
        ).status_code
        == 422
    )
    assert (
        api_client.post(
            "/api/study/answer",
            json={
                "kind": "word",
                "target_id": 999999,
                "phase": "review",
                "selected_ids": [1],
            },
        ).status_code
        == 404
    )

    # 设置
    settings = api_client.put("/api/settings", json={"new_per_day": 50, "review_per_day": 100})
    assert settings.status_code == 200
    assert settings.json()["new_per_day"] == 50

    # 删除当前词书 → 配置清空，今日任务提示先选词书
    assert api_client.delete(f"/api/books/{book_id}").status_code == 200
    assert api_client.get("/api/settings").json()["active_book_id"] is None
    assert api_client.get("/api/study/today").status_code == 400


def test_upload_rejects_non_markdown(auth_client):
    api_client = auth_client
    resp = api_client.post(
        "/api/books/upload",
        files={"file": ("words.pdf", b"not a markdown", "application/pdf")},
    )
    assert resp.status_code == 400
