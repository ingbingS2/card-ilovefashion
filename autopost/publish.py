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


def earliest_post_time(now=None) -> datetime | None:
    """직전 게시 기준으로 다음 게시가 허용되는 가장 이른 시각(KST). 이력이 없으면 None(지금 가능)."""
    now = now or config.now_kst()
    lp = last_post(load_history())
    if not lp:
        return None
    prev = parse_dt(lp["posted_at"]).astimezone(config.KST)
    by_hours = prev + timedelta(hours=config.MIN_HOURS_BETWEEN_POSTS)
    next_day = (prev + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(by_hours, next_day)


def too_soon(prev: datetime, now: datetime) -> bool:
    return (now - prev < timedelta(hours=config.MIN_HOURS_BETWEEN_POSTS)
            or prev.astimezone(config.KST).date() == now.astimezone(config.KST).date())


def approve(folder: str) -> dict:
    """사용자가 세션에서 '승인'했을 때 기록한다 — 승인은 '지금 파일(fingerprint)'에 대한 것.

    간격 규칙 때문에 바로 못 올리면 stage=approved로 남아 저녁 루틴(publish --pending)이 올린다.
    """
    st = load_status(folder)
    if st.get("stage") not in ("built", "approved"):
        raise SystemExit(f"승인할 수 없는 상태(stage={st.get('stage')}) — build가 끝나고 error가 없어야 한다")
    if any(lvl == "error" for lvl, _ in st.get("issues", [])):
        raise SystemExit("build 검사에 error가 남아 있어 승인할 수 없다")
    fp = fingerprint(folder)
    if fp != st.get("fingerprint"):
        raise SystemExit("렌더 이후 파일이 바뀜 — build를 다시 하고 그 결과를 승인받을 것")
    st.update(stage="approved", approved_at=config.now_kst().isoformat(timespec="seconds"), approved_fingerprint=fp)
    save_status(folder, st)
    return st


def gate(folder: str, approved: bool, now=None) -> list[str]:
    now = now or config.now_kst()
    problems = []
    st = load_status(folder)
    stage = st.get("stage")
    recorded = stage == "approved" and st.get("approved_fingerprint") == st.get("fingerprint")
    if not approved and not recorded:
        problems.append("--user-approved 없음 — 사용자가 이 세션에서 승인한 뒤에만 게시한다")
    if stage == "posted":
        problems.append(f"이미 게시됨: {st.get('permalink')}")
    elif stage == "publishing":
        problems.append("이전 게시 시도가 결과 확인 없이 끊김(stage=publishing) — 인스타 앱에서 게시 여부를 "
                        "먼저 확인하고 사용자에게 알린다. 자동 재시도 금지")
    elif stage not in ("built", "approved"):
        problems.append(f"build가 끝나지 않았거나 낡음(stage={stage})")
    if any(lvl == "error" for lvl, _ in st.get("issues", [])):
        problems.append("build 검사에 error가 남아 있음")
    if stage in ("built", "approved"):
        fp = fingerprint(folder)
        if fp != st.get("fingerprint"):
            problems.append("렌더 이후 파일이 바뀜 — build → verify 다시")
        if stage == "approved" and st.get("approved_fingerprint") != fp:
            problems.append("승인 뒤에 파일이 바뀜 — 사용자에게 다시 보여주고 승인받을 것")
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
        staged = subprocess.run(["git", "-C", d, "diff", "--cached", "--quiet"]).returncode != 0
        if staged:
            subprocess.run(["git", "-C", d, "commit", "-qm", message], check=True, capture_output=True)
        push = ["git", "-C", d, "push", "-q", "origin", f"HEAD:{config.DATA_BRANCH}"]
        if subprocess.run(push, capture_output=True).returncode != 0:
            # 다른 세션(아침/저녁 루틴)이 먼저 밀었을 수 있다 — 되감아 올리고 다시(강제 푸시는 하지 않는다)
            subprocess.run(["git", "-C", d, "pull", "-q", "--rebase", "origin", config.DATA_BRANCH], check=True,
                           capture_output=True)
            subprocess.run(push, check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"⚠️ 데이터 브랜치 푸시 실패: {e} — 반드시 수동으로 푸시할 것(안 하면 다음 회차가 이 게시를 모른다)")
        return False


def publish(folder: str, approved: bool = False) -> dict:
    """게이트를 안에서 다시 검사한다 — 어떤 경로로 불려도 승인·재검증·간격 없이는 게시되지 않게."""
    problems = gate(folder, approved)
    if problems:
        raise SystemExit("게시 거부: " + "; ".join(problems))
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
    tag_blocked: set[str] = set()   # 인스타가 '태그 불가 계정'이라고 답한 것만 — 일시 오류로는 끄지 않는다
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
                tag_rejected = "Invalid user id" in str(e) or "2207018" in str(e)
                if extra and (tag_rejected or attempt >= 1):  # 태그 거부면 바로, 아니면 두 번 실패 뒤 태그를 빼고 다시
                    print(f"⚠️ {i}번 사진 태그 실패 → 태그 없이 다시 시도: {str(e)[:120]}")
                    extra = {}
                    if tag_rejected:
                        tag_blocked.update(t["username"] for t in tags.get(i, []))
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

    mark_tag_blocked(sorted(tag_blocked))
    st = load_status(folder)
    st.update(stage="publishing", carousel_id=carousel, image_urls=urls,
              user_tags={str(i): {"tags": [t["username"] for t in tags.get(i, [])], "result": r}
                         for i, r in tag_result.items()},
              publishing_at=config.now_kst().isoformat(timespec="seconds"))
    save_status(folder, st)
    push_data(f"autopost: {folder} 게시 시작")   # 컨테이너가 죽어도 '게시 중' 표시가 원격에 남게(중복 게시 방지)
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


PRICE_UP_LIMIT = 1.2   # 승인 뒤 가격이 20% 넘게 오르거나 할인이 사라지면 자동 게시하지 않는다(SKILL 8단계)


def pending_episodes() -> list[str]:
    """stage=approved인 회차 폴더명(오래된 승인부터)."""
    out = []
    if not config.EPISODES_DIR.exists():
        return out
    for d in config.EPISODES_DIR.iterdir():
        st = load_status(d.name) if (d / "status.json").exists() else {}
        if st.get("stage") == "approved":
            out.append((st.get("approved_at", ""), d.name))
    return [name for _, name in sorted(out)]


def risky_changes(folder: str, fresh: dict) -> list[str]:
    """재검증에서 바뀐 숫자 중 승인 범위를 벗어나는 것 — 할인 소멸, 20% 넘는 인상."""
    ep_dir = config.episode_dir(folder)
    cands = {str(c["goodsNo"]): c for c in
             json.loads((ep_dir / "candidates.json").read_text(encoding="utf-8"))["candidates"]}
    risky = []
    for no, new in fresh.items():
        old = cands.get(no) or {}
        if old.get("discount", 0) > 0 and new.get("discount", 0) == 0:
            risky.append(f"{old.get('brand')}({no}): 할인이 사라짐({old.get('discount')}% → 0%)")
        if old.get("sale_price") and new.get("sale_price", 0) > old["sale_price"] * PRICE_UP_LIMIT:
            risky.append(f"{old.get('brand')}({no}): 가격 {old['sale_price']:,} → {new['sale_price']:,} (20% 초과 인상)")
    return risky


def publish_pending(now=None) -> list[str]:
    """저녁 루틴용: 승인된 회차를 재검증하고 간격 규칙이 허용하면 게시한다. 보고 줄 목록을 돌려준다."""
    from . import verify as verify_mod
    from .build import build as build_episode

    lines = []
    for folder in pending_episodes():
        st = load_status(folder)
        blocks, changes, failed, fresh = verify_mod.check(folder)
        if blocks:
            st.update(stage="blocked", blocked_reason=blocks)
            save_status(folder, st)
            lines.append(f"⛔ {folder}: 게시 불가 — " + "; ".join(blocks) + " (상품 교체 후 다시 승인 필요)")
            continue
        if failed:
            lines.append(f"⚠️ {folder}: 몰 조회 실패 — 다음 실행에 다시 시도: " + "; ".join(failed))
            continue
        if changes:
            risky = risky_changes(folder, fresh)
            if risky:
                st.update(stage="built", approved_at=None, approved_fingerprint=None, needs_reapproval=risky)
                save_status(folder, st)
                lines.append(f"⚠️ {folder}: 승인 뒤 숫자가 크게 바뀜 — 다시 보여주고 승인받아야 함: " + "; ".join(risky))
                continue
            verify_mod.apply(folder, fresh)          # 숫자 갱신 → stage=stale
            rep = build_episode(folder)              # 같은 선택으로 다시 렌더
            if not rep["rendered"] or any(l == "error" for l, _ in rep["issues"]):
                lines.append(f"⚠️ {folder}: 숫자 갱신 후 렌더 실패 — " + "; ".join(m for l, m in rep["issues"] if l == "error"))
                continue
            st = load_status(folder)
            st.update(stage="approved", approved_at=st.get("approved_at") or config.now_kst().isoformat(timespec="seconds"),
                      approved_fingerprint=st["fingerprint"], refreshed_numbers=changes)
            save_status(folder, st)
            rc = verify_mod.run(folder)
            if rc != verify_mod.EXIT_OK:
                lines.append(f"⚠️ {folder}: 갱신 후 재검증 실패(exit {rc}) — 다음 실행에 다시")
                continue
        else:
            rc = verify_mod.run(folder)
            if rc != verify_mod.EXIT_OK:
                lines.append(f"⚠️ {folder}: 재검증 실패(exit {rc}) — 다음 실행에 다시")
                continue
        problems = gate(folder, approved=True, now=now)
        if problems:
            lines.append(f"⏳ {folder}: 아직 게시 조건 미충족 — " + "; ".join(problems))
            continue
        result = publish(folder, approved=True)
        extra = f" · 숫자 갱신 {len(changes)}건" if changes else ""
        lines.append(f"✅ {folder}: 게시 완료 {result['posted_at']} → {result.get('permalink')}{extra}")
        break  # 하루 한 건
    if not lines:
        lines.append("승인 대기 회차 없음")
    return lines


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="인스타 게시 (사용자 승인 후에만)")
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--user-approved", action="store_true")
    ap.add_argument("--check", action="store_true", help="게시하지 않고 조건만 확인")
    ap.add_argument("--approve", action="store_true", help="사용자 승인을 기록만 한다(간격 규칙으로 못 올리면 저녁 루틴이 게시)")
    ap.add_argument("--pending", action="store_true", help="저녁 루틴: 승인된 회차를 재검증 후 게시")
    ap.add_argument("--next", action="store_true", help="다음 게시 가능 시각(KST)만 출력")
    args = ap.parse_args(argv)
    if args.next:
        t = earliest_post_time()
        print("지금 게시 가능" if t is None or t <= config.now_kst() else f"다음 게시 가능 시각: {t:%m-%d %H:%M} KST")
        return
    if args.pending:
        for line in publish_pending():
            print(line)
        push_data("autopost: 승인 대기 회차 처리")
        return
    if not args.folder:
        ap.error("folder가 필요합니다")
    if args.approve:
        st = approve(args.folder)
        print(f"승인 기록 {st['approved_at']} (fingerprint {st['approved_fingerprint'][:12]}…)")
        push_data(f"autopost: {args.folder} 승인")
        return
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
    st = publish(args.folder, approved=args.user_approved)
    print(f"게시 완료 {st['posted_at']} → {st.get('permalink')}")
    if st.get("caption_ok") is False:
        print("⚠️ 게시된 캡션이 원본과 다릅니다(한글 깨짐 의심) — 인스타 앱에서 확인하세요.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
