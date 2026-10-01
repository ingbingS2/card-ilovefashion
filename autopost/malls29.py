"""29CM API 조회 (crawler/FINDINGS.md + 2026-10-01 실측).

카드 가격은 상세(bff-api) `sellPrice`(쿠폰 미적용가)·`consumerPrice`(정가) — 검색의 `totalSellPrice`·랭킹 `displayPrice`는
쿠폰 반영가라 몰 비교·카드에 쓰지 않는다(KEYWORD-POLICY §2). bff-api는 Origin/Referer 없이 부르면 403.
연속 호출 차단(FINDINGS 09-13) — 동시 1건, 간격 0.4초, 회차당 상세 40건 안팎.
"""
from __future__ import annotations

import re
import time
from datetime import date

import requests

from . import malls

SEARCH_URL = "https://search-api.29cm.co.kr/api/v4/products/search"
DETAIL_URL = "https://bff-api.29cm.co.kr/api/v5/product-detail/{no}"
REVIEW_URL = "https://review-api.29cm.co.kr/api/v4/reviews"
IMG_HOST = "https://img.29cm.co.kr"
HEADERS = {**malls.HEADERS, "Origin": "https://product.29cm.co.kr", "Referer": "https://product.29cm.co.kr/"}
MALL = "29CM"
DETAIL_DELAY_SEC = 1.5   # 10-01 실측: 0.4초 간격이면 6건 중 5건 403, 세션+2초면 10건 중 8건 200
RETRY_WAIT_SEC = 8

_session: requests.Session | None = None


def _bff_get(url: str) -> dict:
    """bff-api 전용 — 세션 쿠키를 한 번 받아 두고, 403이면 잠시 쉬고 한 번만 다시 묻는다(우회가 아니라 속도 조절)."""
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update(HEADERS)
        try:
            _session.get("https://product.29cm.co.kr/", timeout=20)
        except requests.exceptions.RequestException:
            pass
    last = ""
    for attempt in range(2):
        time.sleep(DETAIL_DELAY_SEC if attempt == 0 else RETRY_WAIT_SEC)
        try:
            r = _session.get(url, timeout=30)
            if r.ok:
                return r.json()
            last = f"HTTP {r.status_code}"
            if r.status_code not in (403, 429):
                break
        except requests.exceptions.RequestException as e:
            last = repr(e)
    raise malls.MallError(f"GET {url} 실패: {last}")


def search(keyword: str, size: int = 50) -> list[dict]:
    """검색 결과 → data.products[] (itemNo·itemName·frontBrandNameKor/Eng·isSoldOut·reviewCount·frontCategoryInfo)."""
    data = malls._get(SEARCH_URL, {"keyword": keyword, "page": 1, "size": size}, headers=HEADERS)
    return (data.get("data") or {}).get("products") or []


def detail(item_no) -> dict:
    data = _bff_get(DETAIL_URL.format(no=item_no)).get("data")
    if not data:
        raise malls.MallError(f"29CM 상세 없음: {item_no}")
    return data


def reviews(item_no, pages: int = 3, size: int = 20) -> tuple[list[dict], int]:
    out: list[dict] = []
    total = 0
    for page in range(pages):
        data = malls._get(REVIEW_URL, {"itemId": item_no, "page": page, "size": size, "sort": "BEST"},
                          headers=HEADERS).get("data") or {}
        batch = data.get("results") or []
        total = data.get("count") or total
        out.extend(batch)
        if len(batch) < size:
            break
    return out, int(total or 0)


def find_review(item_no, review_no, pages: int = 15) -> dict | None:
    for page in range(pages):
        data = malls._get(REVIEW_URL, {"itemId": item_no, "page": page, "size": 20, "sort": "BEST"},
                          headers=HEADERS).get("data") or {}
        batch = data.get("results") or []
        for r in batch:
            if str(r.get("itemReviewNo")) == str(review_no):
                return r
        if len(batch) < 20:
            break
    return None


# ---------- 상세 응답 해석 (순수 함수) ----------

def image_url(path: str) -> str:
    if not path:
        return ""
    if path.startswith("//"):
        return "https:" + path
    return path if path.startswith("http") else IMG_HOST + path


def images(d: dict) -> list[str]:
    out = []
    for img in d.get("itemImages") or []:
        url = image_url(img.get("imageUrl", ""))
        if url and url not in out:
            out.append(url)
    return out


def release_date(d: dict) -> date | None:
    """판매 개시일 = availableBeginTimestamp. visibleBeginTimestamp는 재진열일이라 쓰지 않는다(§2)."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(d.get("availableBeginTimestamp") or ""))
    return date(int(m[1]), int(m[2]), int(m[3])) if m else None


def price_facts(d: dict) -> dict:
    sale = int(d.get("sellPrice") or 0)
    normal = int(d.get("consumerPrice") or 0) or sale
    rate = d.get("discountRate")
    if rate is None:
        rate = round((1 - sale / normal) * 100) if normal and sale and sale < normal else 0
    return {"sale_price": sale, "normal_price": normal, "discount": int(rate or 0)}


def review_summary(d: dict) -> dict:
    agg = d.get("reviewAggregation") or {}
    avg = agg.get("averagePoint")
    return {"review_count": int(agg.get("totalCount") or 0), "rating": round(float(avg), 1) if avg else None}


def sold_out(d: dict) -> bool:
    status = str(d.get("frontItemStockStatus") or d.get("itemStockStatus") or "")
    return bool(d.get("isSoldout")) or "SOLD" in status.upper()


def spec_text(d: dict) -> str:
    """상세 설명·실측표·모델 사이즈의 문자열을 모은다 — spec_line 숫자 대조용."""
    parts: list[str] = []

    def walk(x):
        if isinstance(x, str):
            parts.append(x)
        elif isinstance(x, (int, float)) and not isinstance(x, bool):
            parts.append(str(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    for k in ("itemDescriptions", "itemDetailsList", "itemModelSizes", "itemSizeCharts", "itemSubjects"):
        walk(d.get(k))
    return malls.strip_html(" ".join(p for p in parts if not p.startswith(("/", "http"))))
