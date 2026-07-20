# Phase 1: 크롤러 + Firestore 적재 + 매시간 스케줄 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 무신사 카테고리별 TOP 50 + 29CM 베스트 TOP 50 의 순위·가격·평점·후기를 매시간 수집해 Firestore(또는 로컬 JSON)에 적재하는 크롤러와 GitHub Actions 스케줄을 만든다.

**Architecture:** 순수 파서(`parsers.py`) / HTTP 계층(`fetchers.py`) / 저장 계층(`store.py`: LocalJsonStore·FirestoreStore) / 오케스트레이션(`main.py`) 4개 모듈로 분리. 후기는 "후기 수가 변했거나 랭킹에 새로 진입한 상품만" 증분 수집. 매시간 워크플로는 Firebase 시크릿이 없으면 로컬 JSON 모드로 돌고 아티팩트만 업로드한다(시크릿 등록 즉시 Firestore 모드로 전환).

**Tech Stack:** Python 3.12 (crawler/.venv), requests, google-cloud-firestore, pytest. GitHub Actions cron.

## Global Constraints

- 모든 사용자 노출 텍스트·문서·로그 메시지는 한국어 (코드 식별자·주석은 영어 허용) — CLAUDE.md.
- 셸 명령은 Bash 툴로, 실행 전 `export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"` — CLAUDE.md. 파이썬은 `crawler/.venv/Scripts/python.exe`, 한글 출력 시 `PYTHONIOENCODING=utf-8`.
- **pytest 는 네트워크 호출 금지** — 파서는 커밋된 픽스처로, fetcher 는 requests 목으로, 저장소는 tmp_path·페이크 클라이언트로 검증. 실제 몰 접속은 Task 6(운영 실행)과 Task 7의 Actions 실행에서만.
- 요청 매너: 실 크롤링 시 요청 간 딜레이 1.0초 이상, 재시도는 지수 백오프 3회, 403/429 시 해당 몰 중단·기록(우회 금지) — 스펙.
- 비밀키 커밋 금지. Firebase 서비스 계정은 GitHub Secret `FIREBASE_SERVICE_ACCOUNT`(기존 deploy.yml 과 공유) → 워크플로에서 파일로 풀어 `GOOGLE_APPLICATION_CREDENTIALS` 로 주입.
- 엔드포인트·필드 경로는 전부 `crawler/FINDINGS.md` 실측값을 그대로 사용한다 (이 계획의 코드에 이미 반영됨 — 임의 변경 금지).
- 커밋 메시지 끝에 트레일러 2줄:
  `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01PgitEtAu5cwDBPf5BsKcLr`

## File Structure

```
crawler/
  config.py          # [신규] 수집 대상(무신사 카테고리 6종) + 상수 (TOP_N=50, 딜레이)
  parsers.py         # [신규] 순수 파서 4종: 응답 JSON → 정규화 dict 리스트
  fetchers.py        # [신규] requests 래퍼 4종 (딜레이·재시도 내장)
  store.py           # [신규] Store 추상 + LocalJsonStore + FirestoreStore
  main.py            # [신규] crawl_once() 오케스트레이션 + CLI
  requirements.txt   # [수정] google-cloud-firestore 추가
  tests/
    fixtures/        # [신규] 실측 응답을 2~3개 아이템으로 잘라낸 커밋용 픽스처
    test_parsers.py  # [신규]
    test_fetchers.py # [신규]
    test_store.py    # [신규]
    test_main.py     # [신규]
.github/workflows/crawl.yml   # [신규] 매시간 cron + workflow_dispatch
```

## 정규화 스키마 (전 태스크 공통 — 이 형태를 벗어나지 말 것)

상품(dict): `{"mall": "musinsa"|"cm29", "product_id": str, "rank": int, "brand": str, "name": str, "price": int|None, "original_price": int|None, "discount_rate": int|None, "review_score": float|None (5점 만점), "review_count": int|None, "thumbnail": str|None, "product_url": str, "category_code": str|None, "category_name": str|None}`

후기(dict): `{"score": int|None, "text": str, "date": str|None, "likes": int|None}`

---

### Task 1: 픽스처 생성 + 랭킹 파서 2종 (`parsers.py`)

**Files:**
- Create: `crawler/parsers.py`, `crawler/tests/fixtures/` (4개 JSON), `crawler/tests/test_parsers.py`

**Interfaces:**
- Produces:
  - `parse_musinsa_ranking(data: dict) -> list[dict]` — sections/200 응답 → 정규화 상품 리스트(순위순)
  - `parse_cm29_best(data: dict) -> list[dict]` — plp/best/items 응답 → 정규화 상품 리스트
  - 픽스처 파일: `fixtures/musinsa_ranking.json`, `fixtures/cm29_best.json`, `fixtures/musinsa_reviews.json`, `fixtures/cm29_reviews.json` (Task 2 도 사용)

- [ ] **Step 1: 로컬 실측 샘플에서 픽스처 4개 생성** (네트워크 없음 — Phase 0 때 저장된 `crawler/samples/` 원본을 잘라내기)

