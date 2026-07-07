"""Firestore 저장소 구현.

실제 Firebase 자격증명이 있을 때만 사용된다(STORAGE_BACKEND=firestore).
지연 임포트로, 패키지/자격증명이 없어도 앱 임포트는 실패하지 않는다.
"""
from __future__ import annotations

from ..config import Settings
from ..models import CardNews
from .base import CardNewsStore

COLLECTION = "cardnews"


class FirestoreStore(CardNewsStore):
    def __init__(self, settings: Settings) -> None:
        from google.cloud import firestore  # 지연 임포트

        self._db = firestore.Client(project=settings.google_cloud_project or None)

    def save(self, cardnews: CardNews) -> CardNews:
        data = cardnews.model_dump(exclude={"id"})
        ref = self._db.collection(COLLECTION).document()
        ref.set(data)
        return cardnews.model_copy(update={"id": ref.id})

    def list(self) -> list[CardNews]:
        docs = self._db.collection(COLLECTION).stream()
        items = [CardNews(id=d.id, **d.to_dict()) for d in docs]
        return items

    def get(self, doc_id: str) -> CardNews | None:
        snap = self._db.collection(COLLECTION).document(doc_id).get()
        if not snap.exists:
            return None
        return CardNews(id=snap.id, **snap.to_dict())
