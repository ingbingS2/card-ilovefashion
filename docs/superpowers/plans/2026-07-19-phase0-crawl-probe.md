# Phase 0: 크롤링 가능성 검증(프로브) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 무신사·29CM의 랭킹/후기 데이터를 주는 실제 API 엔드포인트를 자동 탐색해 응답 샘플을 확보하고, 같은 프로브가 GitHub Actions 러너에서도 성공하는지 검증한다.

**Architecture:** Playwright 헤드리스로 각 몰의 랭킹 페이지를 실제 로드하면서 XHR/fetch 응답을 가로채 저장하는 `discover` 모드와, 찾아낸 엔드포인트를 브라우저 없이 `requests`로 재현하는 `direct` 모드를 가진 단일 CLI(`crawler/probe.py`). 결과는 `crawler/samples/`에 저장하고 결론은 `crawler/FINDINGS.md`에 기록한다.

**Tech Stack:** Python 3.12, requests, Playwright(Chromium), pytest. GitHub Actions(workflow_dispatch).

## Global Constraints

- 모든 사용자 노출 텍스트·문서는 한국어 (코드 식별자·주석은 영어 허용) — CLAUDE.md.
- 셸 명령은 Bash 툴로 실행, 실행 전 `export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"` — CLAUDE.md.
- pytest 는 네트워크 호출 금지(픽스처 문자열만 사용). 실제 몰 접속은 프로브 *운영 실행*(Task 3·5)에서만 발생한다.
- 비밀키 불필요·커밋 금지. 이 페이즈는 인증 없는 공개 페이지만 다룬다.
- 요청 매너: 프리셋 페이지 수 최소(몰당 1페이지), 요청 간 딜레이, 봇 위장 목적의 프록시/우회 없음. 차단 시그널(403/429)이 나오면 그대로 기록하고 중단 — 우회 시도 금지.
- 커밋 메시지 끝에 Co-Authored-By/Claude-Session 트레일러 추가 (세션 규칙).

## 사전 참고

- `crawler/` 디렉토리는 아직 없다(신규). 저장소 루트: `C:\Users\yepdo\OneDrive\Desktop\fashion-cardnews`.
- Python 3.12는 `/c/Users/yepdo/AppData/Local/Programs/Python/Python312/python.exe`. crawler 는 backend 의 venv 를 쓰지 않고 전용 venv `crawler/.venv` 를 만든다.
- 성공 기준(스펙 Phase 0): 두 몰의 랭킹·후기 응답 샘플 확보 + "GitHub Actions에서 크롤링 가능/불가" 결론. 불가면 크롤러 실행 위치를 내 PC 스케줄러로 전환한다는 결정만 기록하면 된다(설계 변경 없음).

---

### Task 1: 프로젝트 골격 + 응답 분석 헬퍼 (`probe_lib.py`)

**Files:**
- Create: `crawler/requirements.txt`
- Create: `crawler/probe_lib.py`
- Create: `crawler/tests/test_probe_lib.py`
- Modify: `.gitignore` (crawler 항목 추가)

**Interfaces:**
- Produces:
  - `summarize_json(data: Any, max_depth: int = 3) -> Any` — JSON 구조 스케치(dict 는 키별 재귀, list 는 `{"__len__", "__first__"}`, 스칼라는 타입명 문자열).
  - `extract_next_data(html: str) -> dict | None` — `<script id="__NEXT_DATA__">` JSON 추출, 없으면 None.
  - `safe_name(s: str) -> str` — 파일명 안전 문자열(영숫자·`._-` 외 `_` 치환, 80자 제한).

- [ ] **Step 1: 디렉토리·의존성 파일 생성**

`crawler/requirements.txt`:

```
requests>=2.32,<3.0
playwright>=1.45,<2.0
pytest>=8.3,<9.0
```

`.gitignore` 끝에 추가:

```
# crawler
crawler/.venv/
crawler/samples/
crawler/__pycache__/
```

- [ ] **Step 2: venv 생성 + 의존성 설치**

```bash
export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
cd crawler && python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m playwright install chromium
```

Expected: 설치 성공 (playwright 브라우저 다운로드 포함, 수 분 소요 가능).

- [ ] **Step 3: 실패하는 테스트 작성**

`crawler/tests/test_probe_lib.py`:

```python
"""probe_lib 단위 테스트 — 네트워크 호출 없음, 문자열 픽스처만 사용."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe_lib import extract_next_data, safe_name, summarize_json


def test_summarize_json_dict_and_scalar_types():
    data = {"name": "셔츠", "price": 10000, "soldout": False}
    assert summarize_json(data) == {"name": "str", "price": "int", "soldout": "bool"}


def test_summarize_json_list_shows_len_and_first():
    data = {"items": [{"id": 1}, {"id": 2}, {"id": 3}]}
    assert summarize_json(data) == {
        "items": {"__len__": 3, "__first__": {"id": "int"}}
    }


def test_summarize_json_empty_list():
    assert summarize_json([]) == {"__len__": 0, "__first__": None}


def test_summarize_json_respects_max_depth():
    data = {"a": {"b": {"c": {"d": 1}}}}
    # depth 0=a-dict, 1=b-dict, 2=c-dict 에서 절단 → "dict" 타입명
    assert summarize_json(data, max_depth=3) == {"a": {"b": {"c": "dict"}}}


def test_extract_next_data_found():
    html = '<html><script id="__NEXT_DATA__" type="application/json">{"props": {"ok": true}}</script></html>'
    assert extract_next_data(html) == {"props": {"ok": True}}


def test_extract_next_data_missing_or_broken():
    assert extract_next_data("<html></html>") is None
    broken = '<script id="__NEXT_DATA__">{not json}</script>'
    assert extract_next_data(broken) is None


def test_safe_name():
    assert safe_name("https://api.a.com/v1/best?x=1") == "https_api.a.com_v1_best_x_1"
    assert len(safe_name("a" * 200)) == 80
```

- [ ] **Step 4: 테스트가 실패하는지 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'probe_lib'`

- [ ] **Step 5: 구현**

`crawler/probe_lib.py`:

```python
"""프로브 응답 분석 헬퍼 (순수 함수만 — 네트워크 없음)."""
from __future__ import annotations

import json
import re
from typing import Any

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def summarize_json(data: Any, max_depth: int = 3, _depth: int = 0) -> Any:
    """JSON 구조 스케치를 돌려준다.

    dict → 키마다 재귀, list → {"__len__", "__first__"}, 스칼라 → 타입명.
    max_depth 도달 시 컨테이너도 타입명 문자열로 절단.
    """
    if _depth >= max_depth and isinstance(data, (dict, list)):
        return type(data).__name__
    if isinstance(data, dict):
        return {k: summarize_json(v, max_depth, _depth + 1) for k, v in data.items()}
    if isinstance(data, list):
        first = summarize_json(data[0], max_depth, _depth + 1) if data else None
        return {"__len__": len(data), "__first__": first}
    return type(data).__name__


def extract_next_data(html: str) -> dict | None:
    """Next.js 페이지의 __NEXT_DATA__ JSON 을 추출한다. 없거나 깨졌으면 None."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def safe_name(s: str) -> str:
    """URL 등을 파일명으로 안전하게 변환 (영숫자·._- 유지, 80자 제한)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:80]
```

- [ ] **Step 6: 테스트 통과 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: `7 passed`

- [ ] **Step 7: 커밋**

```bash
git add crawler/requirements.txt crawler/probe_lib.py crawler/tests/test_probe_lib.py .gitignore
git commit -m "feat(crawler): 프로브 헬퍼(probe_lib) + 크롤러 골격"
```

---

### Task 2: 프로브 CLI (`probe.py`) — discover / direct 두 모드

**Files:**
- Create: `crawler/probe.py`
- Create: `crawler/probe_targets.py`
- Test: `crawler/tests/test_probe_cli.py`

**Interfaces:**
- Consumes: Task 1 의 `summarize_json`, `safe_name`.
- Produces:
  - CLI: `python probe.py discover <preset|custom> [url] [--keywords a,b] [--wait 8]`
  - CLI: `python probe.py direct <name> <url> [--params k=v ...]`
  - 산출물 규약(이후 계획들이 사용): `crawler/samples/<run-name>/index.json` — `[{"url", "status", "content_type", "file"}]`; 본문은 같은 폴더의 `NNN_<safe_name>.json|.txt`.
  - `probe_targets.PAGES: dict[str, dict]` — 프리셋 이름 → `{"url", "keywords"}`.

- [ ] **Step 1: 프리셋 정의**

`crawler/probe_targets.py`:

```python
"""discover 프리셋: 실제 브라우저로 로드할 페이지와 채집 키워드.

주의: 여기 URL 은 '페이지' 주소다. API 엔드포인트는 추측해 적지 않는다 —
페이지를 실제로 로드하며 XHR 을 가로채는 것이 이 프로브의 목적이다.
경로가 바뀌었으면 브라우저에서 실제 랭킹/베스트 페이지 주소를 확인해 갱신할 것.
"""

