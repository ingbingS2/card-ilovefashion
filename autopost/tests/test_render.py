"""실제 Chromium 렌더 스모크 테스트 — Playwright가 없으면 건너뛴다(CI는 설치한다)."""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
pytest.importorskip("PIL")

from PIL import Image  # noqa: E402

from autopost import build, render  # noqa: E402


def test_render_three_cards(tmp_path):
    (tmp_path / "assets").mkdir()
    Image.new("RGB", (1500, 1800), "#8a7f74").save(tmp_path / "assets" / "p.jpg")
    Image.new("RGB", (800, 600), "#cccccc").save(tmp_path / "assets" / "z.jpg")
    cards = [
        {"kind": "cover", "img": "assets/p.jpg", "pos": "50% 20%", "kicker": "AUTUMN JACKET",
         "title": build.rich("아침저녁만 추운 날<br><em>가을 재킷</em> 다섯"), "sub": "후기로 두께를 확인했습니다"},
        {"kind": "item", "img": "assets/p.jpg", "pos": "50% 18%", "prod": "버던트 · <b>워크 자켓</b> 카키",
         "title": build.rich("안에 후드티를 입어도<br><em>남는 워크 자켓</em>"), "mall": "무신사",
         "normal": "86,500원", "sale": "34,600원", "off": "60%", "proof": "후기 56개 · ⭐ 4.9",
         "sp": "“생각보다 좀 큰 편이라서 안에 후드티를 입어도 됩니다” —&nbsp;실제&nbsp;후기"},
        {"kind": "cta", "img": "assets/z.jpg", "title": "재킷 하나만 잘 골라도<br><em>가을이 편해집니다</em>",
         "sub": "고민이 줄어듭니다"},
    ]
    shots = render.render(cards, tmp_path, tmp_path)
    assert [s["file"] for s in shots] == ["1.jpg", "2.jpg", "3.jpg"]
    for s in shots:
        assert Image.open(tmp_path / s["file"]).size == (1080, 1350)
    assert 0 < shots[1]["text_ratio"] <= 0.35
    assert shots[2]["text_ratio"] is None  # CTA는 오버레이 없음
    assert not (tmp_path / "_render.html").exists()
