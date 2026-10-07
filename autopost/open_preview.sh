#!/bin/sh
# PC에서 회차 결과물을 D:\카드뉴스\<폴더명>\ 에 복사하고 _preview.html을 Chrome으로 연다(10-07 사용자 지시).
#   sh autopost/open_preview.sh "20261007 가을 하렘팬츠"
# 클라우드(Linux)에서는 아무것도 하지 않는다 — 미리보기는 GitHub 링크로 본다.
set -e
cd "$(dirname "$0")/.."
folder="${1:?폴더명이 필요합니다}"
src="autopost-data/episodes/$folder"
[ -d "$src" ] || { echo "회차 폴더 없음: $src" >&2; exit 1; }
if [ "$(uname -s)" = Linux ]; then echo "클라우드 — 로컬 미리보기 생략"; exit 0; fi
base="/d/카드뉴스"
[ -d "$base" ] || base="$(cd .. && pwd)/카드뉴스"
dst="$base/$folder"
mkdir -p "$dst"
cp "$src"/[1-7].jpg "$src/caption.txt" "$src/_preview.html" "$dst/"
win=$(cygpath -w "$dst/_preview.html" 2>/dev/null || echo "$dst/_preview.html")
powershell.exe -NoProfile -Command "Start-Process chrome -ArgumentList ('\"' + '$win' + '\"')" >/dev/null 2>&1 \
  || echo "Chrome을 열지 못함 — 직접 여세요"
echo "미리보기: $win"
