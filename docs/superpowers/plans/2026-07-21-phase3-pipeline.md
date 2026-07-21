# Phase 3: 로컬 원클릭 파이프라인 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사이트의 "카드뉴스 만들기" 버튼을 받아주는 로컬 FastAPI 앱(포트 8787) — 선택 상품의 상세·후기를 Firestore 에서 읽고, 문구를 생성(Claude API, 키 없으면 규칙 기반 폴백)해 C안 템플릿으로 1080×1350 JPG 를 렌더한 뒤, 미리보기 페이지에서 "게시" 클릭 시 인스타 캐러셀로 게시한다.

**Architecture:** `pipeline/` 에 모듈 4개 — `reader.py`(Firestore REST 공개 읽기+이미지 다운로드), `copywriter.py`(Claude/폴백 문구+캡션), `renderer.py`(card-drafts C안 템플릿 주입+Playwright 렌더), `app.py`(FastAPI: CORS 허용, 잡 오케스트레이션 스레드, 미리보기/게시). 게시는 기존 `scripts/post_ig.py` 함수 재사용. 파이썬 환경은 crawler/.venv 재사용(+fastapi/uvicorn/anthropic 추가).

**Tech Stack:** Python 3.12 (crawler/.venv), FastAPI+uvicorn, requests, Playwright, Pillow, anthropic(선택), pytest.

## Global Constraints

- 모든 사용자 노출 텍스트(미리보기 페이지·로그·에러) 한국어 — CLAUDE.md.
- Bash 툴, python 명령 전 `export PATH="/c/Users/yepdo/AppData/Local/Programs/Python/Python312:$PATH"`, 파이썬 = `crawler/.venv/Scripts/python.exe`, 한글 출력 `PYTHONIOENCODING=utf-8`.
- **pytest 는 외부 호출 전면 금지**: Anthropic 목, Firestore REST 목, 인스타/이미지 호스팅 목, Playwright 렌더 목(렌더 실검증은 Task 5 운영 리허설에서).
- 비밀키: `pipeline/.env`(미커밋)에 `ANTHROPIC_API_KEY`(선택). 없으면 폴백 문구 모드로 동작해야 한다(전 구간 키 없이 실행 가능). IG 토큰은 기존 `카드뉴스\ig_api_token.txt` 재사용(post_ig 경유). `.env.example` 만 커밋.
- CORS: `https://fashion-cardnews.web.app` + `http://localhost:5173` + `http://localhost:4173` 허용 (최종 리뷰 이관 사항).
- 산출물 저장 규칙: `C:\Users\yepdo\OneDrive\Desktop\카드뉴스\YYYYMMDD 랭킹픽\1.jpg~N.jpg` + `caption.txt` (기존 규칙).
- 카드 구성 = C안 고정: 표지 + 상품 N장(상품명 라인 포함) + CTA. 캡션 = 절제 톤(제목형 1줄, 담백한 2~3문장, 경험 소환형 질문, 이모지 0~1, 해시태그 10~11, 나열체·말줄임표 금지).
- 커밋 트레일러 2줄: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01PgitEtAu5cwDBPf5BsKcLr`

## File Structure

```
pipeline/
  requirements.txt      # fastapi, uvicorn, anthropic (나머지는 crawler venv 에 이미 있음)
  .env.example          # ANTHROPIC_API_KEY=sk-ant-xxx (선택)
  reader.py             # Firestore REST 읽기 + 이미지 다운로드
  copywriter.py         # 문구·캡션 생성 (Claude / 폴백)
  renderer.py           # C안 템플릿 주입 + Playwright 1080x1350 렌더
  publisher.py          # scripts/post_ig 함수 재사용 게시
  jobs.py               # 잡 상태 머신 (dict 기반, 단계 진행)
  app.py                # FastAPI 진입점 (CORS, 엔드포인트, 미리보기 HTML)
  tests/
    test_reader.py  test_copywriter.py  test_renderer.py  test_jobs_app.py