```bash
export PATH="/c/Users/yepdo/AppData/Local/Programs/Python/Python312:$PATH"
cd "C:/Users/yepdo/OneDrive/Desktop/fashion-cardnews/crawler" && mkdir -p tests/fixtures && PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe - << 'EOF'
import json, glob

def load(pat):
    fs = sorted(glob.glob(pat))
    assert fs, f"샘플 없음: {pat} — Phase 0 samples/ 가 로컬에 있어야 함"
    return json.load(open(fs[0], encoding="utf-8"))

# 1) 무신사 랭킹: MULTICOLUMN 모듈 1개 + items 3개만 남기기
d = load("samples/actions_musinsa/musinsa_ranking/*sections_200*.json") 
mods = [m for m in d["data"]["modules"] if m.get("type") == "MULTICOLUMN" and m.get("items")]
d["data"]["modules"] = [dict(mods[0], items=mods[0]["items"][:3])]
json.dump(d, open("tests/fixtures/musinsa_ranking.json", "w", encoding="utf-8"), ensure_ascii=False)

# 2) 29CM 베스트: list 3개만
d = load("samples/actions_cm29/cm29_best/*plp_best_items*.json")
d["data"]["list"] = d["data"]["list"][:3]
json.dump(d, open("tests/fixtures/cm29_best.json", "w", encoding="utf-8"), ensure_ascii=False)

# 3) 무신사 후기: list 2개만
d = load("samples/musinsa_product_review/*view_list*.json")
d["data"]["list"] = d["data"]["list"][:2]
json.dump(d, open("tests/fixtures/musinsa_reviews.json", "w", encoding="utf-8"), ensure_ascii=False)

# 4) 29CM 후기: results 2개만
d = load("samples/cm29_product_review/*reviews_itemId*.json")
d["data"]["results"] = d["data"]["results"][:2]
json.dump(d, open("tests/fixtures/cm29_reviews.json", "w", encoding="utf-8"), ensure_ascii=False)
print("fixtures ok")
EOF
```

Expected: `fixtures ok` + 4개 파일 생성. (만약 glob 이 비면 `samples/musinsa_ranking/`, `samples/cm29_best/` 등 로컬 1차 채집 폴더로 패턴을 바꿔 재시도 — 구조는 동일함이 FINDINGS 로 확인돼 있다.)

- [ ] **Step 2: 실패하는 테스트 작성**

`crawler/tests/test_parsers.py`:

```python
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
```

- [ ] **Step 3: 실패 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_parsers.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'parsers'`

- [ ] **Step 4: 구현**

`crawler/parsers.py`:

```python
"""응답 JSON → 정규화 dict. 순수 함수만 (네트워크·파일 IO 없음).

필드 경로는 crawler/FINDINGS.md 실측값 기준.
"""
from __future__ import annotations


def _to_int(v):
    try:
        return int(str(v).replace(",", ""))
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
        for i, item in enumerate(module.get("items") or []):
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
```

- [ ] **Step 5: 통과 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_parsers.py -q
```

Expected: `5 passed`

- [ ] **Step 6: 전체 스위트 확인 + 커밋**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/ -q
git add crawler/parsers.py crawler/tests/
git commit -m "feat(crawler): 랭킹 파서 2종 + 실측 픽스처"
```

Expected: 기존 12개 + 신규 5개 = `17 passed`

---

### Task 2: 후기 파서 2종 (`parsers.py` 확장)

**Files:**
- Modify: `crawler/parsers.py` (함수 2개 추가)
- Modify: `crawler/tests/test_parsers.py` (테스트 추가)

**Interfaces:**
- Consumes: Task 1 픽스처 `musinsa_reviews.json`, `cm29_reviews.json`
- Produces:
  - `parse_musinsa_reviews(data: dict) -> list[dict]` — review/v1/view/list 응답 → 후기 리스트
  - `parse_cm29_reviews(data: dict) -> list[dict]` — api/v4/reviews 응답 → 후기 리스트

- [ ] **Step 1: 실패하는 테스트 추가** (`test_parsers.py` 끝에)

```python
def test_parse_musinsa_reviews():
    from parsers import parse_musinsa_reviews
    reviews = parse_musinsa_reviews(fx("musinsa_reviews.json"))
    assert len(reviews) == 2
    r = reviews[0]
    assert set(r) == {"score", "text", "date", "likes"}
    assert r["text"]
    assert r["score"] is None or 1 <= r["score"] <= 5


def test_parse_musinsa_reviews_empty():
    from parsers import parse_musinsa_reviews
    assert parse_musinsa_reviews({"data": {"list": []}}) == []


def test_parse_cm29_reviews():
    from parsers import parse_cm29_reviews
    reviews = parse_cm29_reviews(fx("cm29_reviews.json"))
    assert len(reviews) == 2
    r = reviews[0]
    assert set(r) == {"score", "text", "date", "likes"}
    assert r["text"]


def test_parse_cm29_reviews_empty():
    from parsers import parse_cm29_reviews
    assert parse_cm29_reviews({"data": {"results": []}}) == []
```

- [ ] **Step 2: 실패 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_parsers.py -q
```

Expected: FAIL — `ImportError: cannot import name 'parse_musinsa_reviews'`

- [ ] **Step 3: 구현** (`parsers.py` 끝에 추가)

```python
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
```

