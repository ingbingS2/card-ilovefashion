# -*- coding: utf-8 -*-
"""인스타그램 카드뉴스 캐러셀 자동 게시 (인수인계 문서 검증 플로우).

사용법:
    python post_ig.py "20260719 카시오시계"          # 카드뉴스 기본 폴더 안 폴더명
    python post_ig.py "C:\\경로\\20260719 카시오시계"  # 전체 경로도 가능
    python post_ig.py "20260719 카시오시계" --dry-run  # 게시 없이 절차만 확인

폴더 규칙: 1.jpg ~ N.jpg (번호 순서 = 캐러셀 순서, 2~10장) + caption.txt (UTF-8)

토큰: C:\\Users\\yepdo\\OneDrive\\Desktop\\카드뉴스\\ig_api_token.txt (하드코딩 금지)

플로우 (graph.instagram.com/v23.0, 2026-07-19 실게시 검증):
  1) GET /me 토큰 검증
  2) litterbox.catbox.moe 1시간 임시 호스팅으로 공개 URL 확보
  3) POST /me/media (image_url, is_carousel_item) x N
  4) POST /me/media (media_type=CAROUSEL, children, caption)
  5) status_code=FINISHED 대기 → POST /me/media_publish
  6) GET permalink + 캡션 재조회로 한글 깨짐 검증 (필수)

주의: 한글 캡션을 절대 셸 인자로 넘기지 않는다 — requests data 로만 전송 (CP949 깨짐 방지).
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

import requests

GRAPH = "https://graph.instagram.com/v23.0"
LITTERBOX = "https://litterbox.catbox.moe/resources/internals/api.php"
BASE_DIR = r"C:\Users\yepdo\OneDrive\Desktop\카드뉴스"
TOKEN_FILE = os.path.join(BASE_DIR, "ig_api_token.txt")


def resolve_folder(arg: str, base_dir: str = BASE_DIR) -> str:
    """인자가 전체 경로면 그대로, 폴더명이면 카드뉴스 기본 폴더 기준으로 해석."""
    if os.path.isabs(arg):
        return arg
    return os.path.join(base_dir, arg)


def load_token(path: str = TOKEN_FILE) -> str:
    """토큰 파일에서 읽기 (앞뒤 공백/개행 제거). 없으면 종료."""
    if not os.path.exists(path):
        sys.exit(f"토큰 파일이 없습니다: {path}")
    token = open(path, encoding="utf-8").read().strip()
    if not token:
        sys.exit(f"토큰 파일이 비어 있습니다: {path}")
    return token


def collect_images(folder: str) -> list[str]:
    """1.jpg ~ N.jpg 를 번호 순으로 수집."""
    files = []
    for name in os.listdir(folder):
        m = re.fullmatch(r"(\d+)\.jpe?g", name, re.IGNORECASE)
        if m:
            files.append((int(m.group(1)), os.path.join(folder, name)))
    files.sort()
    return [p for _, p in files]


def load_caption(folder: str, override: str | None = None) -> str:
    """caption.txt 를 UTF-8(BOM 허용)로 읽기. 없으면 빈 캡션."""
    path = override or os.path.join(folder, "caption.txt")
    if not os.path.exists(path):
        return ""
    return open(path, encoding="utf-8-sig").read().strip()


def captions_match(sent: str, fetched: str) -> bool:
    """게시 후 재조회한 캡션이 원본과 같은지 (앞뒤 공백·개행 종류만 무시)."""
    norm = lambda s: (s or "").replace("\r\n", "\n").strip()
    return norm(sent) == norm(fetched)


def api(method: str, endpoint: str, token: str, **data):
    """Graph API 호출. 한글 파라미터는 반드시 data 로 전달 (셸 인자 금지)."""
    data["access_token"] = token
    r = requests.request(method, f"{GRAPH}/{endpoint}", data=data, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Graph API 오류 {r.status_code}: {r.text}")
    return r.json()


def host_image(path: str) -> str:
    """litterbox 에 올리고 공개 URL 반환 (1시간 뒤 자동 삭제 — 컨테이너 생성이면 충분)."""
    with open(path, "rb") as f:
        r = requests.post(
            LITTERBOX,
            data={"reqtype": "fileupload", "time": "1h"},
            files={"fileToUpload": f},
            timeout=120,
        )
    r.raise_for_status()
    url = r.text.strip()
    if not url.startswith("http"):
        raise RuntimeError(f"litterbox 업로드 실패: {r.text[:200]}")
    return url


def wait_ready(container_id: str, token: str, timeout_sec: int = 120) -> None:
    """컨테이너가 FINISHED 될 때까지 대기."""
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        status = api("GET", container_id, token, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"컨테이너 {container_id} 처리 실패 (status=ERROR)")
        time.sleep(3)
    raise RuntimeError("컨테이너 준비 대기 시간 초과")


def main() -> None:
    ap = argparse.ArgumentParser(description="인스타그램 카드뉴스 캐러셀 자동 게시")
    ap.add_argument("folder", help='카드뉴스 폴더명 (예: "20260719 카시오시계") 또는 전체 경로')
    ap.add_argument("--caption", help="캡션 파일 경로 (기본: 폴더 안 caption.txt)")
    ap.add_argument("--dry-run", action="store_true", help="실제 게시 없이 절차만 출력")
    args = ap.parse_args()

    folder = resolve_folder(args.folder)
    if not os.path.isdir(folder):
        sys.exit(f"폴더가 없습니다: {folder}")

    images = collect_images(folder)
    caption = load_caption(folder, args.caption)

    print(f"폴더   : {folder}")
    print(f"이미지 : {len(images)}장 → " + ", ".join(os.path.basename(p) for p in images))
    print(f"캡션   : {len(caption)}자" + (f" · 시작: {caption[:30]}…" if caption else " (caption.txt 없음)"))

    if not 2 <= len(images) <= 10:
        sys.exit(f"캐러셀은 2~10장이어야 합니다 (현재 {len(images)}장)")
    if not caption:
        print("경고: 캡션이 비어 있습니다. 캡션 없이 게시됩니다.")

    if args.dry_run:
        print("\n[dry-run] 실제 게시 없이 종료. 절차:")
        print("  1) GET /me 토큰 검증")
        print(f"  2) litterbox 1시간 호스팅 x {len(images)}")
        print(f"  3) 캐러셀 아이템 컨테이너 x {len(images)} → 캐러셀 컨테이너 → FINISHED 대기 → 게시")
        print("  4) permalink 확인 + 캡션 재조회 검증")
        return

    token = load_token()

    print("\n[1/6] 토큰 검증…")
    me = api("GET", "me", token, fields="user_id,username,account_type")
    print(f"       @{me.get('username')} ({me.get('account_type')})")

    print(f"[2/6] 이미지 호스팅 (litterbox, 1시간) x {len(images)}…")
    urls = []
    for p in images:
        url = host_image(p)
        urls.append(url)
        print(f"       {os.path.basename(p)} → {url}")

    print(f"[3/6] 캐러셀 아이템 컨테이너 생성 x {len(urls)}…")
    children = []
    for url in urls:
        res = api("POST", "me/media", token, image_url=url, is_carousel_item="true")
        children.append(res["id"])
        print(f"       {res['id']}")

    print("[4/6] 캐러셀 컨테이너 생성…")
    carousel = api(
        "POST", "me/media", token,
        media_type="CAROUSEL", children=",".join(children), caption=caption,
    )["id"]
    wait_ready(carousel, token)

    print("[5/6] 게시…")
    post_id = api("POST", "me/media_publish", token, creation_id=carousel)["id"]

    print("[6/6] 게시 확인 + 캡션 검증…")
    info = api("GET", post_id, token, fields="permalink,caption")
    permalink = info.get("permalink", "(permalink 조회 실패)")
    if not captions_match(caption, info.get("caption", "")):
        sys.exit(
            "실패: 게시된 캡션이 원본과 다릅니다 (한글 깨짐 의심).\n"
            f"게시물: {permalink}\n"
            "API 로는 수정/삭제가 불가하니 인스타그램 앱에서 확인 후 수동 삭제하세요."
        )
    print(f"\n완료! {permalink}")
    print("캡션 검증: 일치")


if __name__ == "__main__":
    main()
