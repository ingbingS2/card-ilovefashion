"""프로브 응답 분석 헬퍼 (순수 함수만 — 네트워크 없음)."""
from __future__ import annotations

import json
import re
from typing import Any

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


def summarize_json(data: Any, max_depth: int = 3, _depth: int = 0) -> Any:
    """JSON 구조 스케치를 돌려준다.

    dict → 키마다 재귀, list → {"__len__", "__first__"}, 스칼라 → 타입명.
    max_depth 도달 시 컨테이너도 타입명 문자열로 절단.
    """
    if _depth >= max_depth and isinstance(data, (dict, list)):
        return type(data).__name__
    if isinstance(data, dict):
        return {k: summarize_json(v, max_depth, _depth + 1) for k, v in data.items()}
    if isinstance(data, list):
        first = summarize_json(data[0], max_depth, _depth + 1) if data else None
        return {"__len__": len(data), "__first__": first}
    return type(data).__name__


def extract_next_data(html: str) -> dict | None:
    """Next.js 페이지의 __NEXT_DATA__ JSON 을 추출한다. 없거나 깨졌으면 None."""
    m = _NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def safe_name(s: str) -> str:
    """URL 등을 파일명으로 안전하게 변환 (영숫자·._- 유지, 80자 제한)."""
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_")[:80]