- [ ] **Step 4: 통과 + 커밋**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/ -q
git add crawler/parsers.py crawler/tests/test_parsers.py
git commit -m "feat(crawler): 후기 파서 2종"
```

Expected: `21 passed`

---

### Task 3: HTTP 계층 (`fetchers.py`)

**Files:**
- Create: `crawler/fetchers.py`
- Test: `crawler/tests/test_fetchers.py`

**Interfaces:**
- Produces (Task 5 의 main 이 그대로 호출):
  - `fetch_musinsa_ranking(category_code: str, page: int = 1) -> dict`
  - `fetch_musinsa_reviews(goods_no: str, size: int = 10) -> dict`
  - `fetch_cm29_best(page: int = 1, size: int = 100) -> dict`
  - `fetch_cm29_reviews(item_id: str, size: int = 10) -> dict`
  - 모듈 상수 `DELAY_SEC = 1.0` — 모든 fetch 는 호출 시작 시 `time.sleep(DELAY_SEC)` (요청 매너, Global Constraints)
  - `FetchError(RuntimeError)` — 3회 재시도 후에도 실패 시 발생

- [ ] **Step 1: 실패하는 테스트 작성**

`crawler/tests/test_fetchers.py`:

```python
"""fetchers 테스트 — requests 목 처리, 실제 네트워크·sleep 없음."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fetchers


class FakeResp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self.ok = status < 400
        self._body = body if body is not None else {"ok": True}
        self.text = str(self._body)

    def json(self):
        return self._body


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(fetchers.time, "sleep", lambda s: None)


def test_musinsa_ranking_builds_params(monkeypatch):
    captured = {}

    def fake_request(method, url, **kw):
        captured.update(method=method, url=url, **kw)
        return FakeResp()

    monkeypatch.setattr(fetchers.requests, "request", fake_request)
    out = fetchers.fetch_musinsa_ranking("001")
    assert out == {"ok": True}
    assert captured["method"] == "GET"
    assert "sections/200" in captured["url"]
    p = captured["params"]
    assert p["categoryCode"] == "001" and p["storeCode"] == "musinsa" and p["page"] == 1


def test_cm29_best_posts_json_body(monkeypatch):
    captured = {}

    def fake_request(method, url, **kw):
        captured.update(method=method, url=url, **kw)
        return FakeResp()

    monkeypatch.setattr(fetchers.requests, "request", fake_request)
    fetchers.fetch_cm29_best(page=2, size=100)
    assert captured["method"] == "POST"
    body = captured["json"]
    assert body["pageRequest"] == {"page": 2, "size": 100}
    assert body["facets"]["rankingFacetInput"]["type"] == "POPULARITY"
    assert captured["headers"]["Content-Type"] == "application/json"


def test_retry_then_success(monkeypatch):
    calls = {"n": 0}

    def flaky(method, url, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise fetchers.requests.exceptions.ConnectionError("boom")
        return FakeResp()

    monkeypatch.setattr(fetchers.requests, "request", flaky)
    assert fetchers.fetch_cm29_reviews("123") == {"ok": True}
    assert calls["n"] == 3


def test_gives_up_after_retries(monkeypatch):
    def always_500(method, url, **kw):
        return FakeResp(status=500)

    monkeypatch.setattr(fetchers.requests, "request", always_500)
    with pytest.raises(fetchers.FetchError):
        fetchers.fetch_musinsa_reviews("5928448")
```

- [ ] **Step 2: 실패 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_fetchers.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'fetchers'`

- [ ] **Step 3: 구현**

`crawler/fetchers.py`:

```python
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


def fetch_cm29_best(page: int = 1, size: int = 100) -> dict:
    return _request("POST", CM29_BEST_URL, json_body={
        "pageRequest": {"page": page, "size": size},
        "userSegment": {"gender": "F", "age": "THIRTIES"},
        "facets": {"periodFacetInput": {"type": "HOURLY", "order": "DESC"},
                   "rankingFacetInput": {"type": "POPULARITY"}},
    }, headers={"Content-Type": "application/json"})


def fetch_cm29_reviews(item_id: str, size: int = 10) -> dict:
    return _request("GET", CM29_REVIEW_URL, params={
        "itemId": item_id, "page": 0, "size": size, "sort": "BEST",
    })
```

- [ ] **Step 4: 통과 + 커밋**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/ -q
git add crawler/fetchers.py crawler/tests/test_fetchers.py
git commit -m "feat(crawler): HTTP 계층 (딜레이·재시도 내장)"
```

Expected: `25 passed`

---

### Task 4: 설정 + 저장 계층 (`config.py`, `store.py`)

**Files:**
- Create: `crawler/config.py`, `crawler/store.py`
- Modify: `crawler/requirements.txt` (google-cloud-firestore 추가)
- Test: `crawler/tests/test_store.py`

**Interfaces:**
- Produces:
  - `config.MUSINSA_CATEGORIES: dict[str, str]` — 코드→한글명 6종 (FINDINGS 확인분만)
  - `config.TOP_N = 50`, `config.REVIEW_SIZE = 10`, `config.HISTORY_CAP = 168`
  - `class Store(ABC)`: `load_ranking(mall, category_code) -> dict|None` / `save_ranking(mall, category_code, snapshot: dict) -> None` / `save_product(product: dict, reviews: list[dict]|None, now_iso: str) -> None`
  - `LocalJsonStore(out_dir: str)` — `out_dir/rankings/{mall}_{cat}.json`, `out_dir/products/{mall}_{pid}.json`
  - `FirestoreStore()` — 컬렉션 `rankings/{mall}_{cat}`, `products/{mall}_{pid}` (자격증명은 `GOOGLE_APPLICATION_CREDENTIALS` 환경변수로 ADC 주입)
  - 저장 규칙: `save_product` 는 기존 문서의 `history` 배열에 `{"t": now_iso, "rank", "price", "review_score", "review_count"}` 를 append (최대 HISTORY_CAP, 초과 시 앞에서 절단). `reviews` 가 None 이면 기존 후기 유지, 리스트면 교체.
  - 랭킹 스냅샷 형태: `{"updatedAt": now_iso, "items": [상품 dict, ...]}`

- [ ] **Step 1: requirements 추가**

`crawler/requirements.txt` 끝에 `google-cloud-firestore>=2.18,<3.0` 추가 후:

```bash
cd crawler && ./.venv/Scripts/python.exe -m pip install -q -r requirements.txt
```

- [ ] **Step 2: 실패하는 테스트 작성**

`crawler/tests/test_store.py`:

```python
"""저장 계층 테스트 — LocalJsonStore 는 tmp_path, Firestore 는 페이크 클라이언트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from store import FirestoreStore, LocalJsonStore


