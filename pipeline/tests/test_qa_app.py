"""/api/qa, /dashboard 테스트 — Claude 호출은 목, 실제 네트워크 없음."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import app as app_module
import qa

client = TestClient(app_module.app, base_url="http://localhost")


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """QA 저장 파일을 테스트 전용 임시 파일로 격리한다."""
    monkeypatch.setattr(qa, "QA_FILE", str(tmp_path / "_qa.json"))


def test_post_qa_without_key_saves_pending(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/api/qa", json={"question": "저장률이 뭐야?"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "대기"
    assert body["answer"] is None
    assert qa.load_qas()[0]["question"] == "저장률이 뭐야?"


def test_post_qa_with_key_returns_answer(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(qa, "answer_question", lambda q, api_key: "답변입니다")
    r = client.post("/api/qa", json={"question": "질문"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "완료"
    assert body["answer"] == "답변입니다"
    assert qa.load_qas()[0]["answer"] == "답변입니다"


def test_post_qa_answer_failure_is_502_and_not_saved(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    def boom(q, api_key):
        raise RuntimeError("API 오류")

    monkeypatch.setattr(qa, "answer_question", boom)
    r = client.post("/api/qa", json={"question": "질문"})
    assert r.status_code == 502
    assert qa.load_qas() == []


def test_post_qa_rejects_empty():
    r = client.post("/api/qa", json={"question": "   "})
    assert r.status_code == 400


def test_post_qa_rejects_untrusted_origin(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post(
        "/api/qa", json={"question": "질문"}, headers={"Origin": "https://evil.example"}
    )
    assert r.status_code == 403
    assert qa.load_qas() == []


def test_get_qa_lists_saved_items(monkeypatch):
    qa.add_qa("질문1", "답1", "완료")
    qa.add_qa("질문2", None, "대기")
    r = client.get("/api/qa")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["question"] for i in items] == ["질문1", "질문2"]


def test_dashboard_served(monkeypatch, tmp_path):
    html = tmp_path / "_dashboard.html"
    html.write_text("<html>대시보드</html>", encoding="utf-8")
    monkeypatch.setattr(app_module, "DASHBOARD_FILE", str(html))
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "대시보드" in r.text
