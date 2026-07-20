"""파서 단위 테스트 — 커밋된 픽스처만 사용, 네트워크 없음."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

FIX = Path(__file__).parent / "fixtures"


def fx(name):
    return json.load(open(FIX / name, encoding="utf-8"))


def test_parse_musinsa_ranking_normalizes():
    from parsers import parse_musinsa_ranking
    items = parse_musinsa_ranking(fx("musinsa_ranking.json"))
    assert len(items) == 3
    p = items[0]
    assert p["mall"] == "musinsa"
    assert isinstance(p["product_id"], str) and p["product_id"]
    assert p["product_url"] == f"https://www.musinsa.com/products/{p['product_id']}"
    assert isinstance(p["rank"], int) and p["rank"] >= 1
    assert p["brand"] and p["name"]
    assert p["price"] is None or isinstance(p["price"], int)
    # 평점: analytics payload 의 100점 문자열 → 5점 float 로 정규화
    assert p["review_score"] is None or (isinstance(p["review_score"], float) and 0 <= p["review_score"] <= 5)
    assert p["review_count"] is None or isinstance(p["review_count"], int)


def test_parse_musinsa_ranking_missing_payload_is_none():
    from parsers import parse_musinsa_ranking
    data = fx("musinsa_ranking.json")
    item = data["data"]["modules"][0]["items"][0]
    item.get("image", {}).pop("onClickLike", None)  # analytics payload 제거
    items = parse_musinsa_ranking(data)
    assert items[0]["review_score"] is None
    assert items[0]["review_count"] is None


def test_parse_musinsa_ranking_empty():
    from parsers import parse_musinsa_ranking
    assert parse_musinsa_ranking({"data": {"modules": []}}) == []


def test_parse_cm29_best_normalizes():
    from parsers import parse_cm29_best
    items = parse_cm29_best(fx("cm29_best.json"))
    assert len(items) == 3
    p = items[0]
    assert p["mall"] == "cm29"
    assert p["product_id"] and isinstance(p["product_id"], str)
    assert p["rank"] == 1 and items[1]["rank"] == 2  # 응답 순서 = 순위
    assert p["product_url"].startswith("https://")
    assert p["review_score"] is None or 0 <= p["review_score"] <= 5
    assert p["category_code"] is None or isinstance(p["category_code"], str)


def test_parse_cm29_best_empty():
    from parsers import parse_cm29_best
    assert parse_cm29_best({"data": {"list": []}}) == []
