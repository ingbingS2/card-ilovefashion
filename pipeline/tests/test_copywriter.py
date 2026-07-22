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
    # 후기 없을 때 sp 는 계절·상황형 문구 — '랭킹' 키워드를 쓰지 않는다 (사용자 지시)
    assert "랭킹" not in it2["sp"] and "상의" in it2["sp"]
    cap = c["caption"]
    assert "#" not in cap  # 2026-07-22 사용자 지시: 해시태그 금지
    assert "…" not in cap and "..." not in cap


def test_fallback_cm29_mall_name():
    p = prod()
    p["mall"] = "cm29"
    c = copywriter.fallback_copy([p], "랭킹 픽")
    it = c["items"][0]
    assert "29CM" in it["meta"]
    assert "cm29" not in it["meta"]
    assert it["cr"] == "이미지 출처 : 29CM"


def test_write_copy_without_key_uses_fallback():
    c = copywriter.write_copy([prod()], api_key=None)
    assert c["cover"]["kicker"].endswith("MOOD")  # 계절 무드 kicker


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
    assert c["cover"]["kicker"].endswith("MOOD")  # 계절 무드 kicker  # 폴백 전환, 예외 없음


def test_fallback_sp_skips_negative_reviews():
    """부정 후기(cs·배송 불만 등)는 셀링포인트로 쓰지 않는다 (2026-07-22 실사고 회귀)."""
    p = prod(reviews=[
        {"score": 2, "text": "상품은 괜찮은데 cs랑 배송이 너무 불편해요 환불도 안 되고", "date": None, "likes": 50},
        {"score": 5, "text": "핏이 예쁘고 재질도 좋아서 매일 입어요", "date": None, "likes": 3},
    ])
    c = copywriter.fallback_copy([p], "랭킹 픽")
    sp = c["items"][0]["sp"]
    assert "cs" not in sp.lower() and "불편" not in sp and "환불" not in sp
    assert "핏이 예쁘고" in sp  # 긍정 후기가 선택됨


def test_fallback_sp_no_positive_review_uses_feature_line():
    """긍정 후기가 하나도 없으면 후기 인용을 포기하고 상품 특징으로 폴백."""
    p = prod(reviews=[{"score": 1, "text": "배송 지연에 불량까지 최악이에요", "date": None, "likes": 9}])
    c = copywriter.fallback_copy([p], "랭킹 픽")
    sp = c["items"][0]["sp"]
    assert "최악" not in sp and "불량" not in sp and "지연" not in sp
    assert "실제 후기" not in sp  # 후기 인용 안 함


def test_clip_sentence_ends_on_boundary():
    """문장 중간에서 뚝 끊기지 않는다."""
    long = "정말 가볍고 튼튼해서 매일 들고 다녀요. 수납도 넉넉하고 디자인도 예뻐서 만족합니다"
    out = copywriter._clip_sentence(long, 20)
    assert out.endswith("다녀요.") or out.endswith("요.") or out.endswith("요") or out.endswith("…") is False
    assert "\n" not in out


def test_fallback_long_note_becomes_editor_pick_line():
    """긴 코멘트 → '에디터 픽' 라인, 후기 인용은 밀려나고 후기는 근거로만."""
    p = prod()
    p["note"] = "장마철 출근할 때 딱 좋고 색이 실물이 더 예뻐요"
    c = copywriter.fallback_copy([p], "여름 무드", month=7)
    it = c["items"][0]
    assert "에디터 픽" in it["sp"] and "장마철 출근할 때 딱" in it["sp"]
    assert "실제 후기" not in it["sp"]           # 후기 인용은 사용자 의견에 밀림
    assert "후기 5개" in it["proof"]             # 후기는 근거로 남음


def test_fallback_short_note_becomes_headline():
    """짧은 코멘트 → 큰 헤드라인으로 (사용자 목소리를 크게)."""
    p = prod()
    p["note"] = "데일리로 최고"
    c = copywriter.fallback_copy([p], "여름 무드", month=7)
    it = c["items"][0]
    assert "데일리로" in it["title"] and "<em>" in it["title"]
    assert "에디터 픽" not in it["sp"]           # 짧은 코멘트는 헤드라인, sp 는 근거 후기


def test_fallback_no_note_keeps_auto_copy():
    p = prod()
    p["note"] = ""  # 빈 코멘트는 자동 문구 유지
    c = copywriter.fallback_copy([p], "여름 무드", month=7)
    assert "에디터 픽" not in c["items"][0]["sp"]


def test_headline_from_note_short_and_long():
    assert "<em>" in copywriter._headline_from_note("가성비 최고")
    long = copywriter._headline_from_note("장마철 출근할 때 딱 좋고 색이 실물이 더 예뻐요")
    assert "<br>" in long and "<em>" in long and "\n" not in long
