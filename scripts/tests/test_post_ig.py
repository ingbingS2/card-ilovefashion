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
    # 1..10 연속이어야 검증(피처 4)을 통과하므로 4~9번도 채운다.
    names = ["2.jpg", "10.jpg", "1.JPG", "3.jpeg", "cover.png", "caption.txt"]
    names += [f"{n}.jpg" for n in range(4, 10)]
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    got = [Path(p).name for p in post_ig.collect_images(str(tmp_path))]
    assert got[:3] == ["1.JPG", "2.jpg", "3.jpeg"]
    assert got[-1] == "10.jpg"
    assert len(got) == 10


def test_collect_images_rejects_gap(tmp_path):
    """2.jpg 가 없으면(1,3만 존재) 게시 없이 즉시 종료해야 한다."""
    for name in ["1.jpg", "3.jpg"]:
        (tmp_path / name).write_bytes(b"x")
    with pytest.raises(SystemExit):
        post_ig.collect_images(str(tmp_path))


def test_collect_images_rejects_duplicate(tmp_path):
    """1.jpg 와 1.jpeg 가 같이 있으면(중복 번호) 즉시 종료해야 한다."""
    for name in ["1.jpg", "1.jpeg", "2.jpg"]:
        (tmp_path / name).write_bytes(b"x")
    with pytest.raises(SystemExit):
        post_ig.collect_images(str(tmp_path))


def test_collect_images_happy_path_contiguous(tmp_path):
    for name in ["1.jpg", "2.jpeg", "3.JPG"]:
        (tmp_path / name).write_bytes(b"x")
    got = [Path(p).name for p in post_ig.collect_images(str(tmp_path))]
    assert got == ["1.jpg", "2.jpeg", "3.JPG"]


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

    def fake_request(method, url, params=None, data=None, timeout=None):
        captured.update(method=method, url=url, params=params, data=data)
        return FakeResp()

    monkeypatch.setattr(post_ig.requests, "request", fake_request)
    out = post_ig.api("POST", "me/media", "tok", caption="한글 캡션", media_type="CAROUSEL")
    assert out == {"id": "123"}
    assert captured["data"]["caption"] == "한글 캡션"
    assert captured["data"]["access_token"] == "tok"
    assert "한글" not in captured["url"]


def test_api_get_uses_query_params_not_body(monkeypatch):
    """GET 은 params 로 전달되어야 한다 (Graph API GET 은 쿼리스트링 필요)."""
    captured = {}

    class FakeResp:
        ok = True

        def json(self):
            return {"username": "me"}

    def fake_request(method, url, params=None, data=None, timeout=None):
        captured.update(method=method, url=url, params=params, data=data)
        return FakeResp()

    monkeypatch.setattr(post_ig.requests, "request", fake_request)
    out = post_ig.api("GET", "me", "tok", fields="username")
    assert out == {"username": "me"}
    assert captured["method"] == "GET"
    assert captured["params"]["fields"] == "username"
    assert captured["params"]["access_token"] == "tok"
    assert captured["data"] is None


def test_api_post_uses_body_data_not_query_params(monkeypatch):
    """POST 는 data(본문)로 전달되고 params 는 사용하지 않아야 한다."""
    captured = {}

    class FakeResp:
        ok = True

        def json(self):
            return {"id": "1"}

    def fake_request(method, url, params=None, data=None, timeout=None):
        captured.update(method=method, url=url, params=params, data=data)
        return FakeResp()

    monkeypatch.setattr(post_ig.requests, "request", fake_request)
    out = post_ig.api("POST", "me/media_publish", "tok", creation_id="c1")
    assert out == {"id": "1"}
    assert captured["method"] == "POST"
    assert captured["data"]["creation_id"] == "c1"
    assert captured["params"] is None


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


def _setup_main_folder(tmp_path, caption="캡션"):
    (tmp_path / "1.jpg").write_bytes(b"x")
    (tmp_path / "2.jpg").write_bytes(b"x")
    (tmp_path / "caption.txt").write_text(caption, encoding="utf-8")
    return str(tmp_path)


def test_main_verification_exception_does_not_hide_successful_publish(monkeypatch, tmp_path):
    """게시(media_publish)는 성공했는데 확인(GET) 단계에서 예외가 나면
    트레이스백이 아니라 '게시는 완료됐다'는 한글 안내와 post_id 로 종료돼야 한다."""
    folder = _setup_main_folder(tmp_path)
    monkeypatch.setattr(sys, "argv", ["post_ig.py", folder])
    monkeypatch.setattr(post_ig, "load_token", lambda *a, **k: "tok")
    monkeypatch.setattr(post_ig, "host_image", lambda p: f"http://x/{Path(p).name}")
    monkeypatch.setattr(post_ig, "wait_ready", lambda *a, **k: None)

    def fake_api(method, endpoint, token, **kwargs):
        if endpoint == "me":
            return {"username": "u", "account_type": "PERSONAL"}
        if endpoint == "me/media" and kwargs.get("media_type") == "CAROUSEL":
            return {"id": "carousel1"}
        if endpoint == "me/media" and "is_carousel_item" in kwargs:
            return {"id": "child"}
        if endpoint == "me/media_publish":
            return {"id": "post1"}
        if endpoint == "post1":  # 확인(GET) 단계 — 여기서 터진다
            raise RuntimeError("network blew up")
        raise AssertionError(f"unexpected call: {endpoint} {kwargs}")

    monkeypatch.setattr(post_ig, "api", fake_api)

    with pytest.raises(SystemExit) as exc_info:
        post_ig.main()
    msg = str(exc_info.value)
    assert "post1" in msg
    assert "게시" in msg and "완료" in msg
    assert "network blew up" in msg


def test_main_caption_mismatch_still_reports_permalink_distinctly(monkeypatch, tmp_path):
    """캡션 불일치는 확인 단계 예외와 별개의, 기존 문구 그대로의 실패로 남아야 한다."""
    folder = _setup_main_folder(tmp_path, caption="원본 캡션")
    monkeypatch.setattr(sys, "argv", ["post_ig.py", folder])
    monkeypatch.setattr(post_ig, "load_token", lambda *a, **k: "tok")
    monkeypatch.setattr(post_ig, "host_image", lambda p: f"http://x/{Path(p).name}")
    monkeypatch.setattr(post_ig, "wait_ready", lambda *a, **k: None)

    def fake_api(method, endpoint, token, **kwargs):
        if endpoint == "me":
            return {"username": "u", "account_type": "PERSONAL"}
        if endpoint == "me/media" and kwargs.get("media_type") == "CAROUSEL":
            return {"id": "carousel1"}
        if endpoint == "me/media" and "is_carousel_item" in kwargs:
            return {"id": "child"}
        if endpoint == "me/media_publish":
            return {"id": "post1"}
        if endpoint == "post1":
            return {"permalink": "https://instagram.com/p/x", "caption": "?? ??"}
        raise AssertionError(f"unexpected call: {endpoint} {kwargs}")

    monkeypatch.setattr(post_ig, "api", fake_api)

    with pytest.raises(SystemExit) as exc_info:
        post_ig.main()
    msg = str(exc_info.value)
    assert "한글 깨짐" in msg
    assert "https://instagram.com/p/x" in msg
    assert "확인 단계에서 오류" not in msg  # 새 except 블록에 흡수되면 안 됨
