#!/bin/sh
# autopost 명령 실행기 — Claude Code의 Bash 호출은 셸 변수를 이어 주지 않으므로 매번 이걸로 부른다.
#   sh autopost/ap.sh <collect|build|verify|publish|measure|zzal> [인자…]
# PC(Windows)는 .venv 파이썬 + 설치된 Chrome, 클라우드(Linux)는 시스템 python + Playwright chromium.
set -e
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
if [ -x ./.venv/Scripts/python.exe ]; then
  PY=./.venv/Scripts/python.exe
  CHROME="C:/Program Files/Google/Chrome/Application/chrome.exe"
  if [ -z "${CHROME_PATH:-}" ] && [ -f "$CHROME" ]; then export CHROME_PATH="$CHROME"; fi
elif [ -x ./.venv/bin/python ]; then
  PY=./.venv/bin/python
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  PY=python3
fi
mod="${1:-}"
case "$mod" in
  collect|build|verify|publish|measure|zzal) shift ;;
  *) echo "사용법: sh autopost/ap.sh <collect|build|verify|publish|measure|zzal> [인자…]" >&2; exit 64 ;;
esac
exec "$PY" -m "autopost.$mod" "$@"
