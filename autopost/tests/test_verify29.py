"""verify.check — 29CM 상품 경로 (몰 호출은 전부 목). 평점은 collect와 같은 출처(후기 API 평균)여야 한다."""
from __future__ import annotations

import pytest

from autopost import malls, malls29, verify
from autopost.tests.conftest import write_episode

FOLDER = "20261002 가을 재킷"
QUOTE = "색감이 어두워서 과하지 않게 여기저기 걸치고 다니기 좋아요 자주 입고 다닙니다"


@pytest.fixture
def ep29(episode, cands):
    for c in cands["candidates"]:
        c["mall"] = "29CM"   # make_candidate 기본 숫자: 49,900원 · 정가 129,900 · 62% · 후기 43 · ⭐4.9
    write_episode(FOLDER, episode, cands)
    return cands


def _mall29(monkeypatch, *, price=49900, stock="ON_STOCK", contents=QUOTE, avg=4.9, review_fail=False):
    """상세 reviewAggregation 평균은 0.5 단위(5.0) — 후기 API 평균(4.9)과 다르다(실측 형태)."""
    def detail(no):
        return {"itemNo": no, "sellPrice": price, "consumerPrice": 129900, "discountRate": 62,
                "reviewAggregation": {"totalCount": 43, "averagePoint": 5.0},
                "frontItemStockStatus": stock, "isSoldout": None, "itemStockStatus": 1}

    def reviews(no, pages=3, size=20):
        if review_fail:
            raise malls.MallError("HTTP 500")
        return [], 43, avg

    def find_review(no, review_no, pages=15):
        r = {"itemReviewNo": review_no}
        if contents is not None:
            r["contents"] = contents
        return r

    def musinsa_detail(no):
        raise AssertionError("29CM 상품에 무신사 상세를 부르면 안 된다")
    monkeypatch.setattr(malls29, "detail", detail)
    monkeypatch.setattr(malls29, "reviews", reviews)
    monkeypatch.setattr(malls29, "find_review", find_review)
    monkeypatch.setattr(malls, "detail", musinsa_detail)


def test_unchanged_numbers_report_no_change(ep29, monkeypatch):
    _mall29(monkeypatch)
    blocks, changes, failed, fresh = verify.check(FOLDER)
    assert (blocks, changes, failed) == ([], [], [])
    assert fresh["100"]["rating"] == 4.9 and fresh["100"]["review_count"] == 43


def test_price_change_is_reported(ep29, monkeypatch):
    _mall29(monkeypatch, price=45900)
    blocks, changes, failed, _ = verify.check(FOLDER)
    assert not blocks and not failed
    assert len(changes) == 5 and all("sale_price 49900 → 45900" in c for c in changes)


def test_sold_out_blocks(ep29, monkeypatch):
    _mall29(monkeypatch, stock="SOLD_OUT")
    blocks, changes, failed, _ = verify.check(FOLDER)
    assert len(blocks) == 5 and all(b.endswith("품절") for b in blocks)
    assert not changes and not failed


def test_quote_present_in_contents_is_ok(ep29, monkeypatch):
    _mall29(monkeypatch, contents="정말 " + QUOTE.replace("좋아요 ", "좋아요\n") + " 추천해요")
    blocks, _, failed, _ = verify.check(FOLDER)
    assert not blocks and not failed


@pytest.mark.parametrize("contents", ["전혀 다른 후기 내용입니다", None])
def test_quote_missing_from_contents_blocks(ep29, monkeypatch, contents):
    _mall29(monkeypatch, contents=contents)
    blocks, _, failed, _ = verify.check(FOLDER)
    assert len(blocks) == 5 and all("인용 후기 원문이 바뀜" in b for b in blocks)
    assert not failed


def test_review_api_failure_keeps_card_rating(ep29, monkeypatch):
    """후기 API가 실패하면 0.5 단위 상세 평점으로 '변경'을 만들지 않고 카드 값을 유지한다."""
    _mall29(monkeypatch, review_fail=True)
    blocks, changes, failed, fresh = verify.check(FOLDER)
    assert not blocks and not failed
    assert fresh["100"]["rating"] == 4.9
    assert not any("rating" in c for c in changes)