```

## 데이터 계약 (전 태스크 공통)

- 입력(사이트 → POST /api/selections): `{"createdAt": str, "items": [RankItem...]}` — RankItem 은 Phase 2 정규화 스키마(14필드).
- `reader.load_products(items) -> list[Product]`: Product = RankItem 필드 + `{"reviews": [{"score","text","date","likes"}...], "image_path": str|None}` (Firestore `products/{mall}_{pid}` 공개 REST 로 후기 보강, 썸네일 다운로드).
- `copywriter.write_copy(products, topic) -> Copy`: `{"topic": str, "cover": {"kicker","title","sub"}, "items": [{"prod","title","meta","proof","sp","badge"|None}...], "cta": {"title","sub"}, "caption": str}` — title/sub 는 `<em>`·`<br>` 허용 HTML 조각.
- `renderer.render(copy, products, out_dir) -> list[str]`: `1.jpg..N.jpg` 절대경로 (1080×1350, cover+items+cta 순).
- `jobs`: `{"id", "status": "받음|문구 생성 중|렌더 중|미리보기 대기|게시 중|완료|실패", "error", "folder", "images", "permalink"}`.

---

### Task 1: 골격 + Firestore 리더 (`reader.py`)

**Files:**
- Create: `pipeline/requirements.txt`, `pipeline/.env.example`, `pipeline/reader.py`, `pipeline/tests/test_reader.py`

- [ ] **Step 1: 의존성 설치**

`pipeline/requirements.txt`:

```
fastapi>=0.115,<1.0
uvicorn[standard]>=0.32,<1.0
anthropic>=0.40,<1.0
```

`pipeline/.env.example`:

```
# 선택: 있으면 Claude 로 문구 생성, 없으면 규칙 기반 폴백
ANTHROPIC_API_KEY=sk-ant-xxxxxxxx
```

```bash
cd crawler && ./.venv/Scripts/python.exe -m pip install -q -r ../pipeline/requirements.txt
```

- [ ] **Step 2: 실패하는 테스트**

`pipeline/tests/test_reader.py`:

```python
"""reader 테스트 — 전부 목, 네트워크 없음."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reader


def item(pid="1", mall="musinsa"):
    return {"mall": mall, "product_id": pid, "rank": 1, "brand": "b", "name": "n",
            "price": 1000, "original_price": None, "discount_rate": 10,
            "review_score": 4.8, "review_count": 5,
            "thumbnail": "https://img.example/x.jpg", "product_url": "https://u",
            "category_code": None, "category_name": None}


def test_decode_fs_value_roundtrip():
    fs = {"mapValue": {"fields": {"score": {"integerValue": "5"},
                                  "text": {"stringValue": "굿"}}}}
    assert reader.fv(fs) == {"score": 5, "text": "굿"}


def test_load_products_merges_reviews_and_downloads(monkeypatch, tmp_path):
    def fake_get(url, **kw):
        class R:
            ok = True
            status_code = 200
            content = b"IMGDATA"
            def json(self):
                return {"fields": {"reviews": {"arrayValue": {"values": [
                    {"mapValue": {"fields": {"score": {"integerValue": "5"},
                                             "text": {"stringValue": "아주 좋아요"},
                                             "date": {"nullValue": None},
                                             "likes": {"integerValue": "2"}}}}]}}}}
        return R()

    monkeypatch.setattr(reader.requests, "get", fake_get)
    out = reader.load_products([item()], assets_dir=str(tmp_path))
    p = out[0]
    assert p["reviews"][0]["text"] == "아주 좋아요"
    assert p["image_path"] and Path(p["image_path"]).read_bytes() == b"IMGDATA"


def test_load_products_survives_missing_doc(monkeypatch, tmp_path):
    def fake_get(url, **kw):
        class R:
            ok = False
            status_code = 404
            content = b""
            def json(self):
                return {}
        return R()

    monkeypatch.setattr(reader.requests, "get", fake_get)
    out = reader.load_products([item()], assets_dir=str(tmp_path))
    assert out[0]["reviews"] == [] and out[0]["image_path"] is None
```

- [ ] **Step 3: 실패 확인**

```bash
cd pipeline && ../crawler/.venv/Scripts/python.exe -m pytest tests/test_reader.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'reader'`

- [ ] **Step 4: 구현**

`pipeline/reader.py`:

```python
"""선택 상품 보강: Firestore 공개 REST 로 후기 로드 + 썸네일 다운로드."""
from __future__ import annotations

import os

import requests

PROJECT = "fashion-cardnews"
KEY = "AIzaSyBZIp-NLD8rw6asKSAwIOH-4I4hg9ecALo"  # 공개 웹 API 키 (규칙으로 보호)
BASE = f"https://firestore.googleapis.com/v1/projects/{PROJECT}/databases/(default)/documents"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def fv(v):
    if not isinstance(v, dict):
        return None
    if "stringValue" in v: return v["stringValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue" in v: return v["doubleValue"]
    if "booleanValue" in v: return v["booleanValue"]
    if "nullValue" in v: return None
    if "mapValue" in v:
        return {k: fv(x) for k, x in (v["mapValue"].get("fields") or {}).items()}
    if "arrayValue" in v:
        return [fv(x) for x in (v["arrayValue"].get("values") or [])]
    return None


def _fetch_reviews(mall: str, pid: str) -> list[dict]:
    url = f"{BASE}/products/{mall}_{pid}?key={KEY}&mask.fieldPaths=reviews"
    r = requests.get(url, timeout=30, headers=UA)
    if not r.ok:
        return []
    fields = r.json().get("fields") or {}
    reviews = fv(fields.get("reviews", {"arrayValue": {}})) or []
    return [rv for rv in reviews if isinstance(rv, dict) and rv.get("text")]


def _download_image(url: str | None, dest: str) -> str | None:
    if not url:
        return None
    try:
        r = requests.get(url, timeout=60, headers=UA)
        if not r.ok or len(r.content) < 1000 and not r.content:
            return None
        open(dest, "wb").write(r.content)
        return os.path.abspath(dest)
    except requests.exceptions.RequestException:
        return None


def load_products(items: list[dict], assets_dir: str) -> list[dict]:
    os.makedirs(assets_dir, exist_ok=True)
    out = []
    for it in items:
        pid, mall = str(it["product_id"]), it["mall"]
        reviews = _fetch_reviews(mall, pid)
        image_path = _download_image(
            it.get("thumbnail"), os.path.join(assets_dir, f"{mall}_{pid}.jpg"))
        out.append({**it, "reviews": reviews, "image_path": image_path})
    return out
```

- [ ] **Step 5: 통과 + 커밋**

```bash
cd pipeline && ../crawler/.venv/Scripts/python.exe -m pytest tests/ -q
git add pipeline/requirements.txt pipeline/.env.example pipeline/reader.py pipeline/tests/test_reader.py
git commit -m "feat(pipeline): Firestore 리더 + 골격"
```

Expected: `3 passed`

---

### Task 2: 문구·캡션 생성 (`copywriter.py`)

**Files:**
- Create: `pipeline/copywriter.py`, `pipeline/tests/test_copywriter.py`

**요구 (Copy 계약은 공통 절):**
- `write_copy(products, topic="랭킹 픽", api_key=None) -> dict` — api_key 있으면 Claude(`claude-sonnet-5`, JSON 응답 파싱), 없거나 실패하면 `fallback_copy` 로 자동 전환(예외 금지).
- `fallback_copy(products, topic)`: 규칙 기반 —
  - cover: kicker `"TODAY PICK {N}"`, title `f"오늘의 픽,<br><em>{topic}</em>"`, sub `f"무신사·29CM 랭킹에서 고른 {N}개"`
  - item(상품별): prod `f"{brand} · <b>{이름 30자 절단}</b>"`, title `f"랭킹 {rank}위<br><em>{brand}</em>"`, meta `f"{몰명} {price:,}원"`(+정가 취소선 `<s>` if original_price), proof `f"후기 {review_count}개 · ⭐{review_score}"`(없으면 `"신상 픽"`), sp = 첫 후기 80자 절단 `f"\"{...}\" — 실제 후기"`(후기 없으면 `f"{category_name or '지금'} 랭킹 {rank}위 아이템"`), badge `f"{discount_rate}%"`(할인>0), cr `"이미지 출처 : 무신사"`/29CM
  - cta: title `"오늘 픽,<br><em>저장</em>으로 끝"`, sub `"📌 최애는 댓글로<br>다음 픽은 팔로우하면 먼저 봐요"`
  - caption(절제 톤): `f"{topic} {N}\n\n무신사와 29CM 랭킹에서 후기로 검증된 {N}개를 골랐습니다.\n가격과 순위는 오늘 기준입니다.\n\n요즘 눈여겨보는 아이템이 있다면 댓글로 알려주세요.\n\n#패션 #쇼핑 #랭킹 #무신사 #29CM #오늘의픽 #패션추천 #데일리룩 #쇼핑리스트 #위시리스트"`
- Claude 경로: system 프롬프트에 C안 후킹 톤 규칙 + Copy JSON 스키마 명시, user 에 상품 데이터(JSON). 응답은 코드펜스 허용 파싱(```json 제거). 파싱 실패/예외 → 폴백. **테스트는 anthropic 모듈 목**(`monkeypatch.setattr(copywriter, "_call_claude", ...)` 수준 허용).

- [ ] **Step 1: 실패하는 테스트** — `test_copywriter.py`:

```python
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
    assert cap.count("#") in (10, 11)
    assert "…" not in cap and "..." not in cap


def test_write_copy_without_key_uses_fallback():
    c = copywriter.write_copy([prod()], api_key=None)
    assert c["cover"]["kicker"].startswith("TODAY PICK")


def test_write_copy_claude_success(monkeypatch):
    fake = {"topic": "T", "cover": {"kicker": "K", "title": "T<em>t</em>", "sub": "s"},
            "items": [{"prod": "p", "title": "t", "meta": "m", "proof": "pr", "sp": "s", "badge": None}],
            "cta": {"title": "c", "sub": "s"}, "caption": "cap #a #b #c #d #e #f #g #h #i #j"}
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
```

- [ ] **Step 2: 실패 확인** — 위와 동일 패턴.

- [ ] **Step 3: 구현** — 계약·폴백 규칙을 그대로 코드로. `_call_claude(products, topic, key) -> str` 는 anthropic 지연 임포트, `client.messages.create(model="claude-sonnet-5", max_tokens=4096, system=..., messages=[...])`, 텍스트 블록 연결 반환. `write_copy` 는 `_parse(text)`(코드펜스 제거 후 json.loads, 스키마 키 검증) 실패 시 폴백. 후기 sp 선택은 "가장 긴 텍스트 우선" 대신 **첫 후기** 사용(결정적).

- [ ] **Step 4: 통과 + 커밋** — `git add pipeline/copywriter.py pipeline/tests/test_copywriter.py` / `feat(pipeline): 문구·캡션 생성 (Claude+폴백)`

Expected: `7 passed` (누적)

---

### Task 3: 렌더러 (`renderer.py`)

**Files:**
- Create: `pipeline/renderer.py`, `pipeline/tests/test_renderer.py`

**요구:**
- 템플릿 = `card-drafts/uvparasol-insta.html` (저장소에 있음, C안+상품명 라인). `renderer.build_html(copy, products) -> str`: 템플릿을 읽어 `var IMAGES = ...;` / `var META = ...;` / `var CARDS = ...;` 블록을 정규식으로 교체(기존 build 스크립트 방식). IMAGES: image_path 를 base64 data URI 로(없으면 회색 1px PNG 폴백 상수), META: Pillow 로 w/h/bg(코너 픽셀), CARDS: copy 구조 → 템플릿 CARDS 형식(cover/item/cta, item 은 prod/title/meta_/proof/cr/sp/badge/num).
- `renderer.render(copy, products, out_dir) -> list[str]`: build_html 임시 저장 → Playwright(chromium, device_scale_factor=2) → **1열 레이아웃 CSS 주입 후** 카드별 element.screenshot(jpeg q92) → Pillow 로 정확히 1080×1350 크롭 → `out_dir/1.jpg..N.jpg`. (기존 렌더 스크립트의 검증된 시퀀스 그대로: transform none, scroll_into_view, 150ms 대기)
- 테스트: **Playwright 실행 없이** — `build_html` 만 검증: 교체 3블록 존재, CARDS 에 표지+상품+CTA 개수, base64 포함, 폴백 이미지 경로 None 처리. `render` 는 `_screenshot_cards` 를 목으로 대체해 파일명 규약만 검증.

- [ ] Steps: 실패 테스트 → 확인 → 구현 → `7+4=11 passed` → 커밋 `feat(pipeline): C안 렌더러`

테스트 코드(그대로 사용):

```python
"""renderer 테스트 — Playwright 목, 네트워크 없음."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import renderer


