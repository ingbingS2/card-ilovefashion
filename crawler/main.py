"""크롤러 진입점: 무신사 카테고리별 + 29CM 베스트 → 저장소 적재.

사용법:
  python main.py --store json [--out out]     # 로컬 JSON (개발/시크릿 없는 CI)
  python main.py --store firestore            # Firestore (GOOGLE_APPLICATION_CREDENTIALS 필요)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

import config
import fetchers as _fetchers
import parsers as _parsers
from store import FirestoreStore, LocalJsonStore


def _collect_reviews(product, prev_counts, fetch, parse, stats):
    pid = product["product_id"]
    if pid in prev_counts and prev_counts[pid] == product["review_count"]:
        return None  # 변동 없음 → 기존 후기 유지
    if product["mall"] == "musinsa":
        reviews = parse.parse_musinsa_reviews(
            fetch.fetch_musinsa_reviews(pid, size=config.REVIEW_SIZE))
    else:
        reviews = parse.parse_cm29_reviews(
            fetch.fetch_cm29_reviews(pid, size=config.REVIEW_SIZE))
    stats["reviews_fetched"] += 1
    return reviews


def _run_job(store, mall, cat, products, now_iso, fetch, parse, stats):
    prev = store.load_ranking(mall, cat) or {}
    prev_counts = {p["product_id"]: p.get("review_count")
                   for p in prev.get("items") or []}
    for product in products:
        try:
            reviews = _collect_reviews(product, prev_counts, fetch, parse, stats)
        except Exception as e:  # 후기 실패는 상품 저장을 막지 않는다
            stats["errors"].append(f"후기 수집 실패 {mall}/{product['product_id']}: {e}")
            reviews = None
        store.save_product(product, reviews, now_iso)
        stats["products_saved"] += 1
    # 랭킹 스냅샷은 상품 저장이 전부 끝난 뒤에 기록한다.
    # (먼저 저장하면 상품 저장 실패로 카테고리가 실패 처리돼도 새 스냅샷이
    #  이미 남아, 다음 실행의 prev_counts 가 저장되지 않은 후기를 건너뛴다)
    store.save_ranking(mall, cat, {"updatedAt": now_iso, "items": products})
    stats["rankings_saved"] += 1


def crawl_once(store, now_iso: str, fetch=_fetchers, parse=_parsers) -> dict:
    stats = {"rankings_saved": 0, "products_saved": 0,
             "reviews_fetched": 0, "errors": []}
    for cat, cat_name in config.MUSINSA_CATEGORIES.items():
        try:
            products = parse.parse_musinsa_ranking(
                fetch.fetch_musinsa_ranking(cat))[:config.TOP_N]
            for p in products:
                p["category_code"], p["category_name"] = cat, cat_name
            _run_job(store, "musinsa", cat, products, now_iso, fetch, parse, stats)
        except Exception as e:
            stats["errors"].append(f"무신사 {cat}({cat_name}) 실패: {e}")
    try:
        products = parse.parse_cm29_best(fetch.fetch_cm29_best())[:config.TOP_N]
        _run_job(store, "cm29", "best", products, now_iso, fetch, parse, stats)
    except Exception as e:
        stats["errors"].append(f"29CM best 실패: {e}")
    for cat, cat_name in config.CM29_CATEGORIES.items():
        try:
            products = parse.parse_cm29_best(
                fetch.fetch_cm29_best(category_large_id=cat))[:config.TOP_N]
            for p in products:
                p["category_code"], p["category_name"] = cat, cat_name
            _run_job(store, "cm29", cat, products, now_iso, fetch, parse, stats)
        except Exception as e:
            stats["errors"].append(f"29CM {cat}({cat_name}) 실패: {e}")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="패션 랭킹 크롤러")
    ap.add_argument("--store", choices=["json", "firestore"], required=True)
    ap.add_argument("--out", default="out", help="json 모드 출력 폴더")
    args = ap.parse_args()

    store = LocalJsonStore(args.out) if args.store == "json" else FirestoreStore()
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stats = crawl_once(store, now_iso)

    print(f"완료: 랭킹 {stats['rankings_saved']}건, 상품 {stats['products_saved']}건, "
          f"후기 수집 {stats['reviews_fetched']}건, 오류 {len(stats['errors'])}건")
    for err in stats["errors"]:
        print("  오류:", err)
    if stats["rankings_saved"] == 0:
        return 2
    return 1 if stats["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
