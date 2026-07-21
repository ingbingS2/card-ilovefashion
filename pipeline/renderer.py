"""C안 카드뉴스 렌더러: 템플릿 HTML 빌드 + Playwright 스크린샷."""
from __future__ import annotations

import base64
import json
import os
import re
from pathlib import Path

from PIL import Image

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "card-drafts" / "uvparasol-insta.html"

# 1x1 회색(#f4f3f1) PNG 폴백 — image_path 없을 때 사용.
FALLBACK_PNG = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP48vkjAAW3Atlbb6eXAAAAAElFTkSuQmCC"
)

_MIME_BY_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _image_data_uri(image_path: str | None) -> str:
    if not image_path or not os.path.isfile(image_path):
        return FALLBACK_PNG
    ext = Path(image_path).suffix.lower()
    mime = _MIME_BY_EXT.get(ext, "image/jpeg")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _image_meta(image_path: str | None) -> dict:
    if not image_path or not os.path.isfile(image_path):
        return {"w": 1, "h": 1, "bg": "#f4f3f1"}
    with Image.open(image_path) as img:
        w, h = img.size
        rgb = img.convert("RGB")
        px = (3, 3) if w >= 4 and h >= 4 else (0, 0)
        r, g, b = rgb.getpixel(px)
        return {"w": w, "h": h, "bg": "#%02x%02x%02x" % (r, g, b)}


def build_html(copy: dict, products: list[dict]) -> str:
    """템플릿의 IMAGES/META/CARDS 블록을 copy·products 데이터로 교체한다."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    keys = [f"p{i}" for i in range(len(products))]
    images: dict = {}
    meta: dict = {}
    for key, p in zip(keys, products):
        image_path = p.get("image_path")
        images[key] = _image_data_uri(image_path)
        meta[key] = _image_meta(image_path)

    first_key = keys[0]

    cover = copy["cover"]
    cta = copy["cta"]

    cards: list[dict] = [{
        "kind": "cover",
        "img": first_key,
        "lab": "표지",
        "pw": 300,
        "kicker": cover["kicker"],
        "title": cover["title"],
        "sub": cover["sub"],
    }]

    for i, (item, key, p) in enumerate(zip(copy["items"], keys, products)):
        card = {
            "kind": "item",
            "img": key,
            "lab": p.get("brand") or "",
            "pw": 330,
            "num": f"{i + 1:02d}",
            "prod": item.get("prod"),
            "title": item.get("title"),
            "meta_": item.get("meta"),
            "proof": item.get("proof"),
            "cr": item.get("cr"),
            "sp": item.get("sp"),
        }
        if item.get("badge"):
            card["badge"] = item["badge"]
        cards.append(card)

    cards.append({
        "kind": "cta",
        "img": first_key,
        "lab": "CTA",
        "pw": 300,
        "title": cta["title"],
        "sub": cta["sub"],
    })

    # 치환은 반드시 함수형으로 한다. re.sub 의 치환 "문자열" 은 백슬래시를
    # 해석하므로(예: json 의 \n → 실제 개행, \" → ", \u → 오류) 데이터가 깨진다.
    # 람다 치환은 백슬래시를 그대로 두므로 json 출력이 안전하게 삽입된다.
    def _js(var: str, value) -> str:
        payload = json.dumps(value, ensure_ascii=False)
        # U+2028/U+2029 는 JSON 은 허용하나 JS 문자열 리터럴에선 불법 (이스케이프)
        payload = payload.replace(chr(0x2028), "\u2028").replace(chr(0x2029), "\u2029")
        # script 종료 태그만 조기 종료를 유발 → 그것만 무력화 (다른 태그는 보존)
        payload = payload.replace("</script", r"<\/script").replace("</SCRIPT", r"<\/SCRIPT")
        return f"{var} {payload};"

    template = re.sub(r"var IMAGES = \{.*?\};",
                      lambda m: _js("var IMAGES =", images), template, count=1, flags=re.S)
    template = re.sub(r"var META   = \{.*?\};",
                      lambda m: _js("var META   =", meta), template, count=1, flags=re.S)
    template = re.sub(r"var CARDS  = \[.*?\];",
                      lambda m: _js("var CARDS  =", cards), template, count=1, flags=re.S)

    return template


def _crop_to_1080x1350(path: str) -> None:
    """스크린샷을 1080x1350 으로 중앙 크롭 보정한다. 손상된 파일은 조용히 건너뛴다."""
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            target_w, target_h = 1080, 1350
            scale = max(target_w / w, target_h / h)
            new_w, new_h = max(target_w, round(w * scale)), max(target_h, round(h * scale))
            img = img.resize((new_w, new_h))
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            img = img.crop((left, top, left + target_w, top + target_h))
            img.save(path, "JPEG", quality=92)
    except Exception as e:
        print(f"경고: 크롭 보정 실패({path}): {e} — 원본 크기 유지")


def render(copy: dict, products: list[dict], out_dir: str) -> list[str]:
    """copy·products 로 카드뉴스를 렌더링해 out_dir/1.jpg..N.jpg 로 저장하고 절대경로 리스트를 반환한다."""
    os.makedirs(out_dir, exist_ok=True)

    html = build_html(copy, products)  # copy["cover"]/["cta"] 접근 → KeyError 는 여기서 전파

    html_path = os.path.join(out_dir, "_render.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    n_cards = len(products) + 2  # cover + items + cta
    shots = _screenshot_cards(html_path, n_cards, out_dir)
    assert len(shots) == n_cards, f"렌더 카드 수 불일치: {len(shots)}/{n_cards}"

    out = []
    for shot in shots:
        _crop_to_1080x1350(shot)
        out.append(os.path.abspath(shot))
    return out


def _screenshot_cards(html: str, n_cards: int, out_dir: str) -> list[str]:
    """Playwright(chromium) 로 카드별 스크린샷을 out_dir/{k+1}.jpg 로 저장한다."""
    from playwright.sync_api import sync_playwright

    url = Path(html).resolve().as_uri()
    paths: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1400, "height": 1000}, device_scale_factor=2)
            page.goto(url)
            page.wait_for_timeout(3000)
            page.add_style_tag(content=(
                ".board{display:block !important}"
                ".col{max-width:none !important;width:540px;margin:0 auto 80px}"
                ".slot{height:auto !important}"
                ".card{transform:none !important}"
            ))
            for k in range(n_cards):
                locator = page.locator(f"#card{k}")
                locator.scroll_into_view_if_needed()
                page.wait_for_timeout(150)
                dest = os.path.join(out_dir, f"{k + 1}.jpg")
                locator.screenshot(type="jpeg", quality=92, path=dest)
                paths.append(dest)
        finally:
            browser.close()

    return paths
