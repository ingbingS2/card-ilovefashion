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
    if not products:
        # 아래에서 keys[0] 을 쓰므로 빈 목록이면 IndexError 로 터진다.
        # 원인을 알 수 있는 메시지로 바꿔 잡 실패 사유가 그대로 보이게 한다.
        raise ValueError("선택된 상품이 없습니다 — 카드뉴스를 만들 수 없습니다")

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

    # 표지 카드 이미지: copy["cover"]["image_path"] 가 주어지면 그 이미지를 쓴다.
    # (KEYWORD-POLICY.md §4 디자인(표지 착용컷·다른 원본) — 표지는 2번(첫 상품) 카드와 같은 사진을 그대로
    #  재사용하지 않는다. 템플릿의 scale(1.45) 줌 크롭만으로는 전신 스튜디오컷을
    #  차별화하지 못하는 경우가 있어, 아예 다른 사진을 지정할 수 있게 한다.)
    cover_key = first_key
    if cover.get("image_path"):
        images["cover"] = _image_data_uri(cover["image_path"])
        meta["cover"] = _image_meta(cover["image_path"])
        cover_key = "cover"

    cards: list[dict] = [{
        "kind": "cover",
        "img": cover_key,
        "lab": "표지",
        # 표지 사진 폭은 상품 카드와 같은 330 — 300이면 표지만 사진이 작아 보여
        # 첫 장이 어색해진다 (2026-08-10 사용자 피드백).
        "pw": 330,
        "kicker": cover["kicker"],
        "title": cover["title"],
        "sub": cover["sub"],
    }]

    for i, (item, key, p) in enumerate(zip(copy["items"], keys, products)):
        # 이미지 출처 표기는 카피 엔진(Claude/폴백)이 뭐라 쓰든 상관없이 항상 상품의
        # 실제 판매처(mall)에서 직접 파생한다 — 두 경로 모두 항상 정확한 출처를 보장.
        mall = p.get("mall")
        cr = "이미지 출처 : 무신사" if mall == "musinsa" else "이미지 출처 : 29CM"
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
            "cr": cr,
            "sp": item.get("sp"),
        }
        if item.get("badge"):
            card["badge"] = item["badge"]
        cards.append(card)

    # CTA(마지막) 카드 이미지: copy["cta"]["image_path"] 가 주어지면 그 이미지를 쓴다.
    # (KEYWORD-POLICY.md — 마지막 카드는 항상 CARD/zzal 최신 짤 사용)
    cta_key = first_key
    if cta.get("image_path"):
        images["cta"] = _image_data_uri(cta["image_path"])
        meta["cta"] = _image_meta(cta["image_path"])
        cta_key = "cta"

    cards.append({
        "kind": "cta",
        "img": cta_key,
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
        # U+2028/U+2029 는 JSON 은 허용하나 JS 문자열 리터럴에선 불법이므로,
        # 리터럴 6글자 유니코드 이스케이프 시퀀스로 치환한다 (raw string 필수 --
        # 일반 문자열이면 파이썬이 실제 U+2028 문자로 해석해 사실상 no-op이 됨).
        payload = payload.replace(chr(0x2028), r"\u2028").replace(chr(0x2029), r"\u2029")
        # 닫는 태그(스킴 무관 </xxx>)는 전부 이스케이프한다 (대소문자 혼합
        # </ScRiPt> 등 HTML 파서의 조기 스크립트 종료를 모두 막기 위함). JS
        # 문자열 리터럴 안에서 이스케이프된 슬래시는 그냥 슬래시로 해석되므로,
        # 실행 시점엔 원래 문자(예: 닫는 em 태그)가 그대로 화면에 나타난다.
        payload = payload.replace("</", r"<\/")
        return f"{var} {payload};"

    template, n_images = re.subn(r"var IMAGES = \{.*?\};",
                                  lambda m: _js("var IMAGES =", images), template, count=1, flags=re.S)
    template, n_meta = re.subn(r"var META   = \{.*?\};",
                                lambda m: _js("var META   =", meta), template, count=1, flags=re.S)
    template, n_cards = re.subn(r"var CARDS  = \[.*?\];",
                                 lambda m: _js("var CARDS  =", cards), template, count=1, flags=re.S)

    if n_images != 1 or n_meta != 1 or n_cards != 1:
        raise RuntimeError("템플릿 앵커(IMAGES/META/CARDS)를 찾지 못했습니다")

    return template


def _crop_to_1080x1350(path: str) -> None:
    """스크린샷을 1080x1350 으로 중앙 크롭 보정한다.

    실패하면 예외를 던진다 — 예전에는 경고만 찍고 통과시켰는데, 그러면 규격 미달
    이미지가 그대로 게시까지 흘러간다(인스타 게시는 되돌릴 수 없다). 여기서 실패하면
    잡이 "실패"로 끝나고 사용자가 다시 돌리면 되므로, 조용히 넘기는 쪽이 더 위험하다.
    """
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
        raise RuntimeError(f"크롭 보정 실패({path}): {e}") from e

    # 저장된 결과가 실제로 규격을 만족하는지 확인한다 (Pillow 버전/모드 차이로
    # 위 계산이 어긋나도 규격 미달본이 게시로 넘어가지 않게 하는 마지막 방어선).
    with Image.open(path) as saved:
        if saved.size != (1080, 1350):
            raise RuntimeError(f"크롭 후 크기가 1080x1350 이 아닙니다({path}): {saved.size}")


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

    # 렌더용 임시 HTML 은 결과 폴더에 남기지 않는다 (사용자가 여는 폴더이므로).
    try:
        os.remove(html_path)
    except OSError:
        pass
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
