import uuid


def unique():
    return f"rl_{uuid.uuid4().hex[:10]}"


def test_sliding_window_limiter(api_client):
    from app.services.rate_limit import SlidingWindowLimiter

    limiter = SlidingWindowLimiter()
    assert limiter.check("key", 2, 60) is None
    assert limiter.check("key", 2, 60) is None
    retry_after = limiter.check("key", 2, 60)
    assert retry_after is not None and retry_after > 0
    # 不同 key 互不影响
    assert limiter.check("other", 2, 60) is None
    limiter.reset()
    assert limiter.check("key", 2, 60) is None


def test_login_rate_limit_returns_429(api_client, monkeypatch):
    from app.config import config
    from app.services.rate_limit import limiter

    limiter.reset()
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(config, "LOGIN_RATE_LIMIT", 2)

    name = unique()
    for _ in range(2):
        resp = api_client.post("/api/auth/login", json={"username": name, "password": "wrong-pass"})
        assert resp.status_code == 401

    limited = api_client.post("/api/auth/login", json={"username": name, "password": "wrong-pass"})
    assert limited.status_code == 429
    assert limited.headers.get("Retry-After")
    assert "频繁" in limited.json()["detail"]
    limiter.reset()
