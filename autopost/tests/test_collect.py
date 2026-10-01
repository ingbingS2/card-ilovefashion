from __future__ import annotations

import json
from datetime import date

from autopost import collect, config, malls, malls29
from autopost.tests.conftest import make_candidate


def test_ranking_skips_banner_slots(monkeypatch):
    payload = {"data": {"modules": [{"type": "MULTICOLUMN", "items": [
        {"id": "1", "image": {"rank": 1}, "info": {"brandName": "A", "productName": "니트", "finalPrice": 1}},
        {"id": None, "image": {}, "info": {}}]}]}}
    monkeypatch.setattr(malls, "_get", lambda *a, **k: payload)
    rows = malls.ranking("001")
    assert [r["name"] for r in rows] == ["니트"]


def _fix_now(monkeypatch):
    monkeypatch.setattr(config, "now_kst", lambda: config.datetime(2026, 10, 2, 7, tzinfo=config.KST))


def test_candidates_filters_caps_and_mixes_malls(monkeypatch):
    musinsa_rows = (
        [{"goodsNo": 10 + i, "brandName": "무신사 스탠다드 우먼", "reviewCount": 100 - i} for i in range(5)]
        + [{"goodsNo": 30, "brandName": "핀카", "reviewCount": 50},
           {"goodsNo": 31, "brandName": "핀카", "reviewCount": 49, "isSoldOut": True},
           {"goodsNo": 32, "brandName": "미치코런던 코시노", "reviewCount": 48},
           {"goodsNo": 33, "brandName": "에트오소메", "reviewCount": 47},   # 직전 회차(시드 부츠) 브랜드
           {"goodsNo": 34, "brandName": "오래된브랜드", "reviewCount": 46}])
    cm_rows = [{"itemNo": 900, "frontBrandNameKor": "노티아", "reviewCount": 80, "frontCategoryInfo": [
                   {"categoryLargeName": "여성의류"}]},
               {"itemNo": 901, "frontBrandNameKor": "남자브랜드", "reviewCount": 90, "frontCategoryInfo": [
                   {"categoryLargeName": "남성의류"}]},
               {"itemNo": 902, "frontBrandNameKor": "MICHIKO", "frontBrandNameEng": "michiko london",
                "reviewCount": 70}]
    monkeypatch.setattr(malls, "search", lambda q, gf="A", size=60: musinsa_rows)
    monkeypatch.setattr(malls29, "search", lambda q, size=50: cm_rows)
    brands = {r["goodsNo"]: r["brandName"] for r in musinsa_rows}
    brands.update({r["itemNo"]: r["frontBrandNameKor"] for r in cm_rows})

    def fake_build(no, handles):
        rd = "2023-05-01" if brands[no] == "오래된브랜드" else "2026-08-01"
        return make_candidate(no, brands[no], release_date=rd)

    def fake_build29(no, handles):
        return make_candidate(no, brands[no], mall="29CM")

    monkeypatch.setitem(collect.BUILDERS, "무신사", fake_build)
    monkeypatch.setitem(collect.BUILDERS, "29CM", fake_build29)
    monkeypatch.setattr(collect, "contact_sheet", lambda c, p: None)
    monkeypatch.setattr(collect, "cheaper_elsewhere", lambda c: None)
    _fix_now(monkeypatch)
    res = collect.candidates("20261002 가을 니트", ["가을 니트"], gf="F")
    got = [(c["mall"], c["goodsNo"]) for c in res["candidates"]]
    assert ("29CM", 900) in got and ("29CM", 901) not in got and ("29CM", 902) not in got
    assert [n for m, n in got if m == "무신사"] == [10, 11, 30]
    assert got[0] == ("무신사", 10) and got[1] == ("29CM", 900)  # 두 몰을 번갈아
    d = res["dropped"]
    assert d["품절"] == 1 and d["일시 제외 브랜드"] == 2 and d["직전 회차 브랜드"] == 1
    assert d["브랜드당 2개 초과(색상 변형 등)"] == 3
    assert any("신상 기준" in k for k in d)
    saved = json.loads((config.episode_dir("20261002 가을 니트") / "candidates.json").read_text(encoding="utf-8"))
    assert [(c["mall"], c["goodsNo"]) for c in saved["candidates"]] == got


def test_musinsa_search_blocked_falls_back_to_ranking(monkeypatch):
    def blocked(*a, **k):
        raise malls.MallError("HTTP 403 cloudflare")
    monkeypatch.setattr(malls, "search", blocked)
    monkeypatch.setattr(malls29, "search", lambda q, size=50: [])
    monkeypatch.setattr(malls, "ranking", lambda code, gf="F": [
        {"rank": 1, "goodsNo": "77", "brand": "핀카", "name": "울 니트 가디건"},
        {"rank": 2, "goodsNo": "78", "brand": "B", "name": "데님 팬츠"}])
    notes = []
    rows = collect.search_rows(["가을 니트"], "F", notes)
    assert {r["no"] for r in rows} == {77}
    assert any("랭킹으로 대체" in n for n in notes)


def test_cheaper_elsewhere_matches_same_product(monkeypatch):
    c = make_candidate(10, "노티아", name="[노티아] 울 블렌드 라운드 니트 가디건", sale_price=59000)
    monkeypatch.setattr(malls29, "search", lambda q, size=10: [
        {"itemNo": 555, "frontBrandNameKor": "노티아", "itemName": "울 블렌드 라운드 니트 가디건 (3color)"}])
    monkeypatch.setattr(malls29, "detail", lambda no: {"sellPrice": 55000, "consumerPrice": 79000})
    alt = collect.cheaper_elsewhere(c)
    assert alt == {"mall": "29CM", "goodsNo": 555, "sale_price": 55000,
                   "url": "https://product.29cm.co.kr/catalog/555"}
    monkeypatch.setattr(malls29, "detail", lambda no: {"sellPrice": 61000, "consumerPrice": 79000})
    assert collect.cheaper_elsewhere(c) is None


def test_malls29_parsers():
    d = {"sellPrice": 93220, "consumerPrice": 118000, "discountRate": 21,
         "availableBeginTimestamp": "2026-09-01 10:00:00", "visibleBeginTimestamp": "2026-09-20 10:00:00",
         "reviewAggregation": {"totalCount": 133, "averagePoint": 4.96},
         "itemImages": [{"imageUrl": "/item/202608/a.jpg"}, {"imageUrl": "/item/202608/a.jpg"},
                        {"imageUrl": "https://img.29cm.co.kr/item/b.jpg"}],
         "isSoldout": False, "frontItemStockStatus": "ON_SALE",
         "itemModelSizes": [{"height": 168, "size": "S"}], "itemDescriptions": ["총장 62cm"]}
    assert malls29.price_facts(d) == {"sale_price": 93220, "normal_price": 118000, "discount": 21}
    assert malls29.release_date(d) == date(2026, 9, 1)
    assert malls29.review_summary(d) == {"review_count": 133, "rating": 5.0}
    assert malls29.images(d) == ["https://img.29cm.co.kr/item/202608/a.jpg", "https://img.29cm.co.kr/item/b.jpg"]
    assert not malls29.sold_out(d)
    assert malls29.sold_out({"frontItemStockStatus": "SOLD_OUT"})
    assert "168" in malls29.spec_text(d) and "총장 62cm" in malls29.spec_text(d)
    assert malls29.price_facts({"sellPrice": 80000, "consumerPrice": 100000}) == \
        {"sale_price": 80000, "normal_price": 100000, "discount": 20}
