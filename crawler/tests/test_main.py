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

    def fetch_cm29_best(self, page=1, size=100):
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
