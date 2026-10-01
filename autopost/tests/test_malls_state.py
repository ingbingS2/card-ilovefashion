from __future__ import annotations

from datetime import date

import pytest

from autopost import malls, state


def test_full_image_url_big():
    assert malls.full_image_url("/images/goods_img/20260731/6966779/6966779_1788_500.jpg") == \
        "https://image.msscdn.net/images/goods_img/20260731/6966779/6966779_1788_big.jpg"
    assert malls.full_image_url("//image.msscdn.net/a/b_60.png").endswith("/a/b_big.png")


def test_release_date_is_earliest_image_folder():
    d = {"goodsImages": [{"imageUrl": "/images/prd_img/20260805/1/detail_1_500.jpg"},
                         {"imageUrl": "/images/goods_img/20260731/1/1_500.jpg"}],
         "thumbnailImageUrl": "/images/goods_img/20260901/1/1_500.jpg"}
    assert malls.release_date(d) == date(2026, 7, 31)
    assert malls.release_date({}) is None


def test_season_and_material_and_price():
    assert malls.season_label({"seasonYear": "2026", "season": 2}) == "2026 F/W"
    assert malls.season_label({"seasonYear": "0000", "season": 2}) == ""
    d = {"goodsMaterial": {"materials": [
        {"name": "핏", "items": [{"name": "루즈", "isSelected": True}, {"name": "슬림", "isSelected": False}]},
        {"name": "두께", "items": [{"name": "약간|두꺼움", "isSelected": True}]}]},
         "goodsPrice": {"salePrice": 105000, "normalPrice": 185000, "discountRate": 43, "couponPrice": 99000},
         "goodsReview": {"totalCount": 19, "satisfactionScore": 4.95}}
    assert malls.material_facts(d) == ["핏: 루즈", "두께: 약간 두꺼움"]
    assert malls.price_facts(d) == {"sale_price": 105000, "normal_price": 185000, "discount": 43}
    assert malls.review_summary(d) == {"review_count": 19, "rating": 5.0}


def test_strip_html():
    assert malls.strip_html("<p>총장 62cm</p><script>x()</script><br>어깨&nbsp;51cm") == "총장 62cm\n어깨 51cm"


def test_find_handle_exact_then_prefix(handles):
    assert state.find_handle(handles, "무드인사이드 우먼")["handle"] == "moodinside_official"
    assert state.find_handle(handles, "", "MOOD INSIDE")["handle"] == "moodinside_official"
    assert state.find_handle(handles, "전혀다른브랜드") is None


def test_history_falls_back_to_seed():
    rows = state.load_history()
    assert rows and rows[-1]["keyword"] == "가을 부츠"
    assert state.last_post(rows)["keyword"] == "가을 부츠"
    state.save_history(rows[:1])
    assert len(state.load_history()) == 1


class _Resp:
    def __init__(self, status: int, text: str = "", payload: dict | None = None):
        self.status_code, self.text, self._payload = status, text, payload
        self.ok = 200 <= status < 300

    def json(self):
        return self._payload


def test_cloudflare_403_blocks_host_without_bypass(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        if "client.musinsa.com" in url:
            return _Resp(200, payload={"data": {"ok": 1}})
        return _Resp(403, "<html><title>Attention Required! | Cloudflare</title>")
    monkeypatch.setattr(malls.requests, "get", fake_get)
    monkeypatch.setattr(malls.time, "sleep", lambda s: None)
    monkeypatch.setattr(malls, "_blocked_hosts", set())
    with pytest.raises(malls.MallError, match="무신사 차단.*우회하지 않음"):
        malls._get("https://goods-detail.musinsa.com/api2/goods/1")
    assert len(calls) == 1                                  # 재시도·브라우저 경유 없음
    with pytest.raises(malls.MallError, match="차단"):
        malls._get("https://goods-detail.musinsa.com/api2/goods/2")
    assert len(calls) == 1                                  # 같은 호스트는 네트워크 없이 바로 실패
    assert malls._get(malls.RANKING_URL) == {"data": {"ok": 1}}   # 다른 호스트(랭킹)는 그대로
    assert not hasattr(malls, "_browser_fallback")


def test_plain_403_is_not_retried_or_remembered(monkeypatch):
    calls = []
    monkeypatch.setattr(malls.requests, "get", lambda url, **k: calls.append(url) or _Resp(403, "forbidden"))
    monkeypatch.setattr(malls.time, "sleep", lambda s: None)
    monkeypatch.setattr(malls, "_blocked_hosts", set())
    with pytest.raises(malls.MallError, match="HTTP 403"):
        malls._get("https://goods.musinsa.com/api2/review/v1/view/list")
    assert len(calls) == 1 and not malls._blocked_hosts


def test_29cm_detail_circuit_breaker(monkeypatch):
    from autopost import malls29

    class Session:
        def __init__(self):
            self.statuses: list[int] = []
            self.calls = 0

        def get(self, url, timeout=None):
            self.calls += 1
            st = self.statuses.pop(0)
            return _Resp(st, payload={"data": {"itemNo": 1}})
    s = Session()
    monkeypatch.setattr(malls29, "_session", s)
    monkeypatch.setattr(malls29, "_bff_403_streak", 0)
    monkeypatch.setattr(malls29.time, "sleep", lambda sec: None)

    # 403 두 번(각각 재시도 포함) → 성공으로 초기화 → 다시 403 두 번은 아직 차단 아님
    s.statuses = [403, 403, 403, 403, 200, 403, 403, 403, 403]
    for _ in range(2):
        with pytest.raises(malls.MallError, match="HTTP 403"):
            malls29.detail(1)
    assert malls29.detail(1) == {"itemNo": 1} and malls29._bff_403_streak == 0
    for _ in range(2):
        with pytest.raises(malls.MallError, match="HTTP 403"):
            malls29.detail(1)
    # 세 번째 연속 403(재시도 후) → 차단, 그 뒤로는 호출 없이 바로 실패
    s.statuses = [403, 403]
    with pytest.raises(malls.MallError, match="29CM 상세 차단 — 이번 실행 중단"):
        malls29.detail(1)
    before = s.calls
    with pytest.raises(malls.MallError, match="29CM 상세 차단 — 이번 실행 중단"):
        malls29.detail(2)
    assert s.calls == before
    # 404 같은 다른 실패는 연속 횟수에 넣지 않는다(재시도도 없음)
    monkeypatch.setattr(malls29, "_bff_403_streak", 2)
    s.statuses = [404]
    with pytest.raises(malls.MallError, match="HTTP 404"):
        malls29.detail(3)
    assert malls29._bff_403_streak == 2
