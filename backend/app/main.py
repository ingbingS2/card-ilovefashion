"""FastAPI 진입점: 카드뉴스 생성/저장 API."""
from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import Settings, get_settings
from .models import CardNews, GenerateRequest, GenerateResponse
from .services.generator import CardNewsGenerator
from .storage.base import CardNewsStore
from .storage.memory import InMemoryStore

# 앱 전역 단일 저장소 인스턴스(기본 인메모리). firestore 선택 시 교체.
_store_singleton: CardNewsStore = InMemoryStore()


def get_store(settings: Settings = Depends(get_settings)) -> CardNewsStore:
    if settings.storage_backend == "firestore":
        from .storage.firestore import FirestoreStore

        return FirestoreStore(settings)
    return _store_singleton


def get_generator(settings: Settings = Depends(get_settings)) -> CardNewsGenerator:
    return CardNewsGenerator(settings)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI 카드뉴스 자동 생성기", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/generate", response_model=GenerateResponse)
    def generate(
        req: GenerateRequest,
        generator: CardNewsGenerator = Depends(get_generator),
    ) -> GenerateResponse:
        try:
            slides = generator.generate(req)
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return GenerateResponse(slides=slides, meta={"topic": req.topic})

    @app.post("/api/cardnews", response_model=CardNews)
    def save_cardnews(
        cardnews: CardNews,
        store: CardNewsStore = Depends(get_store),
    ) -> CardNews:
        return store.save(cardnews)

    @app.get("/api/cardnews", response_model=list[CardNews])
    def list_cardnews(store: CardNewsStore = Depends(get_store)) -> list[CardNews]:
        return store.list()

    @app.get("/api/cardnews/{doc_id}", response_model=CardNews)
    def get_cardnews(doc_id: str, store: CardNewsStore = Depends(get_store)) -> CardNews:
        item = store.get(doc_id)
        if item is None:
            raise HTTPException(status_code=404, detail="카드뉴스를 찾을 수 없습니다.")
        return item

    return app


app = create_app()