PAGES: dict[str, dict] = {
    # 무신사 랭킹 (전체)
    "musinsa_ranking": {
        "url": "https://www.musinsa.com/main/musinsa/ranking",
        "keywords": ["rank", "best", "goods", "api", "review"],
    },
    # 29CM 베스트 (전체)
    "cm29_best": {
        "url": "https://www.29cm.co.kr/home/best",
        "keywords": ["best", "rank", "product", "api", "review", "item"],
    },
}
```

- [ ] **Step 2: 실패하는 테스트 작성 (CLI 껍데기의 순수 부분만)**

`crawler/tests/test_probe_cli.py`:

```python
"""probe.py 의 순수 함수(파서·저장 경로 계산)만 테스트 — 네트워크·브라우저 없음."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from probe import build_parser, classify_body, sample_filename


def test_build_parser_discover_preset():
    args = build_parser().parse_args(["discover", "musinsa_ranking"])
    assert args.command == "discover"
    assert args.name == "musinsa_ranking"
    assert args.url is None


def test_build_parser_discover_custom_with_keywords():
    args = build_parser().parse_args(
        ["discover", "custom", "https://example.com/x", "--keywords", "review,goods"]
    )
    assert args.url == "https://example.com/x"
    assert args.keywords == "review,goods"


def test_build_parser_direct_with_params():
    args = build_parser().parse_args(
        ["direct", "t1", "https://example.com/api", "--params", "a=1", "b=2"]
    )
    assert args.command == "direct"
    assert args.params == ["a=1", "b=2"]


def test_classify_body_json_vs_text():
    assert classify_body('{"a": 1}') == ("json", {"a": 1})
    kind, parsed = classify_body("<html>hi</html>")
    assert kind == "text" and parsed is None


def test_sample_filename():
    assert sample_filename(3, "https://a.com/v1/best?p=1", "json") == (
        "003_https_a.com_v1_best_p_1.json"
    )
```

- [ ] **Step 3: 테스트 실패 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/test_probe_cli.py -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'probe'`

- [ ] **Step 4: 구현**

`crawler/probe.py`:

```python
"""엔드포인트 탐색 프로브.

discover: Playwright 로 페이지를 실제 로드하면서 키워드가 URL 에 포함된
          XHR/fetch 응답을 전부 저장한다. (엔드포인트를 '찾는' 단계)
direct  : 찾아낸 엔드포인트를 브라우저 없이 requests 로 재현한다.
          (크롤러가 브라우저 없이 동작 가능한지 확인하는 단계)

사용 예:
  python probe.py discover musinsa_ranking
  python probe.py discover custom https://www.musinsa.com/products/1234 --keywords review
  python probe.py direct musinsa_rank_api "https://api.musinsa.com/..." --params page=1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

from probe_lib import safe_name, summarize_json
from probe_targets import PAGES

SAMPLES = Path(__file__).resolve().parent / "samples"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="무신사/29CM 엔드포인트 탐색 프로브")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="페이지 로드 + XHR 채집")
    d.add_argument("name", help="프리셋 이름 또는 'custom'")
    d.add_argument("url", nargs="?", default=None, help="custom 일 때 페이지 URL")
    d.add_argument("--keywords", default=None, help="쉼표 구분 URL 키워드 필터")
    d.add_argument("--wait", type=int, default=8, help="로드 후 대기 초 (기본 8)")

    t = sub.add_parser("direct", help="requests 로 엔드포인트 직접 호출")
    t.add_argument("name", help="저장 폴더 이름")
    t.add_argument("url", help="엔드포인트 URL")
    t.add_argument("--params", nargs="*", default=[], help="k=v 쿼리 파라미터")
    return p


def classify_body(body: str):
    """본문이 JSON 이면 ("json", 파싱결과), 아니면 ("text", None)."""
    try:
        return "json", json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return "text", None


def sample_filename(seq: int, url: str, kind: str) -> str:
    ext = "json" if kind == "json" else "txt"
    return f"{seq:03d}_{safe_name(url)}.{ext}"


