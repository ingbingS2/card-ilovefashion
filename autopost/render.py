"""카드 렌더 — Playwright(Chromium)로 템플릿을 열고 카드마다 1080×1350 JPG를 찍는다.

텍스트 블록 높이(.over)를 같이 재서 돌려준다 — 카드 높이의 35% 이하인지 build가 검사한다(§4).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import config


def render(cards: list[dict], base_dir: Path, out_dir: Path) -> list[dict]:
    """cards의 img는 base_dir 기준 상대경로. 반환: [{index, file, text_ratio}]."""
    from playwright.sync_api import sync_playwright

    html = config.TEMPLATE_HTML.read_text(encoding="utf-8")
    # 이미지 상대경로가 풀리도록 회차 폴더에 임시 페이지를 둔다
    page_file = base_dir / "_render.html"
    page_file.write_text(html, encoding="utf-8")
    results = []
    try:
        with sync_playwright() as pw:
            launch = {"headless": True}
            env_chrome = os.environ.get("CHROME_PATH")
            chrome = env_chrome if env_chrome and os.path.exists(env_chrome) else next(
                (p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                             r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")
                 if os.path.exists(p)), None)  # 없으면 Playwright 번들 Chromium(클라우드)
            if chrome:
                launch["executable_path"] = chrome
            browser = pw.chromium.launch(**launch)
            page = browser.new_page(viewport={"width": 600, "height": 900}, device_scale_factor=2)
            page.add_init_script(f"window.CARDS = {json.dumps(cards, ensure_ascii=False)};")
            page.goto(page_file.as_uri())
            page.wait_for_load_state("networkidle")
            page.evaluate("document.fonts.ready")
            page.wait_for_function(
                "Array.from(document.images).every(i => i.complete && i.naturalWidth > 0)",
                timeout=30000)
            # check()는 '불러올 글꼴이 없음'에도 true라 쓸모없다 — Pretendard가 실제로 loaded인지 본다
            font_ok = page.evaluate("[...document.fonts].some(f => f.family.replace(/\"/g, '').startsWith('Pretendard')"
                                    " && f.status === 'loaded')")
            for i in range(len(cards)):
                el = page.locator(f"#card{i}")
                out = out_dir / f"{i + 1}.jpg"
                el.screenshot(path=str(out), type="jpeg", quality=95)
                ratio = page.evaluate(
                    "(i) => { const o = document.querySelector(`#card${i} .over`);"
                    " return o ? o.getBoundingClientRect().height / 675 : null; }", i)
                results.append({"index": i + 1, "file": out.name, "text_ratio": ratio,
                                "font_ok": font_ok})
            browser.close()
    finally:
        page_file.unlink(missing_ok=True)
    return results
