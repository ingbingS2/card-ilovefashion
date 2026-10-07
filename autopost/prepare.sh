#!/bin/sh
# daily-feed 0단계 — 데이터 브랜치(claude/autopost-data)를 autopost-data/ worktree로 준비한다.
#   sh autopost/prepare.sh
# 한 줄 명령이라 PC 예약 작업에서도 권한 확인 창 없이 돈다(.claude/settings.json allow).
# 하나라도 실패하면 0이 아닌 코드로 끝난다 — 그때는 더 진행하지 않는다(SKILL 0단계).
set -e
cd "$(dirname "$0")/.."
if [ -x ./.venv/Scripts/python.exe ]; then PY=./.venv/Scripts/python.exe
elif command -v python >/dev/null 2>&1; then PY=python
else PY=python3; fi
$PY -c "import requests, PIL, playwright" 2>/dev/null || $PY -m pip install -q -r autopost/requirements.txt
case "$PY" in
  ./.venv/*) ;;
  *) $PY -m playwright install chromium >/dev/null 2>&1 || $PY -m playwright install --with-deps chromium ;;
esac
if [ "$(uname -s)" = Linux ] && ! fc-list 2>/dev/null | grep -qi "noto sans cjk"; then
  echo "⚠️ 한글 시스템 글꼴 없음(fonts-noto-cjk) — 렌더 결과의 한글 깨짐을 꼭 눈으로 확인"
fi
git fetch -q origin main && git merge -q --ff-only origin/main 2>/dev/null || true
git worktree prune
if [ ! -d autopost-data ]; then
  if git ls-remote --exit-code --heads origin claude/autopost-data >/dev/null; then
    git fetch -q origin claude/autopost-data
    git worktree add -f -B claude/autopost-data autopost-data origin/claude/autopost-data
    git -C autopost-data branch -q -u origin/claude/autopost-data
  else   # 첫 실행 — 데이터 브랜치를 새로 만든다
    git worktree add --detach autopost-data
    git -C autopost-data checkout -q --orphan claude/autopost-data
    git -C autopost-data rm -rfq .
    printf 'episodes/*/assets/\nepisodes/*/_render.html\n' > autopost-data/.gitignore
    cp autopost/seed/history.json autopost/seed/handles.json autopost-data/
    git -C autopost-data add -A && git -C autopost-data commit -qm "autopost: 데이터 브랜치 시작"
    git -C autopost-data push -q -u origin HEAD:claude/autopost-data
  fi
fi
git -C autopost-data pull -q --ff-only origin claude/autopost-data
test -f autopost-data/history.json
# 'TZ=Asia/Seoul'은 Windows Git Bash에서 무시돼 UTC가 나온다 — POSIX 표기 KST-9는 어디서나 KST
today=$(TZ=KST-9 date +%Y%m%d)
echo "준비 완료 · 오늘(KST) $today"
for d in autopost-data/episodes/"$today"*; do
  [ -d "$d" ] && echo "오늘 회차 이미 있음: ${d#autopost-data/episodes/}"
done
exit 0
