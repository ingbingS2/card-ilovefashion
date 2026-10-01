"""+72h 인사이트 측정 + 인스타 토큰 연장.

    python -m autopost.measure            # 72시간 지난 미측정 게시물 측정 → history.json·result.md
    python -m autopost.measure --token    # 토큰 확인·연장(refresh_access_token)

판정(§8): 도달 200 이상 + 공유 1건 이상 → 통과. 유입 경로('기타')는 Graph API에 없어 웹 인사이트에서만 보인다.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta

import requests

from . import config
from .publish import api
from .state import load_history, parse_dt, save_history

sys.path.insert(0, str(config.REPO_ROOT / "scripts"))
import post_ig  # noqa: E402

METRICS = ("reach", "saved", "shares", "likes", "comments", "total_interactions", "profile_visits",
           "follows", "views")
CORE = ("reach", "saved", "shares", "likes", "comments")  # 지원 안 되는 지표가 있으면 여기로 물러선다


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


def write_result(h: dict) -> None:
    res = config.episode_dir(h["folder"]) / "result.md"
    if not res.exists():
        return
    m = h["metrics"]
    rows = "\n".join(f"| {k} | {m.get(k, '')} |" for k in METRICS if k in m)
    text = res.read_text(encoding="utf-8").replace(
        "- (measure가 채운다)",
        f"측정 {h['measured_at']} (KST, Graph API)\n\n| 지표 | +72시간 |\n|---|---|\n{rows}\n\n"
        f"**판정: {h['verdict']}** (기준 도달 200+ · 공유 1+). 유입 '기타' 비중은 "
        f"`instagram.com/insights/media/{h['media_id']}/`에서 확인.")
    res.write_text(text, encoding="utf-8")


def fetch(media_id: str, token: str) -> dict:
    try:
        return parse_insights(api("GET", f"{media_id}/insights", token, metric=",".join(METRICS)))
    except RuntimeError:
        return parse_insights(api("GET", f"{media_id}/insights", token, metric=",".join(CORE)))


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
        h["verdict"] = verdict(h["metrics"])
        write_result(h)
        save_history(hist)  # 한 건씩 저장 — 뒤에서 실패해도 앞의 측정은 남는다
        done.append(h)
    return done, errors


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
    ap.add_argument("--token", action="store_true")
    args = ap.parse_args(argv)
    token = os.environ.get("IG_ACCESS_TOKEN") or post_ig.load_token()
    if args.token:
        data = refresh_token(token)
        days = int(data.get("expires_in", 0)) // 86400
        print(f"토큰 연장 완료 — 남은 기간 약 {days}일")
        if data.get("access_token") and data["access_token"] != token:
            print("⚠️ 새 토큰 문자열이 발급됐습니다. 클라우드 환경변수 IG_ACCESS_TOKEN을 바꿔야 합니다"
                  " (값은 출력하지 않음 — 사용자에게 Meta 앱에서 새 토큰을 발급해 넣도록 안내).")
        return
    done, errors = measure(token)
    for h in done:
        m = h["metrics"]
        print(f"{h['folder']}: 도달 {m.get('reach')} · 공유 {m.get('shares')} · 저장 {m.get('saved')} → {h['verdict']}")
    for e in errors:
        print(f"[측정 실패] {e}")
    if not done and not errors:
        print("측정 대상 없음")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
