SAMPLE_BOOK = """# 测试词书

| 单词 | 音标 | 释义 | 例句 |
|---|---|---|---|
| abandon | /əˈbændən/ | v. 放弃 | He abandoned it. 他放弃了。 |
| benefit | /ˈbenɪfɪt/ | n. 好处 | |
| crucial | /ˈkruːʃl/ | adj. 至关重要的 | |
| emerge | /ɪˈmɜːdʒ/ | v. 出现 | |
"""


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
    assert resp.json()["imported"] == 4

    books = api_client.get("/api/books").json()
    assert len(books) == 1 and books[0]["is_active"] is True
    book_id = books[0]["id"]

    # 今日任务：4 个新词，均带题目
    today = api_client.get("/api/study/today").json()
    assert len(today["new_words"]) == 4
    assert all(w["quiz"] and len(w["quiz"]["options"]) == 4 for w in today["new_words"])
    word_id = today["new_words"][0]["id"]

    # 新词自评「不认识」→ 未毕业（learning）
    resp = api_client.post(
        "/api/study/answer",
        json={"word_id": word_id, "phase": "new_first", "result": "unknown"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "learning"

    # 挖空答对 → 毕业（reviewing），有稳定性与难度
    resp = api_client.post(
        "/api/study/answer",
        json={"word_id": word_id, "phase": "new_quiz", "result": "correct"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "reviewing"
    assert body["stability"] > 0
    assert 1.0 <= body["difficulty"] <= 10.0

    # 进度：该词已计入新词完成
    progress = api_client.get("/api/study/progress").json()
    assert progress["new_done"] == 1
    assert progress["new_target"] == 4

    # 第二个词自评「认识」→ 直接毕业
    second_id = next(w["id"] for w in today["new_words"] if w["id"] != word_id)
    resp = api_client.post(
        "/api/study/answer",
        json={"word_id": second_id, "phase": "new_first", "result": "know"},
    )
    assert resp.json()["status"] == "reviewing"

    # 复习答错 → 退回重学
    wrong = api_client.post(
        "/api/study/answer",
        json={"word_id": second_id, "phase": "review", "result": "wrong"},
    ).json()
    assert wrong["status"] == "learning"

    # 重学答对 → 再次毕业
    relearn = api_client.post(
        "/api/study/answer",
        json={"word_id": second_id, "phase": "relearn", "result": "correct"},
    ).json()
    assert relearn["status"] == "reviewing"

    # 参数校验
    assert (
        api_client.post(
            "/api/study/answer",
            json={"word_id": word_id, "phase": "bogus", "result": "correct"},
        ).status_code
        == 400
    )
    assert (
        api_client.post(
            "/api/study/answer",
            json={"word_id": 999999, "phase": "review", "result": "correct"},
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
