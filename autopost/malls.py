"""무신사 API 조회 (엔드포인트·필드는 crawler/FINDINGS.md 실측값, 2026-10-01 재확인).

카드에 쓰는 가격은 상세 `goodsPrice.salePrice`(쿠폰 미적용 표시가)·`normalPrice`·`discountRate`.
랭킹·검색의 price/finalPrice는 쿠폰가일 수 있어 후보 정렬에만 쓴다.

Cloudflare 403(데이터센터 IP 차단)을 받으면 그 호스트는 이번 실행 동안 차단으로 기억하고 바로 실패한다 —
브라우저 흉내·우회는 하지 않는다. User-Agent도 브라우저로 위장하지 않고 이 도구임을 밝힌다.
"""
from __future__ import annotations

import re
import time
from datetime import date

import requests

UA = "i_s2_fashion-autopost/1.0 (card-news bot; python-requests)"
HEADERS = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
           "Accept-Language": "ko-KR,ko;q=0.9"}
IMG_HOST = "https://image.msscdn.net"
DELAY_SEC = 0.4

SEARCH_URL = "https://api.musinsa.com/api2/dp/v1/plp/goods"
DETAIL_URL = "https://goods-detail.musinsa.com/api2/goods/{no}"
REVIEW_URL = "https://goods.musinsa.com/api2/review/v1/view/list"
RANKING_URL = "https://client.musinsa.com/api/home/web/v5/pans/ranking/sections/200"

_DATE_IN_PATH = re.compile(r"/(?:goods_img|prd_img)/(\d{8})/")


class MallError(RuntimeError):
    pass


_blocked_hosts: set[str] = set()   # Cloudflare 403을 받은 호스트 — 이번 실행 동안 네트워크 없이 바로 실패


def _blocked_error(host: str) -> MallError:
    mall = "29CM" if "29cm" in host else ("무신사" if "musinsa" in host or "msscdn" in host else host)
    return MallError(f"{mall} 차단(데이터센터 IP 403) — 우회하지 않음: {host}")


def _cloudflare_block(r) -> bool:
    text = r.text or ""
    return r.status_code == 403 and ("Attention Required" in text or "Just a moment" in text
                                     or "cf-" in text[:3000])


def _get(url: str, params: dict | None = None, retries: int = 3, headers: dict | None = None) -> dict:
    host = url.split("/")[2]
    if host in _blocked_hosts:
        raise _blocked_error(host)
    last = ""
    for attempt in range(retries):
        time.sleep(DELAY_SEC)
        try:
            r = requests.get(url, params=params, headers=headers or HEADERS, timeout=30)
            if r.ok:
                return r.json()
            last = f"HTTP {r.status_code}: {r.text[:200]}"
            if _cloudflare_block(r):
                _blocked_hosts.add(host)   # 데이터센터 IP 차단(FINDINGS 10-01) — 다시 묻지도, 돌아가지도 않는다
                raise _blocked_error(host)
            if r.status_code in (403, 404, 429):
                break  # 차단·없음 — 재시도로 우회하지 않는다
        except requests.exceptions.RequestException as e:
            last = repr(e)
        time.sleep(2 ** attempt)
    raise MallError(f"GET {url} 실패: {last}")


def search(keyword: str, gf: str = "A", size: int = 60) -> list[dict]:
    """무신사 검색(인기순). 반환: data.list[] — goodsNo·brand·brandName·goodsName·isSoldOut·reviewCount·thumbnail."""
    data = _get(SEARCH_URL, {"gf": gf, "keyword": keyword, "sortCode": "POPULAR",
                             "page": 1, "size": size, "caller": "SEARCH"})
    return (data.get("data") or {}).get("list") or []


def detail(goods_no: int | str) -> dict:
    data = _get(DETAIL_URL.format(no=goods_no)).get("data")
    if not data:
        raise MallError(f"상세 없음: {goods_no}")
    return data


