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

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

import copywriter
import jobs
import publisher
import qa
import reader
import renderer


def _load_env_file() -> None:
    """pipeline/.env 가 있으면 환경변수로 로드한다 (이미 설정된 값이 우선)."""
    try:
        lines = (Path(__file__).resolve().parent / ".env").read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env_file()

app = FastAPI(title="패션 카드뉴스 자동 생성")

ALLOWED_ORIGINS = [
    "https://fashion-cardnews.web.app",
    "http://localhost:5173",
    "http://localhost:4173",
    # 미리보기 페이지(이 앱이 직접 서빙)의 "게시" 버튼도 자기 오리진으로 POST 하므로 허용해야 한다.
    "http://localhost:8787",
    "http://127.0.0.1:8787",
]

# CORS 에는 "null"(file:// 로 연 대시보드)도 허용해 조회(GET)는 되게 한다.
# 상태를 바꾸는 POST 는 _reject_untrusted_origin 이 ALLOWED_ORIGINS 로만 판정하므로
# file:// 페이지는 여전히 게시/질문 등록을 못 한다 (읽기 전용).
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS + ["null"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 이 앱은 로컬(127.0.0.1:8787)에서만 떠 있는 개인용 원클릭 서버다 — 다른 호스트로
# 위장한 Host 헤더 요청(DNS 리바인딩 등)을 미리 걸러낸다.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

# 완성본 저장 위치: 바탕화면\카드뉴스\YYYYMMDD 주제\ (사용자 확정 규칙)
CARDNEWS_BASE_DIR = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "카드뉴스")

# 마지막(CTA) 카드 이미지로 쓰는 무한도전 짤 폴더 (KEYWORD-POLICY.md — 항상 최신 파일 사용)
ZZAL_DIR = Path(__file__).resolve().parents[1] / "CARD" / "zzal"


