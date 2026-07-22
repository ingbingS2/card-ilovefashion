"""문구·캡션 생성: Claude(claude-sonnet-5) 우선 시도, 실패/키없음 시 규칙 기반 폴백."""
from __future__ import annotations

import json
import re

SYSTEM_PROMPT = """당신은 패션 카드뉴스(인스타그램) 전문 카피라이터입니다.

# 가장 중요 — 에디터(사용자) 의견 우선
- 각 상품에 `note`(에디터가 직접 쓴 한 줄 의견)가 있으면, 그 상품 카드의 헤드라인과 sp 는
  **그 의견을 핵심으로** 만듭니다. 의견의 뜻을 바꾸거나 지어내지 말고 자연스럽게 다듬어 씁니다.
  후기·가격·평점은 그 의견을 뒷받침하는 근거로만 작게 배치합니다.
- `note` 가 없는 상품만 계절·상황·무드 기반의 자동 문구를 씁니다.

# 카드뉴스 본문 톤 (C안 · 후킹형)
- "랭킹 N위", "오늘의 픽", "베스트" 같은 순위·랭킹 키워드를 헤드라인에 쓰지 않습니다.
  대신 **계절감·상황·무드**(예: 장마, 환절기, 데일리, 출근룩, 무더위)를 살린 문구를 씁니다.
  순위 정보가 필요하면 proof 같은 작은 자리에만 담고, 큰 제목은 분위기로 채웁니다.
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
    # 종결부호(. ! ?) 뒤에서 분리한다. 한국어 후기는 "좋아요!!!다음문장" 처럼 부호 뒤에
    # 공백이 없는 경우가 많으므로 부호 run 의 끝에서 분리한다.
    # '~' 는 문장 끝이 아니라 강조(너~무, 좋아용~)로 쓰여 종결부호에서 제외한다.
    parts = re.split(r"(?<=[.!?])(?![.!?])\s*", text)
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


# 긍정 신호 단어 — 셀링포인트로 쓸 후기에는 이 중 하나가 있어야 한다.
_POSITIVE_WORDS = (
    "예쁘", "이쁘", "좋아", "좋고", "좋습니다", "좋네", "만족", "편하", "편해", "가볍",
    "부드럽", "마음에", "추천", "잘 맞", "핏이", "고급", "예뻐", "이뻐", "재구매",
    "잘 어울", "매일", "튼튼", "퀄리티",
)
# 개인정보/신체치수가 드러나는 후기는 홍보 문구로 부적합 (예: "163cm 52kg", "임신 30주차")
_PERSONAL_RE = re.compile(r"\d\s*(kg|cm|키로|주차|호|사이즈)", re.IGNORECASE)


def _pick_positive_review(reviews: list[dict]) -> str | None:
    """긍정·대표 후기 하나를 골라 첫 문장으로 다듬어 반환. 없으면 None.

    규칙: 별점 4+ · 불만 키워드 없음 · 긍정 단어 하나 이상 · 개인 신체치수 없음 · 8자+.
    깔끔하게 읽히는 것을 우선(긍정 단어 많고, 지나치게 길지 않은 것). 통과가 없으면
    None → 상품 특징 문구로 폴백(장황하거나 부정 꼬리가 붙은 후기를 억지로 쓰지 않는다).
    """
    scored = []
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
        if _PERSONAL_RE.search(text):
            continue
        pos_hits = sum(1 for w in _POSITIVE_WORDS if w in text)
        if pos_hits == 0:
            continue
        first = _split_sentences(text)[0] if _split_sentences(text) else text
        # 첫 문장에도 부정/개인정보가 있으면 제외
        if any(m in first.lower() for m in _NEGATIVE_MARKERS) or _PERSONAL_RE.search(first):
            continue
        # 짧고 긍정 신호 많은 문장 우선 (장황함 회피)
        scored.append((pos_hits, -len(first), r.get("likes") or 0, first))
    if not scored:
        return None
    scored.sort(reverse=True)
    return _clip_sentence(scored[0][3])


# 계절·상황·무드 문구 테이블 (랭킹 키워드 대신 계절감/상황/무드를 살린다).
_SEASON_BY_MONTH = {
    12: "겨울", 1: "겨울", 2: "겨울",
    3: "봄", 4: "봄", 5: "봄",
    6: "여름", 7: "여름", 8: "여름",
    9: "가을", 10: "가을", 11: "가을",
}
_MOOD = {
    "봄": {"kicker": "SPRING MOOD", "cover_title": "살랑이는 계절엔<br><em>가볍게</em>",
           "cover_sub": "환절기 데일리로 손이 가는 것들",
           "cta_title": "봄, 뭐부터<br><em>꺼낼까</em>", "cta_sub": "마음에 담은 건 댓글로 남겨 주세요",
           "cap_lead": "완연한 봄, 가볍게 걸치기 좋은 것들로 골랐습니다."},
    "여름": {"kicker": "SUMMER MOOD", "cover_title": "무더위에도<br><em>산뜻하게</em>",
             "cover_sub": "장마와 한여름을 나는 아이템",
             "cta_title": "이번 여름은<br><em>어떻게</em>", "cta_sub": "요즘 찾는 아이템이 있다면 댓글로",
             "cap_lead": "장마와 무더위를 산뜻하게 나는 것들로 골랐습니다."},
    "가을": {"kicker": "AUTUMN MOOD", "cover_title": "선선한 바람엔<br><em>레이어드</em>",
             "cover_sub": "환절기에 걸치기 좋은 것들",
             "cta_title": "가을, 뭐부터<br><em>걸칠까</em>", "cta_sub": "눈길 간 건 댓글로 알려 주세요",
             "cap_lead": "선선해진 요즘, 하나씩 걸치기 좋은 것들로 골랐습니다."},
    "겨울": {"kicker": "WINTER MOOD", "cover_title": "추운 날일수록<br><em>포근하게</em>",
             "cover_sub": "한파에도 든든한 아이템",
             "cta_title": "이번 겨울은<br><em>뭘로</em>", "cta_sub": "찜한 아이템은 댓글로 남겨 주세요",
             "cap_lead": "추위가 깊어진 요즘, 든든하게 챙기기 좋은 것들로 골랐습니다."},
}
# 카테고리별 상황형 헤드라인 변주 (랭킹 대신 '언제/어떻게 쓰는지'를 살린다).
# 계절 특정 표현(쌀쌀할 때 등)은 넣지 않는다 — 현재 계절과 모순될 수 있으므로.
# 같은 카테고리가 여러 장이면 index 로 변주를 돌려 문구가 겹치지 않게 한다.
_CATEGORY_HOOK = {
    "가방": ["손이 자주 가는<br><em>데일리 백</em>", "어디에나<br><em>잘 어울리는</em>",
            "가볍게 드는<br><em>한 손 백</em>"],
    "신발": ["매일 신게 되는<br><em>한 켤레</em>", "어떤 룩에도<br><em>무난한</em>",
            "발 편한<br><em>데일리 슈즈</em>"],
    "슈즈": ["매일 신게 되는<br><em>한 켤레</em>", "어떤 룩에도<br><em>무난한</em>",
            "발 편한<br><em>데일리 슈즈</em>"],
    "상의": ["하나만 걸쳐도<br><em>완성되는</em>", "데일리로<br><em>손이 가는</em>",
            "무심하게<br><em>툭 걸치는</em>"],
    "니트": ["포인트 주기<br><em>좋은</em>", "레이어드로<br><em>제격인</em>"],
    "아우터": ["걸치면<br><em>완성되는</em>", "무드 살리는<br><em>겉옷</em>"],
    "바지": ["매일 입기 좋은<br><em>한 벌</em>", "핏이 사는<br><em>데일리 팬츠</em>"],
    "하의": ["매일 입기 좋은<br><em>한 벌</em>", "핏이 사는<br><em>데일리 팬츠</em>"],
    "스커트": ["그냥 입어도<br><em>분위기</em>", "실루엣이 사는<br><em>한 벌</em>"],
    "원피스": ["하나로 끝내는<br><em>한 벌</em>", "입기만 해도<br><em>완성</em>"],
}


def _season(month: int) -> str:
    return _SEASON_BY_MONTH.get(month, "여름")


def _headline_from_note(note: str) -> str:
    """사용자 코멘트에서 큰 헤드라인을 만든다. 코멘트 자체를 존중하되 카드에 맞게 다듬는다.

    - 짧으면(≤16자) 그대로 헤드라인으로.
    - 길면 앞부분을 단어 경계에서 자르고 <br> 로 두 줄 배치, 마지막 어절에 <em> 강조.
    코멘트를 지어내거나 바꾸지 않는다 (사용자의 말 그대로).
    """
    text = " ".join(note.split())
    words = text.split(" ")
    if len(text) <= 16 or len(words) <= 2:
        # 두 어절이면 뒤 어절 강조, 한 어절이면 통째 강조
        if len(words) >= 2:
            return f"{' '.join(words[:-1])}<br><em>{words[-1]}</em>"
        return f"<em>{text}</em>"
    # 앞에서부터 ~10자 근처의 어절 경계에서 1행/2행을 나눈다
    line1, i = "", 0
    while i < len(words) and len(line1) + len(words[i]) <= 12:
        line1 += (" " if line1 else "") + words[i]
        i += 1
    if not line1:  # 첫 단어가 너무 길면 강제로 한 어절
        line1, i = words[0], 1
    rest = words[i:] or [""]
    line2 = " ".join(rest[:-1] + [f"<em>{rest[-1]}</em>"]) if rest[-1] else f"<em>{line1}</em>"
    return f"{line1}<br>{line2}"


def _category_hook(category_name: str | None, brand: str, idx: int = 0) -> str:
    for key, variants in _CATEGORY_HOOK.items():
        if category_name and key in category_name:
            return variants[idx % len(variants)]
    # 카테고리를 못 맞추면 브랜드를 살린 담백한 헤드라인
    return f"요즘 담는<br><em>{brand or '이 아이템'}</em>"


def fallback_copy(products: list[dict], topic: str, month: int | None = None) -> dict:
    n = len(products)
    if month is None:
        from datetime import datetime
        month = datetime.now().month
    mood = _MOOD[_season(month)]

    items = []
    hook_seen: dict[str, int] = {}  # 카테고리별 변주 인덱스
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
        note = (p.get("note") or "").strip()  # 사용자(에디터)가 상품별로 적은 한 줄 의견

        prod = f"{brand} · <b>{name}</b>"

        meta = f"{mall_name} {price:,}원"
        if original_price:
            meta += f" <s>{original_price:,}원</s>"

        if review_count:
            proof = f"후기 {review_count}개 · ⭐{review_score}"
        else:
            proof = "신상 픽"

        cat_word = category_name or "요즘"

        def _auto_sp() -> str:
            # 코멘트가 없거나 헤드라인으로 쓸 때, sp 는 긍정 후기(근거) 또는 특징 문구.
            positive = _pick_positive_review(reviews)
            if positive:
                return f"\"{positive}\" — 실제 후기"
            if review_count:
                return f"후기 {review_count}개가 쌓인 {cat_word} 아이템"
            return f"요즘 눈에 띄는 {cat_word} 한 벌"

        if note and len(note) <= 14:
            # 짧고 강한 코멘트 → 큰 헤드라인으로 (사용자 목소리를 크게). sp 는 근거 후기.
            title = _headline_from_note(note)
            sp = _auto_sp()
        elif note:
            # 긴 코멘트 → 헤드라인은 짧은 훅, 코멘트 전문은 '에디터 픽' 라인으로.
            _idx = hook_seen.get(cat_word, 0)
            hook_seen[cat_word] = _idx + 1
            title = _category_hook(category_name, brand, _idx)
            sp = f"“{note}” — 에디터 픽"
        else:
            # 코멘트 없음 → 계절·상황형 자동 헤드라인 + 긍정 후기(폴백).
            _idx = hook_seen.get(cat_word, 0)
            hook_seen[cat_word] = _idx + 1
            title = _category_hook(category_name, brand, _idx)
            sp = _auto_sp()

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
        "kicker": mood["kicker"],
        "title": mood["cover_title"],
        "sub": mood["cover_sub"],
    }
    cta = {
        "title": mood["cta_title"],
        "sub": mood["cta_sub"],
    }
    caption = (
        f"{mood['cover_sub']}\n\n"
        f"{mood['cap_lead']}\n"
        "후기와 평점을 함께 살펴봤습니다.\n\n"
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