def reviews(goods_no: int | str, pages: int = 3, size: int = 20) -> tuple[list[dict], int]:
    """도움순 후기. pageSize 50은 빈 목록이라 20씩 페이징 (FINDINGS)."""
    out: list[dict] = []
    total = 0
    for page in range(pages):
        data = _get(REVIEW_URL, {"page": page, "pageSize": size, "goodsNo": goods_no,
                                 "sort": "up_cnt_desc", "selectedSimilarNo": goods_no,
                                 "myFilter": "false", "hasPhoto": "false",
                                 "isExperience": "false"}).get("data") or {}
        batch = data.get("list") or []
        total = data.get("total") or total
        out.extend(batch)
        if len(batch) < size:
            break
    return out, int(total or 0)


def ranking(category: str, gf: str = "F") -> list[dict]:
    """실시간 랭킹 상위 ~100. 반환: [{rank, goodsNo, brand, name, price}]."""
    data = _get(RANKING_URL, {"storeCode": "musinsa", "gf": gf, "ageBand": "AGE_BAND_ALL",
                              "period": "REALTIME", "eventPeriod": "BASIC_REALTIME",
                              "categoryCode": category, "contentsId": "", "variantValue": "",
                              "page": 1, "startRank": 1, "offset": 0}).get("data") or {}
    rows = []
    for module in data.get("modules") or []:
        if module.get("type") != "MULTICOLUMN":
            continue
        for item in module.get("items") or []:
            info = item.get("info") or {}
            if not item.get("id") or not info.get("productName"):
                continue  # 배너·광고 슬롯
            rows.append({"rank": (item.get("image") or {}).get("rank"), "goodsNo": item.get("id"),
                         "brand": info.get("brandName"), "name": info.get("productName"),
                         "price": info.get("finalPrice")})
    return rows


# ---------- 상세 응답 해석 (순수 함수 — 테스트 대상) ----------

def full_image_url(path: str, size: str = "big") -> str:
    """상대경로 썸네일(_500) → 원본(_big, 1500×1800) 절대 URL."""
    url = path if path.startswith("http") else IMG_HOST + path
    if url.startswith("//"):
        url = "https:" + url
    return re.sub(r"_(?:\d+|big)\.(jpe?g|png|webp)$", rf"_{size}.\1", url)


def release_date(d: dict) -> date | None:
    """판매 개시일 = 이미지 경로 날짜 폴더 중 가장 이른 값 (sellStartDate는 null — KEYWORD-POLICY §2)."""
    paths = [img.get("imageUrl", "") for img in d.get("goodsImages") or []]
    paths.append(d.get("thumbnailImageUrl") or "")
    dates = []
    for p in paths:
        m = _DATE_IN_PATH.search(p)
        if m:
            s = m.group(1)
            try:
                dates.append(date(int(s[:4]), int(s[4:6]), int(s[6:])))
            except ValueError:
                pass
    return min(dates) if dates else None


def season_label(d: dict) -> str:
    """seasonYear+season(1=SS, 2=FW) → '2026 F/W'. 값이 없으면 ''."""
    year = str(d.get("seasonYear") or "")
    season = {"1": "S/S", "2": "F/W"}.get(str(d.get("season") or ""), "")
    if year and year != "0000" and season:
        return f"{year} {season}"
    return ""


def material_facts(d: dict) -> list[str]:
    """상세의 체크형 소재 정보(핏·촉감·두께 등)에서 선택된 값만 '항목: 값'으로."""
    facts = []
    mat = d.get("goodsMaterial")
    if isinstance(mat, dict):
        for group in mat.get("materials") or []:
            picked = [i.get("name", "").replace("|", " ") for i in group.get("items") or []
                      if i.get("isSelected")]
            if picked:
                facts.append(f"{group.get('name')}: {', '.join(picked)}")
    return facts


def strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html or "", flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def price_facts(d: dict) -> dict:
    gp = d.get("goodsPrice") or {}
    return {"sale_price": int(gp.get("salePrice") or 0),
            "normal_price": int(gp.get("normalPrice") or 0),
            "discount": int(gp.get("discountRate") or 0)}


def review_summary(d: dict) -> dict:
    gr = d.get("goodsReview") or {}
    score = gr.get("satisfactionScore")
    return {"review_count": int(gr.get("totalCount") or 0),
            "rating": round(float(score), 1) if score else None}
