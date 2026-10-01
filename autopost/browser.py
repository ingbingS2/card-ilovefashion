"""브라우저 경유 몰 조회 — `requests`가 Cloudflare 403을 받을 때 Playwright 페이지 안에서 fetch 한다.

KEYWORD-POLICY §6·crawler/FINDINGS.md가 안내하는 방식(실제 브라우저로 www.musinsa.com 상품 페이지를 열고
그 페이지 안에서 API를 fetch)을 코드로 옮긴 것. 브라우저는 프로세스당 하나만 띄워 재사용한다.
우회(IP 변경·캡차 풀기)는 하지 않는다 — 브라우저로도 막히면 그대로 실패를 돌려준다.
"""
from __future__ import annotations

import atexit
import json
import os
import time
from urllib.parse import urlparse

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
# API 호스트 → 그 API를 fetch 할 수 있는 "집" 페이지(같은 사이트 오리진·쿠키)
HOME_PAGES = {
    "musinsa.com": "https://www.musinsa.com/products/{hint}",
    "msscdn.net": "https://www.musinsa.com/products/{hint}",
    "29cm.co.kr": "https://product.29cm.co.kr/catalog/{hint}",
}
DEFAULT_HINT = {"musinsa.com": "5336051", "29cm.co.kr": "3730955"}


class BrowserUnavailable(RuntimeError):
    pass


class _Session:
    def __init__(self):
        self._pw = None
        self._browser = None
        self._pages: dict[str, object] = {}
        self._failed: dict[str, str] = {}   # 한 번 못 연 호스트는 이유를 기억하고 바로 포기(호출마다 브라우저 재시도 방지)

    def _ensure(self):
        if self._browser:
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise BrowserUnavailable("playwright 미설치") from e
        self._pw = sync_playwright().start()
        launch = {"headless": True, "args": ["--disable-blink-features=AutomationControlled"]}
        chrome = os.environ.get("CHROME_PATH")
        if chrome and os.path.exists(chrome):
            launch["executable_path"] = chrome
        self._browser = self._pw.chromium.launch(**launch)
        atexit.register(self.close)

    def page_for(self, host_key: str, hint: str | None = None):
        if host_key in self._failed:
            raise BrowserUnavailable(self._failed[host_key])
        try:
            self._ensure()
        except Exception as e:  # 설치 안 됨·실행 파일 없음 등
            self._failed[host_key] = f"브라우저 실행 실패: {str(e)[:120]}"
            raise BrowserUnavailable(self._failed[host_key]) from None
        if host_key not in self._pages:
            url = HOME_PAGES[host_key].format(hint=hint or DEFAULT_HINT.get(host_key, ""))
            try:
                ctx = self._browser.new_context(user_agent=UA, locale="ko-KR", viewport={"width": 1280, "height": 900})
                page = ctx.new_page()
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                time.sleep(3)  # 사이트 스크립트가 쿠키를 심을 시간
                html = page.content()
            except Exception as e:  # 프록시 차단(ERR_TUNNEL)·타임아웃 등 — 이 호스트는 더 시도하지 않는다
                self._failed[host_key] = f"{host_key}: 페이지 열기 실패 {type(e).__name__}: {str(e)[:100]}"
                raise BrowserUnavailable(self._failed[host_key]) from None
            if "Attention Required" in html or "Just a moment" in html:
                ctx.close()
                self._failed[host_key] = f"{host_key}: 브라우저로도 Cloudflare에 막힘 — 더 시도하지 않음"
                raise BrowserUnavailable(self._failed[host_key])
            self._pages[host_key] = page
        return self._pages[host_key]

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._browser = self._pw = None
        self._pages = {}


_session = _Session()


def host_key(url: str) -> str | None:
    host = urlparse(url).netloc
    for key in HOME_PAGES:
        if host == key or host.endswith("." + key):
            return key
    return None


def fetch_json(url: str, headers: dict | None = None, hint: str | None = None) -> dict:
    """페이지 안에서 fetch(url) → JSON. 상태가 2xx가 아니면 RuntimeError(상태 코드 포함)."""
    key = host_key(url)
    if not key:
        raise BrowserUnavailable(f"브라우저 경유 대상이 아님: {url}")
    page = _session.page_for(key, hint)
    try:
        result = page.evaluate(
            """async ([u, h]) => {
                const r = await fetch(u, {credentials: 'include', headers: h || {}});
                const t = await r.text();
                return {status: r.status, text: t};
            }""", [url, {k: v for k, v in (headers or {}).items() if k.lower() in ("accept", "accept-language")}])
    except Exception as e:  # 페이지 안 fetch 실패(네트워크·CORS) — 호출자는 MallError로 바꾼다
        raise RuntimeError(f"페이지 안 fetch 실패 {type(e).__name__}: {str(e)[:120]}") from None
    if not 200 <= int(result["status"]) < 300:
        raise RuntimeError(f"HTTP {result['status']}: {result['text'][:120]}")
    try:
        return json.loads(result["text"])
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON 아님: {result['text'][:120]}") from e


def fetch_bytes(url: str, hint: str | None = None) -> bytes:
    """이미지 등 바이너리 — 페이지 안에서 fetch 후 base64로 받는다."""
    import base64
    key = host_key(url)
    if not key:
        raise BrowserUnavailable(f"브라우저 경유 대상이 아님: {url}")
    page = _session.page_for(key, hint)
    b64 = page.evaluate(
        """async u => {
            const r = await fetch(u, {credentials: 'include'});
            if (!r.ok) throw new Error('HTTP ' + r.status);
            const buf = await r.arrayBuffer();
            let s = ''; const bytes = new Uint8Array(buf);
            for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
            return btoa(s);
        }""", url)
    return base64.b64decode(b64)


def close() -> None:
    _session.close()
