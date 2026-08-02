#!/usr/bin/env bash
# Claude Code SessionStart hook.
# PROJECT-BRIEF.md 를 세션 시작 컨텍스트에 통째로 주입한다.
# → 새 에이전트는 아무 것도 안 해도 프로젝트 지도를 먼저 읽은 상태에서 시작한다.
# 실패해도 세션을 막지 않는다 (항상 exit 0).

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
[ -f "PROJECT-BRIEF.md" ] || exit 0

PY=""
for c in python python3 "/c/Users/yepdo/AppData/Local/Programs/Python/Python312/python.exe"; do
  command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
done
[ -n "$PY" ] || exit 0

"$PY" - <<'PYEOF' 2>/dev/null || exit 0
import json, sys

try:
    with open("PROJECT-BRIEF.md", encoding="utf-8") as f:
        brief = f.read()
except OSError:
    sys.exit(0)

header = (
    "이 저장소(fashion-cardnews)에서 작업하기 전에 반드시 아래 온보딩 브리프를 반영해라.\n"
    "이것은 참고 자료가 아니라 작업 규칙이다. 특히 §2 절대 규칙과 §8 함정은 어기면 사고로 이어진다.\n"
    "카드뉴스 관련 작업이라면 KEYWORD-POLICY.md 도 반드시 열어서 읽어라 (브리프는 요약본일 뿐이다).\n"
    "원본 경로: PROJECT-BRIEF.md\n\n"
    "===== PROJECT-BRIEF.md (전문) =====\n"
)

# ensure_ascii=True 로 순수 ASCII JSON 을 낸다.
# (한국어 Windows 의 stdout 기본 인코딩이 cp949 라, 한글을 그대로 print 하면
#  UnicodeEncodeError 로 훅이 조용히 아무것도 출력하지 않는다.)
sys.stdout.write(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": header + brief,
    },
    "suppressOutput": True,
}, ensure_ascii=True))
PYEOF

exit 0
