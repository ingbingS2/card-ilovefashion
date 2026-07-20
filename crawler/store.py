"""저장 계층: 로컬 JSON(개발·시크릿 없는 CI용) / Firestore(운영)."""
from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod

import config


def _updated_product_doc(old: dict | None, product: dict, reviews, now_iso: str) -> dict:
    doc = dict(old or {})
    doc.update(product)
    if reviews is not None:
        doc["reviews"] = reviews
    doc.setdefault("reviews", [])
    history = list(doc.get("history") or [])
    history.append({"t": now_iso, "rank": product.get("rank"),
                    "price": product.get("price"),
                    "review_score": product.get("review_score"),
                    "review_count": product.get("review_count")})
    doc["history"] = history[-config.HISTORY_CAP:]
    doc["updatedAt"] = now_iso
    return doc


class Store(ABC):
    @abstractmethod
    def load_ranking(self, mall: str, category_code: str) -> dict | None: ...

    @abstractmethod
    def save_ranking(self, mall: str, category_code: str, snapshot: dict) -> None: ...

    @abstractmethod
    def save_product(self, product: dict, reviews, now_iso: str) -> None: ...


class LocalJsonStore(Store):
    def __init__(self, out_dir: str):
        self.out = out_dir
        os.makedirs(os.path.join(out_dir, "rankings"), exist_ok=True)
        os.makedirs(os.path.join(out_dir, "products"), exist_ok=True)

    def _rank_path(self, mall, cat):
        return os.path.join(self.out, "rankings", f"{mall}_{cat}.json")

    def _prod_path(self, product):
        return os.path.join(self.out, "products",
                            f"{product['mall']}_{product['product_id']}.json")

    def load_ranking(self, mall, category_code):
        p = self._rank_path(mall, category_code)
        if not os.path.exists(p):
            return None
        return json.load(open(p, encoding="utf-8"))

    def save_ranking(self, mall, category_code, snapshot):
        json.dump(snapshot, open(self._rank_path(mall, category_code), "w",
                                 encoding="utf-8"), ensure_ascii=False)

    def save_product(self, product, reviews, now_iso):
        p = self._prod_path(product)
        old = json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None
        json.dump(_updated_product_doc(old, product, reviews, now_iso),
                  open(p, "w", encoding="utf-8"), ensure_ascii=False)


class FirestoreStore(Store):
    """Firestore 저장소. 자격증명은 GOOGLE_APPLICATION_CREDENTIALS(ADC)."""

    def __init__(self, client=None):
        if client is None:
            from google.cloud import firestore  # 지연 임포트
            client = firestore.Client()
        self._db = client

    def load_ranking(self, mall, category_code):
        snap = self._db.collection("rankings").document(f"{mall}_{category_code}").get()
        return snap.to_dict() if snap.exists else None

    def save_ranking(self, mall, category_code, snapshot):
        self._db.collection("rankings").document(f"{mall}_{category_code}").set(snapshot)

    def save_product(self, product, reviews, now_iso):
        ref = self._db.collection("products").document(
            f"{product['mall']}_{product['product_id']}")
        snap = ref.get()
        old = snap.to_dict() if snap.exists else None
        ref.set(_updated_product_doc(old, product, reviews, now_iso))
