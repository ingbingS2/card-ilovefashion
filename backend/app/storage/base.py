"""저장소 추상 인터페이스."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CardNews


class CardNewsStore(ABC):
    @abstractmethod
    def save(self, cardnews: CardNews) -> CardNews:
        """카드뉴스를 저장하고 id 가 채워진 객체를 반환."""

    @abstractmethod
    def list(self) -> list[CardNews]:
        """저장된 카드뉴스 목록(최신순)을 반환."""

    @abstractmethod
    def get(self, doc_id: str) -> CardNews | None:
        """id 로 단건 조회."""
