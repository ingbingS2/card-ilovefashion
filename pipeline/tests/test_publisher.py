"""publisher 테스트 — post_ig 재사용 함수 전부 목, 실제 네트워크 없음."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import publisher


def _setup_folder(tmp_path, caption="원본 캡션"):
    folder = tmp_path / "20260722 랭킹픽"
    folder.mkdir()
    (folder / "1.jpg").write_bytes(b"x")
    (folder / "2.jpg").write_bytes(b"x")
    (folder / "caption.txt").write_text(caption, encoding="utf-8")
    return str(folder)


def _patch_happy_flow(monkeypatch, caption="원본 캡션", permalink="https://instagram.com/p/xyz",
                       fetched_caption=None):
    if fetched_caption is None:
        fetched_caption = caption

    monkeypatch.setattr(publisher.post_ig, "load_token", lambda *a, **k: "tok")
    monkeypatch.setattr(publisher.post_ig, "host_image", lambda p: f"http://x/{Path(p).name}")
    monkeypatch.setattr(publisher.post_ig, "wait_ready", lambda *a, **k: None)
    monkeypatch.setattr(publisher.time, "sleep", lambda s: None)

    def fake_api(method, endpoint, token, **kwargs):
        if endpoint == "me":
            return {"username": "u", "account_type": "PERSONAL"}
        if endpoint == "me/media" and kwargs.get("media_type") == "CAROUSEL":
            assert kwargs.get("caption") == caption
            return {"id": "carousel1"}
        if endpoint == "me/media" and "is_carousel_item" in kwargs:
            return {"id": "child"}
        if endpoint == "me/media_publish":
            return {"id": "post1"}
        if endpoint == "post1":
            return {"permalink": permalink, "caption": fetched_caption}
        raise AssertionError(f"unexpected call: {endpoint} {kwargs}")

    monkeypatch.setattr(publisher.post_ig, "api", fake_api)


def test_publish_happy_path_returns_permalink(monkeypatch, tmp_path):
    folder = _setup_folder(tmp_path)
    _patch_happy_flow(monkeypatch)

    permalink = publisher.publish(folder)
    assert permalink == "https://instagram.com/p/xyz"


def test_publish_rejects_out_of_range_image_count(tmp_path):
    folder = tmp_path / "only-one"
    folder.mkdir()
    (folder / "1.jpg").write_bytes(b"x")
    (folder / "caption.txt").write_text("c", encoding="utf-8")

    with pytest.raises(RuntimeError, match="2~10장"):
        publisher.publish(str(folder))


def test_publish_verification_exception_surfaces_post_id_not_generic_failure(monkeypatch, tmp_path):
    """media_publish 는 이미 성공했는데 확인(GET permalink+caption) 단계에서
    네트워크 오류 등이 나면, 사용자가 재시도해 중복 게시하지 않도록 '게시는
    완료되었으나 확인 단계에서 오류' + post_id 를 담은 메시지로 구분돼야 한다
    (post_ig.py main() 의 동일 케이스와 동작을 맞춤)."""
    folder = _setup_folder(tmp_path)

    monkeypatch.setattr(publisher.post_ig, "load_token", lambda *a, **k: "tok")
    monkeypatch.setattr(publisher.post_ig, "host_image", lambda p: f"http://x/{Path(p).name}")
    monkeypatch.setattr(publisher.post_ig, "wait_ready", lambda *a, **k: None)
    monkeypatch.setattr(publisher.time, "sleep", lambda s: None)

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

    monkeypatch.setattr(publisher.post_ig, "api", fake_api)

    with pytest.raises(RuntimeError) as exc_info:
        publisher.publish(folder)
    msg = str(exc_info.value)
    assert "post1" in msg
    assert "완료" in msg and "확인 단계" in msg
    assert "network blew up" in msg


def test_publish_caption_mismatch_still_raises_with_permalink(monkeypatch, tmp_path):
    folder = _setup_folder(tmp_path, caption="원본 캡션")
    _patch_happy_flow(monkeypatch, caption="원본 캡션", fetched_caption="?? ??")

    with pytest.raises(RuntimeError) as exc_info:
        publisher.publish(folder)
    msg = str(exc_info.value)
    assert "한글 깨짐" in msg
    assert "https://instagram.com/p/xyz" in msg


def test_publish_item_container_retries_then_succeeds(monkeypatch, tmp_path):
    """인수인계 문서 검증: 아이템 컨테이너 생성이 간헐적으로 실패해도 3회까지
    재시도해 결국 성공하면 게시가 이어져야 한다."""
    folder = _setup_folder(tmp_path)
    attempts = {"n": 0}

    monkeypatch.setattr(publisher.post_ig, "load_token", lambda *a, **k: "tok")
    monkeypatch.setattr(publisher.post_ig, "host_image", lambda p: f"http://x/{Path(p).name}")
    monkeypatch.setattr(publisher.post_ig, "wait_ready", lambda *a, **k: None)
    monkeypatch.setattr(publisher.time, "sleep", lambda s: None)

    def fake_api(method, endpoint, token, **kwargs):
        if endpoint == "me":
            return {"username": "u", "account_type": "PERSONAL"}
        if endpoint == "me/media" and "is_carousel_item" in kwargs:
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("일시적 오류 9004")
            return {"id": "child"}
        if endpoint == "me/media" and kwargs.get("media_type") == "CAROUSEL":
            return {"id": "carousel1"}
        if endpoint == "me/media_publish":
            return {"id": "post1"}
        if endpoint == "post1":
            return {"permalink": "https://instagram.com/p/xyz", "caption": "원본 캡션"}
        raise AssertionError(f"unexpected call: {endpoint} {kwargs}")

    monkeypatch.setattr(publisher.post_ig, "api", fake_api)

    permalink = publisher.publish(folder)
    assert permalink == "https://instagram.com/p/xyz"
    # 이미지 2장: 1번째는 실패+재시도 성공(2회 호출), 2번째는 바로 성공(1회 호출) = 총 3회
    assert attempts["n"] == 3
