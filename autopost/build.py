"""episode.json(세션이 쓴 선택·문구) + candidates.json(몰 사실) → 검사 → 사진 내려받기 → 렌더 → 캡션·미리보기·result.md.

    python -m autopost.build "20261002 가을 니트"

사실(가격·할인·후기 수·평점·인용문 원문)은 전부 candidates.json에서 코드가 넣는다 — 세션이 숫자나 인용문을 옮겨 적지 않는다.
끝나면 status.json에 stage(built|invalid)와 fingerprint를 남긴다. 이후 무엇이든 바뀌면 verify·publish가 거부한다.
종료 코드: 0 = 렌더 완료·error 없음 / 1 = error 있음.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import sys

import requests

from . import config, malls, rules
from .state import fingerprint, load_handles, load_history, load_status, save_status

_TAG_TOKENS = {"&lt;em&gt;": "<em>", "&lt;/em&gt;": "</em>", "&lt;br&gt;": "<br>"}


def rich(s: str) -> str:
    """이스케이프 후 <em>·<br>만 되살린다."""
    out = html.escape(rules.norm_br(s or ""), quote=True)
    for k, v in _TAG_TOKENS.items():
        out = out.replace(k, v)
    return out


def won(n: int) -> str:
    return f"{n:,}원"


def latest_zzal():
    files = sorted(p for p in config.ZZAL_DIR.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    if not files:
        raise SystemExit(f"CTA 짤이 없습니다: {config.ZZAL_DIR}")
    return files[-1]  # 파일명이 YYYYMMDD — git 체크아웃은 수정일을 보존하지 않아 이름으로 고른다


def download(url: str, path) -> None:
    if path.exists() and path.stat().st_size > 0:
        return
    r = requests.get(url, headers=malls.HEADERS, timeout=60)
    r.raise_for_status()
    path.write_bytes(r.content)


def enrich(ep: dict, cands: dict) -> list[dict]:
    """후보 사실 + 세션 선택. 세션 쪽은 허용 키만 섞는다 — 가격·인용 원문을 덮어쓰지 못하게."""
    by_no = {str(c["goodsNo"]): c for c in cands["candidates"]}
    rows = []
    for p in ep["products"]:
        c = by_no[str(p["goodsNo"])]
        row = {**c, **{k: v for k, v in p.items() if k in config.PRODUCT_KEYS}}
        row.pop("quote_text", None)
        if p.get("quote_no") is not None:
            q = next(q for q in c["quotes"] if str(q["no"]) == str(p["quote_no"]))
            row["quote_text"] = q["text"]
        else:
            row["quote_text"] = None
        rows.append(row)
    return rows


def asset_name(prefix: str, goods_no, index: int) -> str:
    return f"{prefix}-{goods_no}-{index}.jpg"  # 사진 번호를 바꾸면 파일도 바뀐다


def card_dicts(ep: dict, prods: list[dict], cover_cand: dict, zzal_rel: str) -> list[dict]:
    cover = ep["cover"]
    cards = [{"kind": "cover", "img": "assets/" + asset_name("cover", cover_cand["goodsNo"], cover["image"]),
              "pos": cover.get("pos", "50% 20%"), "kicker": html.escape(cover.get("kicker", "")),
              "title": rich(cover["title"]), "sub": rich(cover.get("sub", ""))}]
    for i, p in enumerate(prods, 1):
        if p["review_count"] and p.get("rating"):
            proof = f"후기 {p['review_count']:,}개 · ⭐ {p['rating']}"
        else:
            proof = f"후기 {p['review_count']:,}개" + (f" · {p['season']}" if p.get("season") else "")
        if p.get("quote_text"):
            sp = f"“{html.escape(p['quote_text'])}” —&nbsp;실제&nbsp;후기"
        else:
            sp = f"{html.escape(p['spec_line'])} —&nbsp;상세&nbsp;페이지&nbsp;표기"
        name = html.escape(p.get("display_name") or p["name"])
        color = html.escape(p.get("color", ""))
        cards.append({
            "kind": "item", "img": "assets/" + asset_name(f"{i:02d}", p["goodsNo"], p["image"]),
            "pos": p.get("pos", "50% 18%"),
            "prod": f"{html.escape(p['brand'])} · <b>{name}</b>{(' ' + color) if color else ''}",
            "title": rich(p["headline"]), "mall": "무신사",
            "normal": won(p["normal_price"]), "sale": won(p["sale_price"]),
            "off": f"{p['discount']}%" if p["discount"] else "", "proof": proof, "sp": sp})
    cta = ep["cta"]
    cards.append({"kind": "cta", "img": zzal_rel, "title": rich(cta["title"]), "sub": rich(cta.get("sub", ""))})
    return cards


def caption_text(ep: dict, prods: list[dict], handles: dict) -> tuple[str, list[str]]:
    lines, skipped = rules.brand_lines(prods, handles)
    body = ep["caption"].strip()
    if lines:
        body += "\n\n📌 브랜드 계정\n" + "\n".join(lines)
    return body, skipped


def preview_html(folder: str, caption: str, issues: list) -> str:
    imgs = "".join(f'<img src="{i}.jpg?t=0" alt="{i}">' for i in range(1, 8))
    warn = "".join(f"<li class={lvl}>{html.escape(msg)}</li>" for lvl, msg in issues)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(folder)}</title>
<style>body{{margin:0;background:#141416;color:#e8e5de;font-family:system-ui,sans-serif;padding:24px 16px}}
h1{{font-size:18px}}.g{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
img{{width:100%;display:block}}pre{{white-space:pre-wrap;background:#1e1e21;padding:16px;line-height:1.7}}
li.error{{color:#ff6b81}}li.warn{{color:#ffd166}}</style></head><body>
<h1>{html.escape(folder)} — 미리보기</h1><ul>{warn}</ul><div class="g">{imgs}</div>
<h2>캡션</h2><pre>{html.escape(caption)}</pre>
<script>document.querySelectorAll('img').forEach(i=>i.src=i.src.replace(/\\?t=0$/,'?t='+Date.now()))</script>
</body></html>"""


