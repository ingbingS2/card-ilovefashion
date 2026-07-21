"""fetchers 테스트 — requests 목 처리, 실제 네트워크·sleep 없음."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fetchers


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body if body is not None else {"ok": True}
        self.text = str(self._body)

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(fetchers.time, "sleep", lambda s: None)


def test_musinsa_ranking_builds_params(monkeypatch):
    captured = {}

    def fake_request(method, url, **kw):
        captured.update(method=method, url=url, **kw)
        return FakeResp()

    monkeypatch.setattr(fetchers.requests, "request", fake_request)
    out = fetchers.fetch_musinsa_ranking("001")
    assert out == {"ok": True}
    assert captured["method"] == "GET"
    assert "sections/200" in captured["url"]
    p = captured["params"]
    assert p["categoryCode"] == "001" and p["storeCode"] == "musinsa" and p["page"] == 1


def test_cm29_best_posts_json_body(monkeypatch):
    captured = {}

    def fake_request(method, url, **kw):
        captured.update(method=method, url=url, **kw)
        return FakeResp()

    monkeypatch.setattr(fetchers.requests, "request", fake_request)
    fetchers.fetch_cm29_best(page=2, size=100)
    assert captured["method"] == "POST"
    body = captured["json"]
    assert body["pageRequest"] == {"page": 2, "size": 100}
    assert body["facets"]["rankingFacetInput"]["type"] == "POPULARITY"
    assert captured["headers"]["Content-Type"] == "application/json"


def test_retry_then_success(monkeypatch):
    calls = {"n": 0}

    def flaky(method, url, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise fetchers.requests.exceptions.ConnectionError("boom")
        return FakeResp()

    monkeypatch.setattr(fetchers.requests, "request", flaky)
    assert fetchers.fetch_cm29_reviews("123") == {"ok": True}
    assert calls["n"] == 3


def test_gives_up_after_retries(monkeypatch):
    def always_500(method, url, **kw):
        return FakeResp(status=500)

    monkeypatch.setattr(fetchers.requests, "request", always_500)
    with pytest.raises(fetchers.FetchError):
        fetchers.fetch_musinsa_reviews("5928448")


def test_block_status_no_retry(monkeypatch):
    calls = {"n": 0}

    def blocked(method, url, **kw):
        calls["n"] += 1
        return FakeResp(status=403)

    monkeypatch.setattr(fetchers.requests, "request", blocked)
    with pytest.raises(fetchers.FetchError):
        fetchers.fetch_musinsa_ranking("001")
    assert calls["n"] == 1


def test_cm29_best_category_filter_body(monkeypatch):
    captured = {}

    def fake_request(method, url, **kw):
        captured.update(method=method, url=url, **kw)
        return FakeResp()

    monkeypatch.setattr(fetchers.requests, "request", fake_request)
    fetchers.fetch_cm29_best(category_large_id="269100100")
    assert captured["json"]["facets"]["categoryFacetInputs"] == [{"largeId": 269100100}]
    # 카테고리 없으면 필드 자체가 없어야 함
    fetchers.fetch_cm29_best()
    assert "categoryFacetInputs" not in captured["json"]["facets"]
