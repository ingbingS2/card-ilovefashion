"""CTA 무한도전 짤 — 인터넷에서 찾은 후보를 안전하게 받아 검증하고, 고른 것을 목록에 올린다.

    python -m autopost.zzal fetch <이미지URL> [<이미지URL> ...]      # 후보 받기 → .autopost-work/zzal-candidates/
    python -m autopost.zzal page <글URL>                              # 블로그·커뮤니티 글에서 이미지 주소 뽑기
    python -m autopost.zzal adopt <후보파일> --source <URL> --caption "자막" --scene "장면" --mood "무드" --fits "어울리는 주제"

받는 것은 이미지(jpg/png/webp/gif 첫 프레임)뿐, 5MB 이하, 가로 400px 이상. Pillow로 열어 실제 이미지인지 확인하고
JPG로 다시 저장한다(원본 바이트를 그대로 두지 않는다). 무도 장면인지·자막이 읽히는지·남의 워터마크가 없는지는
세션이 Read로 직접 보고 판단한다 — 코드는 형식만 거른다.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from html import unescape
from urllib.parse import urljoin, urlparse

import requests

from . import config

CAND_DIR = config.WORK_DIR / "zzal-candidates"
MAX_BYTES = 5 * 1024 * 1024
MIN_WIDTH = 400
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36", "Accept": "image/*,*/*;q=0.8"}


def _safe_url(url: str) -> bool:
    """http(s) 공개 호스트만 — 사설·루프백·링크로컬(클라우드 메타데이터 169.254.x)·예약 대역은 DNS를 풀어서 거른다."""
    import ipaddress
    import socket

    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname
    try:
        infos = socket.getaddrinfo(host, p.port or (443 if p.scheme == "https" else 80), proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return True


def fetch(url: str) -> dict:
    """한 장 받아 검증 후 후보 폴더에 JPG로 저장. 반환: {ok, path|reason, size}."""
    from PIL import Image

    if not _safe_url(url):
        return {"ok": False, "url": url, "reason": "http(s) 공개 주소만"}
    try:
        r = requests.get(url, headers=UA, timeout=30, stream=True)
        if any(not _safe_url(h.headers.get("Location", "")) for h in r.history) or not _safe_url(r.url):
            return {"ok": False, "url": url, "reason": "리다이렉트 목적지가 공개 주소가 아님"}
        r.raise_for_status()
        data = r.raw.read(MAX_BYTES + 1, decode_content=True)
    except requests.exceptions.RequestException as e:
        return {"ok": False, "url": url, "reason": f"다운로드 실패 {str(e)[:80]}"}
    if len(data) > MAX_BYTES:
        return {"ok": False, "url": url, "reason": "5MB 초과"}
    try:
        im = Image.open(io.BytesIO(data))
        im.verify()
        im = Image.open(io.BytesIO(data)).convert("RGB")
    except Exception:
        return {"ok": False, "url": url, "reason": "이미지가 아님"}
    if im.width < MIN_WIDTH:
        return {"ok": False, "url": url, "reason": f"너무 작음({im.width}px)"}
    CAND_DIR.mkdir(parents=True, exist_ok=True)
    name = "cand-" + hashlib.sha1(url.encode()).hexdigest()[:10] + ".jpg"
    path = CAND_DIR / name
    im.save(path, quality=92)
    (CAND_DIR / (name + ".src")).write_text(url, encoding="utf-8")
    return {"ok": True, "url": url, "path": str(path), "size": f"{im.width}x{im.height}"}


def page_images(url: str, limit: int = 30) -> list[str]:
    """글 HTML에서 본문 이미지 주소를 뽑는다(아이콘·이모티콘·광고 주소는 거른다)."""
    if not _safe_url(url):
        return []
    try:
        html = requests.get(url, headers={**UA, "Accept": "text/html"}, timeout=30).text
    except requests.exceptions.RequestException:
        return []
    srcs = re.findall(r"""(?:data-src|data-original|src)\s*=\s*["']([^"']+\.(?:jpe?g|png|webp|gif)(?:\?[^"']*)?)["']""",
                      html, flags=re.I)
    out = []
    for s in srcs:
        full = urljoin(url, unescape(s))
        if any(w in full.lower() for w in ("icon", "emoticon", "logo", "banner", "profile", "btn", "sprite", "ads")):
            continue
        if full not in out:
            out.append(full)
    return out[:limit]


def adopt(cand: str, source: str, caption: str, scene: str, mood: str, fits: str) -> dict:
    """후보를 데이터 브랜치 autopost-data/zzal/web-YYYYMMDD-N.jpg로 옮기고 그 index.json에 항목 추가.

    (main 작업 폴더 CARD/zzal이 아니라 데이터 브랜치에 두는 이유: main 커밋 금지 규칙·클라우드 컨테이너 소멸 뒤에도 보존.)"""
    from shutil import copyfile
    from pathlib import Path

    src = Path(cand)
    if not src.is_file() or src.parent.resolve() != CAND_DIR.resolve():
        raise SystemExit("후보 폴더(.autopost-work/zzal-candidates)의 파일만 올릴 수 있습니다")
    config.ZZAL_WEB_DIR.mkdir(parents=True, exist_ok=True)
    today = config.now_kst().strftime("%Y%m%d")
    n = 1
    while (config.ZZAL_WEB_DIR / f"web-{today}-{n}.jpg").exists() or (config.ZZAL_DIR / f"web-{today}-{n}.jpg").exists():
        n += 1
    dest = config.ZZAL_WEB_DIR / f"web-{today}-{n}.jpg"
    copyfile(src, dest)
    idx = json.loads(config.ZZAL_WEB_INDEX.read_text(encoding="utf-8")) if config.ZZAL_WEB_INDEX.exists() else {"zzal": []}
    entry = {"file": dest.name, "caption": caption, "scene": scene, "mood": mood, "fits": fits,
             "last_used": "", "source": source}
    idx["zzal"].append(entry)
    config.ZZAL_WEB_INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return entry


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="CTA 짤 후보 받기·올리기")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch"); f.add_argument("urls", nargs="+")
    p = sub.add_parser("page"); p.add_argument("url")
    a = sub.add_parser("adopt")
    a.add_argument("cand"); a.add_argument("--source", required=True); a.add_argument("--caption", required=True)
    a.add_argument("--scene", required=True); a.add_argument("--mood", required=True); a.add_argument("--fits", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        for u in args.urls:
            print(json.dumps(fetch(u), ensure_ascii=False))
    elif args.cmd == "page":
        print("\n".join(page_images(args.url)))
    else:
        print(json.dumps(adopt(args.cand, args.source, args.caption, args.scene, args.mood, args.fits), ensure_ascii=False))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
