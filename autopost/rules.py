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
# 캡션 소재·세탁 표현(§2 '소재·스펙은 상세 페이지에서 확인한 것만'). 긴 표현을 앞에 둬 '울 세탁'이 '울'·'세탁'으로
# 쪼개지지 않게. '면'·'울'은 앞뒤가 한글이 아닐 때만(앞면·측면·화면·면접·입으면·겨울·서울·어울리는 제외).
_FACT_TERM = re.compile(
    r"드라이\s*[클크]리닝|울\s*세탁|손세탁|세탁|캐시미어|알파카|모헤어|폴리|나일론|레이온|아크릴|린넨|리넨|혼용|코튼"
    r"|(?<![가-힣])면(?:(?![가-힣])|(?=소재|혼방|혼용|원단))"
    r"|(?<![가-힣])울(?:(?![가-힣])|(?=소재|혼방|혼용|원단|니트|로|이|과|은|의|을|처럼))")
_FACT_SYNONYMS = {
    "면": ("면", "순면", "코튼", "cotton"), "코튼": ("면", "순면", "코튼", "cotton"),
    "울": ("울", "wool", "양모", "메리노", "램스울", "모~"), "캐시미어": ("캐시미어", "cashmere"), "알파카": ("알파카", "alpaca"),
    "모헤어": ("모헤어", "mohair"), "폴리": ("폴리", "polyester"), "나일론": ("나일론", "nylon", "폴리아미드"),
    "레이온": ("레이온", "rayon", "viscose", "비스코스"), "아크릴": ("아크릴", "acrylic"),
    "린넨": ("린넨", "리넨", "linen"), "리넨": ("린넨", "리넨", "linen"),
    "드라이클리닝": ("드라이클리닝", "드라이크리닝", "dryclean"), "드라이크리닝": ("드라이클리닝", "드라이크리닝", "dryclean"),
}
_CHEAPER_CLAIM = re.compile(r"저렴한\s*쪽|더\s*저렴|최저가|싼\s*쪽|더\s*싼(?!티)")


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


def detail_text(c: dict, fields: tuple[str, ...] = ("spec_text", "material", "name")) -> str:
    """후보의 상세 원문을 한 문자열로 — material이 목록이든 문자열이든, spec_text가 None이든 숫자 대조가 깨지지 않게."""
    parts = []
    for k in fields:
        v = c.get(k)
        if isinstance(v, (list, tuple)):
            parts.extend(str(x) for x in v if x)
        elif v:
            parts.append(str(v))
    return " ".join(parts)


def fact_terms_missing(caption: str, source: str) -> list[str]:
    """캡션의 소재·세탁 표현 중 상세 원문에 없는 것. 동의어(면=코튼=cotton)·띄어쓰기 차이는 같은 것으로 본다."""
    flat = re.sub(r"\s", "", source or "").lower()
    missing: list[str] = []
    for m in _FACT_TERM.finditer(caption or ""):
        term = re.sub(r"\s", "", m.group(0))
        if term in missing:
            continue
        found = False
        for s in _FACT_SYNONYMS.get(term, (term,)):
            if s in ("면", "울"):   # 원문에서도 '정면'·'겨울' 같은 단어 속 글자는 치지 않는다
                found = bool(re.search(rf"(?<![가-힣]){s}", source or ""))
            elif s == "모~":          # 혼용률 표기 '모 70%'·'모70%'(=울)
                found = bool(re.search(r"(?<![가-힣])모\s*\d", source or ""))
            else:
                found = s.lower() in flat
            if found:
                break
        if not found:
            missing.append(term)
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


def zzal_path(name: str):
    """짤 파일 위치 — 데이터 브랜치(인터넷에서 채택, autopost-data/zzal) 우선, 다음 저장소 CARD/zzal."""
    if not name or "/" in name or "\\" in name or name.startswith("."):
        return None
    for d in (config.ZZAL_WEB_DIR, config.ZZAL_DIR):
        p = d / name
        if p.is_file():
            return p
    return None


