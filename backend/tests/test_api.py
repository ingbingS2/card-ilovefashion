"""API 엔드포인트 테스트 (목 기반, 실제 외부 호출 없음)."""
from __future__ import annotations


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_generate_returns_slides(client):
    res = client.post("/api/generate", json={"topic": "AI 카드뉴스 자동화", "slide_count": 10})
    assert res.status_code == 200
    data = res.json()
    assert len(data["slides"]) == 10
    assert data["slides"][0]["index"] == 1
    assert "AI 카드뉴스 자동화" in data["slides"][0]["headline"]
    assert data["meta"]["topic"] == "AI 카드뉴스 자동화"


def test_generate_requires_topic(client):
    res = client.post("/api/generate", json={"slide_count": 5})
    assert res.status_code == 422  # topic 필수


def test_save_and_list_cardnews(client):
    payload = {
        "topic": "테스트 주제",
        "slides": [
            {"index": 1, "headline": "제목", "body": "본문"},
        ],
    }
    saved = client.post("/api/cardnews", json=payload)
    assert saved.status_code == 200
    doc_id = saved.json()["id"]
    assert doc_id

    listed = client.get("/api/cardnews")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    single = client.get(f"/api/cardnews/{doc_id}")
    assert single.status_code == 200
    assert single.json()["topic"] == "테스트 주제"


def test_get_missing_cardnews_404(client):
    res = client.get("/api/cardnews/nonexistent")
    assert res.status_code == 404