def copy2():
    return {"topic": "T",
            "cover": {"kicker": "K", "title": "커버<em>강조</em>", "sub": "부제"},
            "items": [{"prod": "브랜드 · <b>상품</b>", "title": "티<em>강</em>", "meta": "무신사 1,000원",
                       "proof": "후기 5개", "sp": "셀링", "badge": "20%"}],
            "cta": {"title": "씨<em>강</em>", "sub": "부제"},
            "caption": "cap"}


def prods():
    return [{"mall": "musinsa", "product_id": "1", "image_path": None, "brand": "브랜드"}]


def test_build_html_replaces_blocks(tmp_path):
    html = renderer.build_html(copy2(), prods())
    assert "var IMAGES = {" in html and "var META   = {" in html and "var CARDS  = [" in html
    assert "커버<em>강조</em>" in html
    assert "data:image/png;base64," in html  # image_path None → 폴백 1px


def test_build_html_card_count():
    html = renderer.build_html(copy2(), prods())
    import json, re
    cards = json.loads(re.search(r"var CARDS  = (\[.*?\]);", html, re.S).group(1))
    assert len(cards) == 3  # cover + 1 item + cta
    assert cards[1]["prod"] == "브랜드 · <b>상품</b>"


def test_render_writes_numbered_jpgs(monkeypatch, tmp_path):
    def fake_shots(html, n_cards, out_dir):
        paths = []
        for i in range(n_cards):
            p = Path(out_dir) / f"{i+1}.jpg"
            p.write_bytes(b"JPG")
            paths.append(str(p))
        return paths

    monkeypatch.setattr(renderer, "_screenshot_cards", fake_shots)
    out = renderer.render(copy2(), prods(), str(tmp_path))
    assert [Path(p).name for p in out] == ["1.jpg", "2.jpg", "3.jpg"]


