---
active: true
iteration: 1
session_id: 3821ae99-ba6d-408b-8b31-e6e35af62e1e
max_iterations: 40
completion_promise: "CARDNEWS_BUILD_COMPLETE"
started_at: "2026-07-07T16:25:31Z"
---

이 저장소에서 먼저 SPEC.md 와 CLAUDE.md 를 읽고, AI 카드뉴스 자동 생성기를 구현하라. 스택 고정: 프론트엔드는 frontend/ 에 React+Vite+TypeScript, 백엔드는 backend/ 에 FastAPI(Python 3.12), Firebase 는 설정 파일만(firebase.json/.firebaserc/firestore.rules). 모든 UI 텍스트는 한국어. 매 반복마다 git 로그와 파일 상태로 지금까지 진행분을 확인하고, 다음 미완성 부분을 이어서 구현하라. 셸 명령은 반드시 Bash 툴로 실행하며 node/npm/npx/python/pip/firebase 는 이미 설치되어 PATH 에 있다. 금지: 실제 Claude API 호출, firebase login/deploy, 비밀키 커밋 — 백엔드 테스트는 Anthropic 호출과 Firestore 를 목(mock)으로 처리하고 .env.example 만 둔다. 각 반복 끝에서 frontend 는 npm run build, backend 는 pytest 를 실제로 실행해 통과를 확인하라. CLAUDE.md 의 완료 기준 6가지를 모두 실제 명령 실행으로 검증(빌드 성공·pytest 통과·백엔드 import·firebase 설정 유효·README·비밀키 미커밋)한 뒤에만 <promise>CARDNEWS_BUILD_COMPLETE</promise> 를 출력하라. 하나라도 실패/미검증이면 promise 를 내지 말고 계속 작업하라.
