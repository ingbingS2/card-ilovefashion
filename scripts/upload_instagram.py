# -*- coding: utf-8 -*-
"""인스타그램 카드뉴스 캐러셀 자동 업로드 (Instagram Graph API 공식).

사용법:
    python upload_instagram.py "C:\\Users\\yepdo\\OneDrive\\Desktop\\카드뉴스\\20260718 롱스커트"
    python upload_instagram.py <폴더> --dry-run          # 실제 게시 없이 절차만 확인
    python upload_instagram.py <폴더> --caption cap.txt  # 캡션 파일 지정 (기본: 폴더 안 caption.txt)

폴더 규칙: 1.jpg ~ N.jpg (순서대로 캐러셀, 최대 10장)

.env (이 파일과 같은 scripts/ 폴더에 두기, 절대 커밋 금지):
    IG_USER_ID=...          # 인스타그램 계정 숫자 ID
    IG_ACCESS_TOKEN=...     # Instagram Login 장기 토큰 (60일, 갱신 가능)
    IMGBB_API_KEY=...       # 이미지 임시 호스팅용 (api.imgbb.com, 무료)

원리: Graph API는 로컬 파일을 받지 않고 공개 URL만 받으므로,
  1) imgbb에 JPG 업로드(공개 URL 확보, 자동 만료 설정)
  2) URL마다 캐러셀 아이템 컨테이너 생성
  3) 캐러셀 컨테이너 생성(캡션 포함) → 게시
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

import requests

GRAPH = "https://graph.instagram.com/v23.0"
IMGBB = "https://api.imgbb.com/1/upload"
IMGBB_EXPIRE_SEC = 24 * 3600  # 게시 후엔 원본 URL이 필요 없으므로 24시간 뒤 자동 삭제


def load_env(path: str) -> dict:
    env = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    for k in ("IG_USER_ID", "IG_ACCESS_TOKEN", "IMGBB_API_KEY"):
        env.setdefault(k, os.environ.get(k, ""))
    return env


def collect_images(folder: str) -> list[str]:
    files = []
    for name in os.listdir(folder):
        m = re.fullmatch(r"(\d+)\.jpe?g", name, re.IGNORECASE)
        if m:
            files.append((int(m.group(1)), os.path.join(folder, name)))
    files.sort()
    return [p for _, p in files]


def host_image(path: str, api_key: str) -> str:
    """imgbb에 올리고 공개 URL 반환 (24시간 뒤 자동 삭제)."""
    with open(path, "rb") as f:
        r = requests.post(
            IMGBB,
            params={"key": api_key, "expiration": IMGBB_EXPIRE_SEC},
            files={"image": f},
            timeout=60,
        )
    r.raise_for_status()
    return r.json()["data"]["url"]


def api(method: str, endpoint: str, token: str, **params):
    params["access_token"] = token
    r = requests.request(method, f"{GRAPH}/{endpoint}", params=params, timeout=60)
    if not r.ok:
        raise RuntimeError(f"Graph API 오류 {r.status_code}: {r.text}")
    return r.json()


def wait_ready(container_id: str, token: str, timeout_sec: int = 120):
    """컨테이너가 게시 가능 상태(FINISHED)가 될 때까지 대기."""
    t0 = time.time()
    while time.time() - t0 < timeout_sec:
        status = api("GET", container_id, token, fields="status_code").get("status_code")
        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(f"컨테이너 {container_id} 처리 실패")
        time.sleep(3)
    raise RuntimeError("컨테이너 준비 대기 시간 초과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", help="1.jpg~N.jpg가 든 카드뉴스 폴더")
    ap.add_argument("--caption", help="캡션 텍스트 파일 (기본: 폴더 안 caption.txt)")
    ap.add_argument("--dry-run", action="store_true", help="실제 게시 없이 절차만 출력")
    args = ap.parse_args()

    env = load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

    images = collect_images(args.folder)
    if not images:
        sys.exit("이미지(1.jpg~N.jpg)가 없습니다: " + args.folder)
    if len(images) > 10:
        sys.exit(f"캐러셀은 최대 10장입니다 (현재 {len(images)}장)")

    cap_path = args.caption or os.path.join(args.folder, "caption.txt")
    caption = open(cap_path, encoding="utf-8").read().strip() if os.path.exists(cap_path) else ""

    print(f"폴더      : {args.folder}")
    print(f"이미지    : {len(images)}장 → " + ", ".join(os.path.basename(p) for p in images))
    print(f"캡션      : {'(' + str(len(caption)) + '자) ' + caption[:40] + '…' if caption else '없음 — caption.txt를 폴더에 두면 자동 사용'}")

    if args.dry_run:
        print("\n[dry-run] 실제 게시 없이 종료합니다. 절차:")
        print("  1) imgbb 업로드 → 공개 URL 확보 (24h 자동 만료)")
        print("  2) 캐러셀 아이템 컨테이너 생성 x", len(images))
        print("  3) 캐러셀 컨테이너 생성(캡션 포함) → status FINISHED 대기 → 게시")
        return

    missing = [k for k in ("IG_USER_ID", "IG_ACCESS_TOKEN", "IMGBB_API_KEY") if not env[k]]
    if missing:
        sys.exit("scripts/.env에 다음 값이 필요합니다: " + ", ".join(missing))

    user, token = env["IG_USER_ID"], env["IG_ACCESS_TOKEN"]

    print("\n1/4 이미지 호스팅(imgbb)…")
    urls = []
    for p in images:
        url = host_image(p, env["IMGBB_API_KEY"])
        urls.append(url)
        print("   ", os.path.basename(p), "→", url)

    print("2/4 캐러셀 아이템 컨테이너 생성…")
    children = []
    for url in urls:
        res = api("POST", f"{user}/media", token, image_url=url, is_carousel_item="true")
        children.append(res["id"])
        print("   ", res["id"])

    print("3/4 캐러셀 컨테이너 생성…")
    carousel = api(
        "POST", f"{user}/media", token,
        media_type="CAROUSEL", children=",".join(children), caption=caption,
    )["id"]
    wait_ready(carousel, token)

    print("4/4 게시…")
    post = api("POST", f"{user}/media_publish", token, creation_id=carousel)
    print("\n완료! media id:", post["id"])


if __name__ == "__main__":
    main()