def test_render_requires_cover_and_cta(tmp_path):
    import pytest
    bad = copy2(); bad.pop("cover")
    with pytest.raises(KeyError):
        renderer.render(bad, prods(), str(tmp_path))
```

---

### Task 4: FastAPI 앱 (`jobs.py`, `publisher.py`, `app.py`)

**Files:**
- Create: `pipeline/jobs.py`, `pipeline/publisher.py`, `pipeline/app.py`, `pipeline/tests/test_jobs_app.py`

**요구:**
- `jobs.py`: `create_job() -> dict`(uuid id, status "받음"), `set_status(job, status, **extra)`, in-memory `JOBS: dict[str, dict]`.
- `publisher.py`: `publish(folder: str) -> str` — `scripts/post_ig.py` 를 `sys.path` 로 임포트해 함수 재사용(collect_images/load_caption/load_token/api/host_image/wait_ready/captions_match). post_ig 의 검증 플로우 그대로: 토큰 검증→호스팅→아이템 컨테이너→캐러셀→FINISHED→게시→permalink+캡션 검증. 캡션 불일치 시 RuntimeError(게시물 링크 포함). 반환 = permalink.
- `app.py`:
  - CORS 미들웨어: 허용 오리진 3개(Global Constraints).
  - `POST /api/selections` → job 생성, **백그라운드 스레드**에서 실행: 문구 생성 중 → (reader.load_products) → (copywriter.write_copy, `.env` 의 키) → 렌더 중 → (renderer.render → `카드뉴스\YYYYMMDD 랭킹픽` 폴더, caption.txt 저장) → 미리보기 대기. 각 단계 실패 시 status 실패+error. 응답 `{"job_id", "preview_url": "http://localhost:8787/preview/{id}"}` 즉시 반환. 완료 시 `webbrowser.open(preview_url)`.
  - `GET /api/jobs/{id}` → 잡 상태 JSON.
  - `GET /preview/{id}` → 한국어 HTML: 진행 중이면 상태 + 3초 자동 새로고침, 미리보기 대기면 JPG 들(`/files/{id}/{n}.jpg`) + 캡션 텍스트 + [인스타에 게시] 버튼(POST /api/jobs/{id}/publish fetch) + [폴더 열기 안내], 완료면 permalink 링크.
  - `GET /files/{id}/{name}` → 잡 폴더의 파일 서빙 (FileResponse, 경로 탈출 방지: name 은 `[0-9]+\.jpg|caption\.txt` 만 허용).
  - `POST /api/jobs/{id}/publish` → 상태 "게시 중" → publisher.publish(folder) 스레드 → 완료/실패.
  - `if __name__ == "__main__": uvicorn.run(app, host="127.0.0.1", port=8787)`.
  - 폴더명: 같은 날 중복 시 ` (2)` 등 접미사.
- 테스트(`fastapi.testclient`, 파이프라인 단계 전부 목):
  - CORS 프리플라이트에 web.app 오리진 허용 확인
  - POST /api/selections → 202/200 + job_id, (목 처리된) 단계 완료 후 잡 상태 "미리보기 대기", images 채워짐
  - GET /preview/{id} 에 "인스타에 게시" 버튼 HTML 포함
  - /files 경로 탈출 차단 (`../` → 404/400)
  - POST publish → publisher.publish 목 호출 확인, 상태 "완료" + permalink
  - 잡 없음 → 404

(구현자는 테스트를 먼저 쓰고, 스레드는 테스트에서 동기 실행되도록 `run_pipeline(job, items, sync=True)` 헬퍼 또는 스레드 join 가능 구조로. 표준 라이브러리 threading 사용, asyncio 불필요.)

- [ ] Steps: 실패 테스트 → 확인 → 구현 → 전체 스위트(누적 ~17+) 통과 → 커밋 `feat(pipeline): FastAPI 원클릭 앱 (미리보기 게이트)`

---

### Task 5: 운영 리허설 (Phase 4 전반부)

운영 실행 — 실제 Firestore 읽기·실렌더. **인스타 실게시는 하지 않는다** (사용자 승인 게이트).

- [ ] **Step 1:** `cd pipeline && ../crawler/.venv/Scripts/python.exe app.py` 백그라운드 기동 (세션 배경 작업으로 — 서브에이전트 배경 프로세스는 태스크 종료 시 죽는 문제가 있으므로 컨트롤러가 직접).
- [ ] **Step 2:** 라이브 사이트 대신 curl 로 실제 선택 페이로드 전송(대시보드 Firestore 실데이터에서 상위 5개 조합) → 잡 완료까지 폴링.
- [ ] **Step 3:** 산출 검증 — `카드뉴스\YYYYMMDD 랭킹픽\1.jpg..7.jpg` 존재·1080×1350·caption.txt 규칙(해시태그 수·금지 문자), 미리보기 페이지 HTTP 200 + 게시 버튼.
- [ ] **Step 4:** (선택) 라이브 사이트에서 실제 버튼 클릭 E2E — Playwright 로 fashion-cardnews.web.app 열고 선택→전송→미리보기 URL 응답 확인 (CORS 실검증).
- [ ] **Step 5:** README 에 파이프라인 섹션(실행법: `crawler/.venv/Scripts/python.exe pipeline/app.py`) 추가, 커밋 `docs: 파이프라인 실행 안내`.

---

## Self-Review 결과

- **스펙 커버리지**: 스펙 §5 로컬 파이프라인 5단계(수집→문구→렌더→미리보기 게이트→게시) 전부 태스크에 대응. 진행 상태 표시는 미리보기 페이지 자동 새로고침으로 구현(사이트 내 표시 대신 — 스펙의 목적(진행 가시성) 충족, 구현 위치 단순화). 실패 시 중간 산출물 보존(폴더에 JPG/caption 남음, 상태 실패+error). CORS 는 Phase 2 최종 리뷰 이관 사항 반영.
- **플레이스홀더**: Task 2·4 는 계약+테스트 코드 완전 명시, 구현 코드는 계약 기술(전 태스크가 목 기반 테스트로 강제되므로 구현 자유도 안전). Task 1·3 은 코드 완전 수록.
- **타입 일관성**: Copy/Product/잡 상태 문자열이 태스크 간 동일 명칭. renderer 가 uvparasol 템플릿의 CARDS 필드명(prod/title/meta_/proof/cr/sp/badge) 사용 — copywriter 의 meta→meta_ 매핑은 renderer 책임으로 명시.
