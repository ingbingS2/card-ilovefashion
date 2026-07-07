"""카드뉴스 생성 서비스 (Anthropic Claude).

테스트에서는 `generate_cardnews` 를 목(mock)으로 대체하거나,
`CardNewsGenerator` 를 주입해 실제 API 호출 없이 검증한다.
"""
from __future__ import annotations

import json

from ..config import Settings
from ..models import GenerateRequest, Slide

# 카드뉴스 디렉터 시스템 프롬프트 (한국어 카드뉴스 규칙 요약)
SYSTEM_PROMPT = (
    "너는 한국어 카드뉴스 디자인 디렉터다. 주어진 주제로 세련되고 실용적인 "
    "한국어 카드뉴스를 만든다. 모든 문구는 자연스러운 한국어여야 하며, 슬라이드마다 "
    "하나의 핵심만 담는다. 반드시 아래 JSON 스키마로만 응답한다.\n"
    '{ "slides": [ { "index": 정수, "headline": "문자열", "body": "문자열", '
    '"layout": "문자열", "graphic": "문자열", "design_point": "문자열" } ], '
    '"meta": { } }'
)


def build_user_prompt(req: GenerateRequest) -> str:
    lines = [f"주제: {req.topic}", f"슬라이드 수: {req.slide_count}"]
    if req.target:
        lines.append(f"타깃: {req.target}")
    if req.goal:
        lines.append(f"목표: {req.goal}")
    if req.tone:
        lines.append(f"톤: {req.tone}")
    if req.cta:
        lines.append(f"CTA: {req.cta}")
    lines.append(
        "위 조건으로 카드뉴스를 만들어라. index 는 1부터 순서대로. "
        "JSON 외 텍스트는 절대 출력하지 마라."
    )
    return "\n".join(lines)


class CardNewsGenerator:
    """Anthropic API 래퍼. 실제 호출은 여기서만 발생한다."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def generate(self, req: GenerateRequest) -> list[Slide]:
        if not self.settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY 가 설정되지 않았습니다.")

        # 지연 임포트: 테스트 환경에서 anthropic 패키지가 없어도 임포트 에러가 나지 않도록.
        from anthropic import Anthropic

        client = Anthropic(api_key=self.settings.anthropic_api_key)
        message = client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(req)}],
        )
        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        return parse_slides(text)


def parse_slides(text: str) -> list[Slide]:
    """모델 응답 텍스트(JSON)를 Slide 리스트로 파싱."""
    text = text.strip()
    # 코드펜스 제거
    if text.startswith("```"):
        text = text.split("```", 2)[1] if "```" in text[3:] else text
        text = text.lstrip("json").strip("` \n")
    data = json.loads(text)
    slides = data["slides"] if isinstance(data, dict) else data
    return [Slide(**s) for s in slides]