def result_md(ep: dict, prods: list[dict], issues: list, skipped: list[str]) -> str:
    rows = "\n".join(
        f"| {i} | {p['brand']} | {p.get('display_name') or p['name']} ({p['goodsNo']}) | {p['sale_price']:,} | "
        f"{p['normal_price']:,} | {p['discount']}% | {p['review_count']} | {p.get('rating') or '—'} | "
        f"{p['release_date']} {p.get('season', '')} | {'인용' if p.get('quote_text') else '스펙'} | "
        f"{('@' + p['handle']) if p.get('handle') else '(태그 안 함)'}{' ★로스터' if p.get('roster') else ''} |"
        for i, p in enumerate(prods, 1))
    warns = "\n".join(f"- [{lvl}] {msg}" for lvl, msg in issues) or "- 없음"
    return f"""# 실험 로그 — {ep['folder']}

> 자동 제작(claude/autopost-data · autopost). 양식: RESULT-TEMPLATE.md. 숫자는 무신사 상세 API 기준(쿠폰 미적용가).

## 1. 실험 설계 (게시 전)
- **실험 번호**: #5 (브랜드 반응·공유)
- **키워드**: {ep['keyword']} — 시즌어 '{ep['season_word']}' · 품목어 '{ep['item_word']}'
- **수요 근거**: {ep.get('demand_evidence', '')}
- **축**: {ep.get('axis', '')}
- **가설**: {ep.get('hypothesis', '')}
- **바꾼 변수 (1개만)**: {ep.get('changed_variable', '')}
- **대조군**: {ep.get('control', '')}
- **판정 기준**: +72h 도달 200 이상 + 공유 1건 이상 · 유입 '기타' 비중 참고
- **캡션 무드**: {ep.get('mood', '')}

## 2. 게시 전 검증
- 자동 검사 결과:
{warns}
- 태그에서 뺀 브랜드(핸들 미검증): {', '.join(skipped) or '없음'}

| # | 브랜드 | 상품 | 판매가 | 정가 | 할인 | 후기 | 평점 | 판매 개시 | 근거 | 핸들 |
|---|---|---|---:|---:|---:|---:|---:|---|---|---|
{rows}

## 3. 게시 정보
- (게시 후 publish가 채운다)

## 4. 측정값 — 게시 +72시간
- (measure가 채운다)
"""