def prod(pid="1", rank=1, count=5):
    return {"mall": "musinsa", "product_id": pid, "rank": rank, "brand": "b",
            "name": "n", "price": 1000, "original_price": None, "discount_rate": 0,
            "review_score": 4.8, "review_count": count, "thumbnail": None,
            "product_url": "u", "category_code": "001", "category_name": None}


def test_local_ranking_roundtrip(tmp_path):
    s = LocalJsonStore(str(tmp_path))
    assert s.load_ranking("musinsa", "001") is None
    snap = {"updatedAt": "2026-07-20T00:00:00", "items": [prod()]}
    s.save_ranking("musinsa", "001", snap)
    assert s.load_ranking("musinsa", "001") == snap


def test_local_product_history_appends_and_caps(tmp_path):
    s = LocalJsonStore(str(tmp_path))
    import store as store_mod
    orig_cap = store_mod.config.HISTORY_CAP
    store_mod.config.HISTORY_CAP = 3
    try:
        for i in range(5):
            s.save_product(prod(count=i), None, f"2026-07-20T0{i}:00:00")
        doc = json.load(open(tmp_path / "products" / "musinsa_1.json", encoding="utf-8"))
        assert len(doc["history"]) == 3
        assert doc["history"][-1]["t"] == "2026-07-20T04:00:00"
        assert doc["history"][0]["t"] == "2026-07-20T02:00:00"  # 앞에서 절단
    finally:
        store_mod.config.HISTORY_CAP = orig_cap


def test_local_product_reviews_replace_or_keep(tmp_path):
    s = LocalJsonStore(str(tmp_path))
    s.save_product(prod(), [{"score": 5, "text": "굿", "date": None, "likes": 0}], "t1")
    s.save_product(prod(), None, "t2")  # None → 기존 후기 유지
    doc = json.load(open(tmp_path / "products" / "musinsa_1.json", encoding="utf-8"))
    assert doc["reviews"][0]["text"] == "굿"
    assert len(doc["history"]) == 2


class FakeDoc:
    def __init__(self, db, key):
        self.db, self.key = db, key

    def get(self):
        class Snap:
            def __init__(self, data):
                self.exists = data is not None
                self._d = data

            def to_dict(self):
                return self._d
        return Snap(self.db.data.get(self.key))

    def set(self, data):
        self.db.data[self.key] = data


class FakeFirestore:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        db = self

        class Col:
            def document(self, doc_id):
                return FakeDoc(db, f"{name}/{doc_id}")
        return Col()


def test_firestore_store_same_contract():
    s = FirestoreStore(client=FakeFirestore())
    assert s.load_ranking("cm29", "best") is None
    snap = {"updatedAt": "t", "items": [prod()]}
    s.save_ranking("cm29", "best", snap)
    assert s.load_ranking("cm29", "best") == snap
    s.save_product(prod(), [{"score": 5, "text": "굿", "date": None, "likes": 0}], "t1")
    s.save_product(prod(), None, "t2")
    doc = s._db.data["products/musinsa_1"]
    assert doc["reviews"][0]["text"] == "굿" and len(doc["history"]) == 2
```

- [ ] **Step 3: 실패 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_store.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'store'`

- [ ] **Step 4: 구현**

`crawler/config.py`:

```python
"""수집 대상·상수 설정. 카테고리 추가/제거는 이 파일만 수정."""
from __future__ import annotations

# 무신사 카테고리 코드 → 한글명 (FINDINGS.md 실측 확인분)
MUSINSA_CATEGORIES: dict[str, str] = {
    "001": "상의",
    "002": "아우터",
    "003": "바지",
    "100": "원피스/스커트",
    "004": "가방",
    "103": "신발",
}

TOP_N = 50          # 카테고리당 저장 상위 개수
REVIEW_SIZE = 10    # 상품당 후기 수집 개수
HISTORY_CAP = 168   # 상품 이력 보존 개수 (시간당 1개 기준 약 1주)
```

`crawler/store.py`:

