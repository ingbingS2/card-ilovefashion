"""verify — 브라우저에서 받은 무신사 원본으로 재검증(11-02). 무신사 네트워크 호출은 하면 안 된다."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta

import pytest

from autopost import config, malls, verify
from autopost.tests.conftest import write_episode

FOLDER = "20261002 가을 재킷"
QUOTE = "색감이 어두워서 과하지 않게 여기저기 걸치고 다니기 좋아요 자주 입고 다닙니다"


def _facts_file(tmp_path, items, minutes_ago=5, tamper=False):
    cap = (config.now_kst() - timedelta(minutes=minutes_ago)).isoformat()
    payload = json.dumps({"captured_at": cap, "items": items}, ensure_ascii=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if tamper:
        payload = payload.replace("49900", "39900")
    path = tmp_path / "facts.json"
    path.write_text(json.dumps({"payload": payload, "sha256": digest}, ensure_ascii=False), encoding="utf-8")
    return str(path)


def _item(no, price=49900, sale_type="SALE", quote=True):
    return {"goodsPrice": {"salePrice": price, "normalPrice": 129900, "discountRate": 62},
            "goodsReview": {"totalCount": 43, "satisfactionScore": 4.9},
            "isOutOfStock": False, "goodsSaleType": sale_type,
            "quote": {"no": no * 10, "content": QUOTE} if quote else None}


@pytest.fixture
def setup(episode, cands, monkeypatch):
    write_episode(FOLDER, episode, cands)

    def no_network(*a, **k):
        raise AssertionError("브라우저 원본이 있으면 무신사를 부르면 안 된다")
    monkeypatch.setattr(malls, "detail", no_network)
    monkeypatch.setattr(verify, "find_review", no_network)
    yield [c["goodsNo"] for c in cands["candidates"]]
    verify.use_browser_facts(None)


def test_browser_facts_pass(setup, tmp_path):
    verify.use_browser_facts(verify.load_browser_facts(_facts_file(tmp_path, {str(n): _item(n) for n in setup})))
    blocks, changes, failed, _ = verify.check(FOLDER)
    assert (blocks, changes, failed) == ([], [], [])


def test_browser_facts_detects_change_stop_sale_and_missing_quote(setup, tmp_path):
    items = {str(n): _item(n) for n in setup}
    items[str(setup[0])] = _item(setup[0], price=45900)
    items[str(setup[1])] = _item(setup[1], sale_type="STOP_SALE")
    items[str(setup[2])] = _item(setup[2], quote=False)
    del items[str(setup[3])]
    verify.use_browser_facts(verify.load_browser_facts(_facts_file(tmp_path, items)))
    blocks, changes, failed, _ = verify.check(FOLDER)
    assert any("sale_price" in c for c in changes)
    assert any("품절" in b for b in blocks) and any("인용 후기" in b for b in blocks)
    assert any("브라우저 원본에 이 상품이 없음" in f for f in failed)


def test_browser_facts_rejects_tamper_and_stale(tmp_path):
    with pytest.raises(verify.BrowserFactsError, match="해시"):
        verify.load_browser_facts(_facts_file(tmp_path, {"1": _item(1)}, tamper=True))
    with pytest.raises(verify.BrowserFactsError, match="분 전"):
        verify.load_browser_facts(_facts_file(tmp_path, {"1": _item(1)}, minutes_ago=config.VERIFY_FRESH_MINUTES + 5))
