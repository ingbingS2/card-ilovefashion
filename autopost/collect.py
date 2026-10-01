"""오늘의 신호 요약 + 키워드 후보 상품 수집.

    python -m autopost.collect signals
    python -m autopost.collect candidates --folder "20261002 가을 니트" -q "가을 니트" -q "니트 가디건" [--gf F]

candidates는 신상·재고·제외 브랜드·직전 회차 브랜드를 걸러 `episodes/<folder>/candidates.json`을 쓰고,
상품마다 사진 번호를 붙인 시트(`.autopost-work/<folder>/sheets/<goodsNo>.jpg`)를 만든다 — 세션이 보고 고른다.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from datetime import date

import requests

from . import config, malls, rules
from .state import excluded_brand, find_handle, load_handles, load_history, norm_brand, posted, same_brand

WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
MAX_PER_BRAND = 2      # 한 브랜드의 색상 변형이 후보를 다 채우지 않게
MAX_DETAIL_CALLS = 80  # 상세·후기 조회 상한 (몰 API 연속 호출 매너)


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


# ---------- candidates ----------

def build_candidate(goods_no, handles: dict) -> dict:
    d = malls.detail(goods_no)
    revs, total = malls.reviews(goods_no)
    brand = (d.get("brandInfo") or {}).get("brandName") or d.get("brand", "")
    quotes = []
    for r in revs:
        text = rules.flatten_quote(r.get("content", ""))
        if rules.quote_problem(text, r.get("grade"), r.get("type", "")) is None:
            quotes.append({"no": r.get("no"), "text": text, "grade": int(r.get("grade")),
                           "likes": r.get("likeCount", 0), "date": (r.get("createDate") or "")[:10]})
    rd = malls.release_date(d)
    images = []
    for img in d.get("goodsImages") or []:
        url = malls.full_image_url(img.get("imageUrl", ""))
        if url not in images:
            images.append(url)
    entry = find_handle(handles, brand, (d.get("brandInfo") or {}).get("brandEnglishName", ""),
                        d.get("brand", ""))
    spec = malls.strip_html(" ".join(str(d.get(k) or "") for k in ("specDesc", "headDesc")))
    return {
        "goodsNo": int(d["goodsNo"]),
        "url": f"https://www.musinsa.com/products/{d['goodsNo']}",
        "brand": brand,
        "brand_en": (d.get("brandInfo") or {}).get("brandEnglishName", ""),
        "brand_id": d.get("brand", ""),
        "name": d.get("goodsNm", ""),
        "genders": d.get("genders") or d.get("sex") or [],
        "category": " > ".join(filter(None, [(d.get("category") or {}).get("categoryDepth1Name"),
                                             (d.get("category") or {}).get("categoryDepth2Name")])),
        **malls.price_facts(d),
        **malls.review_summary(d),
        "review_total_listed": total,
        "sold_out": bool(d.get("isOutOfStock")),
        "release_date": rd.isoformat() if rd else None,
        "season": malls.season_label(d),
        "style_no": d.get("styleNo") or "",
        "material": malls.material_facts(d),
        "spec_text": spec[:4000],
        "images": images,
        "quotes": sorted(quotes, key=lambda q: -q["likes"])[:8],
        "roster": bool(entry and entry.get("roster")),
        "handle": entry.get("handle") if entry and entry.get("verified") else None,
    }


def contact_sheet(cand: dict, path) -> None:
    """사진에 0,1,2… 번호를 붙인 한 장짜리 시트 (Pillow). 세션이 Read로 보고 image 인덱스를 고른다."""
    from PIL import Image, ImageDraw

    thumbs = []
    for url in cand["images"][:8]:
        try:
            small = url.replace("_big.", "_500.")
            r = requests.get(small, headers=malls.HEADERS, timeout=30)
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
    draw.text((8, 8), f"goodsNo {cand['goodsNo']}", fill="black")  # 기본 폰트는 한글을 못 그린다
    for i, im in enumerate(thumbs):
        x, y = (i % cols) * 300, (i // cols) * 360 + 40
        sheet.paste(im, (x, y))
        draw.rectangle([x, y, x + 34, y + 30], fill="black")
        draw.text((x + 10, y + 8), str(i), fill="yellow")
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path, quality=80)


def candidates(folder: str, queries: list[str], gf: str = "A", limit: int = 30) -> dict:
    today = config.now_kst().date()
    since = config.new_since(today)
    handles = load_handles()
    hist = posted(load_history())
    last_brands = hist[-1].get("brands", []) if hist else []

    pool: dict[int, dict] = {}
    for q in queries:
        for row in malls.search(q, gf=gf):
            no = int(row["goodsNo"])
            if no not in pool:
                pool[no] = {**row, "_query": q}
    dropped: dict[str, int] = {}

    def drop(reason: str):
        dropped[reason] = dropped.get(reason, 0) + 1

    pre = []
    for row in pool.values():
        if row.get("isSoldOut"):
            drop("품절"); continue
        if row.get("isAd"):
            drop("광고"); continue
        if excluded_brand(today, row.get("brandName", ""), row.get("brand", "")):
            drop("일시 제외 브랜드"); continue
        if any(same_brand(row.get("brandName", ""), b) for b in last_brands):
            drop("직전 회차 브랜드"); continue
        pre.append(row)
    # 후기 많은 순으로 상세를 본다(상세 호출 수 제한)
    pre.sort(key=lambda r: -(r.get("reviewCount") or 0))

    out = []
    per_brand: dict[str, int] = {}
    calls = 0
    for row in pre:
        if len(out) >= limit:
            break
        bkey = norm_brand(row.get("brandName", ""))
        if per_brand.get(bkey, 0) >= MAX_PER_BRAND:
            drop(f"브랜드당 {MAX_PER_BRAND}개 초과(색상 변형 등)"); continue
        if calls >= MAX_DETAIL_CALLS:
            break
        calls += 1
        try:
            c = build_candidate(row["goodsNo"], handles)
        except malls.MallError:
            drop("상세 조회 실패"); continue
        if c["sold_out"]:
            drop("품절(상세)"); continue
        if not c["release_date"] or date.fromisoformat(c["release_date"]) < since:
            drop(f"신상 기준({since.isoformat()}) 미달"); continue
        if len(c["images"]) < 2:
            drop("사진 부족"); continue
        if not c["sale_price"]:
            drop("가격 없음"); continue
        c["query"] = row["_query"]
        out.append(c)
        per_brand[bkey] = per_brand.get(bkey, 0) + 1

    result = {"folder": folder, "collected_at": config.now_kst().isoformat(timespec="minutes"),
              "queries": queries, "gf": gf, "new_since": since.isoformat(),
              "dropped": dropped, "candidates": out}
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
    for c in result["candidates"]:
        flag = "★로스터" if c["roster"] else ("핸들✓" if c["handle"] else "핸들?")
        lines.append(
            f"- {c['goodsNo']} {c['brand']} | {c['name'][:38]} | {c['sale_price']:,}원"
            f"({c['discount']}%) | 후기 {c['review_count']} ⭐{c['rating']} | 개시 {c['release_date']}"
            f" {c['season']} | 인용가능 {len(c['quotes'])} | 사진 {len(c['images'])} | {flag}")
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
