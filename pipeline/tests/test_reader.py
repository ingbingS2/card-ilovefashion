"""reader 테스트 — 전부 목, 네트워크 없음."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import reader


def item(pid="1", mall="musinsa"):
    return {"mall": mall, "product_id": pid, "rank": 1, "brand": "b", "name": "n",
            "price": 1000, "original_price": None, "discount_rate": 10,
            "review_score": 4.8, "review_count": 5,
            "thumbnail": "https://img.example/x.jpg", "product_url": "https://u",
            "category_code": None, "category_name": None}


def test_decode_fs_value_roundtrip():
    fs = {"mapValue": {"fields": {"score": {"integerValue": "5"},
                                  "text": {"stringValue": "굿"}}}}
    assert reader.fv(fs) == {"score": 5, "text": "굿"}


def test_load_products_merges_reviews_and_downloads(monkeypatch, tmp_path):
    img_data = b"IMG" * 400  # 1200 bytes, exceeds 1000-byte minimum
    def fake_get(url, **kw):
        class R:
            ok = True
            status_code = 200
            content = img_data
            def json(self):
                return {"fields": {"reviews": {"arrayValue": {"values": [
                    {"mapValue": {"fields": {"score": {"integerValue": "5"},
                                             "text": {"stringValue": "아주 좋아요"},
                                             "date": {"nullValue": None},
                                             "likes": {"integerValue": "2"}}}}]}}}}
        return R()

    monkeypatch.setattr(reader.requests, "get", fake_get)
    out = reader.load_products([item()], assets_dir=str(tmp_path))
    p = out[0]
    assert p["reviews"][0]["text"] == "아주 좋아요"
    assert p["image_path"] and Path(p["image_path"]).read_bytes() == img_data


def test_load_products_survives_missing_doc(monkeypatch, tmp_path):
    def fake_get(url, **kw):
        class R:
            ok = False
            status_code = 404
            content = b""
            def json(self):
                return {}
        return R()

    monkeypatch.setattr(reader.requests, "get", fake_get)
    out = reader.load_products([item()], assets_dir=str(tmp_path))
    assert out[0]["reviews"] == [] and out[0]["image_path"] is None


def test_fetch_reviews_survives_timeout(monkeypatch, tmp_path):
    import requests
    def fake_get(url, **kw):
        raise requests.exceptions.Timeout("connection timeout")

    monkeypatch.setattr(reader.requests, "get", fake_get)
    out = reader.load_products([item()], assets_dir=str(tmp_path))
    # reviews should be empty (exception handled), image_path should be None (no thumbnail)
    assert out[0]["reviews"] == [] and out[0]["image_path"] is None


def test_download_image_rejects_tiny_body(monkeypatch, tmp_path):
    def fake_get(url, **kw):
        class R:
            ok = True
            status_code = 200
            content = b"tiny"  # only 4 bytes, less than 1000-byte minimum
            def json(self):
                return {"fields": {"reviews": {"arrayValue": {"values": []}}}}
        return R()

    monkeypatch.setattr(reader.requests, "get", fake_get)
    out = reader.load_products([item()], assets_dir=str(tmp_path))
    # image_path should be None due to tiny body, even though HTTP 200
    assert out[0]["image_path"] is None
