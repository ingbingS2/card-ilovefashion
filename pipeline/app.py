"""FastAPI 원클릭 앱 — 상품 선택 → 카드뉴스 렌더 → 미리보기(게이트) → 인스타 게시.

프런트(fashion-cardnews.web.app)에서 선택한 상품 목록을 받아 백그라운드 스레드로
문구 생성(copywriter) → 렌더(renderer) 파이프라인을 돌리고, 완료되면 미리보기
페이지(/preview/{id})를 통해 사용자가 직접 확인 후 "인스타에 게시" 버튼으로
게시(publisher.publish)를 트리거하는 게이트 구조다.
"""
from __future__ import annotations

import html
import os
import re
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import copywriter
import jobs
import publisher
import reader
import renderer

app = FastAPI(title="패션 카드뉴스 자동 생성")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://fashion-cardnews.web.app",
        "http://localhost:5173",
        "http://localhost:4173",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 완성본 저장 위치: 바탕화면\카드뉴스\YYYYMMDD 주제\ (사용자 확정 규칙)
CARDNEWS_BASE_DIR = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "카드뉴스")

_FILE_NAME_RE = re.compile(r"^([0-9]+\.jpg|caption\.txt)$")

# job_id -> Thread. 백그라운드 스레드 참조를 보관해 테스트에서 join 할 수 있게 한다.
_THREADS: dict[str, threading.Thread] = {}


class SelectionsBody(BaseModel):
    createdAt: str | None = None
    items: list[dict]


def _unique_folder(base_dir: str, name: str) -> str:
    """같은 날 중복 시 " (2)", " (3)" ... 접미사를 붙여 유일한 폴더 경로를 만든다."""
    candidate = os.path.join(base_dir, name)
    if not os.path.isdir(candidate):
        return candidate
    i = 2
    while True:
        candidate = os.path.join(base_dir, f"{name} ({i})")
        if not os.path.isdir(candidate):
            return candidate
        i += 1


def run_pipeline(job: dict, items: list[dict], topic: str = "랭킹 픽") -> None:
    """선택 상품으로 카드뉴스를 생성한다.

    운영에서는 POST /api/selections 가 이 함수를 스레드로 띄우고,
    테스트에서는 (모듈 레벨 reader/copywriter/renderer 를 목 처리한 뒤)
    스레드를 join 하거나 이 함수를 직접 호출해 동기적으로 검증할 수 있다.
    """
    try:
        jobs.set_status(job, "문구 생성 중")
        assets_dir = os.path.join(CARDNEWS_BASE_DIR, "_assets", job["id"])
        products = reader.load_products(items, assets_dir)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        copy = copywriter.write_copy(products, topic, api_key=api_key)

        jobs.set_status(job, "렌더 중")
        folder_name = datetime.now().strftime("%Y%m%d") + " 랭킹픽"
        folder = _unique_folder(CARDNEWS_BASE_DIR, folder_name)
        images = renderer.render(copy, products, folder)

        with open(os.path.join(folder, "caption.txt"), "w", encoding="utf-8") as f:
            f.write(copy["caption"])

        jobs.set_status(job, "미리보기 대기", folder=folder, images=images)
        webbrowser.open(f"http://localhost:8787/preview/{job['id']}")
    except Exception as e:
        jobs.set_status(job, "실패", error=str(e))


def run_publish(job: dict, folder: str) -> None:
    """publisher.publish 를 실행해 잡을 "완료"/"실패" 로 마무리한다."""
    try:
        permalink = publisher.publish(folder)
        jobs.set_status(job, "완료", permalink=permalink)
    except Exception as e:
        jobs.set_status(job, "실패", error=str(e))


@app.post("/api/selections")
def post_selections(body: SelectionsBody):
    job = jobs.create_job()
    t = threading.Thread(target=run_pipeline, args=(job, body.items), daemon=True)
    _THREADS[job["id"]] = t
    t.start()
    return {"job_id": job["id"], "preview_url": f"http://localhost:8787/preview/{job['id']}"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = jobs.JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다")
    return job


@app.get("/preview/{job_id}", response_class=HTMLResponse)
def get_preview(job_id: str):
    job = jobs.JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다")

    status = job["status"]

    if status == "실패":
        return (
            "<html><head><meta charset='utf-8'><title>카드뉴스 생성 실패</title></head>"
            f"<body><h1>실패</h1><p>{html.escape(job.get('error') or '알 수 없는 오류')}</p></body></html>"
        )

    if status == "완료":
        permalink = job.get("permalink") or ""
        return (
            "<html><head><meta charset='utf-8'><title>게시 완료</title></head>"
            "<body><h1>게시 완료</h1>"
            f"<p><a href='{html.escape(permalink)}' target='_blank'>{html.escape(permalink)}</a></p>"
            "</body></html>"
        )

    if status == "미리보기 대기":
        images = job.get("images") or []
        img_tags = "".join(
            f"<img src='/files/{job_id}/{i + 1}.jpg' style='max-width:300px;margin:4px'>"
            for i in range(len(images))
        )

        caption_text = ""
        folder = job.get("folder")
        if folder:
            caption_path = os.path.join(folder, "caption.txt")
            if os.path.isfile(caption_path):
                caption_text = open(caption_path, encoding="utf-8").read()

        return f"""
<html><head><meta charset='utf-8'><title>카드뉴스 미리보기</title></head>
<body>
<h1>미리보기</h1>
<div>{img_tags}</div>
<h2>캡션</h2>
<pre>{html.escape(caption_text)}</pre>
<button id='publish-btn' onclick="
  fetch('/api/jobs/{job_id}/publish', {{method: 'POST'}})
    .then(function() {{ alert('게시를 시작했습니다. 잠시 후 새로고침해 확인하세요.'); }});
">인스타에 게시</button>
<p>완성된 이미지는 다음 폴더에서도 확인할 수 있습니다: {html.escape(folder or '')}</p>
</body></html>
"""

    # 진행 중 (받음 / 문구 생성 중 / 렌더 중 / 게시 중 등) — 3초마다 자동 새로고침
    return f"""
<html><head><meta charset='utf-8'><meta http-equiv='refresh' content='3'><title>카드뉴스 생성 중</title></head>
<body><h1>{html.escape(status)}</h1><p>잠시만 기다려주세요…</p></body></html>
"""


@app.get("/files/{job_id}/{name}")
def get_file(job_id: str, name: str):
    job = jobs.JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다")

    if not _FILE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="잘못된 파일명입니다")

    folder = job.get("folder")
    if not folder:
        raise HTTPException(status_code=404, detail="아직 생성된 폴더가 없습니다")

    path = os.path.join(folder, name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    return FileResponse(path)


@app.post("/api/jobs/{job_id}/publish")
def post_publish(job_id: str):
    job = jobs.JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다")

    folder = job.get("folder")
    if not folder:
        raise HTTPException(status_code=400, detail="아직 렌더링이 끝나지 않았습니다")

    jobs.set_status(job, "게시 중")
    t = threading.Thread(target=run_publish, args=(job, folder), daemon=True)
    _THREADS[job_id] = t
    t.start()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