```python
"""저장 계층: 로컬 JSON(개발·시크릿 없는 CI용) / Firestore(운영)."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod

import config


def _updated_product_doc(old: dict | None, product: dict, reviews, now_iso: str) -> dict:
    doc = dict(old or {})
    doc.update(product)
    if reviews is not None:
        doc["reviews"] = reviews
    doc.setdefault("reviews", [])
    history = list(doc.get("history") or [])
    history.append({"t": now_iso, "rank": product.get("rank"),
                    "price": product.get("price"),
                    "review_score": product.get("review_score"),
                    "review_count": product.get("review_count")})
    doc["history"] = history[-config.HISTORY_CAP:]
    doc["updatedAt"] = now_iso
    return doc


class Store(ABC):
    @abstractmethod
    def load_ranking(self, mall: str, category_code: str) -> dict | None: ...

    @abstractmethod
    def save_ranking(self, mall: str, category_code: str, snapshot: dict) -> None: ...

    @abstractmethod
    def save_product(self, product: dict, reviews, now_iso: str) -> None: ...


class LocalJsonStore(Store):
    def __init__(self, out_dir: str):
        self.out = out_dir
        os.makedirs(os.path.join(out_dir, "rankings"), exist_ok=True)
        os.makedirs(os.path.join(out_dir, "products"), exist_ok=True)

    def _rank_path(self, mall, cat):
        return os.path.join(self.out, "rankings", f"{mall}_{cat}.json")

    def _prod_path(self, product):
        return os.path.join(self.out, "products",
                            f"{product['mall']}_{product['product_id']}.json")

    def load_ranking(self, mall, category_code):
        p = self._rank_path(mall, category_code)
        if not os.path.exists(p):
            return None
        return json.load(open(p, encoding="utf-8"))

    def save_ranking(self, mall, category_code, snapshot):
        json.dump(snapshot, open(self._rank_path(mall, category_code), "w",
                                 encoding="utf-8"), ensure_ascii=False)

    def save_product(self, product, reviews, now_iso):
        p = self._prod_path(product)
        old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
        json.dump(_updated_product_doc(old, product, reviews, now_iso),
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)


class FirestoreStore(Store):
    """Firestore 저장소. 자격증명은 GOOGLE_APPLICATION_CREDENTIALS(ADC)."""

    def __init__(self, client=None):
        if client is None:
            from google.cloud import firestore  # 지연 임포트
            client = firestore.Client()
        self._db = client

    def load_ranking(self, mall, category_code):
        snap = self._db.collection("rankings").document(f"{mall}_{category_code}").get()
        return snap.to_dict() if snap.exists else None

    def save_ranking(self, mall, category_code, snapshot):
        self._db.collection("rankings").document(f"{mall}_{category_code}").set(snapshot)

    def save_product(self, product, reviews, now_iso):
        ref = self._db.collection("products").document(
            f"{product['mall']}_{product['product_id']}")
        snap = ref.get()
        old = snap.to_dict() if snap.exists else None
        ref.set(_updated_product_doc(old, product, reviews, now_iso))
```

- [ ] **Step 5: 통과 + 커밋**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/ -q
git add crawler/config.py crawler/store.py crawler/tests/test_store.py crawler/requirements.txt
git commit -m "feat(crawler): 설정 + 저장 계층 (LocalJson/Firestore)"
```

Expected: `30 passed`

---

### Task 5: 오케스트레이션 + CLI (`main.py`)

**Files:**
- Create: `crawler/main.py`
- Test: `crawler/tests/test_main.py`

**Interfaces:**
- Consumes: Task 1~4 의 파서·fetcher·Store·config (정확한 시그니처는 각 태스크 Produces 참고)
- Produces:
  - `crawl_once(store, now_iso: str, fetch=fetchers, parse=parsers) -> dict` — 반환 stats: `{"rankings_saved": int, "products_saved": int, "reviews_fetched": int, "errors": list[str]}`
  - CLI: `python main.py --store json|firestore [--out out]` — 종료코드 0(에러 없음) / 1(부분 실패 — errors 비어있지 않음) / 2(전체 실패)
  - 증분 규칙: 이전 스냅샷의 `{product_id: review_count}` 와 비교해 **변했거나 새로 진입한 상품만** 후기 수집. 나머지는 `reviews=None` 으로 저장(기존 후기 유지).
  - 몰/카테고리 단위 try/except — 실패 시 해당 스냅샷은 저장하지 않고(이전 것 유지) errors 에 기록, 다음으로 진행.

- [ ] **Step 1: 실패하는 테스트 작성**

`crawler/tests/test_main.py`:

```python
"""crawl_once 오케스트레이션 테스트 — fetch/parse/store 전부 페이크."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config
from main import crawl_once
from store import LocalJsonStore


def _prod(mall, pid, count):
    return {"mall": mall, "product_id": pid, "rank": 1, "brand": "b", "name": "n",
            "price": 1, "original_price": None, "discount_rate": 0,
            "review_score": 5.0, "review_count": count, "thumbnail": None,
            "product_url": "u", "category_code": "001", "category_name": None}


class FakeFetch:
    def __init__(self):
        self.review_calls = []

    def fetch_musinsa_ranking(self, category_code, page=1):
        return {"cat": category_code}

    def fetch_cm29_best(self, page=1, size=100):
        return {"best": True}

    def fetch_musinsa_reviews(self, goods_no, size=10):
        self.review_calls.append(("musinsa", goods_no))
        return {}

    def fetch_cm29_reviews(self, item_id, size=10):
        self.review_calls.append(("cm29", item_id))
        return {}


class FakeParse:
    def __init__(self, m_items, c_items):
        self.m, self.c = m_items, c_items

    def parse_musinsa_ranking(self, data):
        return self.m[data["cat"]]

    def parse_cm29_best(self, data):
        return self.c

    def parse_musinsa_reviews(self, data):
        return [{"score": 5, "text": "굿", "date": None, "likes": 0}]

    def parse_cm29_reviews(self, data):
        return [{"score": 5, "text": "좋아요", "date": None, "likes": 0}]


def test_crawl_once_full_flow(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {"001": "상의"})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()
    parse = FakeParse({"001": [_prod("musinsa", "a", 3)]}, [_prod("cm29", "x", 7)])

    stats = crawl_once(store, "t1", fetch=fetch, parse=parse)
    assert stats["rankings_saved"] == 2          # 무신사 001 + 29CM best
    assert stats["products_saved"] == 2
    assert stats["reviews_fetched"] == 2          # 첫 실행 = 전부 신규
    assert stats["errors"] == []
    doc = json.load(open(tmp_path / "products" / "musinsa_a.json", encoding="utf-8"))
    assert doc["reviews"][0]["text"] == "굿"


def test_crawl_once_incremental_reviews(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {"001": "상의"})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()
    parse = FakeParse({"001": [_prod("musinsa", "a", 3)]}, [_prod("cm29", "x", 7)])
    crawl_once(store, "t1", fetch=fetch, parse=parse)
    fetch.review_calls.clear()

    # 2회차: musinsa a 는 후기 수 동일(3) → 스킵, cm29 x 는 7→9 변동 → 수집
    parse.c = [_prod("cm29", "x", 9)]
    stats = crawl_once(store, "t2", fetch=fetch, parse=parse)
    assert fetch.review_calls == [("cm29", "x")]
    assert stats["reviews_fetched"] == 1
    doc = json.load(open(tmp_path / "products" / "musinsa_a.json", encoding="utf-8"))
    assert doc["reviews"][0]["text"] == "굿"      # 유지됨
    assert len(doc["history"]) == 2


def test_crawl_once_category_failure_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MUSINSA_CATEGORIES", {"001": "상의", "002": "아우터"})
    store = LocalJsonStore(str(tmp_path))
    fetch = FakeFetch()

    def boom(category_code, page=1):
        if category_code == "001":
            raise RuntimeError("몰 응답 이상")
        return {"cat": category_code}

    fetch.fetch_musinsa_ranking = boom
    parse = FakeParse({"002": [_prod("musinsa", "b", 1)]}, [])
    stats = crawl_once(store, "t1", fetch=fetch, parse=parse)
    assert len(stats["errors"]) == 1 and "001" in stats["errors"][0]
    assert store.load_ranking("musinsa", "001") is None   # 실패 카테고리는 미저장
    assert store.load_ranking("musinsa", "002") is not None
```

- [ ] **Step 2: 실패 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_main.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: 구현**

`crawler/main.py`:

```python
"""크롤러 진입점: 무신사 카테고리별 + 29CM 베스트 → 저장소 적재.