def check_zzal(cta: dict, zzal_index: dict, history: list[dict], today: date) -> list[tuple[str, str]]:
    issues = []
    f = cta.get("zzal")
    if not f:
        return [("error", "CTA 짤(cta.zzal)을 짤 목록에서 골라 적을 것")]
    if zzal_path(f) is None:
        return [("error", f"CTA 짤 파일이 CARD/zzal·autopost-data/zzal 어디에도 없음: {f}")]
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
    if re.search(config.RANKING_PATTERN, keyword, re.I):
        err("랭킹 키워드 금지(§1)")
    if not ep.get("folder", "").endswith(keyword) or not re.match(r"^\d{8} ", ep.get("folder", "")):
        err("folder는 'YYYYMMDD 키워드' 형식이어야 함")
    elif ep["folder"][:8] != today.strftime("%Y%m%d"):
        warn(f"folder 날짜({ep['folder'][:8]})가 오늘 KST({today.strftime('%Y%m%d')})가 아님 — 클라우드는 UTC 시계라 날짜를 KST로 잡을 것")
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
        if isinstance(alt, dict) and alt.get("unavailable"):
            warn(f"{tag}: 다른 몰 가격을 비교하지 못함(§2 최저가 확인 불가) — {alt['unavailable']}")
        elif alt:
            warn(f"{tag}: 같은 상품이 {alt['mall']}에서 {alt['sale_price']:,}원으로 더 쌈 — 가격·이미지 출처는 "
                 f"저렴한 몰(§2). {alt['mall']} 후보({alt['goodsNo']})로 바꾸는 것을 검토")
        if not str(p.get("display_name", "")).strip():
            err(f"{tag}: display_name(짧은 상품명)을 적을 것 — 비우면 몰 원본 상품명(상품코드·'[29CM 단독]' 등)이 카드에 찍힘(§3)")
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
            missing = spec_missing(p["spec_line"], detail_text(c))
            if missing and not detail_text(c, ("spec_text", "material")).strip():
                err(f"{tag}: 상세 원문(spec_text·material)이 비어 spec_line의 {missing}를 확인할 수 없음 — "
                    f"숫자를 빼거나 인용 후기로(추측 금지 §3)")
            elif missing:
                err(f"{tag}: spec_line의 {missing}가 상세 페이지 텍스트에 없음(추측 금지 §3)")
            terms = fact_terms_missing(str(p["spec_line"]), detail_text(c))
            if terms:
                err(f"{tag}: spec_line의 소재·세탁 표현 {terms}가 상세 원문에 없음 — 카드에 '상세 페이지 표기'로 찍힌다(§3)")
            if not re.search(r"\d", str(p["spec_line"])):
                warn(f"{tag}: 숫자 없는 스펙 주장 — 상세 원문에 있는 사실인지 확인: '{str(p['spec_line'])[:40]}'")
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
    collage = cover.get("collage")
    if collage is not None:
        if not isinstance(collage, list) or not config.COLLAGE_MIN <= len(collage) <= config.COLLAGE_MAX:
            err(f"표지 collage는 {config.COLLAGE_MIN}~{config.COLLAGE_MAX}개 목록")
            collage = []
        seen = set()
        for k, part in enumerate(collage, 1):
            tag = f"표지 콜라주 {k}번"
            if not isinstance(part, dict) or set(part) - {"goodsNo", "image", "pos"}:
                err(f"{tag}: goodsNo·image·pos만 쓸 수 있음")
                continue
            pc = by_no.get(str(part.get("goodsNo")))
            if str(part.get("goodsNo")) not in nos or not pc:
                err(f"{tag}: 5종 중 하나의 사진만 쓸 수 있음(§4)")
                continue
            pi = part.get("image")
            if not isinstance(pi, int) or isinstance(pi, bool) or not 0 <= pi < len(pc.get("images", [])):
                err(f"{tag}: image 인덱스가 범위 밖")
                continue
            url = pc["images"][pi]
            if url in card_images:
                err(f"{tag}: 상품 카드 사진과 같은 원본(§4)")
            if url in seen:
                err(f"{tag}: 콜라주 안에서 같은 사진이 두 번")
            seen.add(url)
            if part.get("pos") is not None and not _POS.match(str(part["pos"])):
                err(f"{tag}: pos는 '50% 20%' 형식")
        if collage and cc and isinstance(ci, int) and not any(
                str(p.get("goodsNo")) == str(cover.get("goodsNo")) and p.get("image") == ci
                for p in collage if isinstance(p, dict)):
            err("표지 goodsNo·image(대표 컷)가 collage 안에 없음")

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
    if re.search(config.RANKING_PATTERN, cap, re.I):
        err("캡션에 랭킹 표현(§1·§5)")
    for pat, why in config.CAPTION_WARN_PATTERNS.items():
        m = re.search(pat, cap)
        if m:
            warn(f"캡션: {why} — '{m.group(0)[:40]}'")
    n = emoji_count(cap)
    if not 3 <= n <= 5:
        warn(f"캡션 이모지 {n}개 (기준 3~5)")
    if any(h.get("caption_first", "")[:6] == fs[:6] for h in hist[-3:] if h.get("caption_first")):
        warn("캡션 첫 문장이 최근 회차와 같은 패턴으로 시작")
    if ep.get("mood") and hist and hist[-1].get("mood") == ep.get("mood"):
        warn(f"캡션 무드 '{ep['mood']}'가 직전 회차와 같음(§5 연속 금지)")
    chosen = [by_no[n] for n in nos if n in by_no]
    cap_body = cap
    for c in chosen:   # 브랜드명 속 글자('코튼○○')는 소재 주장이 아니다
        if c.get("brand"):
            cap_body = cap_body.replace(c["brand"], " ")
    source = " ".join(detail_text(c) for c in chosen)
    for term in fact_terms_missing(cap_body, source):
        warn(f"캡션 소재·세탁 표현 '{term}'이 고른 상품의 상세 원문(spec_text·material·상품명)에 없음 — "
             f"상세 페이지에서 확인한 사실만(§2)")
    claim = _CHEAPER_CLAIM.search(cap)
    if claim:
        alts = [c for c in chosen if c.get("cheaper_elsewhere")]
        neutral = f"'가격은 각 몰 판매가 기준({str(cands.get('collected_at', ''))[5:10] or 'MM-DD'})'처럼 중립 표현으로"
        if any(not (isinstance(c["cheaper_elsewhere"], dict) and c["cheaper_elsewhere"].get("unavailable"))
               for c in alts):
            err(f"캡션 '{claim.group(0)}' 주장이 사실과 다름 — 다른 몰이 더 싼 상품이 있음. {neutral}")
        elif alts:
            warn(f"캡션 '{claim.group(0)}' 주장을 확인할 수 없음 — 다른 몰 가격 비교에 실패한 상품이 있음. {neutral}")

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
