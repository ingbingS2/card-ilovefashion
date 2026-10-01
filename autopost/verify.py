"""게시 직전 재검증 (KEYWORD-POLICY §6 끝 — 가격·할인율·후기 수·평점·구매 가능·인용문 존재).

    python -m autopost.verify "20261002 가을 니트" [--apply]

종료 코드: 0 = 변화 없음(게시 가능, verified_at 기록)
          1 = 막힘(품절·인용 후기 삭제/변경·렌더 이후 파일이 바뀜) — 게시 금지
          3 = 숫자가 바뀜 → --apply로 candidates.json 갱신(회차는 stale) → build → verify 다시
          4 = 몰 조회 실패(일시 오류일 수 있음) — 잠시 뒤 다시
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config, malls, malls29
from .state import fingerprint, load_status, save_status

FIELDS = ("sale_price", "normal_price", "discount", "review_count", "rating")
EXIT_OK, EXIT_BLOCKED, EXIT_CHANGED, EXIT_LOOKUP = 0, 1, 3, 4


def find_review(goods_no, review_no, pages: int = 15) -> dict | None:
    for page in range(pages):
        data = malls._get(malls.REVIEW_URL, {
            "page": page, "pageSize": 20, "goodsNo": goods_no, "sort": "up_cnt_desc",
            "selectedSimilarNo": goods_no, "myFilter": "false", "hasPhoto": "false",
            "isExperience": "false"}).get("data") or {}
        batch = data.get("list") or []
        for r in batch:
            if str(r.get("no")) == str(review_no):
                return r
        if len(batch) < 20:
            break
    return None


def _squash(s: str) -> str:
    return "".join((s or "").split())


def check(folder: str) -> tuple[list[str], list[str], list[str], dict]:
    """반환: (막힘, 변경, 조회 실패, goodsNo → 새 값)."""
    ep_dir = config.episode_dir(folder)
    ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    cands = json.loads((ep_dir / "candidates.json").read_text(encoding="utf-8"))
    by_no = {str(c["goodsNo"]): c for c in cands["candidates"]}
    blocks, changes, failed, fresh = [], [], [], {}
    for i, p in enumerate(ep["products"], 1):
        c = by_no[str(p["goodsNo"])]
        tag = f"{i}번 {c['brand']}({c['goodsNo']})"
        is29 = c.get("mall") == malls29.MALL
        try:
            if is29:
                d = malls29.detail(c["goodsNo"])
                try:   # 평점은 collect와 같은 출처(후기 API 평균) — 상세의 0.5 단위 값과 비교하면 매번 '변경'이 된다
                    avg = malls29.reviews(c["goodsNo"], pages=1)[2]
                except malls.MallError:
                    avg = None
                new = {**malls29.price_facts(d), **malls29.card_review_numbers(d, avg),
                       "sold_out": malls29.sold_out(d)}
                if avg is None:   # 후기 API 실패 — 0.5 단위 상세 값으로 '변경'을 만들지 않고 카드 값을 유지
                    new["rating"] = c.get("rating")
            else:
                d = malls.detail(c["goodsNo"])
                new = {**malls.price_facts(d), **malls.review_summary(d), "sold_out": bool(d.get("isOutOfStock"))}
        except malls.MallError as e:
            failed.append(f"{tag}: 상세 조회 실패 {e}")
            continue
        fresh[str(c["goodsNo"])] = new
        if new["sold_out"]:
            blocks.append(f"{tag}: 품절")
        for f in FIELDS:
            if new[f] != c.get(f):
                changes.append(f"{tag}: {f} {c.get(f)} → {new[f]}")
        if p.get("quote_no") is not None:
            q = next((q for q in c["quotes"] if str(q["no"]) == str(p["quote_no"])), None)
            try:
                finder = malls29.find_review if is29 else find_review
                r = finder(c["goodsNo"], p["quote_no"])
            except malls.MallError as e:
                failed.append(f"{tag}: 후기 조회 실패 {e}")
                continue
            if not r:
                blocks.append(f"{tag}: 인용 후기({p['quote_no']})를 찾을 수 없음 — 삭제됐을 수 있음")
            elif q and _squash(q["text"]) not in _squash(r.get("contents" if is29 else "content")):
                blocks.append(f"{tag}: 인용 후기 원문이 바뀜")
    return blocks, changes, failed, fresh


def apply(folder: str, fresh: dict) -> None:
    path = config.episode_dir(folder) / "candidates.json"
    cands = json.loads(path.read_text(encoding="utf-8"))
    for c in cands["candidates"]:
        if str(c["goodsNo"]) in fresh:
            c.update(fresh[str(c["goodsNo"])])
    path.write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")
    st = load_status(folder)
    if st.get("stage") not in ("posted", "publishing"):
        st["stage"] = "stale"  # 카드 숫자가 낡았다 — build 전엔 게시 불가
        st.pop("verified_at", None)
        save_status(folder, st)


def _invalidate(folder: str) -> None:
    """재검증이 통과하지 못했으면 이전 통과 기록을 지운다 — 60분 안의 옛 기록으로 gate가 열리지 않게."""
    st = load_status(folder)
    if st.pop("verified_at", None) is not None or st.pop("verified_fingerprint", None) is not None:
        save_status(folder, st)


def run(folder: str, do_apply: bool = False) -> int:
    st = load_status(folder)
    if st.get("stage") not in ("built", "approved"):
        print(f"[막힘] 회차 상태가 built/approved가 아님(stage={st.get('stage')}) — build를 먼저")
        return EXIT_BLOCKED
    if st.get("fingerprint") != fingerprint(folder):
        _invalidate(folder)
        print("[막힘] 렌더 이후 episode/candidates/caption/이미지가 바뀜 — build를 다시")
        return EXIT_BLOCKED
    try:
        blocks, changes, failed, fresh = check(folder)
    except Exception as e:  # 몰 모듈의 예상 못 한 예외도 '조회 실패'로 — 트레이스백으로 죽지 않게
        _invalidate(folder)
        print(f"[조회 실패] 예외: {type(e).__name__}: {str(e)[:160]}")
        return EXIT_LOOKUP
    for b in blocks:
        print(f"[막힘] {b}")
    for f in failed:
        print(f"[조회 실패] {f}")
    for c in changes:
        print(f"[변경] {c}")
    if blocks:
        _invalidate(folder)
        return EXIT_BLOCKED
    if failed:
        _invalidate(folder)
        return EXIT_LOOKUP
    if changes:
        _invalidate(folder)
        if do_apply:
            apply(folder, fresh)
            print("candidates.json 갱신, 회차는 stale — build → 카드 확인 → verify를 다시 실행하세요.")
        return EXIT_CHANGED
    st = load_status(folder)
    st["verified_at"] = config.now_kst().isoformat(timespec="seconds")
    st["verified_fingerprint"] = st["fingerprint"]
    save_status(folder, st)
    print("재검증 통과 — 5종 구매 가능, 숫자·인용문 그대로.")
    return EXIT_OK


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="게시 직전 재검증")
    ap.add_argument("folder")
    ap.add_argument("--apply", action="store_true", help="바뀐 숫자를 candidates.json에 반영")
    args = ap.parse_args(argv)
    sys.exit(run(args.folder, args.apply))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
