from __future__ import annotations

import json

from autopost import collect, config, malls
from autopost.tests.conftest import make_candidate


def test_ranking_skips_banner_slots(monkeypatch):
    payload = {"data": {"modules": [{"type": "MULTICOLUMN", "items": [
        {"id": "1", "image": {"rank": 1}, "info": {"brandName": "A", "productName": "니트", "finalPrice": 1}},
        {"id": None, "image": {}, "info": {}}]}]}}
    monkeypatch.setattr(malls, "_get", lambda *a, **k: payload)
    rows = malls.ranking("001")
    assert [r["name"] for r in rows] == ["니트"]


def test_candidates_filters_and_caps_per_brand(monkeypatch):
    search_rows = (
        [{"goodsNo": 10 + i, "brandName": "무신사 스탠다드 우먼", "reviewCount": 100 - i} for i in range(5)]
        + [{"goodsNo": 30, "brandName": "핀카", "reviewCount": 50},
           {"goodsNo": 31, "brandName": "핀카", "reviewCount": 49, "isSoldOut": True},
           {"goodsNo": 32, "brandName": "미치코런던 코시노", "reviewCount": 48},
           {"goodsNo": 33, "brandName": "에트오소메", "reviewCount": 47},   # 직전 회차(시드 부츠) 브랜드
           {"goodsNo": 34, "brandName": "오래된브랜드", "reviewCount": 46}])
    monkeypatch.setattr(malls, "search", lambda q, gf="A", size=60: search_rows)

    def fake_build(no, handles):
        brand = next(r["brandName"] for r in search_rows if r["goodsNo"] == no)
        rd = "2023-05-01" if brand == "오래된브랜드" else "2026-08-01"
        return make_candidate(no, brand, release_date=rd)

    monkeypatch.setattr(collect, "build_candidate", fake_build)
    monkeypatch.setattr(collect, "contact_sheet", lambda c, p: None)
    monkeypatch.setattr(config, "now_kst", lambda: config.datetime(2026, 10, 2, 7, tzinfo=config.KST))
    res = collect.candidates("20261002 가을 니트", ["가을 니트"], gf="F")
    got = [c["goodsNo"] for c in res["candidates"]]
    assert got == [10, 11, 30]
    d = res["dropped"]
    assert d["품절"] == 1 and d["일시 제외 브랜드"] == 1 and d["직전 회차 브랜드"] == 1
    assert d["브랜드당 2개 초과(색상 변형 등)"] == 3
    assert any("신상 기준" in k for k in d)
    saved = json.loads((config.episode_dir("20261002 가을 니트") / "candidates.json").read_text(encoding="utf-8"))
    assert [c["goodsNo"] for c in saved["candidates"]] == got
