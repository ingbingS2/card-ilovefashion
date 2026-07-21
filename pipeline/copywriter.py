"""문구·캡션 생성: Claude(claude-sonnet-5) 우선 시도, 실패/키없음 시 규칙 기반 폴백."""
from __future__ import annotations

import json
import re

SYSTEM_PROMPT = """당신은 패션 카드뉴스(인스타그램) 전문 카피라이터입니다.

# 카드뉴스 본문 톤 (C안 · 후킹형)
- 큰 타이포 제목은 강렬하게 후킹하되, 핵심 키워드 1곳에만 <em>강조</em>를 사용합니다.
- 줄바꿈이 필요하면 <br> 태그를 사용합니다 (실제 개행 문자 사용 금지).
- 반드시 전달받은 상품 데이터의 사실(가격, 순위, 브랜드, 후기 등)만 사용하고 과장·허위 표현을 금지합니다.

# 캡션(인스타 게시글 본문) 톤 — 절제된 톤
- 첫 줄은 제목형으로 짧게 시작합니다.
- 이어서 담백한 2~3문장으로 설명합니다 (나열체, 오글거리는 구어체 금지).
- 독자의 경험을 소환하는 질문을 하나 포함합니다.
- 이모지는 0~1개만 사용합니다.
- 해시태그는 절대 사용하지 않습니다 (한 개도 포함 금지).
- 말줄임표(...·…)와 과도한 감탄사를 사용하지 않습니다.

# 출력 형식
아래 JSON 스키마를 정확히 지켜 응답합니다. JSON 이외의 텍스트(설명, 코드펜스 언급 등)는 출력하지 않습니다.

{
  "topic": "string",
  "cover": {"kicker": "string", "title": "string(<em>,<br> 허용)", "sub": "string"},
  "items": [
    {"prod": "string(<b> 허용)", "title": "string(<em>,<br> 허용)", "meta": "string(<s> 허용)",
     "proof": "string", "sp": "string", "badge": "string 또는 null"}
  ],
  "cta": {"title": "string(<em>,<br> 허용)", "sub": "string"},
  "caption": "string"
}

items 배열의 개수는 전달받은 상품 개수와 정확히 같아야 합니다.
"""


def _call_claude(products: list[dict], topic: str, key: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=key)
    user_content = (
        f"주제: {topic}\n\n상품 데이터(JSON):\n{json.dumps(products, ensure_ascii=False)}\n\n"
        "위 상품들로 카드뉴스 Copy JSON을 생성하세요."
    )
    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    )


_REQUIRED_KEYS = {"topic", "cover", "items", "cta", "caption"}


def _parse(text: str) -> dict:
    cleaned = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict) or not _REQUIRED_KEYS.issubset(data.keys()):
        raise ValueError("copy JSON 필수 키 누락")
    return data


def _truncate(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[:n]


def fallback_copy(products: list[dict], topic: str) -> dict:
    n = len(products)

    items = []
    for p in products:
        brand = p.get("brand") or ""
        name = _truncate(p.get("name") or "", 30)
        rank = p.get("rank")
        mall = p.get("mall")
        mall_name = "무신사" if mall == "musinsa" else "29CM" if mall == "cm29" else (mall or "")
        price = p.get("price") or 0
        original_price = p.get("original_price")
        review_count = p.get("review_count") or 0
        review_score = p.get("review_score")
        discount_rate = p.get("discount_rate") or 0
        reviews = p.get("reviews") or []
        category_name = p.get("category_name")

        prod = f"{brand} · <b>{name}</b>"
        title = f"랭킹 {rank}위<br><em>{brand}</em>"

        meta = f"{mall_name} {price:,}원"
        if original_price:
            meta += f" <s>{original_price:,}원</s>"

        if review_count:
            proof = f"후기 {review_count}개 · ⭐{review_score}"
        else:
            proof = "신상 픽"

        if reviews:
            first_text = _truncate(reviews[0].get("text") or "", 80)
            sp = f"\"{first_text}\" — 실제 후기"
        else:
            sp = f"{category_name or '지금'} 랭킹 {rank}위 아이템"

        badge = f"{discount_rate}%" if discount_rate > 0 else None
        cr = "이미지 출처 : 무신사" if mall == "musinsa" else "이미지 출처 : 29CM"

        items.append({
            "prod": prod,
            "title": title,
            "meta": meta,
            "proof": proof,
            "sp": sp,
            "badge": badge,
            "cr": cr,
        })

    cover = {
        "kicker": f"TODAY PICK {n}",
        "title": f"오늘의 픽,<br><em>{topic}</em>",
        "sub": f"무신사·29CM 랭킹에서 고른 {n}개",
    }
    cta = {
        "title": "오늘 픽,<br><em>저장</em>으로 끝",
        "sub": "📌 최애는 댓글로<br>다음 픽은 팔로우하면 먼저 봐요",
    }
    caption = (
        f"{topic} {n}\n\n"
        f"무신사와 29CM 랭킹에서 후기로 검증된 {n}개를 골랐습니다.\n"
        "가격과 순위는 오늘 기준입니다.\n\n"
        "요즘 눈여겨보는 아이템이 있다면 댓글로 알려주세요."
    )

    return {
        "topic": topic,
        "cover": cover,
        "items": items,
        "cta": cta,
        "caption": caption,
    }


def write_copy(products: list[dict], topic: str = "랭킹 픽", api_key: str | None = None) -> dict:
    if not api_key:
        return fallback_copy(products, topic)
    try:
        text = _call_claude(products, topic, api_key)
        data = _parse(text)
        if len(data["items"]) != len(products):
            raise ValueError("items 개수가 상품 개수와 다름")
        return data
    except Exception:
        return fallback_copy(products, topic)
