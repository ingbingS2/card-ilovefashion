"""crawl_once 오케스트레이션 테스트 — fetch/parse/store 전부 페이크."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from main import crawl_once
from store import LocalJsonStore


def _prod(mall, pid, count):
    return {"mall": mall, "product_id": pid, "rank": 1, "brand": "b", "name": "n",
            "price": 1, "original_price": None, "discount_rate": 0,
            "review_score": 5.0, "review_count": count, "thumbnail": None,
            "product_url": "u", "category_code": "001", "category_name": None}


class FakeFetch:
    def __init__(self):
        self.review_calls = []

    def fetch_musinsa_ranking(self, category_code, page=1):
        return {"cat": category_code}

    def fetch_cm29_best(self, page=1, size=100, category_large_id=None, category_middle_id=None):
        return {"best": True}

    def fetch_musinsa_reviews(self, goods_no, size=10):
        self.review_calls.append(("musinsa", goods_no))
        return {}

    def fetch_cm29_reviews(self, item_id, size=10):
        self.review_calls.append(("cm29", item_id))
        return {}


class FakeParse:
    def __init__(self, m_items, c_items):
        self.m, self.c = m_items, c_items

    def parse_musinsa_ranking(self, data):
        return self.m[data["cat"]]

    def parse_cm29_best(self, data):
        return self.c

    def parse_musinsa_reviews(self, data):
        return [{"score": 5, "text": "굿", "date": None, "likes": 0}]

    def parse_cm29_reviews(self, data):
        return [{"score": 5, "text": "좋아요", "date": None, "likes": 0}]


def test_crawl_once_full_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CM29_CATEGORIES", {})
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {"001": "상의"})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()
    parse = FakeParse({"001": [_prod("musinsa", "a", 3)]}, [_prod("cm29", "x", 7)])

    stats = crawl_once(store, "t1", fetch=fetch, parse=parse)
    assert stats["rankings_saved"] == 2          # 무신사 001 + 29CM best
    assert stats["products_saved"] == 2
    assert stats["reviews_fetched"] == 2          # 첫 실행 = 전부 신규
    assert stats["errors"] == []
    doc = json.load(open(tmp_path / "products" / "musinsa_a.json", encoding="utf-8"))
    assert doc["reviews"][0]["text"] == "굿"


def test_crawl_once_incremental_reviews(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CM29_CATEGORIES", {})
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {"001": "상의"})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()
    parse = FakeParse({"001": [_prod("musinsa", "a", 3)]}, [_prod("cm29", "x", 7)])
    crawl_once(store, "t1", fetch=fetch, parse=parse)
    fetch.review_calls.clear()

    # 2회차: musinsa a 는 후기 수 동일(3) → 스킵, cm29 x 는 7→9 변동 → 수집
    parse.c = [_prod("cm29", "x", 9)]
    stats = crawl_once(store, "t2", fetch=fetch, parse=parse)
    assert fetch.review_calls == [("cm29", "x")]
    assert stats["reviews_fetched"] == 1
    doc = json.load(open(tmp_path / "products" / "musinsa_a.json", encoding="utf-8"))
    assert doc["reviews"][0]["text"] == "굿"      # 유지됨
    assert len(doc["history"]) == 2


def test_crawl_once_category_failure_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CM29_CATEGORIES", {})
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {"001": "상의", "002": "아우터"})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()

    def boom(category_code, page=1):
        if category_code == "001":
            raise RuntimeError("몰 응답 이상")
        return {"cat": category_code}

    fetch.fetch_musinsa_ranking = boom
    parse = FakeParse({"002": [_prod("musinsa", "b", 1)]}, [])
    stats = crawl_once(store, "t1", fetch=fetch, parse=parse)
    assert len(stats["errors"]) == 1 and "001" in stats["errors"][0]
    assert store.load_ranking("musinsa", "001") is None   # 실패 카테고리는 미저장
    assert store.load_ranking("musinsa", "002") is not None


def test_crawl_once_review_fetch_failure_not_counted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CM29_CATEGORIES", {})
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {"001": "상의"})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()

    def boom_cm29_reviews(item_id, size=10):
        raise RuntimeError("후기 서버 오류")

    fetch.fetch_cm29_reviews = boom_cm29_reviews
    parse = FakeParse({"001": [_prod("musinsa", "a", 3)]}, [_prod("cm29", "x", 7)])

    stats = crawl_once(store, "t1", fetch=fetch, parse=parse)
    # musinsa a 수집 성공(1) + cm29 x 후기 실패(0) = 1건만 집계
    assert stats["reviews_fetched"] == 1
    # cm29 x 후기 실패가 오류 목록에 기록됨
    assert any("후기 수집 실패" in err and "cm29" in err for err in stats["errors"])
    # 상품은 여전히 저장됨 (cm29 x)
    doc = json.load(open(tmp_path / "products" / "cm29_x.json", encoding="utf-8"))
    assert doc["product_id"] == "x"  # 상품 정보는 저장됨


class FlakyProductStore(LocalJsonStore):
    """지정한 product_id 저장 시 예외를 던지는 페이크 저장소."""

    def __init__(self, out_dir, fail_pid):
        super().__init__(out_dir)
        self.fail_pid = fail_pid

    def save_product(self, product, reviews, now_iso):
        if product["product_id"] == self.fail_pid:
            raise RuntimeError("상품 저장 실패")
        super().save_product(product, reviews, now_iso)


def test_crawl_once_product_save_failure_skips_ranking_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CM29_CATEGORIES", {})
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {"001": "상의", "002": "아우터"})
    store = FlakyProductStore(str(tmp_path), fail_pid="a")
    fetch = FakeFetch()
    parse = FakeParse(
        {"001": [_prod("musinsa", "a", 3)], "002": [_prod("musinsa", "b", 1)]}, [])

    stats = crawl_once(store, "t1", fetch=fetch, parse=parse)

    assert any("001" in err for err in stats["errors"])
    # 상품 저장 실패 카테고리는 랭킹 스냅샷도 저장되면 안 됨(불일치 방지)
    assert store.load_ranking("musinsa", "001") is None
    # 다른 카테고리는 정상 저장됨
    assert store.load_ranking("musinsa", "002") is not None


def test_crawl_once_cm29_single_facet_category(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {})
    monkeypatch.setattr(config, "CM29_CATEGORIES",
                        {"bag": {"name": "가방", "facets": [{"large": 269100100}]}})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()
    calls = []
    orig = fetch.fetch_cm29_best

    def spy(page=1, size=100, category_large_id=None, category_middle_id=None):
        calls.append((category_large_id, category_middle_id))
        return orig(page=page, size=size)

    fetch.fetch_cm29_best = spy
    parse = FakeParse({}, [_prod("cm29", "x", 7)])
    stats = crawl_once(store, "t1", fetch=fetch, parse=parse)
    assert calls == [(None, None), (269100100, None)]  # 전체 베스트 + 가방
    assert stats["rankings_saved"] == 2
    snap = store.load_ranking("cm29", "bag")
    assert snap["items"][0]["category_name"] == "가방"


def test_crawl_once_cm29_combined_category_interleaves(tmp_path, monkeypatch):
    """원피스/스커트 처럼 facet 이 둘이면 두 랭킹을 교차 병합한다."""
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {})
    monkeypatch.setattr(config, "CM29_CATEGORIES", {"opset": {"name": "원피스/스커트", "facets": [
        {"large": 268100100, "middle": 268104100},
        {"large": 268100100, "middle": 268107100},
    ]}})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()
    mids = []
    orig = fetch.fetch_cm29_best

    def spy(page=1, size=100, category_large_id=None, category_middle_id=None):
        mids.append(category_middle_id)
        # facet 별로 다른 상품을 돌려주도록 middle 을 태그로 심는다
        return {"mid": category_middle_id}

    fetch.fetch_cm29_best = spy

    class P2:
        def parse_cm29_best(self, data):
            mid = data.get("mid")
            if mid is None:
                return [_prod("cm29", "best", 1)]
            tag = "dress" if mid == 268104100 else "skirt"
            return [_prod("cm29", f"{tag}{i}", 1) for i in range(3)]
        def parse_musinsa_ranking(self, d): return []
        def parse_musinsa_reviews(self, d): return []
        def parse_cm29_reviews(self, d): return []

    stats = crawl_once(store, "t1", fetch=fetch, parse=P2())
    assert 268104100 in mids and 268107100 in mids
    snap = store.load_ranking("cm29", "opset")
    ids = [it["product_id"] for it in snap["items"]]
    assert ids[:4] == ["dress0", "skirt0", "dress1", "skirt1"]  # 교차 병합
    assert snap["items"][0]["rank"] == 1 and snap["items"][1]["rank"] == 2
