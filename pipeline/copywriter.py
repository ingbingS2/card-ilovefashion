"""문구·캡션 생성: Claude(claude-sonnet-5) 우선 시도, 실패/키없음 시 규칙 기반 폴백."""
from __future__ import annotations

import json
import re

SYSTEM_PROMPT = """당신은 패션 카드뉴스(인스타그램) 전문 카피라이터입니다.

# 카드뉴스 본문 톤 (C안 · 후킹형)
- 큰 타이포 제목은 강렬하게 후킹하되, 핵심 키워드 1곳에만 <em>강조</em>를 사용합니다.
- 줄바꿈이 필요하면 <br> 태그를 사용합니다 (실제 개행 문자 사용 금지).
- 반드시 전달받은 상품 데이터의 사실(가격, 순위, 브랜드, 후기 등)만 사용하고 과장·허위 표현을 금지합니다.
- sp(셀링포인트)에 후기를 인용할 때는 **긍정적이고 대표적인 후기만** 사용합니다. cs·배송·불량·환불·품질 불만 등 부정적인 후기를 홍보 문구로 절대 쓰지 않으며, 문장 중간에서 자르지 말고 완결된 문장으로 인용합니다. 적합한 긍정 후기가 없으면 상품 특징으로 sp 를 작성합니다.

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


# 셀링포인트로 쓰면 안 되는 '명백한 불만' 신호만 담는다. 하나라도 있으면 후보에서 제외.
# 주의: "배송", "cs", "품질" 같은 주제어는 넣지 않는다 — "배송 빨라요", "cs 친절해요",
# "품질 좋아요" 처럼 긍정 언급에도 등장하기 때문. 불만 감정/하자 표현만 정밀하게 잡는다.
_NEGATIVE_MARKERS = (
    "불편", "실망", "별로", "아쉬", "최악", "안좋", "안 좋", "하자", "불량",
    "환불", "반품", "후회", "비추", "그닥", "돈아깝", "돈 아깝",
    "찢어", "터졌", "터짐", "보풀", "이염", "냄새", "얼룩",
    "지연", "느려터", "너무 느", "너무 늦", "늦게 와", "늦었", "늦어", "안 와요", "안와요",
    "안 돼요", "안돼요", "안 되고", "실밥", "마감이 별로", "생각보다 별로",
)


def _split_sentences(text: str) -> list[str]:
    """후기 텍스트를 문장 단위로 나눈다 (종결부호 뒤에서 분리)."""
    text = " ".join((text or "").split())
    # 종결부호(. ! ? ~) 뒤에 공백/끝이 오면 문장 경계로 본다.
    parts = re.split(r"(?<=[.!?~])\s+", text)
    return [s.strip() for s in parts if s.strip()]


def _clip_sentence(text: str, limit: int = 70) -> str:
    """후기에서 '첫 완결 문장'을 우선 사용한다.

    앞쪽 긍정 문장 뒤에 애매/부정 문장이 딸려오지 않도록, 문장을 앞에서부터
    limit 을 넘지 않는 선까지만 이어 붙인다. 첫 문장이 limit 을 넘으면 그 문장을
    부드러운 지점(공백)에서 자른다.
    """
    text = " ".join((text or "").split())
    sentences = _split_sentences(text)
    if not sentences:
        return text[:limit].strip()
    out = ""
    for s in sentences:
        candidate = (out + " " + s).strip() if out else s
        # 이미 한 문장 이상 확보했고 그게 충분히 길면(18자+) 더 붙이지 않는다.
        # (앞의 긍정 문장 뒤에 애매/부정 문장이 딸려오는 것을 막는다)
        if out and len(out) >= 18:
            break
        if len(candidate) > limit:
            break
        out = candidate
    if out:
        return out
    # 첫 문장이 이미 limit 초과 → 공백 경계에서 자른다 (단어 중간 방지)
    first = sentences[0]
    cut = first[:limit]
    sp = cut.rfind(" ")
    return (cut[:sp] if sp >= 20 else cut).strip()


def _pick_positive_review(reviews: list[dict]) -> str | None:
    """긍정·대표 후기 하나를 골라 문장 단위로 다듬어 반환. 없으면 None.

    규칙: (1) 별점 4점 이상, (2) 불만 키워드 없음, (3) 너무 짧지 않음(8자+).
    도움돼요(likes) 많은 순 → 별점 높은 순으로 우선. 조건 통과가 없으면 None
    (부정 후기를 홍보 문구로 쓰느니 상품 특징 문구로 폴백하는 게 낫다).
    """
    candidates = []
    for r in reviews:
        text = " ".join((r.get("text") or "").split())
        if len(text) < 8:
            continue
        score = r.get("score")
        if score is not None and score < 4:
            continue
        low = text.lower()
        if any(m in low for m in _NEGATIVE_MARKERS):
            continue
        candidates.append(r)
    if not candidates:
        return None
    candidates.sort(key=lambda r: (r.get("likes") or 0, r.get("score") or 0), reverse=True)
    return _clip_sentence(candidates[0].get("text") or "")


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

        # 부정 후기를 홍보 문구로 쓰지 않는다 — 긍정·대표 후기만, 문장 단위로.
        # 적합한 후기가 없으면 후기 인용을 포기하고 상품 특징 문구로 폴백한다.
        positive = _pick_positive_review(reviews)
        if positive:
            sp = f"\"{positive}\" — 실제 후기"
        elif review_count:
            sp = f"후기 {review_count}개가 쌓인 {category_name or '랭킹'} 상위 아이템"
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
