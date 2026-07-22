"""몰 API HTTP 계층. 엔드포인트·파라미터는 FINDINGS.md 실측값 그대로.

모든 호출은 요청 매너 딜레이(DELAY_SEC) + 지수 백오프 재시도(3회)를 거친다.
"""
from __future__ import annotations

import time

import requests

DELAY_SEC = 1.0
RETRIES = 3
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
BASE_HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                "Accept-Language": "ko-KR,ko;q=0.9"}

MUSINSA_RANKING_URL = "https://client.musinsa.com/api/home/web/v5/pans/ranking/sections/200"
MUSINSA_REVIEW_URL = "https://goods.musinsa.com/api2/review/v1/view/list"
CM29_BEST_URL = "https://display-bff-api.29cm.co.kr/api/v1/plp/best/items"
CM29_REVIEW_URL = "https://review-api.29cm.co.kr/api/v4/reviews"


class FetchError(RuntimeError):
    pass


def _request(method: str, url: str, *, params=None, json_body=None, headers=None) -> dict:
    time.sleep(DELAY_SEC)
    h = dict(BASE_HEADERS)
    if headers:
        h.update(headers)
    last = None
    for attempt in range(RETRIES):
        try:
            r = requests.request(method, url, params=params, json=json_body,
                                 headers=h, timeout=30)
            if r.ok:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if r.status_code in (403, 429):
                break  # 차단 시그널 — 재시도(우회) 금지
        except requests.exceptions.RequestException as e:
            last = repr(e)
        if attempt < RETRIES - 1:
            time.sleep(2 ** attempt)
    raise FetchError(f"{method} {url} 실패: {last}")


def fetch_musinsa_ranking(category_code: str, page: int = 1) -> dict:
    offset = (page - 1) * 101
    return _request("GET", MUSINSA_RANKING_URL, params={
        "storeCode": "musinsa", "gf": "A", "ageBand": "AGE_BAND_ALL",
        "period": "REALTIME", "eventPeriod": "BASIC_REALTIME",
        "categoryCode": category_code, "contentsId": "", "variantValue": "",
        "page": page, "startRank": offset + 1, "offset": offset,
    })


def fetch_musinsa_reviews(goods_no: str, size: int = 10) -> dict:
    return _request("GET", MUSINSA_REVIEW_URL, params={
        "page": 0, "pageSize": size, "goodsNo": goods_no,
        "sort": "up_cnt_desc", "myFilter": "false",
        "hasPhoto": "false", "isExperience": "false",
    })


def fetch_cm29_best(page: int = 1, size: int = 100,
                    category_large_id: str | int | None = None,
                    category_middle_id: str | int | None = None) -> dict:
    facets: dict = {"periodFacetInput": {"type": "HOURLY", "order": "DESC"},
                    "rankingFacetInput": {"type": "POPULARITY"}}
    if category_large_id:
        # 실측 (2026-07-21): 대분류 largeId, 중분류는 middleId 를 함께 전달
        cat: dict = {"largeId": int(category_large_id)}
        if category_middle_id:
            cat["middleId"] = int(category_middle_id)
        facets["categoryFacetInputs"] = [cat]
    return _request("POST", CM29_BEST_URL, json_body={
        "pageRequest": {"page": page, "size": size},
        "userSegment": {"gender": "F", "age": "THIRTIES"},
        "facets": facets,
    }, headers={"Content-Type": "application/json"})


def fetch_cm29_reviews(item_id: str, size: int = 10) -> dict:
    return _request("GET", CM29_REVIEW_URL, params={
        "itemId": item_id, "page": 0, "size": size, "sort": "BEST",
    })
