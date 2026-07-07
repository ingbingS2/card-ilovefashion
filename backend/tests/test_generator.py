"""generator 파싱/프롬프트 유닛 테스트 (API 호출 없음)."""
from __future__ import annotations

from app.models import GenerateRequest
from app.services.generator import build_user_prompt, parse_slides


def test_parse_slides_plain_json():
    text = '{"slides": [{"index": 1, "headline": "제목", "body": "본문"}]}'
    slides = parse_slides(text)
    assert len(slides) == 1
    assert slides[0].headline == "제목"


def test_parse_slides_with_code_fence():
    text = '```json\n{"slides": [{"index": 1, "headline": "A"}]}\n```'
    slides = parse_slides(text)
    assert slides[0].index == 1


def test_build_user_prompt_includes_fields():
    req = GenerateRequest(topic="주제", target="크리에이터", cta="댓글")
    prompt = build_user_prompt(req)
    assert "주제" in prompt
    assert "크리에이터" in prompt
    assert "댓글" in prompt
