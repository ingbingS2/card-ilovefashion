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
         "isSoldout": False, "frontItemStockStatus": "ON_STOCK",
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
    # 카드 평점은 후기 API 평균(소수점), 없으면 상세 값
    assert malls29.card_review_numbers(d, 4.87) == {"review_count": 133, "rating": 4.9}
    assert malls29.card_review_numbers(d, None) == {"review_count": 133, "rating": 5.0}


def test_malls29_sold_out_uses_explicit_statuses():
    for st in ("SOLD_OUT", "sold_out", "STOP_SALE", "SALE_END", "OUT_OF_STOCK"):
        assert malls29.sold_out({"frontItemStockStatus": st}), st
    assert malls29.sold_out({"itemStockStatus": "SOLD_OUT"})
    for st in ("ON_STOCK", "SOLD_OUT_SOON", "NOT_SOLD_OUT", "NEW_UNKNOWN", ""):
        assert not malls29.sold_out({"frontItemStockStatus": st}), st   # 'SOLD' 부분 문자열로 판정하지 않는다
    assert not malls29.sold_out({"isSoldout": None, "itemStockStatus": 1, "frontItemStockStatus": "ON_STOCK"})
    assert malls29.sold_out({"isSoldout": True, "frontItemStockStatus": "NEW_UNKNOWN"})   # 플래그는 그대로 본다


def test_summary_handles_every_cheaper_elsewhere_form():
    res = {"folder": "f", "dropped": {}, "notes": [], "candidates": [
        make_candidate(1, "A"),
        make_candidate(2, "B", cheaper_elsewhere=None),
        make_candidate(3, "C", cheaper_elsewhere={"mall": "29CM", "goodsNo": 555, "sale_price": 55000,
                                                  "url": "https://product.29cm.co.kr/catalog/555"}),
        make_candidate(4, "D", cheaper_elsewhere={"unavailable": "다른 몰 검색 실패: 차단"})]}
    lines = collect.summary(res).splitlines()[2:]
    assert "⚠️" not in lines[0] and "⚠️" not in lines[1]
    assert lines[2].endswith(" | ⚠️29CM이 55,000원으로 더 쌈(555)")
    assert lines[3].endswith(" | ⚠️다른 몰 가격 비교 실패")


class _Resp:
    def __init__(self, status: int, text: str = "", payload: dict | None = None):
        self.status_code, self.text, self._payload = status, text, payload
        self.ok = 200 <= status < 300

    def json(self):
        return self._payload


def test_musinsa_blocked_continues_with_29cm_only(monkeypatch):
    """데이터센터 IP: 무신사 검색·상세 Cloudflare 403(랭킹만 열림) → 우회 없이 29CM 후보만, notes에 기록, 예외 없음."""
    ranking = {"data": {"modules": [{"type": "MULTICOLUMN", "items": [
        {"id": "77", "image": {"rank": 1}, "info": {"brandName": "핀카", "productName": "울 니트 가디건"}},
        {"id": "78", "image": {"rank": 2}, "info": {"brandName": "로에일", "productName": "케이블 니트"}}]}]}}
    hits: list[str] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        hits.append(url)
        if url.startswith("https://client.musinsa.com/"):
            return _Resp(200, payload=ranking)
        if "musinsa.com" in url:
            return _Resp(403, "<title>Attention Required! | Cloudflare</title>")
        raise AssertionError(f"예상 밖 호출 {url}")
    monkeypatch.setattr(malls.requests, "get", fake_get)
    monkeypatch.setattr(malls.time, "sleep", lambda s: None)
    monkeypatch.setattr(malls, "_blocked_hosts", set())
    monkeypatch.setattr(malls29, "search", lambda q, size=50: [
        {"itemNo": 900, "frontBrandNameKor": "노티아", "itemName": "울 니트", "reviewCount": 80},
        {"itemNo": 901, "frontBrandNameKor": "커스텀어클락", "itemName": "니트 가디건", "reviewCount": 70}])
    monkeypatch.setitem(collect.BUILDERS, "29CM",
                        lambda no, handles: make_candidate(no, {900: "노티아", 901: "커스텀어클락"}[no], mall="29CM"))
    monkeypatch.setattr(collect, "contact_sheet", lambda c, p: None)
    _fix_now(monkeypatch)

    res = collect.candidates("20261002 가을 니트", ["가을 니트", "니트 가디건"], gf="F")

    assert [(c["mall"], c["goodsNo"]) for c in res["candidates"]] == [("29CM", 900), ("29CM", 901)]
    assert any("무신사 검색 실패" in n for n in res["notes"])
    assert any("무신사 상세 API 차단" in n for n in res["notes"])
    assert sum("api.musinsa.com" in u for u in hits) == 1          # 검색: 첫 403 뒤로는 네트워크 없이 실패
    assert sum("goods-detail.musinsa.com" in u for u in hits) == 1  # 상세: 한 번 막히면 나머지는 건너뜀
    # 다른 몰 가격 비교도 막힌 호스트를 다시 치지 않고 'unavailable'로 남는다 → summary가 죽지 않는다
    assert all(c["cheaper_elsewhere"].get("unavailable") for c in res["candidates"])
    assert collect.summary(res).count("⚠️다른 몰 가격 비교 실패") == 2
    saved = json.loads((config.episode_dir("20261002 가을 니트") / "candidates.json").read_text(encoding="utf-8"))
    assert saved["notes"] == res["notes"]


