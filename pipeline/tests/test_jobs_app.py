"""app.py 통합 테스트 — 파이프라인 단계 전부 목, 실제 네트워크/렌더/게시 없음."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import app as app_module
import jobs

client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """잡 저장소를 매 테스트마다 비우고, 실제 브라우저가 뜨지 않도록 막는다."""
    jobs.JOBS.clear()
    monkeypatch.setattr(app_module.webbrowser, "open", lambda *a, **k: None)


def _make_ready_job(tmp_path, caption="캡션 내용"):
    job = jobs.create_job()
    folder = str(tmp_path / "20260722 랭킹픽")
    Path(folder).mkdir(parents=True, exist_ok=True)
    images = []
    for i in range(1, 3):
        p = Path(folder) / f"{i}.jpg"
        p.write_bytes(b"JPG")
        images.append(str(p))
    (Path(folder) / "caption.txt").write_text(caption, encoding="utf-8")
    jobs.set_status(job, "미리보기 대기", folder=folder, images=images)
    return job


def test_cors_preflight_allows_frontend_origin():
    resp = client.options(
        "/api/selections",
        headers={
            "Origin": "https://fashion-cardnews.web.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert resp.status_code in (200, 204)
    assert resp.headers["access-control-allow-origin"] == "https://fashion-cardnews.web.app"


def test_selections_pipeline_reaches_preview_ready(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CARDNEWS_BASE_DIR", str(tmp_path))

    monkeypatch.setattr(
        app_module.reader, "load_products",
        lambda items, assets_dir: [
            {"mall": "musinsa", "product_id": "1", "image_path": None, "brand": "b"}
        ],
    )
    monkeypatch.setattr(
        app_module.copywriter, "write_copy",
        lambda products, topic, api_key=None: {
            "topic": topic,
            "cover": {"kicker": "K", "title": "T", "sub": "s"},
            "items": [{"prod": "p", "title": "t", "meta": "m", "proof": "pr", "sp": "s", "badge": None}],
            "cta": {"title": "c", "sub": "s"},
            "caption": "캡션 내용",
        },
    )

    def fake_render(copy, products, out_dir):
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        paths = []
        for i in range(3):
            p = Path(out_dir) / f"{i + 1}.jpg"
            p.write_bytes(b"JPG")
            paths.append(str(p))
        return paths

    monkeypatch.setattr(app_module.renderer, "render", fake_render)

    resp = client.post(
        "/api/selections",
        json={"createdAt": "2026-07-22", "items": [{"mall": "musinsa", "product_id": "1"}]},
    )
    assert resp.status_code == 200
    body = resp.json()
    job_id = body["job_id"]
    assert body["preview_url"] == f"http://localhost:8787/preview/{job_id}"

    app_module._THREADS[job_id].join(timeout=5)

    job = jobs.JOBS[job_id]
    assert job["status"] == "미리보기 대기"
    assert len(job["images"]) == 3
    assert job["folder"]
    assert (Path(job["folder"]) / "caption.txt").read_text(encoding="utf-8") == "캡션 내용"


def test_selections_pipeline_marks_failure_on_exception(monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "CARDNEWS_BASE_DIR", str(tmp_path))

    def boom(items, assets_dir):
        raise RuntimeError("상품 로드 실패")

    monkeypatch.setattr(app_module.reader, "load_products", boom)

    resp = client.post("/api/selections", json={"items": [{"mall": "musinsa", "product_id": "1"}]})
    job_id = resp.json()["job_id"]
    app_module._THREADS[job_id].join(timeout=5)

    job = jobs.JOBS[job_id]
    assert job["status"] == "실패"
    assert "상품 로드 실패" in job["error"]


def test_preview_html_contains_publish_button(tmp_path):
    job = _make_ready_job(tmp_path)
    resp = client.get(f"/preview/{job['id']}")
    assert resp.status_code == 200
    assert "인스타에 게시" in resp.text
    assert f"/files/{job['id']}/1.jpg" in resp.text
    assert "캡션 내용" in resp.text


def test_preview_in_progress_autorefreshes():
    job = jobs.create_job()  # status "받음"
    resp = client.get(f"/preview/{job['id']}")
    assert resp.status_code == 200
    assert "refresh" in resp.text
    assert "받음" in resp.text


def test_preview_not_found_returns_404():
    resp = client.get("/preview/nonexistent-id")
    assert resp.status_code == 404


def test_files_endpoint_serves_image(tmp_path):
    job = _make_ready_job(tmp_path)
    resp = client.get(f"/files/{job['id']}/1.jpg")
    assert resp.status_code == 200
    assert resp.content == b"JPG"


def test_files_path_traversal_blocked(tmp_path):
    job = _make_ready_job(tmp_path)
    resp = client.get(f"/files/{job['id']}/..%2F..%2Fsecret.txt")
    assert resp.status_code in (400, 404)

    resp2 = client.get(f"/files/{job['id']}/notallowed.txt")
    assert resp2.status_code in (400, 404)


def test_publish_success_marks_job_complete(monkeypatch, tmp_path):
    job = _make_ready_job(tmp_path)
    monkeypatch.setattr(app_module.publisher, "publish", lambda folder: "https://instagram.com/p/xyz")

    resp = client.post(f"/api/jobs/{job['id']}/publish")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    app_module._THREADS[job["id"]].join(timeout=5)

    updated = jobs.JOBS[job["id"]]
    assert updated["status"] == "완료"
    assert updated["permalink"] == "https://instagram.com/p/xyz"


def test_publish_failure_marks_job_failed(monkeypatch, tmp_path):
    job = _make_ready_job(tmp_path)

    def boom(folder):
        raise RuntimeError("캡션 불일치")

    monkeypatch.setattr(app_module.publisher, "publish", boom)

    resp = client.post(f"/api/jobs/{job['id']}/publish")
    assert resp.status_code == 200
    app_module._THREADS[job["id"]].join(timeout=5)

    updated = jobs.JOBS[job["id"]]
    assert updated["status"] == "실패"
    assert "캡션 불일치" in updated["error"]


def test_publish_system_exit_from_post_ig_marks_job_failed(monkeypatch, tmp_path):
    """post_ig.py 의 load_token/collect_images 등은 실패 시 sys.exit() -> SystemExit 을
    던진다(Exception 이 아닌 BaseException). run_publish 가 이를 놓치면 스레드가 조용히
    죽어 잡이 "게시 중"에 영구히 멈추므로, SystemExit 도 "실패"로 반드시 귀결돼야 한다."""
    job = _make_ready_job(tmp_path)

    def boom(folder):
        raise SystemExit("토큰 파일이 없습니다")

    monkeypatch.setattr(app_module.publisher, "publish", boom)

    resp = client.post(f"/api/jobs/{job['id']}/publish")
    assert resp.status_code == 200
    app_module._THREADS[job["id"]].join(timeout=5)

    updated = jobs.JOBS[job["id"]]
    assert updated["status"] == "실패"
    assert "토큰" in updated["error"]


def test_publish_double_click_does_not_start_second_thread(monkeypatch, tmp_path):
    job = _make_ready_job(tmp_path)
    jobs.set_status(job, "게시 중")  # 이미 게시가 진행 중인 상태를 흉내낸다

    called = {"n": 0}

    def slow_publish(folder):
        called["n"] += 1
        return "https://instagram.com/p/xyz"

    monkeypatch.setattr(app_module.publisher, "publish", slow_publish)

    resp = client.post(f"/api/jobs/{job['id']}/publish")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert job["id"] not in app_module._THREADS  # 새 스레드를 띄우지 않았어야 함
    assert called["n"] == 0


def test_get_job_not_found_returns_404():
    resp = client.get("/api/jobs/nonexistent-id")
    assert resp.status_code == 404


def test_get_job_returns_job_dict(tmp_path):
    job = _make_ready_job(tmp_path)
    resp = client.get(f"/api/jobs/{job['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "미리보기 대기"
