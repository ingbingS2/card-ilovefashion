"""오늘의 신호 요약 + 키워드 후보 상품 수집 (무신사 + 29CM).

    python -m autopost.collect signals
    python -m autopost.collect candidates --folder "20261002 가을 니트" -q "가을 니트" -q "니트 가디건" [--gf F]

candidates는 두 몰을 검색해 신상·재고·제외 브랜드·직전 회차 브랜드를 거르고 `episodes/<folder>/candidates.json`을 쓴다.
상품마다 사진 번호를 붙인 시트(`.autopost-work/<folder>/sheets/<goodsNo>.jpg`)를 만든다 — 세션이 보고 고른다.
무신사 검색 API가 막히면(클라우드 IP에서 Cloudflare 403 — 10-01 실측) 무신사 실시간 랭킹을 검색어로 걸러 대신 쓴다.
같은 상품이 다른 몰에서 더 싸면 `cheaper_elsewhere`에 적는다 — 가격·이미지 출처는 저렴한 몰(§2).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import date

import requests

from . import config, malls, malls29, rules
from .state import excluded_brand, find_handle, load_handles, load_history, norm_brand, posted, same_brand

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MAX_PER_BRAND = 2      # 한 브랜드의 색상 변형이 후보를 다 채우지 않게
MAX_DETAIL_CALLS = 80  # 상세·후기 조회 상한 (몰 API 연속 호출 매너)
MUSINSA, CM29 = "무신사", malls29.MALL


# ---------- signals ----------

def weather_line() -> str:
    try:
        r = requests.get(WEATHER_URL, timeout=20, params={
            "latitude": 37.57, "longitude": 126.98, "timezone": "Asia/Seoul", "forecast_days": 3,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max"})
        d = r.json()["daily"]
        days = [f"{t[5:]} 최저 {lo:.0f}° 최고 {hi:.0f}° 강수 {p}%" for t, hi, lo, p in
                zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"],
                    d["precipitation_probability_max"])]
        return "서울 " + " / ".join(days)
    except Exception as e:  # 날씨는 참고 신호 — 실패해도 진행
        return f"(날씨 조회 실패: {e})"


def signals() -> str:
    today = config.now_kst().date()
    hist = load_history()
    out = [f"# 오늘의 신호 — {today.isoformat()} (KST)", "", "## 날씨", weather_line(), ""]

    out.append("## 최근 회차 (최신이 아래) — 도달·공유는 측정된 값")
    for h in posted(hist)[-12:]:
        m = h.get("metrics") or {}
        out.append(f"- {h['posted_at'][:10]} {h['keyword']} · 도달 {m.get('reach', '?')} · "
                   f"공유 {m.get('shares', '?')} · 축 {h.get('axis', '')} · 무드 {h.get('mood', '')}")
    last = posted(hist)[-1:] or [{}]
    out.append(f"\n직전 회차 브랜드(연속 금지): {', '.join(last[0].get('brands', [])) or '없음'}")
    excl = [f"{k}(~{v[0].isoformat()})" for k, v in config.BRAND_EXCLUSIONS.items() if today <= v[0]]
    out.append(f"일시 제외 브랜드: {', '.join(excl) or '없음'}")
    roster = [b["name"] for b in load_handles().get("brands", []) if b.get("roster")]
    out.append(f"로스터(반응 이력) 브랜드: {', '.join(roster)}")

    out.append("\n## 무신사 여성 실시간 랭킹 상위 30 (수요 확인용 — 랭킹을 키워드로 쓰지 않는다)")
    for code, name in config.MUSINSA_CATEGORIES.items():
        try:
            rows = malls.ranking(code, gf="F")[:30]
            out.append(f"### {name} ({code})")
            out.extend(f"{r['rank']}. {r['brand']} — {r['name']}" for r in rows)
        except malls.MallError as e:
            out.append(f"### {name}: 조회 실패 {e}")
    return "\n".join(out)


# ---------- 후보 한 건 만들기 (몰별) ----------

def _handle_fields(handles: dict, *names: str) -> dict:
    entry = find_handle(handles, *names)
    return {"roster": bool(entry and entry.get("roster")),
            "handle": entry.get("handle") if entry and entry.get("verified") else None}


def _quote(no, text, grade, likes, when, rtype="") -> dict | None:
    text = rules.flatten_quote(text)
    if rules.quote_problem(text, grade, rtype) is not None:
        return None
    return {"no": no, "text": text, "grade": int(grade), "likes": likes or 0, "date": (when or "")[:10]}


def build_musinsa(goods_no, handles: dict) -> dict:
    d = malls.detail(goods_no)
    revs, total = malls.reviews(goods_no)
    info = d.get("brandInfo") or {}
    brand = info.get("brandName") or d.get("brand", "")
    quotes = [q for q in (_quote(r.get("no"), r.get("content", ""), r.get("grade"), r.get("likeCount"),
                                 r.get("createDate"), r.get("type", "")) for r in revs) if q]
    rd = malls.release_date(d)
    images = []
    for img in d.get("goodsImages") or []:
        url = malls.full_image_url(img.get("imageUrl", ""))
        if url not in images:
            images.append(url)
    spec = malls.strip_html(" ".join(str(d.get(k) or "") for k in ("specDesc", "headDesc")))
    return {
        "mall": MUSINSA, "goodsNo": int(d["goodsNo"]),
        "url": f"https://www.musinsa.com/products/{d['goodsNo']}",
        "brand": brand, "brand_en": info.get("brandEnglishName", ""), "brand_id": d.get("brand", ""),
        "name": d.get("goodsNm", ""),
        "genders": d.get("genders") or d.get("sex") or [],
        "category": " > ".join(filter(None, [(d.get("category") or {}).get("categoryDepth1Name"),
                                             (d.get("category") or {}).get("categoryDepth2Name")])),
        **malls.price_facts(d), **malls.review_summary(d),
        "review_total_listed": total,
        "sold_out": bool(d.get("isOutOfStock")),
        "release_date": rd.isoformat() if rd else None,
        "season": malls.season_label(d),
        "style_no": d.get("styleNo") or "",
        "material": malls.material_facts(d),
        "spec_text": spec[:4000],
        "images": images,
        "quotes": sorted(quotes, key=lambda q: -q["likes"])[:8],
        **_handle_fields(handles, brand, info.get("brandEnglishName", ""), d.get("brand", "")),
    }


def build_29cm(item_no, handles: dict) -> dict:
    d = malls29.detail(item_no)
    revs, total = malls29.reviews(item_no)
    fb = d.get("frontBrand") or {}
    brand = fb.get("brandNameKor") or fb.get("brandNameEng") or ""
    quotes = [q for q in (_quote(r.get("itemReviewNo"), r.get("contents", ""), r.get("point"),
                                 r.get("helpfulCount") or r.get("likeCount"), r.get("insertTimestamp"))
                          for r in revs) if q]
    rd = malls29.release_date(d)
    return {
        "mall": CM29, "goodsNo": int(d["itemNo"]),
        "url": f"https://product.29cm.co.kr/catalog/{d['itemNo']}",
        "brand": brand, "brand_en": fb.get("brandNameEng", ""), "brand_id": str(fb.get("frontBrandNo", "")),
        "name": d.get("itemName", ""),
        "genders": [str(d.get("genderAttr") or "")],
        "category": "",
        **malls29.price_facts(d), **malls29.review_summary(d),
        "review_total_listed": total,
        "sold_out": malls29.sold_out(d),
        "release_date": rd.isoformat() if rd else None,
        "season": "",
        "style_no": "",
        "material": [],
        "spec_text": malls29.spec_text(d)[:4000],
        "images": malls29.images(d),
        "quotes": sorted(quotes, key=lambda q: -q["likes"])[:8],
        **_handle_fields(handles, brand, fb.get("brandNameEng", "")),
    }


BUILDERS = {MUSINSA: build_musinsa, CM29: build_29cm}


# ---------- 검색 → 공통 행 ----------

def _tokens(text: str) -> set[str]:
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", (text or "").lower())
    return set(re.findall(r"[0-9a-z가-힣]{2,}", text))


def search_rows(queries: list[str], gf: str, notes: list[str]) -> list[dict]:
    """두 몰 검색 결과를 {mall, no, brand, brand_en, reviews, sold_out, ad, query}로 통일."""
    rows: list[dict] = []
    musinsa_blocked = False
    for q in queries:
        if not musinsa_blocked:
            try:
                for r in malls.search(q, gf=gf):
                    rows.append({"mall": MUSINSA, "no": int(r["goodsNo"]), "brand": r.get("brandName", ""),
                                 "brand_en": r.get("brand", ""), "reviews": r.get("reviewCount") or 0,
                                 "sold_out": bool(r.get("isSoldOut")), "ad": bool(r.get("isAd")), "query": q})
            except malls.MallError as e:
                musinsa_blocked = True
                notes.append(f"무신사 검색 실패 → 랭킹으로 대체: {str(e)[:80]}")
        try:
            for r in malls29.search(q):
                large = " ".join(c.get("categoryLargeName", "") for c in r.get("frontCategoryInfo") or [])
                if (gf == "F" and "남성" in large) or (gf == "M" and "여성" in large):
                    continue
                rows.append({"mall": CM29, "no": int(r["itemNo"]), "brand": r.get("frontBrandNameKor", ""),
                             "brand_en": r.get("frontBrandNameEng", ""), "reviews": r.get("reviewCount") or 0,
                             "sold_out": bool(r.get("isSoldOut")), "ad": False, "query": q})
        except malls.MallError as e:
            notes.append(f"29CM 검색 실패({q}): {str(e)[:80]}")
    if musinsa_blocked:
        rows.extend(ranking_rows(queries, gf if gf in ("F", "M") else "A", notes))
    return rows


def ranking_rows(queries: list[str], gf: str, notes: list[str]) -> list[dict]:
    """무신사 랭킹(클라우드에서도 열림) 상위 상품 중 상품명에 검색어 단어가 들어간 것."""
    words = {w for q in queries for w in _tokens(q)} - {"가을", "겨울", "여름", "봄", "초가을", "늦가을",
                                                        "환절기", "한겨울", "한여름", "초겨울"}
    out = []
    for code in config.MUSINSA_CATEGORIES:
        try:
            for r in malls.ranking(code, gf=gf):
                if words & _tokens(r.get("name", "")) or any(w in (r.get("name") or "") for w in words):
                    out.append({"mall": MUSINSA, "no": int(r["goodsNo"]), "brand": r.get("brand", ""),
                                "brand_en": "", "reviews": 1000 - int(r.get("rank") or 999), "sold_out": False,
                                "ad": False, "query": "(랭킹)"})
        except (malls.MallError, ValueError, TypeError) as e:
            notes.append(f"무신사 랭킹 {code} 실패: {str(e)[:60]}")
    return out


def cheaper_elsewhere(c: dict) -> dict | None:
    """같은 상품을 다른 몰에서 찾아 판매가(쿠폰 미적용)가 더 낮으면 그 정보. 못 찾으면 None."""
    want = _tokens(c["name"])
    if not want:
        return None
    query = f"{c['brand']} {' '.join(sorted(want, key=len, reverse=True)[:3])}"
    try:
        if c["mall"] == MUSINSA:
            hits = [(r["itemNo"], r.get("frontBrandNameKor", ""), r.get("itemName", ""))
                    for r in malls29.search(query, size=10)]
        else:
            hits = [(r["goodsNo"], r.get("brandName", ""), r.get("goodsName", ""))
                    for r in malls.search(query, gf="A", size=10)]
    except malls.MallError:
        return None
    for no, brand, name in hits:
        got = _tokens(name)
        if not same_brand(brand, c["brand"]) or len(want & got) / max(len(want), 1) < 0.6:
            continue
        try:
            if c["mall"] == MUSINSA:
                d = malls29.detail(no)
                price, sold = malls29.price_facts(d)["sale_price"], malls29.sold_out(d)
                mall, url = CM29, f"https://product.29cm.co.kr/catalog/{no}"
            else:
                d = malls.detail(no)
                price, sold = malls.price_facts(d)["sale_price"], bool(d.get("isOutOfStock"))
                mall, url = MUSINSA, f"https://www.musinsa.com/products/{no}"
        except malls.MallError:
            return None
        if price and not sold and price < c["sale_price"]:
            return {"mall": mall, "goodsNo": int(no), "sale_price": price, "url": url}
        return None
    return None


# ---------- 사진 시트 ----------

def contact_sheet(cand: dict, path) -> None:
    """사진에 0,1,2… 번호를 붙인 한 장짜리 시트 (Pillow). 세션이 Read로 보고 image 인덱스를 고른다."""
    from PIL import Image, ImageDraw

    headers = malls29.HEADERS if cand.get("mall") == CM29 else malls.HEADERS
    thumbs = []
    for url in cand["images"][:8]:
        try:
            small = url.replace("_big.", "_500.")
            r = requests.get(small, headers=headers, timeout=30)
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            im.thumbnail((300, 360))
            thumbs.append(im)
        except Exception:
            thumbs.append(Image.new("RGB", (300, 360), "#ddd"))
    if not thumbs:
        return
    cols = 4
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 300, rows * 360 + 40), "white")
    draw = ImageDraw.Draw(sheet)
    tag = "29CM" if cand.get("mall") == CM29 else "MUSINSA"
    draw.text((8, 8), f"{tag} {cand['goodsNo']}", fill="black")  # 기본 폰트는 한글을 못 그린다
    for i, im in enumerate(thumbs):
        x, y = (i % cols) * 300, (i // cols) * 360 + 40
        sheet.paste(im, (x, y))
        draw.rectangle([x, y, x + 34, y + 30], fill="black")
        draw.text((x + 10, y + 8), str(i), fill="yellow")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=80)


# ---------- candidates ----------

def candidates(folder: str, queries: list[str], gf: str = "A", limit: int = 30) -> dict:
    today = config.now_kst().date()
    since = config.new_since(today)
    handles = load_handles()
    hist = posted(load_history())
    last_brands = hist[-1].get("brands", []) if hist else []
    notes: list[str] = []
    dropped: dict[str, int] = {}

    def drop(reason: str):
        dropped[reason] = dropped.get(reason, 0) + 1

    pool: dict[tuple, dict] = {}
    for row in search_rows(queries, gf, notes):
        pool.setdefault((row["mall"], row["no"]), row)

    pre = []
    for row in pool.values():
        if row["sold_out"]:
            drop("품절"); continue
        if row["ad"]:
            drop("광고"); continue
        if excluded_brand(today, row["brand"], row["brand_en"]):
            drop("일시 제외 브랜드"); continue
        if any(same_brand(row["brand"], b) for b in last_brands):
            drop("직전 회차 브랜드"); continue
        pre.append(row)
    # 후기 많은 순으로 상세를 보되 두 몰을 번갈아 — 한 몰이 후보를 다 차지하지 않게
    by_mall = {m: sorted((r for r in pre if r["mall"] == m), key=lambda r: -r["reviews"]) for m in BUILDERS}
    order = []
    while any(by_mall.values()):
        for m in BUILDERS:
            if by_mall[m]:
                order.append(by_mall[m].pop(0))

    out: list[dict] = []
    seen_nos: set[int] = set()
    per_brand: dict[str, int] = {}
    calls = 0
    for row in order:
        if len(out) >= limit or calls >= MAX_DETAIL_CALLS:
            break
        bkey = norm_brand(row["brand"])
        if per_brand.get(bkey, 0) >= MAX_PER_BRAND:
            drop(f"브랜드당 {MAX_PER_BRAND}개 초과(색상 변형 등)"); continue
        if row["no"] in seen_nos:
            drop("다른 몰과 번호 충돌"); continue
        calls += 1
        try:
            c = BUILDERS[row["mall"]](row["no"], handles)
        except malls.MallError:
            drop(f"{row['mall']} 상세 조회 실패"); continue
        if c["sold_out"]:
            drop("품절(상세)"); continue
        if not c["release_date"] or date.fromisoformat(c["release_date"]) < since:
            drop(f"신상 기준({since.isoformat()}) 미달"); continue
        if len(c["images"]) < 2:
            drop("사진 부족"); continue
        if not c["sale_price"]:
            drop("가격 없음"); continue
        if excluded_brand(today, c["brand"], c["brand_en"]) or any(same_brand(c["brand"], b) for b in last_brands):
            drop("제외·직전 회차 브랜드(상세)"); continue
        c["query"] = row["query"]
        out.append(c)
        seen_nos.add(c["goodsNo"])
        per_brand[bkey] = per_brand.get(bkey, 0) + 1

    for c in out:
        c["cheaper_elsewhere"] = cheaper_elsewhere(c)

    result = {"folder": folder, "collected_at": config.now_kst().isoformat(timespec="minutes"),
              "queries": queries, "gf": gf, "new_since": since.isoformat(),
              "notes": notes, "dropped": dropped, "candidates": out}
    ep_dir = config.episode_dir(folder)
    ep_dir.mkdir(parents=True, exist_ok=True)
    (ep_dir / "candidates.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    for c in out:
        contact_sheet(c, config.WORK_DIR / folder / "sheets" / f"{c['goodsNo']}.jpg")
    return result


def summary(result: dict) -> str:
    lines = [f"후보 {len(result['candidates'])}종 · 제외 {result['dropped']}",
             f"사진 시트: {config.WORK_DIR / result['folder'] / 'sheets'}"]
    lines += [f"※ {n}" for n in result.get("notes", [])]
    for c in result["candidates"]:
        flag = "★로스터" if c["roster"] else ("핸들✓" if c["handle"] else "핸들?")
        alt = c.get("cheaper_elsewhere")
        alt_s = f" | ⚠️{alt['mall']}이 {alt['sale_price']:,}원으로 더 쌈({alt['goodsNo']})" if alt else ""
        lines.append(
            f"- [{c['mall']}] {c['goodsNo']} {c['brand']} | {c['name'][:36]} | {c['sale_price']:,}원"
            f"({c['discount']}%) | 후기 {c['review_count']} ⭐{c['rating']} | 개시 {c['release_date']}"
            f" {c['season']} | 인용가능 {len(c['quotes'])} | 사진 {len(c['images'])} | {flag}{alt_s}")
    return "\n".join(lines)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="오늘의 신호·후보 상품 수집")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("signals")
    c = sub.add_parser("candidates")
    c.add_argument("--folder", required=True)
    c.add_argument("-q", "--query", action="append", required=True)
    c.add_argument("--gf", default="A", choices=["A", "F", "M"])
    c.add_argument("--limit", type=int, default=30)
    args = ap.parse_args(argv)
    if args.cmd == "signals":
        print(signals())
    else:
        print(summary(candidates(args.folder, args.query, args.gf, args.limit)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