def build(folder: str) -> dict:
    ep_dir = config.episode_dir(folder)
    prev = load_status(folder)
    if prev.get("stage") in ("posted", "publishing"):
        raise SystemExit(f"이미 게시(중)인 회차입니다 — 다시 렌더하지 않습니다. stage={prev.get('stage')}")
    ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    cands = json.loads((ep_dir / "candidates.json").read_text(encoding="utf-8"))
    history, handles = load_history(), load_handles()
    today = config.now_kst().date()
    issues = rules.check_episode(ep, cands, history, handles, today)
    if ep.get("folder") != folder:
        issues.append(("error", f"episode.json의 folder '{ep.get('folder')}'가 실행한 폴더와 다름"))
    report = {"folder": folder, "issues": issues, "rendered": False}
    # 이전 렌더·검증은 무효 — 이번 결과로 덮는다
    status = {"stage": "invalid", "built_at": config.now_kst().isoformat(timespec="seconds"), "issues": issues}
    if any(lvl == "error" for lvl, _ in issues):
        save_status(folder, status)
        return report

    prods = enrich(ep, cands)
    by_no = {str(c["goodsNo"]): c for c in cands["candidates"]}
    cover_cand = by_no[str(ep["cover"]["goodsNo"])]
    assets = ep_dir / "assets"
    assets.mkdir(exist_ok=True)
    download(cover_cand["images"][ep["cover"]["image"]],
             assets / asset_name("cover", cover_cand["goodsNo"], ep["cover"]["image"]))
    for i, p in enumerate(prods, 1):
        download(p["images"][p["image"]], assets / asset_name(f"{i:02d}", p["goodsNo"], p["image"]))
    zz = latest_zzal()
    shutil.copyfile(zz, assets / f"zzal{zz.suffix.lower()}")

    from .render import render  # Playwright는 렌더할 때만 필요
    cards = card_dicts(ep, prods, cover_cand, f"assets/zzal{zz.suffix.lower()}")
    shots = render(cards, ep_dir, ep_dir)
    for s in shots:
        if s["text_ratio"] is not None and s["text_ratio"] > config.TEXT_BLOCK_MAX_RATIO:
            issues.append(("error", f"{s['index']}번 카드 텍스트 블록이 {s['text_ratio']:.0%} — 35% 이하로 줄일 것(§4)"))
    if shots and not shots[0]["font_ok"]:
        issues.append(("warn", "Pretendard 폰트 로드 확인 실패 — 렌더 이미지 글꼴을 눈으로 확인"))

    caption, skipped = caption_text(ep, prods, handles)
    if skipped:
        issues.append(("warn", f"핸들 미검증으로 태그에서 뺀 브랜드: {', '.join(skipped)}"))
    (ep_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    (ep_dir / "_preview.html").write_text(preview_html(folder, caption, issues), encoding="utf-8")
    (ep_dir / "result.md").write_text(result_md(ep, prods, issues, skipped), encoding="utf-8")
    ok = not any(lvl == "error" for lvl, _ in issues)
    status.update(stage="built" if ok else "invalid", issues=issues, shots=shots,
                  fingerprint=fingerprint(folder))
    save_status(folder, status)
    report.update(rendered=True, shots=shots, caption=caption, skipped=skipped)
    return report


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="회차 렌더·검사")
    ap.add_argument("folder")
    args = ap.parse_args(argv)
    rep = build(args.folder)
    for lvl, msg in rep["issues"]:
        print(f"[{lvl}] {msg}")
    if rep["rendered"]:
        for s in rep["shots"]:
            ratio = s["text_ratio"]
            print(f"{s['file']} 텍스트 블록 {'—' if ratio is None else format(ratio, '.0%')}")
        print("\n--- caption.txt ---\n" + rep["caption"])
    sys.exit(1 if any(lvl == "error" for lvl, _ in rep["issues"]) else 0)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
