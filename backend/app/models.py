"""요청/응답 Pydantic 스키마."""
from __future__ import annotations

from pydantic import BaseModel, Field


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, description="카드뉴스 주제 (필수)")
    target: str | None = Field(None, description="타깃 독자")
    goal: str | None = Field(None, description="콘텐츠 목표")
    tone: str | None = Field(None, description="톤앤매너")
    cta: str | None = Field(None, description="마지막 슬라이드 CTA")
    slide_count: int = Field(10, ge=1, le=20, description="슬라이드 수")


class Slide(BaseModel):
    index: int = Field(..., description="슬라이드 순번 (1부터)")
    headline: str = Field(..., description="화면 헤드라인")
    body: str = Field("", description="보조 문구/본문")
    layout: str = Field("", description="레이아웃 설명")
    graphic: str = Field("", description="그래픽 요소")
    design_point: str = Field("", description="디자인 포인트")


class CardNews(BaseModel):
    id: str | None = Field(None, description="저장 시 부여되는 문서 ID")
    topic: str
    slides: list[Slide]
    meta: dict = Field(default_factory=dict)


class GenerateResponse(BaseModel):
    slides: list[Slide]
    meta: dict = Field(default_factory=dict)
