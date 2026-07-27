"""대시보드 질문 창 백엔드: 질문 저장 + (키 있으면) Claude 답변 생성.

답변 컨텍스트는 실험 정책(KEYWORD-POLICY.md)·실험 로그(카드뉴스\\*\\result.md)·
기존 질문답변에서 만든다. ANTHROPIC_API_KEY 가 없으면 질문을 "대기" 상태로만
저장하고, 다음 Claude Code 세션이 대기 질문을 읽어 답을 채운다.
"""
from __future__ import annotations

import glob
import json
import os
import threading
import uuid
from datetime import datetime

CARDNEWS_DIR = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop", "카드뉴스")
QA_FILE = os.path.join(CARDNEWS_DIR, "_qa.json")
POLICY_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "KEYWORD-POLICY.md"
)

# add_qa 의 읽기-수정-쓰기를 원자적으로 만들어, 거의 동시에 들어온 두 질문이
# 서로의 저장을 덮어쓰지 않게 한다.
_lock = threading.Lock()

SYSTEM_PROMPT = """당신은 @i_s2_fashion 인스타그램 카드뉴스 계정의 콘텐츠 실험 전략 어드바이저입니다.
운영자는 게시물 1개 = 실험 1개로 취급하고, 저장률을 핵심 판정 지표로 씁니다.
함께 제공되는 실험 정책과 실험 로그를 근거로, 대시보드 질문 창에서 온 질문에 답합니다.

- 한국어로, 숫자 근거를 들어 담백하게. 400자를 넘기지 않습니다.
- 제공된 자료에 없는 사실은 지어내지 말고 모른다고 말합니다.
- HTML 태그·마크다운 없이 일반 텍스트로만 답합니다."""


def load_qas() -> list[dict]:
    """_qa.json 의 질문·답변 목록. 파일이 없거나 깨졌으면 빈 목록."""
    try:
        with open(QA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _save_all(items: list[dict]) -> None:
    with open(QA_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)


def add_qa(question: str, answer: str | None, status: str) -> dict:
    """질문(과 답변)을 목록 끝에 추가하고 저장한 항목을 반환한다."""
    entry = {
        "id": uuid.uuid4().hex[:8],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "question": question,
        "answer": answer,
        "status": status,
    }
    with _lock:
        items = load_qas()
        items.append(entry)
        _save_all(items)
    return entry


def build_context() -> str:
    """정책 + 실험 로그 + 최근 답변된 질문 5개를 답변 근거 자료로 묶는다."""
    parts: list[str] = []

    try:
        with open(POLICY_FILE, encoding="utf-8") as f:
            parts.append("# 실험 정책 (KEYWORD-POLICY.md)\n" + f.read())
    except OSError:
        pass

    for path in sorted(glob.glob(os.path.join(CARDNEWS_DIR, "*", "result.md"))):
        try:
            with open(path, encoding="utf-8") as f:
                parts.append(f"# 실험 로그 ({os.path.basename(os.path.dirname(path))})\n" + f.read())
        except OSError:
            continue

    answered = [q for q in load_qas() if q.get("answer")][-5:]
    if answered:
        lines = [f"Q: {q['question']}\nA: {q['answer']}" for q in answered]
        parts.append("# 기존 질문과 답\n" + "\n\n".join(lines))

    return "\n\n".join(parts)


def answer_question(question: str, api_key: str) -> str:
    """Claude 로 답변 텍스트를 생성한다. 실패는 예외로 전파."""
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    resp = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": f"[프로젝트 자료]\n{build_context()}\n\n[대시보드 질문]\n{question}",
        }],
    )
    text = "".join(
        block.text for block in resp.content if getattr(block, "type", None) == "text"
    ).strip()
    if not text:
        raise RuntimeError("빈 답변을 받았습니다")
    return text
