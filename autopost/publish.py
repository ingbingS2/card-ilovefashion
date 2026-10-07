"""인스타 캐러셀 게시 — 되돌릴 수 없다.

    python -m autopost.publish "20261002 가을 니트" --approve --quote "<사용자 승인 메시지 원문>"
    python -m autopost.publish --pending      # 승인 기록된 회차를 재검증 → (안전한) 숫자 갱신 → 게시, 하루 한 건
    python -m autopost.publish "20261002 가을 니트" --check          # 조건만 확인
    python -m autopost.publish "20261002 가을 니트" --user-approved  # PC 수동 즉시 게시(권한 확인 창을 거친다)

게시 조건(하나라도 어기면 거부):
  1) 사용자 승인 — 이 세션의 --user-approved, 또는 --approve로 기록된 승인(원문 인용·48시간 이내·같은 fingerprint).
  2) status.json stage=built/approved, 지금 파일들의 fingerprint == 렌더 시점 == 재검증 시점, 재검증 60분 이내.
  3) 직전 게시와 다른 날(KST) + 20시간 이상, 직전 게시와 브랜드 안 겹침, 최근 10회와 키워드 안 겹침
     — history.json과 인스타 실제 최근 게시물 둘 다 확인.
media_publish 직전에 stage=publishing을 데이터 브랜치에 **먼저 푸시**한다(잠금) — 다른 세션이 먼저 바꿨거나 푸시가
안 되면 게시하지 않는다. 응답이 끊겨도 같은 회차를 다시 게시하지 않는다. 게시 직후 history·status를 쓰고 바로 푸시한다.
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
from .state import (find_handle, fingerprint, last_post, load_handles, load_history, load_status, parse_dt, posted,
                    same_brand, same_keyword, save_handles, save_history, save_status)

sys.path.insert(0, str(config.REPO_ROOT / "scripts"))
import post_ig  # noqa: E402  (기존 검증된 Graph API 플로우 재사용)


def ig_token() -> str:
    """환경변수 IG_ACCESS_TOKEN → 프록시 자격 증명(IG_TOKEN_VIA_PROXY=1) → PC 토큰 파일 순서."""
    if os.environ.get("IG_ACCESS_TOKEN"):
        return os.environ["IG_ACCESS_TOKEN"]
    if os.environ.get("IG_TOKEN_VIA_PROXY") == "1":
        return post_ig.PROXY_TOKEN
    return post_ig.load_token()


def token_source() -> str | None:
    """토큰을 어디서 얻는지(값은 보지 않음). 없으면 None."""
    if os.environ.get("IG_ACCESS_TOKEN"):
        return "env"
    if os.environ.get("IG_TOKEN_VIA_PROXY") == "1":
        return "proxy"
    return "file" if os.path.exists(post_ig.TOKEN_FILE) else None


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


def recent_posts(history: list[dict], exclude: str = "") -> list[tuple[str, datetime]]:
    """게시 시각 목록 — history의 게시 + 아직 history에 안 올라간 다른 회차의 publishing/posted(동시 실행 대비)."""
    out = [(h.get("folder", ""), parse_dt(h["posted_at"])) for h in posted(history) if h.get("folder") != exclude]
    if config.EPISODES_DIR.exists():
        for d in config.EPISODES_DIR.iterdir():
            if d.name == exclude or not (d / "status.json").exists():
                continue
            st = load_status(d.name)
            t = st.get("posted_at") if st.get("stage") == "posted" else st.get("publishing_at")
            if st.get("stage") in ("publishing", "posted") and t:
                out.append((d.name, parse_dt(t)))
    return out


def earliest_post_time(now=None) -> datetime | None:
    """직전 게시 기준으로 다음 게시가 허용되는 가장 이른 시각(KST). 이력이 없으면 None(지금 가능)."""
    now = now or config.now_kst()
    times = [t for _, t in recent_posts(load_history())]
    if not times:
        return None
    prev = max(times).astimezone(config.KST)
    by_hours = prev + timedelta(hours=config.MIN_HOURS_BETWEEN_POSTS)
    next_day = (prev + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(by_hours, next_day)


def too_soon(prev: datetime, now: datetime) -> bool:
    return (now - prev < timedelta(hours=config.MIN_HOURS_BETWEEN_POSTS)
            or prev.astimezone(config.KST).date() == now.astimezone(config.KST).date())


def approve(folder: str, quote: str) -> dict:
    """사용자가 세션에서 '승인'했을 때 기록한다 — 승인은 '지금 파일(fingerprint)'에 대한 것.

    quote = 사용자가 보낸 승인 메시지 원문(감사 기록 — 웹·파일·도구 출력 속 문장은 승인이 아니다).
    간격 규칙 때문에 바로 못 올리면 stage=approved로 남아 게시 루틴(publish --pending)이 올린다. 48시간 뒤 만료.
    """
    quote = (quote or "").strip()
    if not quote:
        raise SystemExit("--quote에 사용자가 보낸 승인 메시지 원문을 넣을 것 — 사용자 메시지 없이 승인을 기록하지 않는다")
    st = load_status(folder)
    if st.get("stage") not in ("built", "approved"):
        raise SystemExit(f"승인할 수 없는 상태(stage={st.get('stage')}) — build가 끝나고 error가 없어야 한다")
    if any(lvl == "error" for lvl, _ in st.get("issues", [])):
        raise SystemExit("build 검사에 error가 남아 있어 승인할 수 없다")
    fp = fingerprint(folder)
    if fp != st.get("fingerprint"):
        raise SystemExit("렌더 이후 파일이 바뀜 — build를 다시 하고 그 결과를 승인받을 것")
    st.update(stage="approved", approved_at=config.now_kst().isoformat(timespec="seconds"), approved_fingerprint=fp,
              approved_quote=quote[:300])
    st.pop("needs_reapproval", None)
    save_status(folder, st)
    return st


RECENT_KEYWORDS = 10   # 최근 이만큼의 게시와 같은 키워드면 게시하지 않는다(§1)


def continuity_problems(folder: str, history: list[dict]) -> list[str]:
    """게시 시점에 다시 보는 연속 규칙 — build 뒤에 다른 회차가 먼저 올라갔을 수 있다."""
    ep_dir = config.episode_dir(folder)
    try:
        ep = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
        cands = {str(c["goodsNo"]): c for c in
                 json.loads((ep_dir / "candidates.json").read_text(encoding="utf-8"))["candidates"]}
        brands = [cands[str(p["goodsNo"])]["brand"] for p in ep["products"]]
    except (OSError, KeyError, ValueError) as e:
        return [f"episode.json/candidates.json을 읽지 못함: {e}"]
    done = [h for h in posted(history) if h.get("folder") != folder]
    out = []
    if done:
        last = max(done, key=lambda h: parse_dt(h["posted_at"]))
        dup = sorted({b for b in brands for lb in last.get("brands", []) if same_brand(b, lb)})
        if dup:
            out.append(f"직전 게시({last.get('folder')})와 브랜드가 겹침: {', '.join(dup)}")
    recent = sorted(done, key=lambda h: parse_dt(h["posted_at"]))[-RECENT_KEYWORDS:]
    if any(same_keyword(ep.get("keyword", ""), h.get("keyword", "")) for h in recent):
        out.append(f"최근 {RECENT_KEYWORDS}회 안에 같은 키워드 '{ep.get('keyword')}'가 게시됨")
    return out


def gate(folder: str, approved: bool, now=None) -> list[str]:
    now = now or config.now_kst()
    problems = []
    st = load_status(folder)
    stage = st.get("stage")
    recorded = (stage == "approved" and st.get("approved_fingerprint") == st.get("fingerprint")
                and bool(st.get("approved_quote")) and bool(st.get("approved_at")))
    if recorded and now - parse_dt(st["approved_at"]) > timedelta(hours=config.APPROVAL_TTL_HOURS):
        problems.append(f"승인 후 {config.APPROVAL_TTL_HOURS}시간이 지남 — 새로 확인한 카드로 다시 승인받을 것")
    if not approved and not recorded:
        problems.append("사용자 승인 없음 — 사용자가 세션에서 '승인'한 뒤에만 게시한다(--approve --quote 또는 --user-approved)")
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
    history = load_history()
    for name, t in sorted(recent_posts(history, exclude=folder), key=lambda x: x[1], reverse=True):
        if too_soon(t, now):
            problems.append(f"직전 게시({name} {t.astimezone(config.KST):%m-%d %H:%M})와 같은 날이거나 "
                            f"{config.MIN_HOURS_BETWEEN_POSTS}시간 미만")
            break
    if stage in ("built", "approved"):
        problems += continuity_problems(folder, history)
    return problems


def _git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-c", "core.quotepath=false", "-C", str(config.DATA_DIR), *args],
                          check=check, capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "GIT_EDITOR": "true"})


STAGE_RANK = {"posted": 6, "publishing": 5, "blocked": 4, "expired": 4, "skipped": 4, "approved": 3, "built": 2}


def merge_data_file(path: str, upstream: str, mine: str) -> str | None:
    """rebase 충돌 해결. status.json은 더 진행된 단계(같으면 원격), history.json은 행 합집합. 그 밖은 None(원격 우선)."""
    name = path.replace("\\", "/").rsplit("/", 1)[-1]
    try:
        up, me = json.loads(upstream), json.loads(mine)
    except ValueError:
        return None
    if name == "status.json" and isinstance(up, dict) and isinstance(me, dict):
        pick = me if STAGE_RANK.get(me.get("stage"), 0) > STAGE_RANK.get(up.get("stage"), 0) else up
    elif name == "history.json" and isinstance(up, list) and isinstance(me, list):
        key = lambda h: h.get("media_id") or f"{h.get('folder')}|{h.get('posted_at')}"
        rows = {key(h): dict(h) for h in up}
        for h in me:
            row = rows.setdefault(key(h), {})
            for f, v in h.items():
                if row.get(f) in (None, "", [], {}):
                    row[f] = v
        pick = sorted(rows.values(), key=lambda h: h.get("posted_at") or "")
    else:
        return None
    return json.dumps(pick, ensure_ascii=False, indent=2) + "\n"


def _rebase_in_progress() -> bool:
    for name in ("rebase-merge", "rebase-apply"):
        out = _git("rev-parse", "--git-path", name, check=False).stdout.strip()
        if out and (Path(out) if Path(out).is_absolute() else config.DATA_DIR / out).exists():
            return True
    return False


def _rebase_onto_remote() -> bool:
    """원격을 받아 내 커밋을 그 위에 다시 쌓는다. 충돌은 merge_data_file 규칙으로 풀고, 못 풀면 abort."""
    if _git("pull", "-q", "--rebase", "origin", config.DATA_BRANCH, check=False).returncode == 0:
        return True
    for _ in range(30):
        if not _rebase_in_progress():
            return False                       # pull 자체가 실패(네트워크 등)
        files = [f for f in _git("diff", "--name-only", "-z", "--diff-filter=U", check=False).stdout.split("\0") if f]
        for f in files:
            up = _git("show", f":2:{f}", check=False)     # rebase 중 :2 = 원격(upstream), :3 = 내 커밋
            me = _git("show", f":3:{f}", check=False)
            merged = merge_data_file(f, up.stdout, me.stdout) if up.returncode == 0 and me.returncode == 0 else None
            if merged is not None:
                (config.DATA_DIR / f).write_text(merged, encoding="utf-8")
                _git("add", "--", f)
            elif up.returncode == 0:
                _git("checkout", "--ours", "--", f, check=False)
                _git("add", "--", f)
            else:
                _git("rm", "-q", "--", f, check=False)
        if _git("rebase", "--continue", check=False).returncode != 0 and not files:
            _git("rebase", "--skip", check=False)    # 해결 결과가 원격과 같아 빈 커밋이 된 경우
        if not _rebase_in_progress():
            return True
    _git("rebase", "--abort", check=False)
    return False


def push_data(message: str) -> bool:
    """데이터 브랜치에 커밋·푸시. 다른 세션이 먼저 밀었으면 rebase(충돌은 규칙대로 해결) 후 다시. 강제 푸시 없음."""
    try:
        _git("add", "-A")
        if _git("diff", "--cached", "--quiet", check=False).returncode != 0:
            _git("commit", "-qm", message)
        push = ("push", "-q", "origin", f"HEAD:{config.DATA_BRANCH}")
        if _git(*push, check=False).returncode != 0:
            if not _rebase_onto_remote():
                raise subprocess.CalledProcessError(1, "git pull --rebase (충돌을 풀지 못함)")
            _git(*push)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"⚠️ 데이터 브랜치 푸시 실패: {e} — `git -C autopost-data pull --rebase origin {config.DATA_BRANCH}` 후 "
              "다시 푸시할 것. 충돌하면 원격(다른 세션의 게시 기록)을 우선한다")
        return False


def claim(folder: str, st: dict, approved: bool = False) -> None:
    """게시 잠금: stage=publishing을 원격에 먼저 올린다. 그 사이 다른 세션이 데이터 브랜치를 바꿨으면 포기한다.

    git push는 원격이 내가 본 상태 그대로일 때만 성공한다(fast-forward) — 그래서 이 푸시가 compare-and-swap이다.
    """
    if not push_data(f"autopost: {folder} 게시 전 동기화"):
        raise SystemExit("게시 거부: 데이터 브랜치 동기화 실패 — 다른 세션의 게시 기록을 확인할 수 없어 게시하지 않음")
    problems = gate(folder, approved=approved)      # 동기화로 들어온 다른 세션의 기록까지 반영해 다시
    if problems:
        raise SystemExit("게시 거부(동기화 후): " + "; ".join(problems))
    before = load_status(folder)
    save_status(folder, st)
    _git("add", "-A")
    _git("commit", "-qm", f"autopost: {folder} 게시 시작(잠금)")
    if _git("push", "-q", "origin", f"HEAD:{config.DATA_BRANCH}", check=False).returncode != 0:
        _git("reset", "-q", "--hard", "HEAD~1", check=False)   # 방금 만든 잠금 커밋만 되돌린다(앞에서 전부 푸시해 둠)
        if load_status(folder) != before:                       # reset이 안 됐어도 로컬에 '게시 중'을 남기지 않는다
            save_status(folder, before)
        _git("pull", "-q", "--ff-only", "origin", config.DATA_BRANCH, check=False)
        raise SystemExit("게시 거부: 게시 직전 다른 세션이 데이터 브랜치를 바꿈(동시 게시 방지) — 다음 실행에서 다시 판단")


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
    token = ig_token()

    me = api("GET", "me", token, fields="user_id,username")
    if me.get("username") != config.ACCOUNT.lstrip("@"):
        raise SystemExit(f"토큰 계정이 다릅니다: @{me.get('username')}")
    recent = api("GET", "me/media", token, fields="timestamp,caption", limit=10).get("data") or []
    if recent:
        ts = datetime.strptime(recent[0]["timestamp"], "%Y-%m-%dT%H:%M:%S%z")
        if too_soon(ts, config.now_kst()):
            raise SystemExit(f"인스타 최근 게시물({ts.astimezone(config.KST):%m-%d %H:%M})과 너무 가깝습니다 — 게시 중단")
    first = caption.strip().split("\n", 1)[0].strip()
    for m in recent:     # 데이터 브랜치 기록이 유실돼도 같은 회차를 두 번 올리지 않게 — 인스타 실제 게시물 기준
        if post_ig.captions_match(caption, m.get("caption", "")) or (first and (m.get("caption") or "").strip().startswith(first)):
            raise SystemExit(f"같은 캡션의 게시물이 이미 인스타에 있음({m.get('timestamp')}) — 중복 게시 거부")

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

    st = load_status(folder)
    st.update(stage="publishing", carousel_id=carousel, image_urls=urls,
              user_tags={str(i): {"tags": [t["username"] for t in tags.get(i, [])], "result": r}
                         for i, r in tag_result.items()},
              publishing_at=config.now_kst().isoformat(timespec="seconds"))
    claim(folder, st, approved)   # '게시 중' 표시를 원격에 먼저 — 못 올리면 게시하지 않는다(중복·동시 게시 방지)
    mark_tag_blocked(sorted(tag_blocked))
    media_id = api("POST", "me/media_publish", token, creation_id=carousel)["id"]

    # 게시는 끝났다 — 이후 단계가 실패해도 기록부터 남긴다(재게시 방지)
    st.update(stage="posted", posted_at=config.now_kst().isoformat(timespec="minutes"), media_id=media_id)
    save_status(folder, st)
    try:
        record(folder, st)
    finally:             # permalink 조회보다 먼저 원격에 — 컨테이너가 여기서 끝나도 다음 실행이 게시 사실을 안다
        push_data(f"autopost: {folder} 게시 기록")
    try:
        info = api("GET", media_id, token, fields="permalink,caption")
        st["permalink"] = info.get("permalink", "")
        st["caption_ok"] = post_ig.captions_match(caption, info.get("caption", ""))
        save_status(folder, st)
        record(folder, st)
    except RuntimeError as e:
        print(f"⚠️ 게시는 완료, permalink 조회 실패: {e}")
    st["pushed"] = push_data(f"autopost: {folder} 게시")
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
    """stage=approved인 회차 폴더명 — 최근 승인부터(어제 밀린 회차가 오늘 회차의 자리를 먹지 않게)."""
    out = []
    if not config.EPISODES_DIR.exists():
        return out
    for d in config.EPISODES_DIR.iterdir():
        st = load_status(d.name) if (d / "status.json").exists() else {}
        if st.get("stage") == "approved":
            out.append((st.get("approved_at", ""), d.name))
    return [name for _, name in sorted(out, reverse=True)]


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


def has_token() -> bool:
    return token_source() is not None


def publish_pending(now=None) -> list[str]:
    """승인 기록된 회차를 재검증하고 간격 규칙이 허용하면 게시한다(게시 루틴·승인 직후 세션 공용). 보고 줄 목록."""
    from . import verify as verify_mod
    from .build import build as build_episode

    folders = pending_episodes()
    if not folders:
        return ["승인 대기 회차 없음"]
    if not has_token():
        return [f"🔑 이 세션에 인스타 토큰 없음 — 승인 대기 {len(folders)}건은 게시 루틴이 처리: " + ", ".join(folders)]
    lines = []
    for folder in folders:
        try:
            line, done = _publish_one(folder, now, verify_mod, build_episode)
        except SystemExit as e:           # 게이트·잠금 거부
            line, done = f"⏳ {folder}: {e}", False
        except Exception as e:            # 예외는 보고하고 멈춘다 — 게시 잠금 뒤 실패였다면 다음 회차를 올리면 안 된다
            lines.append(f"⚠️ {folder}: 처리 중 오류 — {type(e).__name__}: {str(e)[:200]} (이번 실행 중단)")
            break
        lines.append(line)
        if done:
            break  # 하루 한 건
    return lines


def _needs_reapproval(folder: str, reasons: list[str]) -> None:
    st = load_status(folder)
    st.update(approved_at=None, approved_fingerprint=None, approved_quote=None, needs_reapproval=reasons)
    if st.get("stage") == "approved":
        st["stage"] = "built"
    save_status(folder, st)


def _publish_one(folder: str, now, verify_mod, build_episode) -> tuple[str, bool]:
    st = load_status(folder)
    problems = [p for p in gate(folder, approved=False, now=now) if "재검증" not in p]
    if any("시간이 지남" in p for p in problems):
        st.update(stage="expired", expired_reason=problems)
        save_status(folder, st)
        return f"⌛ {folder}: 승인 만료({config.APPROVAL_TTL_HOURS}시간) — 게시하지 않음, 필요하면 다시 승인받을 것", False
    if problems:                          # 몰을 부르기 전에 싼 검사부터(간격·연속)
        return f"⏳ {folder}: 아직 게시 조건 미충족 — " + "; ".join(problems), False
    approval = {k: st.get(k) for k in ("approved_at", "approved_quote")}
    blocks, changes, failed, fresh = verify_mod.check(folder)
    if blocks or failed or changes:      # 이전 '재검증 통과' 기록이 남아 게이트를 통과시키지 않게
        st.pop("verified_at", None)
        st.pop("verified_fingerprint", None)
        save_status(folder, st)
    if blocks:
        st.update(stage="blocked", blocked_reason=blocks)
        save_status(folder, st)
        return f"⛔ {folder}: 게시 불가 — " + "; ".join(blocks) + " (상품 교체 후 다시 승인 필요)", False
    if failed:
        if any("차단" in f for f in failed):
            return (f"🖥️ {folder}: 이 환경(데이터센터 IP)에서는 차단된 몰을 재검증할 수 없음 — PC에서 "
                    f"`sh autopost/ap.sh publish --pending`을 실행해야 게시된다(승인 {config.APPROVAL_TTL_HOURS}시간 안에): "
                    + "; ".join(failed)), False
        return f"⚠️ {folder}: 몰 조회 실패 — 다음 실행에 다시 시도: " + "; ".join(failed), False
    if changes:
        risky = risky_changes(folder, fresh)
        try:
            verify_mod.apply(folder, fresh)      # 숫자 갱신 → stage=stale
            rep = build_episode(folder)          # 같은 선택으로 다시 렌더(크게 바뀐 경우도 새 카드를 보여줘야 하니)
        except Exception as e:
            _needs_reapproval(folder, [f"숫자 갱신·재렌더 중 오류: {type(e).__name__}: {str(e)[:120]}"])
            raise
        errors = [m for l, m in rep["issues"] if l == "error"]
        if risky or not rep["rendered"] or errors:
            reasons = risky + ([f"숫자 갱신 후 렌더 실패: {'; '.join(errors)}"] if (errors or not rep["rendered"]) else [])
            _needs_reapproval(folder, reasons)
            return (f"⚠️ {folder}: 승인 뒤 숫자가 바뀌어 새 카드로 다시 승인받아야 함 — " + "; ".join(reasons)), False
        st = load_status(folder)                 # 가격·할인·후기 수 갱신은 승인 범위 안(SKILL 8단계) — 원래 승인 유지
        st.update(stage="approved", approved_fingerprint=st["fingerprint"], refreshed_numbers=changes, **approval)
        save_status(folder, st)
    rc = verify_mod.run(folder)
    if rc != verify_mod.EXIT_OK:
        return f"⚠️ {folder}: 재검증 실패(exit {rc}) — 다음 실행에 다시", False
    problems = gate(folder, approved=False, now=now)
    if problems:
        return f"⏳ {folder}: 아직 게시 조건 미충족 — " + "; ".join(problems), False
    result = publish(folder)
    extra = f" · 숫자 갱신 {len(changes)}건" if changes else ""
    return f"✅ {folder}: 게시 완료 {result['posted_at']} → {result.get('permalink')}{extra}", True


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="인스타 게시 (사용자 승인 후에만)")
    ap.add_argument("folder", nargs="?")
    mode = ap.add_mutually_exclusive_group()   # '--pending --check' 같은 조합으로 확인 창·의도를 비껴가지 않게
    mode.add_argument("--user-approved", action="store_true")
    mode.add_argument("--check", action="store_true", help="게시하지 않고 조건만 확인")
    mode.add_argument("--approve", action="store_true", help="사용자 승인을 기록하고 데이터 브랜치에 푸시(게시는 --pending)")
    mode.add_argument("--pending", action="store_true", help="승인 기록된 회차를 재검증 후 게시(하루 한 건)")
    mode.add_argument("--next", action="store_true", help="다음 게시 가능 시각(KST)만 출력")
    ap.add_argument("--quote", default="", help="--approve와 함께: 사용자가 보낸 승인 메시지 원문")
    args = ap.parse_args(argv)
    if args.next:
        t = earliest_post_time()
        print("지금 게시 가능" if t is None or t <= config.now_kst() else f"다음 게시 가능 시각: {t:%m-%d %H:%M} KST")
        return
    if args.pending:
        for line in publish_pending():
            print(line)
        if not push_data("autopost: 승인 대기 회차 처리"):
            sys.exit(2)
        return
    if not args.folder:
        ap.error("folder가 필요합니다")
    if args.approve:
        st = approve(args.folder, args.quote)
        print(f"승인 기록 {st['approved_at']} (fingerprint {st['approved_fingerprint'][:12]}…)")
        if not push_data(f"autopost: {args.folder} 승인"):
            print("⚠️ 승인 기록을 푸시하지 못함 — 게시 루틴이 이 승인을 볼 수 없다. 푸시를 다시 할 것")
            sys.exit(2)
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
    if not st.get("pushed"):
        sys.exit(2)   # 게시는 됐다 — 다시 게시하지 말고 데이터 브랜치 푸시만 다시


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