def test_29cm_reorder_markers_are_dropped(monkeypatch):
    names = {900: "[컬러추가] 울 니트", 901: "(2차 재입고) 케이블 니트", 902: "리오더 니트 가디건",
             903: "[3차] 라운드 니트", 904: "울 블렌드 니트",
             905: "알파카 니트"}                         # 검색 이름은 깨끗하지만 상세 이름에 표기
    detail_names = {**names, 905: "알파카 니트 (컬러 추가)"}
    monkeypatch.setattr(malls, "search", lambda q, gf="A", size=60: [
        {"goodsNo": 10, "brandName": "핀카", "goodsName": "[컬러추가] 니트", "reviewCount": 5}])
    monkeypatch.setattr(malls29, "search", lambda q, size=50: [
        {"itemNo": no, "frontBrandNameKor": f"브랜드{no}", "itemName": nm, "reviewCount": 10} for no, nm in names.items()])
    built = []

    def fake_build29(no, handles):
        built.append(no)
        return make_candidate(no, f"브랜드{no}", mall="29CM", name=detail_names[no])
    monkeypatch.setitem(collect.BUILDERS, "29CM", fake_build29)
    monkeypatch.setitem(collect.BUILDERS, "무신사",
                        lambda no, handles: make_candidate(no, "핀카", name="[컬러추가] 니트"))
    monkeypatch.setattr(collect, "contact_sheet", lambda c, p: None)
    monkeypatch.setattr(collect, "cheaper_elsewhere", lambda c: None)
    _fix_now(monkeypatch)
    res = collect.candidates("20261002 가을 니트", ["니트"], gf="F")
    got = {(c["mall"], c["goodsNo"]) for c in res["candidates"]}
    assert got == {("29CM", 904), ("무신사", 10)}          # 무신사는 이미지 날짜로 판정하므로 그대로
    assert res["dropped"][collect.REORDER_DROP] == 5
    assert sorted(built) == [904, 905]                     # 검색 이름에 표기가 있으면 상세 조회도 안 한다


