# CLAUDE.md — 개발 가이드

패션/AI 카드뉴스 자동 생성 웹앱. React(프론트) + FastAPI(백엔드) + Firebase(DB·호스팅).

## 절대 규칙
- 모든 사용자 노출 UI 텍스트는 **한국어**만 사용한다 (코드 식별자·주석은 영어 허용).
- 셸 명령은 **Bash 툴**로 실행한다. `node/npm/npx/python/pip/firebase` shim이 `~/.local/bin`에 있다.
- **중요:** `npm install`/`npm run build` 는 내부적으로 cmd.exe 로 `node` 를 호출하므로,
  npm/vite/python 관련 명령 앞에 반드시 아래를 먼저 실행해 실제 툴 디렉토리를 PATH 에 올린다:
  ```bash
  export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
  ```
- 백엔드는 venv 사용: `cd backend && ./.venv/Scripts/python.exe -m pytest -q`
- **실제 외부 호출·비밀키·배포 금지**:
  - Claude API 실제 호출 금지 → 백엔드 테스트는 반드시 API 응답을 **목(mock)** 처리.
  - `firebase deploy`, `firebase login`, 실제 Firestore 접속 금지 → 설정 파일만 작성/검증.
  - `ANTHROPIC_API_KEY`, Firebase 서비스 계정 등은 `.env.example`로만 문서화하고 커밋하지 않는다.

## 디렉토리 구조 (목표)
```
frontend/          # React + Vite + TypeScript
backend/           # FastAPI (Python 3.12)
firebase.json      # Firestore + Hosting 설정
.firebaserc
firestore.rules
```

## 실행/검증 명령
프론트엔드:
```
cd frontend && npm install
npm run build          # 프로덕션 빌드 (성공해야 함)
npm run lint --if-present
npm test --if-present
```
백엔드:
```
cd backend && python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
pytest                 # 통과해야 함 (Claude API는 목 처리)
python -c "import app.main"   # import 오류 없어야 함
```
Firebase 설정 검증:
```
firebase --version     # 설정 문법만 확인, 실제 배포 X
```

## 완료 기준 (이 모두를 만족해야 함)
1. `frontend` 에서 `npm run build` 성공.
2. `backend` 에서 `pytest` 전부 통과 (목 기반).
3. 백엔드 앱이 import/기동 오류 없이 로드됨.
4. `firebase.json`, `firestore.rules`, `.firebaserc` 존재하고 형식이 유효함.
5. 루트 README에 셋업/실행 방법 문서화.
6. 비밀키/자격증명이 저장소에 커밋되지 않음 (`.env.example`만 존재).