사용법:
  python main.py --store json [--out out]     # 로컬 JSON (개발/시크릿 없는 CI)
  python main.py --store firestore            # Firestore (GOOGLE_APPLICATION_CREDENTIALS 필요)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import config
import fetchers as _fetchers
import parsers as _parsers
from store import FirestoreStore, LocalJsonStore


def _collect_reviews(product, prev_counts, fetch, parse, stats):
    pid = product["product_id"]
    if pid in prev_counts and prev_counts[pid] == product["review_count"]:
        return None  # 변동 없음 → 기존 후기 유지
    stats["reviews_fetched"] += 1
    if product["mall"] == "musinsa":
        return parse.parse_musinsa_reviews(
            fetch.fetch_musinsa_reviews(pid, size=config.REVIEW_SIZE))
    return parse.parse_cm29_reviews(
        fetch.fetch_cm29_reviews(pid, size=config.REVIEW_SIZE))


def _run_job(store, mall, cat, products, now_iso, fetch, parse, stats):
    prev = store.load_ranking(mall, cat) or {}
    prev_counts = {p["product_id"]: p.get("review_count")
                   for p in prev.get("items") or []}
    store.save_ranking(mall, cat, {"updatedAt": now_iso, "items": products})
    stats["rankings_saved"] += 1
    for product in products:
        try:
            reviews = _collect_reviews(product, prev_counts, fetch, parse, stats)
        except Exception as e:  # 후기 실패는 상품 저장을 막지 않는다
            stats["errors"].append(f"후기 수집 실패 {mall}/{product['product_id']}: {e}")
            reviews = None
        store.save_product(product, reviews, now_iso)
        stats["products_saved"] += 1


