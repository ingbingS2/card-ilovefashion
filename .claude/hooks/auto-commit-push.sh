#!/usr/bin/env bash
# Claude Code Stop hook: 코드 수정이 있으면 자동으로 커밋하고 푸시한다.
# 변경 사항이 없으면 아무 것도 하지 않고 조용히 종료한다.

cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0

# git 저장소가 아니면 종료
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0

# 모든 변경 사항 스테이징
git add -A

# 스테이징된 변경이 없으면 조용히 종료
git diff --cached --quiet && exit 0

msg="chore: auto-commit by Claude Code ($(date '+%Y-%m-%d %H:%M:%S'))"
git commit -m "$msg" >/dev/null 2>&1

# 현재 브랜치를 origin으로 푸시 (업스트림 자동 설정)
branch="$(git rev-parse --abbrev-ref HEAD)"
git push -u origin "$branch" >/dev/null 2>&1

exit 0