def test_candidates_append_keeps_existing_and_adds_new(monkeypatch):
    folder = "20261002 가을 니트"
    ep = config.episode_dir(folder)
    ep.mkdir(parents=True)
    old = {"folder": folder, "collected_at": "2026-10-02T07:00+09:00", "queries": ["가을 니트"], "gf": "F",
           "new_since": "2025-01-01", "notes": ["옛 메모"], "dropped": {"품절": 2},
           "candidates": [make_candidate(10, "핀카", cheaper_elsewhere={"mall": "29CM", "goodsNo": 900,
                                                                     "sale_price": 40000, "url": "u"}),
                          make_candidate(20, "로에일", mall="29CM")]}
    (ep / "candidates.json").write_text(json.dumps(old, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(malls, "search", lambda q, gf="A", size=60: [
        {"goodsNo": 10, "brandName": "핀카", "reviewCount": 9},      # 같은 몰+번호 → 중복
        {"goodsNo": 20, "brandName": "핀카", "reviewCount": 1}])     # 기존 29CM 20과 번호 충돌
    monkeypatch.setattr(malls29, "search", lambda q, size=50: [
        {"itemNo": 20, "frontBrandNameKor": "로에일", "itemName": "니트", "reviewCount": 9},   # 중복
        {"itemNo": 900, "frontBrandNameKor": "핀카", "itemName": "울 니트", "reviewCount": 8}])
    built, sheets = [], []
    monkeypatch.setitem(collect.BUILDERS, "무신사", lambda no, h: built.append(("무신사", no)) or make_candidate(no, "핀카"))
    monkeypatch.setitem(collect.BUILDERS, "29CM",
                        lambda no, h: built.append(("29CM", no)) or make_candidate(no, "핀카", mall="29CM"))
    monkeypatch.setattr(collect, "contact_sheet", lambda c, p: sheets.append(c["goodsNo"]))
    monkeypatch.setattr(collect, "cheaper_elsewhere", lambda c: None)
    _fix_now(monkeypatch)

    res = collect.candidates(folder, ["핀카 울 니트"], gf="F", append=True)
    assert [(c["mall"], c["goodsNo"]) for c in res["candidates"]] == [("무신사", 10), ("29CM", 20), ("29CM", 900)]
    assert res["candidates"][0]["cheaper_elsewhere"]["goodsNo"] == 900   # 기존 후보는 손대지 않는다
    assert built == [("29CM", 900)] and sheets == [900]                 # 새 상품만 조회·시트
    assert res["notes"][0] == "옛 메모" and any("--append" in n for n in res["notes"])
    assert res["queries"] == ["가을 니트", "핀카 울 니트"]
    assert res["dropped"]["품절"] == 2 and res["dropped"]["이미 후보에 있음(--append)"] == 2
    assert res["dropped"]["다른 몰과 번호 충돌"] == 1
    saved = json.loads((ep / "candidates.json").read_text(encoding="utf-8"))
    assert [c["goodsNo"] for c in saved["candidates"]] == [10, 20, 900]

    # --append 없이 다시 모으면 예전처럼 덮어쓴다
    res2 = collect.candidates(folder, ["핀카 울 니트"], gf="F")
    assert {c["goodsNo"] for c in res2["candidates"]} <= {10, 20, 900} and "옛 메모" not in res2["notes"]
    assert "appended_at" not in json.loads((ep / "candidates.json").read_text(encoding="utf-8"))


def test_cli_append_flag(monkeypatch):
    seen = {}
    monkeypatch.setattr(collect, "candidates", lambda *a, **k: seen.update(args=a, kw=k) or {})
    monkeypatch.setattr(collect, "summary", lambda r: "")
    collect.main(["candidates", "--folder", "f", "-q", "니트", "--append"])
    assert seen["kw"] == {"append": True}
    collect.main(["candidates", "--folder", "f", "-q", "니트"])
    assert seen["kw"] == {"append": False}


def test_single_29cm_failure_does_not_kill_mall(monkeypatch):
    """한 상품의 403·404는 그 후보만 버린다 — 몰 전체 차단(MallBlocked)일 때만 그 몰을 끊는다."""
    monkeypatch.setattr(malls, "search", lambda q, gf="A", size=60: [])
    monkeypatch.setattr(malls29, "search", lambda q, size=50: [
        {"itemNo": n, "frontBrandNameKor": b, "itemName": "울 니트", "reviewCount": 80}
        for n, b in ((900, "노티아"), (901, "커스텀어클락"), (902, "로에일"))])

    def build(no, handles):
        if no == 900:
            raise malls.MallError("29CM 상세 403 Forbidden")
        return make_candidate(no, {901: "커스텀어클락", 902: "로에일"}[no], mall="29CM")
    monkeypatch.setitem(collect.BUILDERS, "29CM", build)
    monkeypatch.setattr(collect, "contact_sheet", lambda c, p: None)
    monkeypatch.setattr(collect, "cheaper_elsewhere", lambda c: None)
    _fix_now(monkeypatch)
    res = collect.candidates("20261002 가을 니트", ["가을 니트"], gf="F")
    assert [c["goodsNo"] for c in res["candidates"]] == [901, 902]
    assert not any("차단" in n for n in res["notes"])

    def blocked(no, handles):
        raise malls.MallBlocked("29CM 상세 차단 — 이번 실행 중단")
    monkeypatch.setitem(collect.BUILDERS, "29CM", blocked)
    res = collect.candidates("20261002 가을 니트", ["가을 니트"], gf="F")
    assert res["candidates"] == [] and any("29CM 상세 API 차단" in n for n in res["notes"])
