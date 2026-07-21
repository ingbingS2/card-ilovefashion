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
