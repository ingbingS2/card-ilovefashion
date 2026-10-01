#!/usr/bin/env bash
# Claude Code Stop hook: 코드 수정이 있으면 자동으로 커밋하고 푸시한다.
# 변경 사항이 없으면 아무 것도 하지 않고 조용히 종료한다.

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

# 클라우드 루틴(autopost)에서는 쓰지 않는다 — 결과물은 claude/autopost-data 브랜치에 세션이 직접 푸시한다
[ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && exit 0

# git 저장소가 아니면 종료
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# 모든 변경 사항 스테이징 — 단, 기계별 승인 기록(settings.local.json)은 비밀이 섞일 수 있어 제외
git add -A -- . ':!.claude/settings.local.json'

# 스테이징된 변경이 없으면 조용히 종료
git diff --cached --quiet && exit 0

# 비밀 검사: 인스타 토큰(IGAA…)·일반 토큰 패턴이 스테이징에 있으면 커밋하지 않는다(공개 저장소)
if git diff --cached -U0 | grep -E '^\+' | grep -Eq 'IGAA[A-Za-z0-9_-]{40,}|access_token=[A-Za-z0-9_-]{40,}|sk-ant-[A-Za-z0-9_-]{20,}'; then
  echo "auto-commit 중단: 스테이징된 변경에 토큰으로 보이는 문자열이 있습니다." >&2
  git reset -q
  exit 0
fi

msg="chore: auto-commit by Claude Code ($(date '+%Y-%m-%d %H:%M:%S'))"
git commit -m "$msg" >/dev/null 2>&1

# 현재 브랜치를 origin으로 푸시 (업스트림 자동 설정)
branch="$(git rev-parse --abbrev-ref HEAD)"
git push -u origin "$branch" >/dev/null 2>&1

exit 0