def _latest_zzal() -> str | None:
    """CARD/zzal 에서 가장 최근 수정된 이미지 경로. 폴더가 없거나 비어 있으면 None."""
    try:
        files = [p for p in ZZAL_DIR.iterdir()
                 if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")]
    except OSError:
        return None
    if not files:
        return None
    return str(max(files, key=lambda p: p.stat().st_mtime))

_FILE_NAME_RE = re.compile(r"^([0-9]+\.jpg|caption\.txt)\Z")

# job_id -> Thread. 백그라운드 스레드 참조를 보관해 테스트에서 join 할 수 있게 한다.
_THREADS: dict[str, threading.Thread] = {}

# 게시 상태 확인+전환을 원자적으로 만들어, 거의 동시에 들어온 두 POST 가 모두
# "미리보기 대기"를 통과해 게시 스레드를 이중으로 띄우는 경쟁을 막는다.
_publish_lock = threading.Lock()


def _reject_untrusted_origin(request: Request) -> None:
    """상태를 바꾸는 엔드포인트(선택 제출/게시)에서, Origin 헤더가 있는데 허용
    목록에 없으면 거부한다. Origin 헤더가 아예 없는 요청(같은 프로세스, curl 등)은
    통과시킨다 — 이 앱은 브라우저 프런트에서만 호출되는 걸 전제하지 않기 때문."""
    origin = request.headers.get("origin")
    if origin and origin not in ALLOWED_ORIGINS:
        raise HTTPException(status_code=403, detail="허용되지 않은 출처(Origin)입니다")


class SelectionsBody(BaseModel):
    createdAt: str | None = None
    topic: str | None = None       # 대시보드 주제 선택기에서 고른 트렌드 키워드
    topicNote: str | None = None   # 그 주제가 왜 지금 유행인지 한 줄 (카드 정보 블록 근거)
    items: list[dict]


_FOLDER_FORBIDDEN = '<>:"/\\|?*'


def _safe_folder_part(name: str) -> str:
    """주제 문자열을 윈도우 폴더명으로 쓸 수 있게 정리한다.

    주제는 topics.ts 에서 오는 한국어 키워드지만, 사용자가 임의 문자열을 보낼 수도 있어
    경로 구분자·예약문자를 제거한다. 전부 걸러져 비면 호출부가 계절 기본값을 쓰도록 빈 문자열을 돌려준다.
    """
    cleaned = "".join(" " if c in _FOLDER_FORBIDDEN else c for c in name)
    cleaned = " ".join(cleaned.split()).strip(" .")
    return cleaned[:60]


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


_SEASON_BY_MONTH = {12: "겨울", 1: "겨울", 2: "겨울", 3: "봄", 4: "봄", 5: "봄",
                    6: "여름", 7: "여름", 8: "여름", 9: "가을", 10: "가을", 11: "가을"}


def run_pipeline(
    job: dict,
    items: list[dict],
    topic: str | None = None,
    topic_note: str | None = None,
) -> None:
    """선택 상품으로 카드뉴스를 생성한다.

    운영에서는 POST /api/selections 가 이 함수를 스레드로 띄우고,
    테스트에서는 (모듈 레벨 reader/copywriter/renderer 를 목 처리한 뒤)
    스레드를 join 하거나 이 함수를 직접 호출해 동기적으로 검증할 수 있다.

    topic 은 대시보드 상단 주제 선택기에서 고른 트렌드 키워드다. 카피 주제이자
    결과 폴더명이 된다. topic_note 는 그 주제가 왜 지금 유행인지에 대한 한 줄로,
    카피라이터가 카드 정보 블록을 쓸 때 근거로 쓴다.
    """
    try:
        jobs.set_status(job, "문구 생성 중")
        season = _SEASON_BY_MONTH.get(datetime.now().month, "여름")
        topic = (topic or "").strip() or f"{season} 무드"  # 미선택 시 계절 기본값
        assets_dir = os.path.join(CARDNEWS_BASE_DIR, "_assets", job["id"])
        products = reader.load_products(items, assets_dir)
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        copy = copywriter.write_copy(products, topic, api_key=api_key, topic_note=topic_note)

        # 마지막(CTA) 카드는 항상 무한도전 짤 (KEYWORD-POLICY.md). 짤이 없으면 기존 폴백 유지.
        zzal = _latest_zzal()
        if zzal and isinstance(copy.get("cta"), dict):
            copy["cta"]["image_path"] = zzal

        jobs.set_status(job, "렌더 중")
        # 폴더명 = "YYYYMMDD 키워드" (KEYWORD-POLICY). 주제를 고르지 않으면 계절 기본값이라
        # 폴더명이 매번 겹친다 — 그래서 대시보드가 주제 미선택을 경고한다.
        folder_part = _safe_folder_part(topic) or f"{season}무드"
        folder_name = f"{datetime.now().strftime('%Y%m%d')} {folder_part}"
        folder = _unique_folder(CARDNEWS_BASE_DIR, folder_name)
        images = renderer.render(copy, products, folder)

        with open(os.path.join(folder, "caption.txt"), "w", encoding="utf-8") as f:
            f.write(copy["caption"])

        jobs.set_status(job, "미리보기 대기", folder=folder, images=images)
    except (Exception, SystemExit) as e:
        # post_ig.py 재사용 함수(load_token/collect_images 등)는 실패 시 sys.exit() 를
        # 호출해 SystemExit(BaseException)을 던진다. 이를 놓치면 스레드가 조용히 죽고
        # 잡이 진행 중 상태에 영구히 멈추므로(미리보기 자동새로고침만 무한 반복) 함께 잡는다.
        jobs.set_status(job, "실패", error=str(e) or "처리 실패")
        return

    # 미리보기 창 자동 열기는 기본으로 끈다 — 생성·재수정을 반복하면 탭이 계속 쌓인다
    # (2026-08-06 사용자 지시). 주소는 아래 로그와 POST /api/selections 응답에 있으니
    # 사용자가 이미 열어둔 탭을 새로고침하면 된다. 예전 동작이 필요하면 pipeline/.env 에
    # PIPELINE_AUTO_OPEN=1 을 넣는다.
    preview_url = f"http://localhost:8787/preview/{job['id']}"
    print(f"미리보기 준비 완료: {preview_url}")
    if os.environ.get("PIPELINE_AUTO_OPEN", "").strip().lower() in ("1", "true", "yes"):
        # 자동 열기는 부가 기능일 뿐이라 try 밖에서 별도로 감싼다 — 이게 실패해도
        # (예: 브라우저 없음) 이미 정상 완료된 잡을 "실패"로 되돌리면 안 된다.
        try:
            webbrowser.open(preview_url)
        except Exception:
            pass


def run_publish(job: dict, folder: str) -> None:
    """publisher.publish 를 실행해 잡을 "완료"/"실패" 로 마무리한다."""
    try:
        permalink = publisher.publish(folder)
        jobs.set_status(job, "완료", permalink=permalink)
    except (Exception, SystemExit) as e:
        # 위 run_pipeline 과 동일한 이유로 SystemExit 도 함께 포착한다.
        jobs.set_status(job, "실패", error=str(e) or "게시 실패")


@app.post("/api/selections")
def post_selections(body: SelectionsBody, request: Request):
    _reject_untrusted_origin(request)
    if not body.items:
        # 빈 선택으로 잡을 띄우면 썸네일까지 받아온 뒤 렌더 단계에서야 터진다.
        # 여기서 바로 막아 대시보드가 이유를 보여줄 수 있게 한다.
        raise HTTPException(status_code=400, detail="선택된 상품이 없습니다")
    job = jobs.create_job()
    t = threading.Thread(
        target=run_pipeline, args=(job, body.items, body.topic, body.topicNote), daemon=True
    )
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
  var btn = this;
  btn.disabled = true;
  btn.textContent = '게시 중…';
  function reset() {{ btn.disabled = false; btn.textContent = '인스타에 게시'; }}
  fetch('/api/jobs/{job_id}/publish', {{method: 'POST'}})
    .then(function(res) {{
      if (res.ok) {{
        alert('게시를 시작했습니다. 잠시 후 새로고침해 확인하세요.');
      }} else {{
        reset();
        alert('게시할 수 없습니다 (상태 ' + res.status + '). 새로고침 후 다시 시도하세요.');
      }}
    }})
    .catch(function() {{
      reset();
      alert('게시 요청에 실패했습니다. 새로고침 후 다시 시도하세요.');
    }});
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


DASHBOARD_FILE = os.path.join(CARDNEWS_BASE_DIR, "_dashboard.html")

# 대시보드 썸네일(카드뉴스 폴더의 1.jpg 등)을 서버 모드에서도 쓸 수 있게 서빙.
# StaticFiles 로 카드뉴스 폴더를 통째로 마운트하면 같은 폴더에 있는
# ig_api_token.txt(인스타 장기 토큰)·_qa.json 까지 인증 없이 내려간다.
# 대시보드가 실제로 쓰는 건 썸네일 이미지뿐이므로 이미지 확장자만 내보낸다.
_CARDNEWS_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")


@app.get("/cardnews-files/{path:path}")
def get_cardnews_file(path: str):
    base = Path(CARDNEWS_BASE_DIR).resolve()
    try:
        target = (base / path).resolve()
    except OSError:
        raise HTTPException(status_code=400, detail="잘못된 경로입니다")

    # 경로 탈출(../, 심볼릭 링크)로 카드뉴스 폴더 밖을 읽는 것을 막는다.
    if not target.is_relative_to(base):
        raise HTTPException(status_code=403, detail="허용되지 않은 경로입니다")
    if target.suffix.lower() not in _CARDNEWS_IMAGE_EXTS:
        raise HTTPException(status_code=403, detail="이미지 파일만 제공합니다")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    return FileResponse(target)


class QABody(BaseModel):
    question: str


@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    if not os.path.isfile(DASHBOARD_FILE):
        raise HTTPException(status_code=404, detail="대시보드 파일이 없습니다")
    return HTMLResponse(open(DASHBOARD_FILE, encoding="utf-8").read())


@app.get("/api/qa")
def list_qa():
    return {"items": qa.load_qas()}


@app.post("/api/qa")
def post_qa(body: QABody, request: Request):
    _reject_untrusted_origin(request)

    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="질문이 비어 있습니다")
    if len(question) > 2000:
        raise HTTPException(status_code=400, detail="질문이 너무 깁니다 (2000자 이내)")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        # 키가 없으면 즉답 불가 — "대기"로 저장하고 다음 Claude Code 세션이 채운다.
        return qa.add_qa(question, None, "대기")

    try:
        answer = qa.answer_question(question, api_key)
    except Exception:
        # 답변 생성 실패(네트워크·크레딧·과부하 등)로 질문까지 잃으면 안 된다 —
        # "대기"로 폴백 저장하고 성공 응답을 돌려준다 (프런트가 대기 안내를 표시).
        return qa.add_qa(question, None, "대기")
    return qa.add_qa(question, answer, "완료")


@app.post("/api/jobs/{job_id}/publish")
def post_publish(job_id: str, request: Request):
    _reject_untrusted_origin(request)

    job = jobs.JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="잡을 찾을 수 없습니다")

    folder = job.get("folder")
    if not folder:
        raise HTTPException(status_code=400, detail="아직 렌더링이 끝나지 않았습니다")

    # 게시는 되돌릴 수 없다 — "미리보기 대기" 상태에서만 시작할 수 있고, 상태
    # 확인+전환을 락으로 묶어 거의 동시에 들어온 두 요청이 둘 다 통과하는 경쟁을
    # 막는다. 이미 게시 중/완료/실패인 잡은 재게시(중복 게시) 대신 거부한다.
    with _publish_lock:
        if job["status"] != "미리보기 대기":
            raise HTTPException(
                status_code=409,
                detail=f"이미 게시가 진행 중이거나 끝난 잡입니다 (현재 상태: {job['status']})",
            )
        jobs.set_status(job, "게시 중")

    t = threading.Thread(target=run_publish, args=(job, folder), daemon=True)
    _THREADS[job_id] = t
    t.start()
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
