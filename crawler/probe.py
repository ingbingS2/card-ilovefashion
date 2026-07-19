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
