"""KEYWORD-POLICY를 코드로 강제할 수 있는 부분 — 전부 순수 함수.

check_episode()는 세션이 쓴 episode.json을 후보 데이터(candidates.json)와 대조한다.
error가 하나라도 있으면 build가 렌더하지 않는다. warn은 승인 요청 메시지에 그대로 보여준다.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from . import config
from .state import excluded_brand, find_handle, posted, same_brand, same_keyword

_BODY_MEASURE = re.compile(r"(\d{2,3}\s*(cm|kg|키로|센치))|(키\s*\d{3})|(몸무게)|(\d{2,3}\s*/\s*\d{2,3})",
                           re.I)
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_BR = re.compile(r"<br\s*/?>", re.I)
_ALLOWED_TAGS = re.compile(r"</?em>|<br>")
_POS = re.compile(r"^\d{1,3}% \d{1,3}%$")
_SPEC_TOKEN = re.compile(r"(\d+(?:\.\d+)?)\s*(cm|mm|kg|g|%|인치)?", re.I)


# ---------- 후기 인용 (§3) ----------

def quote_problem(text: str, grade, review_type: str = "") -> str | None:
    """통으로 실을 수 있는 후기인지. 문제가 있으면 이유, 없으면 None."""
    t = (text or "").strip()
    if review_type == "experience":
        return "체험단 후기"
    try:
        if int(grade) < config.QUOTE_MIN_GRADE:
            return f"별점 {grade}"
    except (TypeError, ValueError):
        return "별점 없음"
    n = len(t)
    if n < config.QUOTE_MIN_LEN or n > config.QUOTE_MAX_LEN:
        return f"길이 {n}자 (40~120)"
    for word in config.QUOTE_BANNED:
        if word in t:
            return f"금지어 '{word}'"
    if _BODY_MEASURE.search(t):
        return "신체 치수"
    return None


def flatten_quote(text: str) -> str:
    """줄바꿈만 공백으로 — 띄어쓰기·오타·구어체는 고치지 않는다(§3)."""
    return re.sub(r"\s*\n\s*", " ", (text or "").strip())


# ---------- 텍스트 유틸 ----------

def norm_br(html: str) -> str:
    return _BR.sub("<br>", html or "")


def plain(html: str) -> str:
    return re.sub(r"<[^>]+>", "", norm_br(html).replace("<br>", " ")).strip()


def disallowed_tags(html: str) -> list[str]:
    return [t for t in re.findall(r"<[^>]+>", norm_br(html)) if not _ALLOWED_TAGS.fullmatch(t)]


def first_sentence(caption: str) -> str:
    """캡션 첫 줄(첫 문장은 한 줄로 따로 쓴다 — 지난 회차 캡션 전부 그 형식)."""
    first = (caption or "").strip().split("\n", 1)[0]
    return re.split(r"(?<=[.!?])\s", first, maxsplit=1)[0]


def emoji_count(text: str) -> int:
    return len(_EMOJI.findall(text or ""))


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def spec_missing(spec_line: str, source: str) -> list[str]:
    """spec_line의 숫자(+단위)가 상세 텍스트에 그대로 있는지 — '6cm'가 '62cm'에 묻어가지 않게 경계 검사."""
    missing = []
    for num, unit in _SPEC_TOKEN.findall(spec_line or ""):
        pat = rf"(?<![\d.]){re.escape(num)}(?![\d])"
        if unit:
            pat += rf"\s*{re.escape(unit)}"
        if not re.search(pat, source or "", re.I):
            missing.append(num + (unit or ""))
    return missing


# ---------- 회차 검사 ----------

def zzal_last_used(file: str, zzal_index: dict, history: list[dict]) -> date | None:
    """목록의 last_used와 게시 이력(history.zzal) 중 가장 최근 날짜."""
    dates = []
    for z in zzal_index.get("zzal", []):
        if z.get("file") == file and z.get("last_used"):
            dates.append(date.fromisoformat(z["last_used"]))
    for h in history:
        if h.get("zzal") == file and h.get("posted_at"):
            dates.append(date.fromisoformat(h["posted_at"][:10]))
    return max(dates) if dates else None


def check_zzal(cta: dict, zzal_index: dict, history: list[dict], today: date) -> list[tuple[str, str]]:
    issues = []
    f = cta.get("zzal")
    if not f:
        return [("error", "CTA 짤(cta.zzal)을 CARD/zzal/index.json에서 골라 적을 것")]
    if "/" in f or "\\" in f or not (config.ZZAL_DIR / f).is_file():
        return [("error", f"CTA 짤 파일이 CARD/zzal에 없음: {f}")]
    if not any(z.get("file") == f for z in zzal_index.get("zzal", [])):
        issues.append(("warn", f"짤 {f}가 index.json 목록에 없음 — 자막·장면을 보고 항목을 추가할 것"))
    last = zzal_last_used(f, zzal_index, history)
    if last and (today - last).days < config.ZZAL_COOLDOWN_DAYS:
        issues.append(("error", f"짤 {f}는 {last.isoformat()}에 썼음 — {config.ZZAL_COOLDOWN_DAYS}일 안에 반복 금지"))
    return issues


def check_episode(ep: dict, cands: dict, history: list[dict], handles: dict,
                  today: date, zzal_index: dict | None = None) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    err = lambda m: issues.append(("error", m))
    warn = lambda m: issues.append(("warn", m))

    by_no = {str(c["goodsNo"]): c for c in cands.get("candidates", [])}
    season, item = nfc(ep.get("season_word", "")), nfc(ep.get("item_word", ""))
    keyword = nfc(ep.get("keyword", ""))
    hist = posted(history)

    # 키워드 (§1)
    if not season or not item:
        err("season_word·item_word가 비어 있음")
    if season and item and (season not in keyword or item not in keyword):
        err(f"keyword '{keyword}'에 시즌어 '{season}'·품목어 '{item}'가 글자 그대로 없음")
    if any(w in keyword.lower() for w in config.RANKING_WORDS):
        err("랭킹 키워드 금지(§1)")
    if not ep.get("folder", "").endswith(keyword) or not re.match(r"^\d{8} ", ep.get("folder", "")):
        err("folder는 'YYYYMMDD 키워드' 형식이어야 함")
    if any(same_keyword(h.get("keyword", ""), keyword) for h in hist[-10:]):
        err(f"최근 10회차에 같은 키워드 '{keyword}'가 있음")

    # 상품 5종
    prods = ep.get("products") or []
    if len(prods) != config.PRODUCTS_PER_POST:
        err(f"상품은 {config.PRODUCTS_PER_POST}종이어야 함 (현재 {len(prods)})")
    nos = [str(p.get("goodsNo")) for p in prods]
    if len(set(nos)) != len(nos):
        err("같은 상품이 두 번 들어감")
    brands = []
    since = config.new_since(today)
    last_brands = hist[-1].get("brands", []) if hist else []
    roster_count = 0
    card_images = set()
    em_lines = []
    for i, p in enumerate(prods, 1):
        tag = f"{i}번({p.get('goodsNo')})"
        extra = set(p) - config.PRODUCT_KEYS
        if extra:
            err(f"{tag}: episode.json에 쓸 수 없는 키 {sorted(extra)} — 가격·후기·인용 원문은 코드가 채운다")
        c = by_no.get(str(p.get("goodsNo")))
        if not c:
            err(f"{tag}: candidates.json에 없는 상품 — collect로 수집한 것만 쓴다")
            continue
        brands.append(c["brand"])
        if c.get("sold_out"):
            err(f"{tag}: 품절")
        rd = c.get("release_date")
        if not rd or date.fromisoformat(rd) < since:
            err(f"{tag}: 신상 기준({since.isoformat()} 이후) 미달 — 판매 개시 {rd}")
        why = excluded_brand(today, c["brand"], c.get("brand_en", ""))
        if why:
            err(f"{tag}: {why}")
        if any(same_brand(c["brand"], b) for b in last_brands):
            err(f"{tag}: {c['brand']}는 직전 회차에도 있었음(연속 금지)")
        entry = find_handle(handles, c["brand"], c.get("brand_en", ""), c.get("brand_id", ""))
        if entry and entry.get("roster"):
            roster_count += 1
        alt = c.get("cheaper_elsewhere")
        if alt:
            warn(f"{tag}: 같은 상품이 {alt['mall']}에서 {alt['sale_price']:,}원으로 더 쌈 — 가격·이미지 출처는 "
                 f"저렴한 몰(§2). {alt['mall']} 후보({alt['goodsNo']})로 바꾸는 것을 검토")
        if any(b in c["brand"] for b in config.BIG_ACCOUNTS):
            warn(f"{tag}: {c['brand']}는 대형 계정 — 브랜드 반응 기대치 낮음")

        img = p.get("image")
        if not isinstance(img, int) or isinstance(img, bool) or not 0 <= img < len(c.get("images", [])):
            err(f"{tag}: image 인덱스가 범위 밖")
        else:
            card_images.add(c["images"][img])
        if p.get("pos") is not None and not _POS.match(str(p["pos"])):
            err(f"{tag}: pos는 '50% 18%' 형식")

        head = norm_br(p.get("headline", ""))
        bad = disallowed_tags(head)
        if bad:
            err(f"{tag}: 헤드라인에 허용되지 않은 태그 {bad} (<em>·<br>만)")
        if head.count("<br>") > 1 or len(plain(head)) > 32:
            err(f"{tag}: 헤드라인이 너무 김(2줄·32자 이하)")
        for em in re.findall(r"<em>(.*?)</em>", head):
            if len(em.strip()) < 2:
                err(f"{tag}: 조사·어미만 강조함(<em>{em}</em>)")
        lines = head.split("<br>")
        em_lines.append(next((j for j, ln in enumerate(lines) if "<em>" in ln), -1))
        for k in ("display_name", "color"):
            if re.search(r"[<>]", str(p.get(k, ""))):
                err(f"{tag}: {k}에 태그 문자")

        has_quote = p.get("quote_no") is not None
        has_spec = bool(p.get("spec_line"))
        if has_quote == has_spec:
            err(f"{tag}: quote_no와 spec_line 중 정확히 하나만")
        if has_quote and not any(str(q["no"]) == str(p["quote_no"]) for q in c.get("quotes", [])):
            err(f"{tag}: quote_no {p['quote_no']}가 인용 가능 후기 목록에 없음")
        if has_spec:
            source = " ".join([c.get("spec_text", ""), " ".join(c.get("material", [])), c.get("name", "")])
            missing = spec_missing(p["spec_line"], source)
            if missing:
                err(f"{tag}: spec_line의 {missing}가 상세 페이지 텍스트에 없음(추측 금지 §3)")
            if c.get("quotes"):
                warn(f"{tag}: 인용 가능한 후기가 있는데 스펙으로 대체함")

    if prods and roster_count != 1:
        warn(f"로스터 브랜드가 {roster_count}곳 — 기준은 로스터 1 + 신규 4 (§2)")
    if any(same_brand(a, b) for i, a in enumerate(brands) for b in brands[i + 1:]):
        err("한 회차에 같은 브랜드가 두 번")
    if len(em_lines) == 5 and len(set(em_lines)) == 1:
        warn("다섯 헤드라인의 강조가 모두 같은 줄 — 기계적으로 보임(§3)")

    # 표지 (§1·§3·§4)
    cover = ep.get("cover") or {}
    extra = set(cover) - config.COVER_KEYS
    if extra:
        err(f"표지에 쓸 수 없는 키 {sorted(extra)}")
    title = plain(cover.get("title", ""))
    if season not in title or item not in title:
        err(f"표지 헤드라인에 '{season}'·'{item}'가 한글 그대로 없음")
    for k in ("title", "sub"):
        if disallowed_tags(cover.get(k, "")):
            err(f"표지 {k}에 허용되지 않은 태그")
    if re.search(r"[<>]", cover.get("kicker", "")):
        err("표지 kicker에 태그 문자")
    if cover.get("pos") is not None and not _POS.match(str(cover["pos"])):
        err("표지 pos는 '50% 20%' 형식")
    cc = by_no.get(str(cover.get("goodsNo")))
    if str(cover.get("goodsNo")) not in nos:
        err("표지 상품은 5종 중 하나여야 함 — 한 상품의 다른 컷을 표지로(§4)")
    if cc:
        ci = cover.get("image")
        if not isinstance(ci, int) or isinstance(ci, bool) or not 0 <= ci < len(cc.get("images", [])):
            err("표지 image 인덱스가 범위 밖")
        elif cc["images"][ci] in card_images:
            err("표지 사진이 상품 카드 사진과 같은 원본(§4)")

    # 캡션 (§5) — 브랜드 목록은 build가 붙인다
    cap = nfc(ep.get("caption", ""))
    fs = first_sentence(cap)
    if season not in fs or item not in fs:
        err(f"캡션 첫 문장에 '{season}'·'{item}'가 없음: {fs[:40]}")
    if "#" in cap:
        err("해시태그 금지(§5)")
    if "@" in cap or "📌" in cap:
        err("캡션 본문에 @멘션/📌 — 브랜드 목록은 build가 자동으로 붙인다")
    for w in config.CAPTION_BANNED:
        if w in cap.lower():
            err(f"캡션 금지 표현 '{w}'")
    n = emoji_count(cap)
    if not 3 <= n <= 5:
        warn(f"캡션 이모지 {n}개 (기준 3~5)")
    if any(h.get("caption_first", "")[:6] == fs[:6] for h in hist[-3:] if h.get("caption_first")):
        warn("캡션 첫 문장이 최근 회차와 같은 패턴으로 시작")
    if ep.get("mood") and hist and hist[-1].get("mood") == ep.get("mood"):
        warn(f"캡션 무드 '{ep['mood']}'가 직전 회차와 같음(§5 연속 금지)")

    cta = ep.get("cta") or {}
    if set(cta) - config.CTA_KEYS:
        err(f"CTA에 쓸 수 없는 키 {sorted(set(cta) - config.CTA_KEYS)}")
    if not cta.get("title"):
        err("CTA 카드 문구가 없음")
    for k in ("title", "sub"):
        if disallowed_tags(cta.get(k, "")):
            err(f"CTA {k}에 허용되지 않은 태그")
    if zzal_index is not None:
        issues.extend(check_zzal(cta, zzal_index, hist, today))
    return issues


def brand_lines(prods: list[dict], handles: dict) -> tuple[list[str], list[str]]:
    """카드 순서대로 '브랜드명 @핸들'. 검증된 핸들이 없는 브랜드는 빼고 사유를 돌려준다(§5·§6)."""
    lines, skipped = [], []
    for p in prods:
        entry = find_handle(handles, p["brand"], p.get("brand_en", ""), p.get("brand_id", ""))
        if entry and entry.get("verified") and entry.get("handle"):
            lines.append(f"{entry['name']} @{entry['handle'].lstrip('@')}")
        else:
            skipped.append(p["brand"])
    return lines, skipped