def _save(run_dir: Path, seq: int, url: str, status: int, content_type: str, body: str, index: list) -> None:
    kind, parsed = classify_body(body)
    fname = sample_filename(seq, url, kind)
    (run_dir / fname).write_text(body, encoding="utf-8")
    index.append({"url": url, "status": status, "content_type": content_type, "file": fname})
    print(f"  [{status}] {url}")
    if parsed is not None:
        print(f"        구조: {json.dumps(summarize_json(parsed, 2), ensure_ascii=False)[:300]}")


def cmd_discover(name: str, url: str | None, keywords: str | None, wait: int) -> int:
    if name != "custom":
        preset = PAGES.get(name)
        if not preset:
            print(f"알 수 없는 프리셋: {name} (가능: {', '.join(PAGES)})")
            return 2
        url = preset["url"]
        kw = preset["keywords"]
    else:
        if not url:
            print("custom 모드에는 URL 이 필요합니다.")
            return 2
        kw = []
    if keywords:
        kw = [k.strip().lower() for k in keywords.split(",") if k.strip()]

    from playwright.sync_api import sync_playwright

    run_dir = SAMPLES / name
    run_dir.mkdir(parents=True, exist_ok=True)
    index: list = []
    seq = 0

    print(f"discover: {url}\n키워드: {kw or '(전체 XHR)'}")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(user_agent=UA, locale="ko-KR",
                                viewport={"width": 1280, "height": 900})

        def on_response(res):
            nonlocal seq
            if res.request.resource_type not in ("xhr", "fetch"):
                return
            u = res.url.lower()
            if kw and not any(k in u for k in kw):
                return
            try:
                body = res.text()
            except Exception:
                return
            seq += 1
            _save(run_dir, seq, res.url, res.status,
                  res.headers.get("content-type", ""), body, index)

        page.on("response", on_response)
        page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        page.wait_for_timeout(wait * 1000)
        # 지연 로딩 유도: 두 번 스크롤
        for _ in range(2):
            page.mouse.wheel(0, 2500)
            page.wait_for_timeout(2000)
        # 페이지 자체 HTML 도 저장 (__NEXT_DATA__ 분석용)
        html = page.content()
        (run_dir / "page.html").write_text(html, encoding="utf-8")
        browser.close()

    (run_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n채집 {len(index)}건 → {run_dir}")
    return 0 if index else 1


def cmd_direct(name: str, url: str, params: list[str]) -> int:
    run_dir = SAMPLES / name
    run_dir.mkdir(parents=True, exist_ok=True)
    index: list = []
    q = dict(kv.split("=", 1) for kv in params)
    time.sleep(1)  # 요청 매너
    res = requests.get(url, params=q, timeout=30, headers={
        "User-Agent": UA, "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
    })
    _save(run_dir, 1, res.url, res.status_code,
          res.headers.get("content-type", ""), res.text, index)
    (run_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if res.ok else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "discover":
        return cmd_discover(args.name, args.url, args.keywords, args.wait)
    return cmd_direct(args.name, args.url, args.params)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 테스트 통과 확인**

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest tests/ -q
```

Expected: `12 passed` (Task 1 의 7개 + 신규 5개)

- [ ] **Step 6: 커밋**

```bash
git add crawler/probe.py crawler/probe_targets.py crawler/tests/test_probe_cli.py
git commit -m "feat(crawler): discover/direct 프로브 CLI"
```

---

### Task 3: 로컬 실행 — 실제 엔드포인트 채집 + FINDINGS 기록

이 태스크는 실제 몰 접속이 일어나는 **운영 실행**이다 (pytest 아님).

**Files:**
- Create: `crawler/FINDINGS.md`
- (로컬 전용, 미커밋) `crawler/samples/`

**Interfaces:**
- Produces: `crawler/FINDINGS.md` — 이후 "계획 2(크롤러)" 작성의 입력. 최소 포함 항목:
  몰별 랭킹 엔드포인트 URL·파라미터(카테고리·페이지), 응답 구조 요약(상품ID·브랜드·상품명·가격·평점·후기수·썸네일 필드 경로), 후기 엔드포인트 URL·파라미터, 카테고리 코드 목록(확인된 것만), 요청 헤더 요구사항.

- [ ] **Step 1: 두 몰 랭킹 페이지 discover 실행**

```bash
cd crawler && ./.venv/Scripts/python.exe probe.py discover musinsa_ranking
./.venv/Scripts/python.exe probe.py discover cm29_best
```

Expected: 각 실행에서 "채집 N건" (N ≥ 1). 0건이면: `--keywords` 없이 `discover custom <같은 URL>` 로 전체 XHR 을 다시 채집하고, `page.html` 의 `__NEXT_DATA__` 를 `probe_lib.extract_next_data` 로 확인한다 (데이터가 SSR 에 인라인된 경우 그것이 곧 데이터 소스다).

**주의:** 프리셋 URL 이 리다이렉트되거나 404 면, 브라우저에서 실제 랭킹/베스트 페이지 주소를 확인해 `probe_targets.py` 를 갱신하고 재실행한다 (URL 은 바뀌는 값이며, 갱신 자체가 이 태스크의 정상 작업이다).

- [ ] **Step 2: index.json 을 열어 랭킹 데이터 응답 식별**

`crawler/samples/<name>/index.json` 의 각 항목에서 상품 목록(상품ID·가격·상품명 배열)이 든 응답을 찾는다. 구조 요약이 프로브 출력에 이미 찍혀 있으므로 그걸 단서로 본문 파일을 직접 연다.

- [ ] **Step 3: 상품 상세·후기 엔드포인트 discover**

Step 2 에서 찾은 랭킹 데이터에서 상품 페이지 URL(또는 상품ID로 조립) 하나를 골라:

```bash
cd crawler && ./.venv/Scripts/python.exe probe.py discover custom "<상품 페이지 URL>" --keywords review,comment,estimate,rating
```

Expected: 후기 목록/평점 응답 채집. (29CM·무신사 각각 1개 상품씩 수행)

- [ ] **Step 4: direct 재현 — 브라우저 없이도 API 가 응답하는지 확인**

Step 2·3 에서 찾은 핵심 엔드포인트(몰별 랭킹 1개 + 후기 1개, 총 4개)를:

```bash
cd crawler && ./.venv/Scripts/python.exe probe.py direct <이름> "<엔드포인트 URL>"
```

Expected: `[200]` + JSON 구조 출력. 403/401 이면 discover 채집분의 요청 헤더(Referer, 커스텀 헤더)를 확인해 필요 헤더를 FINDINGS 에 기록한다 (이 경우 크롤러는 해당 헤더를 붙이거나 Playwright 경유로 결정 — 결정도 기록).

- [ ] **Step 5: FINDINGS.md 작성**

`crawler/FINDINGS.md` 에 Interfaces 에 명시한 항목을 실측값으로 기록한다. 형식:

```markdown
# 크롤링 탐색 결과 (Phase 0)

- 실행일: YYYY-MM-DD
- 로컬(내 PC) 결과 / GitHub Actions 결과 구분 기재

## 무신사
### 랭킹 엔드포인트
- URL: (실측값)
- 파라미터: (실측값 — 카테고리 코드, 페이지, 사이즈)
- 필요 헤더: (실측값 또는 "없음")
- 응답 구조: (summarize_json 출력 붙여넣기 + 필드 경로 표)
### 후기 엔드포인트
- (동일 형식)

## 29CM
- (동일 형식)

## 카테고리 코드 (확인분)
| 카테고리 | 무신사 코드 | 29CM 코드 |

## 결론
- 브라우저 없이 requests 만으로 수집 가능 여부: (예/아니오 + 근거)
- GitHub Actions 실행 가능 여부: (Task 5 에서 기입)
```

- [ ] **Step 6: 커밋 (samples 는 .gitignore 로 제외됨)**

```bash
git add crawler/FINDINGS.md crawler/probe_targets.py
git commit -m "docs(crawler): Phase 0 로컬 탐색 결과 기록"
```

---

### Task 4: GitHub Actions 프로브 워크플로

**Files:**
- Create: `.github/workflows/probe.yml`

**Interfaces:**
- Consumes: Task 2 의 `probe.py` CLI (discover 프리셋 / direct).
- Produces: workflow_dispatch 로 실행 가능한 `크롤링 프로브` 워크플로. 산출물 `crawler/samples/` 를 `probe-samples` 아티팩트로 업로드.

- [ ] **Step 1: 워크플로 작성**

`.github/workflows/probe.yml`:

```yaml
name: 크롤링 프로브 (Phase 0)

# 수동 실행 전용. Actions 러너(데이터센터 IP)에서 무신사/29CM 가 응답하는지 검증한다.
on:
  workflow_dispatch:
    inputs:
      mode:
        description: "discover 프리셋 이름(musinsa_ranking, cm29_best) 또는 direct"
        required: true
        default: "musinsa_ranking"
      url:
        description: "mode=direct 일 때 엔드포인트 URL"
        required: false
        default: ""

jobs:
  probe:
    runs-on: ubuntu-latest
    timeout-minutes: 15
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
          python -m playwright install --with-deps chromium
      - name: Run probe
        working-directory: crawler
        run: |
          if [ "${{ github.event.inputs.mode }}" = "direct" ]; then
            python probe.py direct actions_direct "${{ github.event.inputs.url }}"
          else
            python probe.py discover "${{ github.event.inputs.mode }}"
          fi
      - name: Upload samples
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: probe-samples-${{ github.event.inputs.mode }}
          path: crawler/samples/
          retention-days: 7
```

- [ ] **Step 2: YAML 문법 검증 (로컬)**

```bash
cd crawler && ./.venv/Scripts/python.exe -c "import yaml,sys; yaml.safe_load(open('../.github/workflows/probe.yml', encoding='utf-8')); print('yaml ok')" 2>/dev/null || ./.venv/Scripts/python.exe -m pip install pyyaml && ./.venv/Scripts/python.exe -c "import yaml; yaml.safe_load(open('../.github/workflows/probe.yml', encoding='utf-8')); print('yaml ok')"
```

Expected: `yaml ok`

- [ ] **Step 3: 커밋·푸시**

```bash
git add .github/workflows/probe.yml
git commit -m "ci(crawler): Phase 0 프로브 workflow_dispatch 워크플로"
git push
```

---

### Task 5: Actions 실행 검증 + 최종 결론

이 태스크도 **운영 실행**이다. `gh` CLI 로 워크플로를 돌리고 결과를 회수한다.

**Files:**
- Modify: `crawler/FINDINGS.md` (결론 섹션 완성)

**Interfaces:**
- Produces: FINDINGS.md 의 "GitHub Actions 실행 가능 여부" 결론 — 계획 2(크롤러)의 실행 위치 결정(Actions vs 내 PC 스케줄러) 입력값.

- [ ] **Step 1: 두 프리셋을 Actions 에서 실행**

```bash
gh workflow run "크롤링 프로브 (Phase 0)" -f mode=musinsa_ranking
gh workflow run "크롤링 프로브 (Phase 0)" -f mode=cm29_best
```

이어서 완료 대기 후 상태 확인:

```bash
gh run list --workflow="크롤링 프로브 (Phase 0)" --limit 2
```

Expected: 두 run 모두 `completed`. (conclusion 은 success 여야 하며, failure 면 Step 3 의 차단 판정으로)

- [ ] **Step 2: 아티팩트 내려받아 로컬 결과와 대조**

```bash
gh run download <run-id> --dir crawler/samples/actions_musinsa
gh run download <run-id-2> --dir crawler/samples/actions_cm29
```

index.json 의 status 가 로컬과 동일하게 200 인지, 본문에 실제 상품 데이터가 있는지 확인. (200 이어도 봇 차단 페이지가 올 수 있으므로 본문 확인 필수)

- [ ] **Step 3: FINDINGS.md 결론 기입**

- Actions 에서 정상 응답 → "크롤러는 GitHub Actions 매시간 스케줄로 실행" 확정 기록.
- 차단(403/429/캡차 페이지) → "크롤러는 내 PC 작업 스케줄러로 실행, 워크플로 파일은 수동 트리거용으로만 유지" 기록. **우회 시도는 하지 않는다.**

- [ ] **Step 4: 커밋 — Phase 0 완료**

```bash
git add crawler/FINDINGS.md
git commit -m "docs(crawler): Phase 0 완료 — Actions 실행 가능 여부 결론"
git push
```

---

## Self-Review 결과

- **스펙 커버리지**: 스펙 Phase 0 의 완료 기준(두 몰 랭킹·후기 응답 샘플 확보 + 차단 시 실행 위치 전환 결정)을 Task 3(로컬 샘플·FINDINGS)과 Task 5(Actions 검증·결론)가 충족. Phase 1~4 는 별도 계획으로 분리(스펙 구축 순서와 일치).
- **플레이스홀더**: Task 3 의 "<상품 페이지 URL>" 등은 탐색 결과에 의존하는 **런타임 입력값**으로, 획득 절차(Step 2 에서 식별)가 명시되어 있음. 코드 블록에는 미정 참조 없음.
- **타입 일관성**: `summarize_json`/`safe_name` 시그니처가 Task 1 정의와 Task 2 사용처에서 일치. `sample_filename(seq, url, kind)` 테스트·구현 일치. index.json 스키마가 Task 2 Produces 와 Task 3·5 사용처에서 일치.
