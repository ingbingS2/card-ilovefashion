# -*- coding: utf-8 -*-
"""post_ig 단위 테스트 — 실제 API 호출 없음 (전부 목/임시 파일)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import post_ig


def test_resolve_folder_name_vs_abspath(tmp_path):
    assert post_ig.resolve_folder("20260719 카시오시계", base_dir=str(tmp_path)) == str(
        tmp_path / "20260719 카시오시계"
    )
    abspath = str(tmp_path / "직접경로")
    assert post_ig.resolve_folder(abspath) == abspath


def test_collect_images_numeric_order(tmp_path):
    # 10.jpg 가 2.jpg 뒤에 와야 함 (문자열 정렬이면 틀림) + jpg/jpeg 대소문자 허용
    for name in ["2.jpg", "10.jpg", "1.JPG", "3.jpeg", "cover.png", "caption.txt"]:
        (tmp_path / name).write_bytes(b"x")
    got = [Path(p).name for p in post_ig.collect_images(str(tmp_path))]
    assert got == ["1.JPG", "2.jpg", "3.jpeg", "10.jpg"]


def test_load_caption_strips_bom(tmp_path):
    (tmp_path / "caption.txt").write_bytes("﻿여름 신상 5선\n#패션".encode("utf-8"))
    assert post_ig.load_caption(str(tmp_path)) == "여름 신상 5선\n#패션"


def test_load_caption_missing_returns_empty(tmp_path):
    assert post_ig.load_caption(str(tmp_path)) == ""


def test_captions_match_normalizes_newlines_and_space():
    assert post_ig.captions_match("가\r\n나\n", "가\n나")
    assert not post_ig.captions_match("한글 캡션", "?? ??")  # 깨진 캡션은 불일치


def test_api_sends_korean_caption_as_body_data(monkeypatch):
    """한글 캡션이 URL 이 아니라 요청 본문(data)으로 전달되는지 — CP949 깨짐 방지 핵심."""
    captured = {}

    class FakeResp:
        ok = True

        def json(self):
            return {"id": "123"}

    def fake_request(method, url, data=None, timeout=None):
        captured.update(method=method, url=url, data=data)
        return FakeResp()

    monkeypatch.setattr(post_ig.requests, "request", fake_request)
    out = post_ig.api("POST", "me/media", "tok", caption="한글 캡션", media_type="CAROUSEL")
    assert out == {"id": "123"}
    assert captured["data"]["caption"] == "한글 캡션"
    assert captured["data"]["access_token"] == "tok"
    assert "한글" not in captured["url"]


def test_api_raises_on_error(monkeypatch):
    class FakeResp:
        ok = False
        status_code = 400
        text = '{"error": "bad"}'

    monkeypatch.setattr(post_ig.requests, "request", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="400"):
        post_ig.api("GET", "me", "tok")


def test_host_image_rejects_non_url(monkeypatch, tmp_path):
    img = tmp_path / "1.jpg"
    img.write_bytes(b"x")

    class FakeResp:
        text = "Something went wrong"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(post_ig.requests, "post", lambda *a, **k: FakeResp())
    with pytest.raises(RuntimeError, match="litterbox"):
        post_ig.host_image(str(img))


def test_wait_ready_finished_and_error(monkeypatch):
    seq = iter(["IN_PROGRESS", "FINISHED"])
    monkeypatch.setattr(post_ig, "api", lambda *a, **k: {"status_code": next(seq)})
    monkeypatch.setattr(post_ig.time, "sleep", lambda s: None)
    post_ig.wait_ready("c1", "tok")  # 예외 없이 통과해야 함

    monkeypatch.setattr(post_ig, "api", lambda *a, **k: {"status_code": "ERROR"})
    with pytest.raises(RuntimeError, match="ERROR"):
        post_ig.wait_ready("c2", "tok")