def crawl_once(store, now_iso: str, fetch=_fetchers, parse=_parsers) -> dict:
    stats = {"rankings_saved": 0, "products_saved": 0,
             "reviews_fetched": 0, "errors": []}
    for cat, cat_name in config.MUSINSA_CATEGORIES.items():
        try:
            products = parse.parse_musinsa_ranking(
                fetch.fetch_musinsa_ranking(cat))[:config.TOP_N]
            for p in products:
                p["category_code"], p["category_name"] = cat, cat_name
            _run_job(store, "musinsa", cat, products, now_iso, fetch, parse, stats)
        except Exception as e:
            stats["errors"].append(f"무신사 {cat}({cat_name}) 실패: {e}")
    try:
        products = parse.parse_cm29_best(fetch.fetch_cm29_best())[:config.TOP_N]
        _run_job(store, "cm29", "best", products, now_iso, fetch, parse, stats)
    except Exception as e:
        stats["errors"].append(f"29CM best 실패: {e}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="패션 랭킹 크롤러")
    ap.add_argument("--store", choices=["json", "firestore"], required=True)
    ap.add_argument("--out", default="out", help="json 모드 출력 폴더")
    args = ap.parse_args()

    store = LocalJsonStore(args.out) if args.store == "json" else FirestoreStore()
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats = crawl_once(store, now_iso)

    print(f"완료: 랭킹 {stats['rankings_saved']}건, 상품 {stats['products_saved']}건, "
          f"후기 수집 {stats['reviews_fetched']}건, 오류 {len(stats['errors'])}건")
    for err in stats["errors"]:
        print("  오류:", err)
    if stats["rankings_saved"] == 0:
        return 2
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과 + 커밋**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/ -q
git add crawler/main.py crawler/tests/test_main.py
git commit -m "feat(crawler): crawl_once 오케스트레이션 + CLI (증분 후기)"
```

Expected: `33 passed`

---

### Task 6: 운영 실행 — 로컬 실크롤 1회 검증

실제 몰 접속이 일어나는 **운영 실행** (pytest 아님). 소요 예상: 카테고리 6 + 베스트 1 = 랭킹 7회 + 첫 실행 후기 최대 350회 × (딜레이 1초 + 응답) ≈ 10~15분.

**Files:** 없음 (산출물 `crawler/out/` 은 .gitignore 대상 — Step 3 에서 추가)

- [ ] **Step 1: .gitignore 에 출력 폴더 추가**

`.gitignore` 의 `# crawler` 블록에 `crawler/out/` 한 줄 추가.

- [ ] **Step 2: 실크롤 실행**

```bash
export PATH="/c/Users/yepdo/AppData/Local/Programs/Python/Python312:$PATH"
cd "C:/Users/yepdo/OneDrive/Desktop/fashion-cardnews/crawler" && PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe main.py --store json --out out
```

Expected: `완료: 랭킹 7건, 상품 350건, 후기 수집 350건, 오류 0건` (첫 실행 기준. 후기 수집 수는 후기 없는 신상품 등으로 ± 가능, 오류 0 이어야 함)

- [ ] **Step 3: 산출물 검증**

```bash
cd "C:/Users/yepdo/OneDrive/Desktop/fashion-cardnews/crawler" && PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe - << 'EOF'
import json, glob
ranks = glob.glob("out/rankings/*.json")
prods = glob.glob("out/products/*.json")
assert len(ranks) == 7, ranks
assert len(prods) >= 300, len(prods)
snap = json.load(open("out/rankings/musinsa_001.json", encoding="utf-8"))
assert len(snap["items"]) == 50 and snap["items"][0]["brand"]
doc = json.load(open(prods[0], encoding="utf-8"))
assert "history" in doc and "reviews" in doc
with_reviews = sum(1 for p in prods if json.load(open(p, encoding="utf-8"))["reviews"])
print(f"검증 OK: 랭킹 {len(ranks)}, 상품 {len(prods)}, 후기 보유 상품 {with_reviews}")
EOF
```

Expected: `검증 OK: ...` (후기 보유 상품 > 200)

- [ ] **Step 4: 2회차 실행으로 증분 동작 확인**

바로 이어서 `main.py --store json --out out` 을 한 번 더 실행.
Expected: `후기 수집` 건수가 1회차보다 **현저히 작아야** 함 (매시간 변동분만 — 보통 수십 건 이하). history 길이 2 확인:

```bash
cd "C:/Users/yepdo/OneDrive/Desktop/fashion-cardnews/crawler" && PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe -c "import json,glob; d=json.load(open(sorted(glob.glob('out/products/*.json'))[0], encoding='utf-8')); print('history:', len(d['history']))"
```

Expected: `history: 2`

- [ ] **Step 5: 커밋**

```bash
git add .gitignore
git commit -m "chore(crawler): 실크롤 검증 완료, out/ gitignore"
```

---

### Task 7: 매시간 워크플로 (`crawl.yml`) + 문서

**Files:**
- Create: `.github/workflows/crawl.yml`
- Modify: `README.md` (크롤러 섹션 추가), `DEPLOY.md` (시크릿 재사용 안내 1줄)

**Interfaces:**
- Consumes: Task 5 CLI (`python main.py --store json|firestore`), GitHub Secret `FIREBASE_SERVICE_ACCOUNT`(기존 deploy.yml 과 동일 키).
- Produces: cron `7 * * * *`(정시 피크 회피) + workflow_dispatch. 시크릿 있으면 firestore 모드, 없으면 json 모드 + `crawl-out` 아티팩트 업로드.

- [ ] **Step 1: 워크플로 작성**

`.github/workflows/crawl.yml`:

```yaml
name: 랭킹 크롤러 (매시간)

# 매시간 7분에 무신사/29CM 랭킹·후기를 수집한다.
# FIREBASE_SERVICE_ACCOUNT 시크릿이 있으면 Firestore 에 적재하고,
# 없으면 로컬 JSON 으로 돌려 아티팩트로만 업로드한다(실패 아님).
on:
  schedule:
    - cron: "7 * * * *"
  workflow_dispatch:

concurrency:
  group: crawl
  cancel-in-progress: false

jobs:
  crawl:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        working-directory: crawler
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt
      - name: Crawl (Firestore 모드)
        if: ${{ secrets.FIREBASE_SERVICE_ACCOUNT != '' }}
        working-directory: crawler
        env:
          FIREBASE_SA: ${{ secrets.FIREBASE_SERVICE_ACCOUNT }}
        run: |
          printf '%s' "$FIREBASE_SA" > /tmp/sa.json
          export GOOGLE_APPLICATION_CREDENTIALS=/tmp/sa.json
          python main.py --store firestore
      - name: Crawl (JSON 모드 — 시크릿 없음)
        if: ${{ secrets.FIREBASE_SERVICE_ACCOUNT == '' }}
        working-directory: crawler
        run: python main.py --store json --out out
      - name: Upload JSON output
        if: ${{ secrets.FIREBASE_SERVICE_ACCOUNT == '' }}
        uses: actions/upload-artifact@v4
        with:
          name: crawl-out
          path: crawler/out/
          retention-days: 3
```

**주의(구현자):** GitHub Actions 의 `if:` 컨텍스트에서 `secrets` 를 직접 비교할 수 없는 러너 버전이 있다. 위 표현식이 워크플로 파싱 오류를 내면, `env: HAS_SA: ${{ secrets.FIREBASE_SERVICE_ACCOUNT != '' }}` 를 job 레벨에 두고 step `if: env.HAS_SA == 'true'` 로 바꾼다 (deploy.yml 의 Gate 스텝 패턴 참고 — 같은 문제를 output 으로 우회하고 있음).

- [ ] **Step 2: YAML 검증**

```bash
cd crawler && ./.venv/Scripts/python.exe -c "import yaml; yaml.safe_load(open('../.github/workflows/crawl.yml', encoding='utf-8')); print('yaml ok')"
```

Expected: `yaml ok` (pyyaml 은 Task 4 의 probe 검증 때 이미 설치됨; 없으면 `pip install pyyaml`)

- [ ] **Step 3: README 크롤러 섹션 추가**

`README.md` 의 "개발 자동화" 섹션 위에 추가:

```markdown
## 랭킹 크롤러 (crawler/)
무신사 카테고리별 TOP 50 + 29CM 베스트 TOP 50 의 순위·가격·평점·후기(상품당 10개)를
매시간 수집한다 (`.github/workflows/crawl.yml`, 매시간 7분).

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest -q   # 테스트 (네트워크 없음)
./.venv/Scripts/python.exe main.py --store json         # 로컬 실크롤 → out/
./.venv/Scripts/python.exe main.py --store firestore    # Firestore 적재 (ADC 필요)
```

- Firestore 모드는 GitHub Secret `FIREBASE_SERVICE_ACCOUNT` 등록 시 자동 활성화 (없으면 JSON 아티팩트 모드).
- 엔드포인트 실측 문서: [crawler/FINDINGS.md](crawler/FINDINGS.md)
```

`DEPLOY.md` 3장 표 아래에 1줄 추가:

```markdown
> 이 시크릿은 `.github/workflows/crawl.yml`(랭킹 크롤러)의 Firestore 적재에도 그대로 사용된다.
```

- [ ] **Step 4: 커밋·푸시 + dispatch 로 1회 실행 확인**

```bash
git add .github/workflows/crawl.yml README.md DEPLOY.md
git commit -m "ci(crawler): 매시간 크롤 워크플로 + 문서"
git push
```

푸시 후 REST API 로 workflow_dispatch 1회 실행(프로브 검증 때 쓴 `git credential fill` 토큰 방식 그대로), run 이 `completed/success` 이고 JSON 모드 아티팩트 `crawl-out` 에 rankings 7개 파일이 있는지 확인한다. (시크릿 등록 전이므로 JSON 모드가 정상이다.)

Expected: run success + 아티팩트에 `rankings/*.json` 7개.

---

### Task 8 (사용자 게이트): Firebase 프로젝트 연결 후 Firestore 실적재 확인

**사전 조건(사용자 작업, DEPLOY.md 1~3장):** Firebase 프로젝트 생성 → 서비스 계정 키 발급 → GitHub Secret `FIREBASE_SERVICE_ACCOUNT` 등록 (+ `.firebaserc` 의 `your-project-id` 교체).

- [ ] **Step 1:** 시크릿 등록 후 workflow_dispatch 로 crawl.yml 1회 실행 → Firestore 모드 로그 확인 (`완료: 랭킹 7건...`).
- [ ] **Step 2:** Firebase 콘솔(또는 로컬 ADC + 파이썬)로 `rankings` 컬렉션 7개 문서, `products` 문서 300+ 존재 확인.
- [ ] **Step 3:** 스펙 Phase 1 완료 기준("Firestore에 실데이터 스냅샷 적재, 파서 테스트 통과") 충족 기록 — `docs/superpowers/specs/...design.md` 는 수정하지 않고 진행 레저에만 기록.

---

## Self-Review 결과

- **스펙 커버리지**: Phase 1 완료 기준 두 가지 — "파서 테스트 통과"(Task 1~5), "Firestore 실데이터 적재"(Task 7 JSON 모드로 파이프라인 검증 + Task 8 에서 Firestore 실적재; Task 8 은 사용자 시크릿 등록에 의존함을 명시). 스펙의 증분 후기·요청 매너·에러 격리(실패 카테고리 스냅샷 유지) 모두 Task 5 에 반영.
- **플레이스홀더 스캔**: 코드 블록 전체 실코드. Task 7 의 `if: secrets` 표현식 이슈는 대안 코드 경로를 본문에 명시(구현자 판단 지점이 아니라 지시된 폴백).
- **타입 일관성**: 정규화 스키마(공통 절) ↔ 파서 출력 ↔ store 테스트의 `prod()` ↔ main 의 필드 접근(`product_id`, `review_count`, `mall`) 일치 확인. `crawl_once(store, now_iso, fetch=, parse=)` 시그니처가 test_main 사용처와 일치. `FirestoreStore(client=None)` 페이크 주입 경로 일치.
