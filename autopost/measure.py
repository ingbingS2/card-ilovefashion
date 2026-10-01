"""+72h 인사이트 측정 + 인스타 토큰 연장.

    python -m autopost.measure            # 72시간 지난 미측정 게시물 측정 → history.json·result.md
    python -m autopost.measure --token    # 토큰 확인·연장(refresh_access_token)

판정(§8): 도달 200 이상 + 공유 1건 이상 → 통과. 유입 경로('기타')는 Graph API에 없어 웹 인사이트에서만 보인다.
브랜드 반응(실험 #5)은 댓글만 API로 본다 — 브랜드의 좋아요·스토리 공유는 Graph API에 없다(앱 알림에서 확인).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta

import requests

from . import config
from .publish import api
from .state import load_history, load_status, parse_dt, save_history

sys.path.insert(0, str(config.REPO_ROOT / "scripts"))
import post_ig  # noqa: E402

METRICS = ("reach", "saved", "shares", "likes", "comments", "total_interactions", "profile_visits",
           "follows", "views")
CORE = ("reach", "saved", "shares", "likes", "comments")  # 지원 안 되는 지표가 있으면 여기로 물러선다
COMMENT_PAGES = 3      # 댓글은 최대 3쪽(쪽당 50개)까지만 — 이 계정 규모에선 충분


def parse_insights(payload: dict) -> dict:
    out = {}
    for row in payload.get("data", []):
        if row.get("total_value"):
            out[row["name"]] = row["total_value"].get("value")
        elif row.get("values"):
            out[row["name"]] = row["values"][0].get("value")
    return out


def verdict(m: dict) -> str:
    return "통과" if (m.get("reach") or 0) >= 200 and (m.get("shares") or 0) >= 1 else "미달"


def due(history: list[dict], now) -> list[dict]:
    return [h for h in history if h.get("media_id") and h.get("posted_at") and not h.get("metrics")
            and now - parse_dt(h["posted_at"]) >= timedelta(hours=config.MEASURE_AFTER_HOURS)]


def brand_line(h: dict) -> str:
    """result.md·보고용 '브랜드 반응(댓글)' 한 줄."""
    if h.get("brand_comments_error"):
        return f"조회 실패 — {h['brand_comments_error']}"
    if "brand_comments" not in h:
        return "기록 없음"
    who = ", ".join("@" + b for b in h["brand_comments"]) or "없음"
    return f"{who} (댓글 {h.get('comment_count', 0)}개 중)"


def write_result(h: dict) -> None:
    res = config.episode_dir(h["folder"]) / "result.md"
    if not res.exists():
        return
    m = h["metrics"]
    rows = "\n".join(f"| {k} | {m.get(k, '')} |" for k in METRICS if k in m)
    text = res.read_text(encoding="utf-8").replace(
        "- (measure가 채운다)",
        f"측정 {h['measured_at']} (KST, Graph API) · 측정 시점: 게시 +{h['measured_hours']}h\n\n"
        f"| 지표 | 게시 +{h['measured_hours']}h |\n|---|---|\n{rows}\n\n"
        f"**판정: {h['verdict']}** (기준 도달 200+ · 공유 1+). 유입 '기타' 비중은 "
        f"`instagram.com/insights/media/{h['media_id']}/`에서 확인.\n\n"
        f"- 브랜드 반응(댓글): {brand_line(h)}\n"
        f"- 브랜드의 좋아요·스토리 공유는 Graph API로 볼 수 없음 — 인스타 앱 알림·스토리 멘션에서 확인")
    res.write_text(text, encoding="utf-8")


def fetch(media_id: str, token: str) -> dict:
    try:
        return parse_insights(api("GET", f"{media_id}/insights", token, metric=",".join(METRICS)))
    except RuntimeError:
        return parse_insights(api("GET", f"{media_id}/insights", token, metric=",".join(CORE)))


def episode_handles(h: dict) -> list[str]:
    """이 회차에서 실제로 쓴 검증 핸들 — 캡션 📌 멘션(history.mentions) + 사진 태그(status.json user_tags)."""
    names = list(h.get("mentions") or [])
    st = load_status(h["folder"]) if h.get("folder") else {}
    for v in (st.get("user_tags") or {}).values():
        names += v.get("tags") or []
    return sorted({n.strip().lstrip("@").lower() for n in names if n and n.strip()})


def fetch_comments(media_id: str, token: str) -> list[dict]:
    """GET /{media_id}/comments — 다음 쪽 커서를 따라 최대 COMMENT_PAGES쪽. api()가 토큰을 가린다."""
    rows, after = [], None
    for _ in range(COMMENT_PAGES):
        params = {"fields": "username,timestamp", "limit": 50}
        if after:
            params["after"] = after
        page = api("GET", f"{media_id}/comments", token, **params)
        rows += page.get("data") or []
        paging = page.get("paging") or {}
        after = (paging.get("cursors") or {}).get("after")
        if not paging.get("next") or not after:
            break
    return rows


def brand_reactions(h: dict, token: str) -> dict:
    """회차 브랜드 핸들 중 댓글을 단 계정만 남긴다 — 다른 사람의 아이디는 저장하지 않는다(개인정보).

    실패(권한 없음 등)해도 측정은 계속한다 — 짧은 오류만 남긴다."""
    try:
        comments = fetch_comments(h["media_id"], token)
    except Exception as e:  # noqa: BLE001 — 댓글 조회 실패가 측정 전체를 막으면 안 된다
        msg = str(e).replace(token, "***") if token else str(e)
        return {"brand_comments_error": msg[:120] or type(e).__name__}
    mine = set(episode_handles(h))
    seen = {str(c.get("username") or (c.get("from") or {}).get("username") or "").lstrip("@").lower()
            for c in comments}
    return {"brand_comments": sorted(mine & seen), "comment_count": len(comments)}


def measure(token: str) -> tuple[list[dict], list[str]]:
    now = config.now_kst()
    hist = load_history()
    done, errors = [], []
    for h in due(hist, now):
        try:
            h["metrics"] = fetch(h["media_id"], token)
        except RuntimeError as e:
            errors.append(f"{h['folder']}: {e}")
            continue
        h["measured_at"] = now.isoformat(timespec="minutes")
        h["measured_hours"] = round((now - parse_dt(h["posted_at"])).total_seconds() / 3600, 1)
        h["verdict"] = verdict(h["metrics"])
        h.update(brand_reactions(h, token))
        write_result(h)
        save_history(hist)  # 한 건씩 저장 — 뒤에서 실패해도 앞의 측정은 남는다
        done.append(h)
    return done, errors


TOKEN_WARN = (" ⚠️ 토큰 만료 임박 — `measure --token`으로 연장하거나 Meta 앱에서 새 토큰을 발급해 "
              "IG_ACCESS_TOKEN(클라우드)·토큰 파일(PC)을 바꿀 것")


def token_key(token: str) -> str:
    """토큰 메타 키 — 값 대신 sha256 앞 12자. PC 파일 토큰과 클라우드 환경변수 토큰이 서로 덮어쓰지 않게."""
    return hashlib.sha256(token.encode()).hexdigest()[:12]


def load_token_meta() -> dict:
    """{"tokens": {키: {first_seen, refreshed_at?, expires_at?}}}. 예전 형식({"hash", "first_seen"})은 옮겨 담는다."""
    meta = {}
    if config.TOKEN_META_FILE.exists():
        try:
            meta = json.loads(config.TOKEN_META_FILE.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    tokens = meta.get("tokens") if isinstance(meta.get("tokens"), dict) else {}
    if meta.get("hash") and meta.get("first_seen"):   # 예전 형식: sha256 앞 16자 → 앞 12자가 새 키
        tokens.setdefault(str(meta["hash"])[:12], {"first_seen": meta["first_seen"]})
    return {"tokens": tokens}


def save_token_meta(meta: dict) -> None:
    config.TOKEN_META_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.TOKEN_META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_token_refresh(token: str, expires_in) -> dict:
    """--token 연장 성공 시 그 토큰 키에 연장 시각·만료 시각을 남긴다(토큰 값은 남기지 않는다)."""
    now = config.now_kst()
    meta = load_token_meta()
    entry = meta["tokens"].setdefault(token_key(token), {"first_seen": now.date().isoformat()})
    entry["refreshed_at"] = now.isoformat(timespec="minutes")
    if expires_in:
        entry["expires_at"] = (now + timedelta(seconds=int(expires_in))).isoformat(timespec="minutes")
    save_token_meta(meta)
    return entry


def token_age_note(token: str) -> str:
    """만료 예고(§8). 연장 기록(expires_at)이 있으면 그것을, 없으면 처음 본 날짜 + 60일로 추정한다."""
    now = config.now_kst()
    meta = load_token_meta()
    key = token_key(token)
    if key not in meta["tokens"]:
        meta["tokens"][key] = {"first_seen": now.date().isoformat()}
        save_token_meta(meta)
    entry = meta["tokens"][key]
    if entry.get("expires_at"):
        exp = parse_dt(entry["expires_at"])
        left = (exp - now).days
        note = f" · 만료 약 {max(left, 0)}일 남음({exp.date().isoformat()}, 연장 기록 기준)"
        return note + (TOKEN_WARN if left < config.TOKEN_WARN_DAYS else "")
    first = datetime.fromisoformat(entry["first_seen"]).date()
    left = config.TOKEN_LIFETIME_DAYS - (now.date() - first).days
    note = f" · 처음 확인 {first.isoformat()}, 만료까지 약 {left}일 이하(추정 — 연장 기록 없음)"
    return note + (TOKEN_WARN if left <= config.TOKEN_WARN_DAYS else "")


def refresh_token(token: str) -> dict:
    try:
        r = requests.get("https://graph.instagram.com/refresh_access_token",
                         params={"grant_type": "ig_refresh_token", "access_token": token}, timeout=30)
    except requests.exceptions.RequestException as e:
        raise RuntimeError(str(e).replace(token, "***")) from None
    if not r.ok:
        raise RuntimeError(f"토큰 연장 실패 {r.status_code}: {r.text[:200].replace(token, '***')}")
    return r.json()


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="+72h 측정·토큰 연장")
    ap.add_argument("--token", action="store_true", help="토큰 연장")
    ap.add_argument("--check", action="store_true", help="토큰 유효성만 확인(값은 출력하지 않음)")
    args = ap.parse_args(argv)
    from_env = bool(os.environ.get("IG_ACCESS_TOKEN"))
    if args.check:
        if not from_env and not os.path.exists(post_ig.TOKEN_FILE):
            print("missing — IG_ACCESS_TOKEN 환경변수도 토큰 파일도 없음")
            return
        token = os.environ.get("IG_ACCESS_TOKEN") or post_ig.load_token()
        try:
            me = api("GET", "me", token, fields="username")
        except RuntimeError as e:
            print(f"invalid — {str(e)[:160]}")
            return
        print(f"ok @{me.get('username')} ({'env' if from_env else 'file'})" + token_age_note(token))
        return
    token = os.environ.get("IG_ACCESS_TOKEN") or post_ig.load_token()
    if args.token:
        data = refresh_token(token)
        days = int(data.get("expires_in", 0)) // 86400
        print(f"토큰 연장 완료 — 남은 기간 약 {days}일")
        new = data.get("access_token")
        entry = record_token_refresh(new or token, data.get("expires_in"))   # 키는 해시 — 값은 남기지 않는다
        if entry.get("expires_at"):
            print(f"만료 예정 {entry['expires_at'][:10]} (token-meta 기록)")
        from .publish import push_data
        push_data("autopost: 토큰 연장 기록")   # 클라우드에서도 만료일 기록이 남게
        if new and new != token:
            if from_env:
                print("⚠️ 새 토큰 문자열이 발급됐습니다. 환경변수 IG_ACCESS_TOKEN을 바꿔야 합니다(값은 출력하지 않음).")
            else:  # 저장소 밖 카드뉴스 폴더의 토큰 파일 — 커밋되지 않는다
                with open(post_ig.TOKEN_FILE, "w", encoding="utf-8") as f:
                    f.write(new + "\n")
                print(f"새 토큰을 {post_ig.TOKEN_FILE}에 저장했습니다(값은 출력하지 않음).")
        return
    done, errors = measure(token)
    if done:
        from .publish import push_data
        push_data("autopost: +72h 측정 기록")   # 클라우드 컨테이너가 사라져도 측정값이 남게
    for h in done:
        m = h["metrics"]
        print(f"{h['folder']}: 게시 +{h['measured_hours']}h 측정 · 도달 {m.get('reach')} · 공유 {m.get('shares')} · "
              f"저장 {m.get('saved')} → {h['verdict']} · 브랜드 댓글: {brand_line(h)}")
    for e in errors:
        print(f"[측정 실패] {e}")
    if not done and not errors:
        print("측정 대상 없음")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
