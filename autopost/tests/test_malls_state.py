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


def test_cloudflare_403_switches_to_browser(monkeypatch):
    from autopost import browser

    class R:
        ok, status_code = False, 403
        text = "<html><title>Attention Required! | Cloudflare</title>"
    calls = {"req": 0, "browser": []}

    def fake_get(*a, **k):
        calls["req"] += 1
        return R()
    monkeypatch.setattr(malls.requests, "get", fake_get)
    monkeypatch.setattr(malls.time, "sleep", lambda s: None)
    monkeypatch.setattr(browser, "fetch_json", lambda url, headers=None, hint=None: calls["browser"].append(url) or {"data": {"ok": 1}})
    malls._blocked_hosts.clear()
    assert malls._get("https://goods-detail.musinsa.com/api2/goods/1") == {"data": {"ok": 1}}
    assert malls._get("https://goods-detail.musinsa.com/api2/goods/2") == {"data": {"ok": 1}}
    assert calls["req"] == 1 and len(calls["browser"]) == 2   # 두 번째부터는 requests를 건너뜀
    # 브라우저도 못 쓰면 원래 403 오류
    monkeypatch.setattr(browser, "fetch_json", lambda *a, **k: (_ for _ in ()).throw(browser.BrowserUnavailable("x")))
    malls._blocked_hosts.clear()
    with pytest.raises(malls.MallError):
        malls._get("https://goods-detail.musinsa.com/api2/goods/3")
    malls._blocked_hosts.clear()
