"""copywriter 테스트 — Claude 호출 목, 네트워크 없음."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import copywriter


def prod(pid="1", rank=1, count=5, reviews=None):
    return {"mall": "musinsa", "product_id": pid, "rank": rank, "brand": "브랜드",
            "name": "아주 긴 상품명이 들어가는 자리입니다 이건 삼십자를 넘겼습니다 확실히요",
            "price": 19900, "original_price": 25000, "discount_rate": 20,
            "review_score": 4.8, "review_count": count, "thumbnail": None,
            "product_url": "u", "category_code": "001", "category_name": "상의",
            "reviews": reviews if reviews is not None else
            [{"score": 5, "text": "재질이 좋고 배송이 빨랐어요. 다음에 또 살 것 같아요", "date": None, "likes": 1}],
            "image_path": None}


def test_fallback_structure_and_rules():
    c = copywriter.fallback_copy([prod(), prod("2", rank=3, count=0, reviews=[])], "랭킹 픽")
    assert set(c) == {"topic", "cover", "items", "cta", "caption"}
    assert len(c["items"]) == 2
    it = c["items"][0]
    assert "브랜드" in it["prod"] and "<b>" in it["prod"]
    assert len(it["prod"]) < 90  # 30자 절단 반영
    assert it["badge"] == "20%"
    assert "후기 5개" in it["proof"]
    assert "실제 후기" in it["sp"]
    it2 = c["items"][1]
    assert it2["proof"] == "신상 픽"
    assert "랭킹 3위" in it2["sp"]
    cap = c["caption"]
    assert "#" not in cap  # 2026-07-22 사용자 지시: 해시태그 금지
    assert "…" not in cap and "..." not in cap


def test_write_copy_without_key_uses_fallback():
    c = copywriter.write_copy([prod()], api_key=None)
    assert c["cover"]["kicker"].startswith("TODAY PICK")


def test_write_copy_claude_success(monkeypatch):
    fake = {"topic": "T", "cover": {"kicker": "K", "title": "T<em>t</em>", "sub": "s"},
            "items": [{"prod": "p", "title": "t", "meta": "m", "proof": "pr", "sp": "s", "badge": None}],
            "cta": {"title": "c", "sub": "s"}, "caption": "cap"}
    import json
    monkeypatch.setattr(copywriter, "_call_claude", lambda products, topic, key: json.dumps(fake))
    c = copywriter.write_copy([prod()], topic="T", api_key="sk-test")
    assert c["cover"]["kicker"] == "K"


def test_write_copy_claude_failure_falls_back(monkeypatch):
    def boom(products, topic, key):
        raise RuntimeError("api down")
    monkeypatch.setattr(copywriter, "_call_claude", boom)
    c = copywriter.write_copy([prod()], api_key="sk-test")
    assert c["cover"]["kicker"].startswith("TODAY PICK")  # 폴백 전환, 예외 없음
