"""pytest 픽스처: TestClient + 목 의존성."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# backend 루트를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import create_app, get_generator, get_store  # noqa: E402
from app.models import GenerateRequest, Slide  # noqa: E402
from app.storage.memory import InMemoryStore  # noqa: E402


class FakeGenerator:
    """실제 Anthropic 호출 대신 고정 슬라이드를 반환."""

    def generate(self, req: GenerateRequest) -> list[Slide]:
        return [
            Slide(
                index=i + 1,
                headline=f"{req.topic} 헤드라인 {i + 1}",
                body="본문 예시",
                layout="중앙 정렬",
                graphic="라인",
                design_point="여백 강조",
            )
            for i in range(req.slide_count)
        ]


@pytest.fixture
def client() -> TestClient:
    os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
    app = create_app()
    store = InMemoryStore()
    app.dependency_overrides[get_generator] = lambda: FakeGenerator()
    app.dependency_overrides[get_store] = lambda: store
    return TestClient(app)
