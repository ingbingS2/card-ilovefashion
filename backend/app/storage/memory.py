"""인메모리 저장소 (개발/테스트용)."""
from __future__ import annotations

import itertools

from ..models import CardNews
from .base import CardNewsStore


class InMemoryStore(CardNewsStore):
    def __init__(self) -> None:
        self._items: dict[str, CardNews] = {}
        self._counter = itertools.count(1)

    def save(self, cardnews: CardNews) -> CardNews:
        doc_id = str(next(self._counter))
        stored = cardnews.model_copy(update={"id": doc_id})
        self._items[doc_id] = stored
        return stored

    def list(self) -> list[CardNews]:
        # 최신(나중에 저장된) 순
        return list(reversed(list(self._items.values())))

    def get(self, doc_id: str) -> CardNews | None:
        return self._items.get(doc_id)
