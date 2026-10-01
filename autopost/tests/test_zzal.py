from __future__ import annotations

import io
import json

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from autopost import config, zzal  # noqa: E402


class FakeRaw(io.BytesIO):
    def read(self, n=-1, decode_content=False):  # urllib3 raw.read 시그니처
        return super().read(n)


class FakeResp:
    def __init__(self, data: bytes, text: str = ""):
        self.raw = FakeRaw(data)
        self.text = text

    def raise_for_status(self):
        pass


def _jpg(w: int, h: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "#888").save(buf, "JPEG")
    return buf.getvalue()


def test_fetch_validates(monkeypatch, tmp_path):
    monkeypatch.setattr(zzal, "CAND_DIR", tmp_path / "cand")
    monkeypatch.setattr(zzal.requests, "get", lambda *a, **k: FakeResp(_jpg(600, 360)))
    ok = zzal.fetch("https://example.com/a.webp")
    assert ok["ok"] and ok["size"] == "600x360"
    monkeypatch.setattr(zzal.requests, "get", lambda *a, **k: FakeResp(_jpg(200, 120)))
    assert "작음" in zzal.fetch("https://example.com/b.jpg")["reason"]
    monkeypatch.setattr(zzal.requests, "get", lambda *a, **k: FakeResp(b"<html>not image</html>"))
    assert zzal.fetch("https://example.com/c.jpg")["reason"] == "이미지가 아님"
    assert not zzal.fetch("file:///etc/passwd")["ok"]
    assert not zzal.fetch("http://127.0.0.1/x.jpg")["ok"]


def test_page_images_filters_icons(monkeypatch):
    html = ('<img src="/img/logo.png"><img data-src="/files/a.webp"><img src="https://x.com/files/b.jpg?w=1">'
            '<img src="/files/a.webp">')
    monkeypatch.setattr(zzal.requests, "get", lambda *a, **k: FakeResp(b"", html))
    assert zzal.page_images("https://site.com/post") == ["https://site.com/files/a.webp", "https://x.com/files/b.jpg?w=1"]


def test_adopt_copies_and_indexes(monkeypatch, tmp_path):
    cand = tmp_path / "cand"
    cand.mkdir()
    (cand / "cand-1.jpg").write_bytes(_jpg(600, 360))
    zdir = tmp_path / "zzal"
    zdir.mkdir()
    (zdir / "index.json").write_text('{"zzal": []}', encoding="utf-8")
    monkeypatch.setattr(zzal, "CAND_DIR", cand)
    monkeypatch.setattr(config, "ZZAL_DIR", zdir)
    monkeypatch.setattr(config, "ZZAL_INDEX", zdir / "index.json")
    e = zzal.adopt(str(cand / "cand-1.jpg"), "https://src", "자막", "장면", "무드", "주제")
    assert (zdir / e["file"]).is_file() and e["file"].startswith("web-")
    assert json.loads((zdir / "index.json").read_text(encoding="utf-8"))["zzal"][0]["source"] == "https://src"
    with pytest.raises(SystemExit):
        zzal.adopt(str(zdir / e["file"]), "s", "c", "s", "m", "f")  # 후보 폴더 밖 파일 금지
