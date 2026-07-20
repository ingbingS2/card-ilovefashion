"""응답 JSON → 정규화 dict. 순수 함수만 (네트워크·파일 IO 없음).

필드 경로는 crawler/FINDINGS.md 실측값 기준.
"""
from __future__ import annotations


def _to_int(v):
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _to_score5(v):
    """무신사 analytics 평점(100점 문자열) → 5점 float."""
    n = _to_int(v)
    return round(n / 20, 2) if n is not None else None


def parse_musinsa_ranking(data: dict) -> list[dict]:
    out = []
    for module in (data.get("data") or {}).get("modules") or []:
        if module.get("type") != "MULTICOLUMN":
            continue
        for item in module.get("items") or []:
            info = item.get("info") or {}
            image = item.get("image") or {}
            payload = (
                ((image.get("onClickLike") or {}).get("eventLog") or {})
                .get("amplitude", {}) or {}
            ).get("payload") or {}
            pid = str(item.get("id") or "")
            if not pid:
                continue
            out.append({
                "mall": "musinsa",
                "product_id": pid,
                "rank": _to_int(image.get("rank")) or (len(out) + 1),
                "brand": info.get("brandName") or "",
                "name": info.get("productName") or "",
                "price": _to_int(info.get("finalPrice")),
                "original_price": None,  # FINDINGS: 정가 정의 불명확 → 채택 안 함
                "discount_rate": _to_int(info.get("discountRatio")),
                "review_score": _to_score5(payload.get("reviewScore")),
                "review_count": _to_int(payload.get("reviewCount")),
                "thumbnail": image.get("url"),
                "product_url": f"https://www.musinsa.com/products/{pid}",
                "category_code": payload.get("category_id"),
                "category_name": None,
            })
    return out


def parse_cm29_best(data: dict) -> list[dict]:
    out = []
    for i, item in enumerate((data.get("data") or {}).get("list") or []):
        info = item.get("itemInfo") or {}
        props = (item.get("itemEvent") or {}).get("eventProperties") or {}
        pid = str(item.get("itemId") or "")
        if not pid:
            continue
        score = info.get("reviewScore")
        out.append({
            "mall": "cm29",
            "product_id": pid,
            "rank": i + 1,
            "brand": info.get("brandName") or props.get("brandName") or "",
            "name": info.get("productName") or "",
            "price": _to_int(info.get("sellPrice")),
            "original_price": _to_int(info.get("originalPrice")),
            "discount_rate": _to_int(info.get("saleRate")),
            "review_score": round(float(score), 2) if score is not None else None,
            "review_count": _to_int(info.get("reviewCount")),
            "thumbnail": info.get("thumbnailUrl"),
            "product_url": (item.get("itemUrl") or {}).get("webLink")
                           or f"https://product.29cm.co.kr/catalog/{pid}",
            "category_code": str(props.get("middleCategoryNo")) if props.get("middleCategoryNo") else None,
            "category_name": props.get("middleCategoryName"),
        })
    return out


def parse_musinsa_reviews(data: dict) -> list[dict]:
    out = []
    for item in (data.get("data") or {}).get("list") or []:
        text = (item.get("content") or "").strip()
        if not text:
            continue
        out.append({
            "score": _to_int(item.get("grade")),
            "text": text,
            "date": item.get("createDate"),
            "likes": _to_int(item.get("likeCount")),
        })
    return out


def parse_cm29_reviews(data: dict) -> list[dict]:
    out = []
    for item in (data.get("data") or {}).get("results") or []:
        text = (item.get("contents") or "").strip()
        if not text:
            continue
        out.append({
            "score": _to_int(item.get("point")),
            "text": text,
            "date": str(item.get("insertTimestamp")) if item.get("insertTimestamp") is not None else None,
            "likes": _to_int(item.get("helpfulCount")),
        })
    return out
