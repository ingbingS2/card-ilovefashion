"""저장 계층 테스트 — LocalJsonStore 는 tmp_path, Firestore 는 페이크 클라이언트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from store import FirestoreStore, LocalJsonStore


def prod(pid="1", rank=1, count=5):
    return {"mall": "musinsa", "product_id": pid, "rank": rank, "brand": "b",
            "name": "n", "price": 1000, "original_price": None, "discount_rate": 0,
            "review_score": 4.8, "review_count": count, "thumbnail": None,
            "product_url": "u", "category_code": "001", "category_name": None}


def test_local_ranking_roundtrip(tmp_path):
    s = LocalJsonStore(str(tmp_path))
    assert s.load_ranking("musinsa", "001") is None
    snap = {"updatedAt": "2026-07-20T00:00:00", "items": [prod()]}
    s.save_ranking("musinsa", "001", snap)
    assert s.load_ranking("musinsa", "001") == snap


def test_local_product_history_appends_and_caps(tmp_path):
    s = LocalJsonStore(str(tmp_path))
    import store as store_mod
    orig_cap = store_mod.config.HISTORY_CAP
    store_mod.config.HISTORY_CAP = 3
    try:
        for i in range(5):
            s.save_product(prod(count=i), None, f"2026-07-20T0{i}:00:00")
        doc = json.load(open(tmp_path / "products" / "musinsa_1.json", encoding="utf-8"))
        assert len(doc["history"]) == 3
        assert doc["history"][-1]["t"] == "2026-07-20T04:00:00"
        assert doc["history"][0]["t"] == "2026-07-20T02:00:00"  # 앞에서 절단
    finally:
        store_mod.config.HISTORY_CAP = orig_cap


def test_local_product_reviews_replace_or_keep(tmp_path):
    s = LocalJsonStore(str(tmp_path))
    s.save_product(prod(), [{"score": 5, "text": "굿", "date": None, "likes": 0}], "t1")
    s.save_product(prod(), None, "t2")  # None → 기존 후기 유지
    doc = json.load(open(tmp_path / "products" / "musinsa_1.json", encoding="utf-8"))
    assert doc["reviews"][0]["text"] == "굿"
    assert len(doc["history"]) == 2


class FakeDoc:
    def __init__(self, db, key):
        self.db, self.key = db, key

    def get(self):
        class Snap:
            def __init__(self, data):
                self.exists = data is not None
                self._d = data

            def to_dict(self):
                return self._d
        return Snap(self.db.data.get(self.key))

    def set(self, data):
        self.db.data[self.key] = data


class FakeFirestore:
    def __init__(self):
        self.data = {}

    def collection(self, name):
        db = self

        class Col:
            def document(self, doc_id):
                return FakeDoc(db, f"{name}/{doc_id}")
        return Col()


def test_firestore_store_same_contract():
    s = FirestoreStore(client=FakeFirestore())
    assert s.load_ranking("cm29", "best") is None
    snap = {"updatedAt": "t", "items": [prod()]}
    s.save_ranking("cm29", "best", snap)
    assert s.load_ranking("cm29", "best") == snap
    s.save_product(prod(), [{"score": 5, "text": "굿", "date": None, "likes": 0}], "t1")
    s.save_product(prod(), None, "t2")
    doc = s._db.data["products/musinsa_1"]
    assert doc["reviews"][0]["text"] == "굿" and len(doc["history"]) == 2
