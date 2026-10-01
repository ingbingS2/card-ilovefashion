"""인스타 캐러셀 게시 — 되돌릴 수 없다.

    python -m autopost.publish "20261002 가을 니트" --user-approved
    python -m autopost.publish "20261002 가을 니트" --check        # 조건만 확인

게시 조건(하나라도 어기면 거부):
  1) --user-approved — 세션은 사용자가 그 세션에서 '승인'이라고 답한 뒤에만 이 플래그를 붙인다.
  2) status.json stage=built, 지금 파일들의 fingerprint == 렌더 시점 == 재검증 시점, 재검증 60분 이내.
  3) 직전 게시와 다른 날(KST) + 20시간 이상 — history.json과 인스타 실제 최근 게시물 둘 다 확인.
media_publish 직전에 stage=publishing을 기록한다 — 응답이 끊겨도 같은 회차를 다시 게시하지 않는다.
게시 직후 history·status를 쓰고 데이터 브랜치에 바로 푸시한다.
이미지 공개 URL은 데이터 브랜치의 raw.githubusercontent.com(공개 저장소) → 실패 시 post_ig의 litterbox/uguu.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

from . import config
from .state import (find_handle, fingerprint, last_post, load_handles, load_history, load_status, parse_dt,
                    save_handles, save_history, save_status)

sys.path.insert(0, str(config.REPO_ROOT / "scripts"))
import post_ig  # noqa: E402  (기존 검증된 Graph API 플로우 재사용)


def api(method: str, endpoint: str, token: str, **data):
    """post_ig.api + 토큰이 예외 메시지(요청 URL)에 실려 로그로 새지 않게 가린다."""
    try:
        return post_ig.api(method, endpoint, token, **data)
    except (requests.exceptions.RequestException, RuntimeError) as e:
        raise RuntimeError(str(e).replace(token, "***")) from None


def raw_url(folder: str, name: str) -> str:
    path = quote(f"episodes/{folder}/{name}")
    return f"https://raw.githubusercontent.com/{config.GITHUB_REPO}/refs/heads/{config.DATA_BRANCH}/{path}"


def public_url(folder: str, local: Path) -> str:
    """푸시된 raw URL이 같은 파일을 돌려주면 그 URL, 아니면 임시 호스팅."""
    url = raw_url(folder, local.name)
    try:
        r = requests.get(url, timeout=30)
        if r.ok and r.content == local.read_bytes():
            return url
    except requests.exceptions.RequestException:
        pass
    return post_ig.host_image(str(local))


TAG_X, TAG_Y = 0.5, 0.42  # 상품 카드에서 옷이 있는 중앙 부근(하단 35%는 글자 영역)


def photo_tags(folder: str) -> dict[int, list[dict]]:
    """캐러셀 사진 번호(1~7) → user_tags. 상품 카드(2~6)에 그 브랜드의 검증된 핸들만. 표지·CTA는 태그 없음."""
    ep_dir = config.episode_dir(folder)
    ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    cands = {str(c["goodsNo"]): c for c in
             json.loads((ep_dir / "candidates.json").read_text(encoding="utf-8"))["candidates"]}
    handles = load_handles()
    out: dict[int, list[dict]] = {}
    for i, p in enumerate(ep["products"], 2):
        c = cands[str(p["goodsNo"])]
        entry = find_handle(handles, c["brand"], c.get("brand_en", ""), c.get("brand_id", ""))
        if entry and entry.get("verified") and entry.get("handle") and entry.get("photo_tag", True):
            out[i] = [{"username": entry["handle"].lstrip("@"), "x": TAG_X, "y": TAG_Y}]
    return out


def mark_tag_blocked(usernames: list[str]) -> None:
    """인스타가 태그를 거부한 계정(태그 허용 안 함 설정 등)은 다음부터 사진 태그를 건너뛴다. 캡션 멘션은 유지."""
    if not usernames:
        return
    handles = load_handles()
    for e in handles.get("brands", []):
        if (e.get("handle") or "").lstrip("@") in usernames:
            e["photo_tag"] = False
            e["photo_tag_note"] = f"{config.now_kst().date().isoformat()} 사진 태그 거부(Invalid user id) — 계정의 태그 허용 설정으로 추정"
    save_handles(handles)


def too_soon(prev: datetime, now: datetime) -> bool:
    return (now - prev < timedelta(hours=config.MIN_HOURS_BETWEEN_POSTS)
            or prev.astimezone(config.KST).date() == now.astimezone(config.KST).date())


def gate(folder: str, approved: bool, now=None) -> list[str]:
    now = now or config.now_kst()
    problems = []
    if not approved:
        problems.append("--user-approved 없음 — 사용자가 이 세션에서 승인한 뒤에만 게시한다")
    st = load_status(folder)
    stage = st.get("stage")
    if stage == "posted":
        problems.append(f"이미 게시됨: {st.get('permalink')}")
    elif stage == "publishing":
        problems.append("이전 게시 시도가 결과 확인 없이 끊김(stage=publishing) — 인스타 앱에서 게시 여부를 "
                        "먼저 확인하고 사용자에게 알린다. 자동 재시도 금지")
    elif stage != "built":
        problems.append(f"build가 끝나지 않았거나 낡음(stage={stage})")
    if any(lvl == "error" for lvl, _ in st.get("issues", [])):
        problems.append("build 검사에 error가 남아 있음")
    if stage == "built":
        fp = fingerprint(folder)
        if fp != st.get("fingerprint"):
            problems.append("렌더 이후 파일이 바뀜 — build → verify 다시")
        v = st.get("verified_at")
        if not v or st.get("verified_fingerprint") != fp:
            problems.append("지금 파일 기준의 게시 직전 재검증(verify) 기록 없음")
        elif now - parse_dt(v) > timedelta(minutes=config.VERIFY_FRESH_MINUTES):
            problems.append(f"재검증이 {config.VERIFY_FRESH_MINUTES}분보다 오래됨 — verify 다시")
    lp = last_post(load_history())
    if lp and too_soon(parse_dt(lp["posted_at"]), now):
        problems.append(f"직전 게시({lp['posted_at']})와 같은 날이거나 {config.MIN_HOURS_BETWEEN_POSTS}시간 미만")
    return problems


def push_data(message: str) -> bool:
    d = str(config.DATA_DIR)
    try:
        subprocess.run(["git", "-C", d, "add", "-A"], check=True)
        subprocess.run(["git", "-C", d, "commit", "-qm", message], check=False)
        subprocess.run(["git", "-C", d, "push", "-q", "origin", f"HEAD:{config.DATA_BRANCH}"], check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"⚠️ 데이터 브랜치 푸시 실패: {e} — 반드시 수동으로 푸시할 것(안 하면 다음 회차가 이 게시를 모른다)")
        return False


def publish(folder: str) -> dict:
    ep_dir = config.episode_dir(folder)
    images = post_ig.collect_images(str(ep_dir))
    caption = post_ig.load_caption(str(ep_dir))
    if len(images) != 7 or not caption:
        raise SystemExit(f"이미지 7장·캡션이 필요합니다 (이미지 {len(images)}장)")
    token = os.environ.get("IG_ACCESS_TOKEN") or post_ig.load_token()

    me = api("GET", "me", token, fields="user_id,username")
    if me.get("username") != config.ACCOUNT.lstrip("@"):
        raise SystemExit(f"토큰 계정이 다릅니다: @{me.get('username')}")
    recent = api("GET", "me/media", token, fields="timestamp", limit=1).get("data") or []
    if recent:
        ts = datetime.strptime(recent[0]["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        if too_soon(ts, config.now_kst()):
            raise SystemExit(f"인스타 최근 게시물({ts.astimezone(config.KST):%m-%d %H:%M})과 너무 가깝습니다 — 게시 중단")

    urls = [public_url(folder, Path(p)) for p in images]
    tags = photo_tags(folder)
    tag_result: dict[int, str] = {}
    children = []
    for i, url in enumerate(urls, 1):
        extra = {"user_tags": json.dumps(tags[i])} if tags.get(i) else {}
        last = None
        for attempt in range(4):  # 9004 간헐 오류는 재시도로 풀린다 (post_ig 주석)
            try:
                children.append(api("POST", "me/media", token, image_url=url, is_carousel_item="true",
                                    **extra)["id"])
                if tags.get(i):
                    tag_result[i] = "ok" if extra else "태그 없이 올림"
                break
            except RuntimeError as e:
                last = e
                if extra and attempt >= 1:  # 태그 때문일 수 있다 — 두 번 실패하면 태그를 빼고 다시
                    print(f"⚠️ {i}번 사진 태그 실패 → 태그 없이 다시 시도: {str(e)[:120]}")
                    extra = {}
                time.sleep(4)
        else:
            raise RuntimeError(f"아이템 컨테이너 생성 실패: {last}")
    carousel = api("POST", "me/media", token, media_type="CAROUSEL",
                   children=",".join(children), caption=caption)["id"]
    for _ in range(40):  # post_ig.wait_ready와 같지만 토큰을 가린 api()로
        status = api("GET", carousel, token, fields="status_code").get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError(f"캐러셀 컨테이너 처리 실패 {carousel}")
        time.sleep(3)
    else:
        raise RuntimeError("캐러셀 컨테이너 준비 대기 시간 초과")

    mark_tag_blocked([t["username"] for i, r in tag_result.items() if r != "ok" for t in tags.get(i, [])])
    st = load_status(folder)
    st.update(stage="publishing", carousel_id=carousel, image_urls=urls,
              user_tags={str(i): {"tags": [t["username"] for t in tags.get(i, [])], "result": r}
                         for i, r in tag_result.items()},
              publishing_at=config.now_kst().isoformat(timespec="seconds"))
    save_status(folder, st)
    media_id = api("POST", "me/media_publish", token, creation_id=carousel)["id"]

    # 게시는 끝났다 — 이후 단계가 실패해도 기록부터 남긴다(재게시 방지)
    st.update(stage="posted", posted_at=config.now_kst().isoformat(timespec="minutes"), media_id=media_id)
    save_status(folder, st)
    record(folder, st)
    try:
        info = api("GET", media_id, token, fields="permalink,caption")
        st["permalink"] = info.get("permalink", "")
        st["caption_ok"] = post_ig.captions_match(caption, info.get("caption", ""))
        save_status(folder, st)
        record(folder, st)
    except RuntimeError as e:
        print(f"⚠️ 게시는 완료, permalink 조회 실패: {e}")
    push_data(f"autopost: {folder} 게시")
    return st


def record(folder: str, st: dict) -> None:
    """history.json에 게시 행을 넣거나(처음) permalink를 채운다(두 번째). result.md §3도 갱신."""
    ep_dir = config.episode_dir(folder)
    ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    cands = {str(c["goodsNo"]): c for c in
             json.loads((ep_dir / "candidates.json").read_text(encoding="utf-8"))["candidates"]}
    caption = (ep_dir / "caption.txt").read_text(encoding="utf-8")
    hist = load_history()
    row = next((h for h in hist if h.get("media_id") == st["media_id"]), None)
    if row is None:
        row = {
            "folder": folder, "keyword": ep["keyword"], "axis": ep.get("axis", ""), "mood": ep.get("mood", ""),
            "posted_at": st["posted_at"], "media_id": st["media_id"],
            "brands": [cands[str(p["goodsNo"])]["brand"] for p in ep["products"]],
            "mentions": [ln.split("@", 1)[1].strip() for ln in caption.split("📌", 1)[-1].splitlines()
                         if "📌" in caption and "@" in ln],
            "goods": [p["goodsNo"] for p in ep["products"]],
            "zzal": (ep.get("cta") or {}).get("zzal", ""),
            "caption_first": caption.strip().split("\n", 1)[0], "auto": True}
        hist.append(row)
    row["permalink"] = st.get("permalink", "")
    save_history(hist)

    res = ep_dir / "result.md"
    text = res.read_text(encoding="utf-8")
    hosting = ("raw.githubusercontent.com" if all("githubusercontent" in u for u in st.get("image_urls", []))
               else "litterbox/uguu 포함")
    block = (f"<!-- publish -->\n- 게시 {st['posted_at']} (KST) · {st.get('permalink', '(permalink 미확인)')} · "
             f"media_id {st['media_id']}\n- 게시 방식: autopost.publish (Graph API) · 호스팅: {hosting}\n"
             f"- 캡션 재조회 일치: {st.get('caption_ok')}\n"
             f"- 사진 태그(user_tags): "
             f"{', '.join(f'{k}번 @' + '/@'.join(v['tags']) + ('' if v['result'] == 'ok' else ' (실패→태그 없이)') for k, v in sorted(st.get('user_tags', {}).items())) or '없음'}\n"
             f"- 측정 예정: +72h\n<!-- /publish -->")
    if "<!-- publish -->" in text:
        text = text[:text.index("<!-- publish -->")] + block + text[text.index("<!-- /publish -->") + 17:]
    else:
        text = text.replace("- (게시 후 publish가 채운다)", block)
    res.write_text(text, encoding="utf-8")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="인스타 게시 (사용자 승인 후에만)")
    ap.add_argument("folder")
    ap.add_argument("--user-approved", action="store_true")
    ap.add_argument("--check", action="store_true", help="게시하지 않고 조건만 확인")
    args = ap.parse_args(argv)
    problems = gate(args.folder, args.user_approved or args.check)
    for p in problems:
        print(f"[거부] {p}")
    if problems:
        sys.exit(1)
    if args.check:
        tags = photo_tags(args.folder)
        for i in range(1, 8):
            print(f"  {i}번 사진 태그: {', '.join('@' + t['username'] for t in tags.get(i, [])) or '없음'}")
        print("게시 조건 충족 (--check: 게시하지 않음)")
        return
    st = publish(args.folder)
    print(f"게시 완료 {st['posted_at']} → {st.get('permalink')}")
    if st.get("caption_ok") is False:
        print("⚠️ 게시된 캡션이 원본과 다릅니다(한글 깨짐 의심) — 인스타 앱에서 확인하세요.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
