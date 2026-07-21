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
    assert r"커버<em>강조<\/em>" in html  # </ 는 전부 이스케이프되어 나온다
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


def test_build_html_escapes_special_chars_for_js():
    """후기 텍스트에 개행·따옴표·백슬래시가 있어도 JS 가 깨지지 않아야 한다.
    (re.sub 치환 문자열이 백슬래시를 해석하던 버그 회귀 방지)"""
    c = copy2()
    c["items"][0]["sp"] = '"인용"\n둘째 줄\t탭\백슬래시 </script>'
    html = renderer.build_html(c, prods())
    import re
    block = re.search(r"var CARDS  = (\[.*?\]);", html, re.S).group(1)
    # 삽입된 CARDS 블록에 날것 개행/조기 스크립트 종료가 없어야 함
    assert "\n둘째 줄" not in block  # 개행이 이스케이프됨
    assert "</script>" not in block   # <\/script> 로 이스케이프됨
    import json as _json
    # 블록이 유효한 JSON 으로 다시 파싱되어야 함 (JS 로도 유효)
    _json.loads(block.replace("<\/", "</"))


def test_build_html_raises_when_template_anchor_missing(monkeypatch, tmp_path):
    """템플릿에서 IMAGES/META/CARDS 앵커 중 하나라도 찾지 못하면 조용히 데모 데이터로
    렌더링하지 말고 즉시 실패해야 한다 (템플릿 리팩터 등으로 앵커 문자열이 바뀌는
    드리프트를 렌더 단계에서 바로 잡아내기 위함)."""
    import pytest

    broken_template = (
        "<html><body><script>\n"
        "var IMAGES = {};\n"
        "var META   = {};\n"
        "</script></body></html>\n"
    )
    fake_path = tmp_path / "broken.html"
    fake_path.write_text(broken_template, encoding="utf-8")
    monkeypatch.setattr(renderer, "TEMPLATE_PATH", fake_path)

    with pytest.raises(RuntimeError, match="템플릿 앵커"):
        renderer.build_html(copy2(), prods())


def test_build_html_cr_derived_from_product_mall_not_copy_engine():
    """이미지 출처(cr)는 카피 엔진(Claude/폴백)이 뭐라고 주든 무시하고 항상
    상품의 실제 mall 에서 파생돼야 한다 (폴백/Claude 경로 모두 정확한 출처 보장)."""
    c = copy2()
    c["items"][0]["cr"] = "이 값은 무시되어야 함"
    p = prods()
    p[0]["mall"] = "cm29"

    html = renderer.build_html(c, p)
    import json, re
    cards = json.loads(re.search(r"var CARDS  = (\[.*?\]);", html, re.S).group(1))
    assert cards[1]["cr"] == "이미지 출처 : 29CM"

    p2 = prods()
    p2[0]["mall"] = "musinsa"
    html2 = renderer.build_html(copy2(), p2)
    cards2 = json.loads(re.search(r"var CARDS  = (\[.*?\]);", html2, re.S).group(1))
    assert cards2[1]["cr"] == "이미지 출처 : 무신사"
