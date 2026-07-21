"""잡(작업) 상태 관리 — 인메모리 저장소.

FastAPI 앱(app.py)이 백그라운드 스레드에서 파이프라인을 실행하는 동안
잡의 진행 상태를 이 딕셔너리에 기록하고, 프런트/미리보기 페이지가 폴링해
현재 상태를 조회한다. 서버 재시작 시 초기화되는 휘발성 저장소다.
"""
from __future__ import annotations

import uuid

JOBS: dict[str, dict] = {}


def create_job() -> dict:
    """새 잡을 만들어 JOBS 에 등록하고 반환한다 (초기 상태: "받음")."""
    job = {
        "id": str(uuid.uuid4()),
        "status": "받음",
        "error": None,
        "folder": None,
        "images": [],
        "permalink": None,
    }
    JOBS[job["id"]] = job
    return job


def set_status(job: dict, status: str, **extra) -> dict:
    """잡의 status 를 갱신하고, 전달된 추가 필드(error/folder/images/permalink 등)도 함께 반영한다."""
    job["status"] = status
    job.update(extra)
    return job
