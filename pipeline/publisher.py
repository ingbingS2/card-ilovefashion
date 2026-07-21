"""인스타그램 게시 — scripts/post_ig.py 의 검증된 플로우(토큰 검증→호스팅→
아이템 컨테이너→캐러셀→FINISHED 대기→게시→permalink+캡션 검증)를 함수 형태로 재사용한다.

post_ig.main() 은 CLI(print/sys.exit) 전용이라 그대로 호출할 수 없으므로,
동일한 함수들(collect_images/load_caption/load_token/api/host_image/wait_ready/
captions_match)을 가져와 웹 앱에서 쓸 수 있는 publish(folder) -> permalink 로 감싼다.
"""
from __future__ import annotations

import os
import sys
import time

_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"
)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

import post_ig  # noqa: E402  (sys.path 조작 이후에 임포트해야 함)


def publish(folder: str) -> str:
    """folder(1.jpg~N.jpg + caption.txt)를 인스타그램 캐러셀로 게시하고 permalink 를 반환한다.

    캡션 재조회 검증에 실패하면 게시물 링크를 포함한 RuntimeError 를 던진다
    (API 로는 수정/삭제가 불가하므로 사용자가 직접 확인할 수 있도록).
    """
    images = post_ig.collect_images(folder)
    if not 2 <= len(images) <= 10:
        raise RuntimeError(f"캐러셀은 2~10장이어야 합니다 (현재 {len(images)}장)")
    caption = post_ig.load_caption(folder)

    token = post_ig.load_token()

    # [1/6] 토큰 검증
    post_ig.api("GET", "me", token, fields="user_id,username,account_type")

    # [2/6] 임시 호스팅
    urls = [post_ig.host_image(p) for p in images]

    # [3/6] 캐러셀 아이템 컨테이너 (인수인계 문서 검증: 간헐적 오류 → 3회 재시도)
    children = []
    for url in urls:
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                res = post_ig.api(
                    "POST", "me/media", token, image_url=url, is_carousel_item="true"
                )
                break
            except RuntimeError as e:
                last_err = e
                time.sleep(4)
        else:
            raise RuntimeError(f"아이템 컨테이너 생성 3회 실패: {last_err}")
        children.append(res["id"])

    # [4/6] 캐러셀 컨테이너 생성 + FINISHED 대기
    carousel = post_ig.api(
        "POST", "me/media", token,
        media_type="CAROUSEL", children=",".join(children), caption=caption,
    )["id"]
    post_ig.wait_ready(carousel, token)

    # [5/6] 게시
    post_id = post_ig.api("POST", "me/media_publish", token, creation_id=carousel)["id"]

    # [6/6] permalink + 캡션 재조회 검증 (한글 깨짐 확인)
    info = post_ig.api("GET", post_id, token, fields="permalink,caption")
    permalink = info.get("permalink", "(permalink 조회 실패)")
    if not post_ig.captions_match(caption, info.get("caption", "")):
        raise RuntimeError(
            "실패: 게시된 캡션이 원본과 다릅니다 (한글 깨짐 의심).\n"
            f"게시물: {permalink}\n"
            "API 로는 수정/삭제가 불가하니 인스타그램 앱에서 확인 후 수동 삭제하세요."
        )
    return permalink
