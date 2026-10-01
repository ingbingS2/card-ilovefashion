"""이력(history.json)·핸들(handles.json)·회차 상태(status.json) 읽기/쓰기."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from pathlib import Path

from . import config


class DataDirMissing(RuntimeError):
    pass


def _load(path: Path, seed_name: str):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    # 데이터 브랜치 없이 시드(9월 이력)로 판정하면 20시간 간격·직전 브랜드 규칙이 틀어진다 → 명시적으로만 허용
    if not os.environ.get("AUTOPOST_ALLOW_SEED"):
        raise DataDirMissing(
            f"{path} 이(가) 없습니다. 데이터 브랜치 worktree(autopost-data/)를 먼저 준비하세요 "
            "(SKILL.md 0단계). 시드로 시작하려면 AUTOPOST_ALLOW_SEED=1.")
    return json.loads((config.SEED_DIR / seed_name).read_text(encoding="utf-8"))


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_history() -> list[dict]:
    return _load(config.HISTORY_FILE, "history.json")


def save_history(rows: list[dict]) -> None:
    _save(config.HISTORY_FILE, rows)


def load_handles() -> dict:
    return _load(config.HANDLES_FILE, "handles.json")


def save_handles(data: dict) -> None:
    _save(config.HANDLES_FILE, data)


# ---------- 회차 상태 ----------

def load_status(folder: str) -> dict:
    path = config.episode_dir(folder) / "status.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_status(folder: str, status: dict) -> None:
    _save(config.episode_dir(folder) / "status.json", status)


def fingerprint(folder: str) -> str:
    """build 입력(episode·candidates)과 출력(caption·1~7.jpg)의 해시. 하나라도 바뀌면 재검증·재승인 대상."""
    d = config.episode_dir(folder)
    h = hashlib.sha256()
    names = ["episode.json", "candidates.json", "caption.txt"] + [f"{i}.jpg" for i in range(1, 8)]
    for name in names:
        p = d / name
        h.update(name.encode())
        h.update(p.read_bytes() if p.exists() else b"<missing>")
    return h.hexdigest()


# ---------- 브랜드·키워드 비교 ----------

def norm_brand(name: str) -> str:
    """'파르티멘토 우먼' / 'PARTIMENTO WOMEN' 비교용 키 — 공백·기호 제거, 소문자."""
    return re.sub(r"[^0-9a-z가-힣]", "", (name or "").lower())


def same_brand(a: str, b: str) -> bool:
    """'파르티멘토' ↔ '파르티멘토 우먼'도 같은 브랜드로 본다(연속 금지 판정용)."""
    x, y = norm_brand(a), norm_brand(b)
    if not x or not y:
        return False
    return x == y or (min(len(x), len(y)) >= 3 and (x.startswith(y) or y.startswith(x)))


def same_keyword(a: str, b: str) -> bool:
    return re.sub(r"\s", "", a or "") == re.sub(r"\s", "", b or "")


def find_handle(handles: dict, *names: str) -> dict | None:
    """브랜드 한글명·영문명·무신사 브랜드 ID 중 하나라도 레지스트리 이름/별칭과 맞으면 그 항목."""
    keys = {norm_brand(n) for n in names if n}
    keys.discard("")
    entries = handles.get("brands", [])
    for entry in entries:  # 정확히 같은 이름 우선
        aliases = {norm_brand(entry["name"])} | {norm_brand(a) for a in entry.get("aliases", [])}
        if keys & aliases:
            return entry
    for entry in entries:  # '무드인사이드 우먼' ↔ '무드인사이드'처럼 접두가 같은 경우
        aliases = {norm_brand(entry["name"])} | {norm_brand(a) for a in entry.get("aliases", [])}
        for k in keys:
            for a in aliases:
                if len(a) >= 3 and len(k) >= 3 and (k.startswith(a) or a.startswith(k)):
                    return entry
    return None


def excluded_brand(today: date, *names: str) -> str | None:
    hay = " ".join(n for n in names if n).lower()
    for label, (until, needles) in config.BRAND_EXCLUSIONS.items():
        if today <= until and any(n.lower() in hay for n in needles):
            return f"{label} — {until.isoformat()}까지 제외(사용자 지시)"
    return None


# ---------- 이력 ----------

def posted(history: list[dict]) -> list[dict]:
    return sorted((h for h in history if h.get("posted_at")), key=lambda h: h["posted_at"])


def last_post(history: list[dict]) -> dict | None:
    rows = posted(history)
    return rows[-1] if rows else None


def parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=config.KST)
