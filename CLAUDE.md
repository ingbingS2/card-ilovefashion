# CLAUDE.md — 개발 규칙

> 처음 작업하는 에이전트는 **[PROJECT-BRIEF.md](PROJECT-BRIEF.md)**(지도·현재 상태)를 먼저 읽는다. 세션 시작 훅이 자동 주입하지만 안 됐으면 직접 읽어라.
> 카드뉴스 작업이면 **[KEYWORD-POLICY.md](KEYWORD-POLICY.md)**(규칙 원본)를 반드시 함께 연다.

패션 인스타 계정 @i_s2_fashion 운영 자동화: 크롤러(무신사·29CM → Firestore) → 카드뉴스 제작(card-drafts/, pipeline/) → 인스타 게시(scripts/post_ig.py). React 대시보드 + FastAPI + Firebase.

## 절대 규칙
- 카드뉴스 키워드·문구·디자인·검증·게시는 KEYWORD-POLICY.md를 따른다. 랭킹 키워드 금지, 항상 시즌성.
- **실제 인스타 게시는 사용자 승인 후에만.** 되돌릴 수 없다.
- 사용자 노출 UI 텍스트는 한국어(코드 식별자·주석은 영어 허용).
- 실제 외부 호출·비밀키·배포 금지: 테스트는 Claude API·Firestore 목 처리, `firebase deploy/login` 금지, 키는 `.env.example`로만 문서화.
- 셸 명령은 Bash 툴. npm/vite/python 명령 앞에 반드시:
  ```bash
  export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
  ```
- 백엔드는 venv: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`. 파이프라인은 `../crawler/.venv/Scripts/python.exe`.
- 프로세스를 싹 죽이지 않는다 — 내가 띄운 PID만.
- 턴 종료마다 `git add -A` 자동 커밋·푸시된다(`.claude/hooks/auto-commit-push.sh`) → 저장소에 임시 파일을 남기지 않는다.

## 디렉토리
```
crawler/  pipeline/  frontend/  backend/  scripts/  card-drafts/  CARD/zzal/  firebase.json  firestore.rules  .firebaserc
```
역할·데이터 흐름·산출물 위치(`바탕화면\카드뉴스\`)는 PROJECT-BRIEF.md §3.

## 검증 명령
```bash
cd frontend && npm install && npm run build
cd backend && ./.venv/Scripts/python.exe -m pytest -q && ./.venv/Scripts/python.exe -c "import app.main"
cd pipeline && ../crawler/.venv/Scripts/python.exe -m pytest -q
cd crawler && ./.venv/Scripts/python.exe -m pytest -q
firebase --version   # 설정 문법만, 배포 X
```

## 완료 기준 (코드 변경 시)
1. `frontend` 빌드 성공 2. 백엔드·파이프라인·크롤러 pytest 통과(목 기반) 3. 백엔드 앱 import 오류 없음 4. `firebase.json`·`firestore.rules`·`.firebaserc` 유효 5. README에 셋업·실행 문서화 6. 비밀키 미커밋.

## 문서 규칙
문서는 6개만 유지한다: CLAUDE.md(개발 규칙) · PROJECT-BRIEF.md(지도·상태) · KEYWORD-POLICY.md(카드뉴스 규칙) · BRAND-ROSTER.md · RESULT-TEMPLATE.md · README.md(셋업). 서브시스템 문서는 `crawler/FINDINGS.md`, `card-drafts/README.md`, 각 회차 `README.md`+`result.md`. 별도 HISTORY·계획서·QA 보고서를 새로 만들지 않는다 — 경위는 회차 README 끝에 몇 줄로.
