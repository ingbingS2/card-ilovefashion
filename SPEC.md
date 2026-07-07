# SPEC — AI 카드뉴스 자동 생성기

## 제품 개요
1인 크리에이터가 **주제를 입력하면 한국어 10장 카드뉴스(4:5, 1080×1350)를 자동 생성**하고,
미리보기 후 PNG로 내보내며, 생성 이력을 저장하는 웹앱.

## 스택 (고정)
- 프론트엔드: **React + Vite + TypeScript**
- 백엔드: **FastAPI (Python 3.12)**, Anthropic SDK (`anthropic`) 사용, 모델 `claude-sonnet-5`
- DB/호스팅: **Firebase** (Firestore + Hosting) — 설정 파일만, 실제 배포는 사용자 몫

## 기능 요구사항

### 프론트엔드
- 입력 폼: `주제(필수)`, `타깃`, `목표`, `톤`, `CTA`, `슬라이드 수(기본 10)`.
- "생성" 버튼 → `POST /api/generate` 호출 → 로딩 표시.
- 결과: 10장 슬라이드를 4:5 비율 카드로 렌더링(캐러셀/그리드). 각 카드에 헤드라인 + 본문.
- 각 슬라이드를 **PNG로 내보내기** (예: `html-to-image`). 전체 일괄 내보내기 버튼 포함.
- 생성 이력 목록: `GET /api/cardnews` 결과 표시, 클릭 시 다시 열기.
- 모든 UI 텍스트 한국어. Pretendard/Noto Sans KR 폰트 스택.

### 백엔드 (FastAPI)
- `POST /api/generate`: 요청 바디(주제 등) → Anthropic API로 카드뉴스 JSON 생성 →
  응답 스키마: `{ slides: [{ index, headline, body, layout, graphic, designPoint }], meta }`.
  - Anthropic 호출은 `services/generator.py`로 분리. 테스트에서 **목 처리** 가능해야 함.
  - `ANTHROPIC_API_KEY`는 환경변수에서 로드. 없으면 명확한 에러(500) 반환.
- `POST /api/cardnews`: 생성 결과 Firestore 저장 (저장 계층은 인터페이스로 추상화, 테스트는 인메모리 목).
- `GET /api/cardnews`: 저장 목록 반환.
- `GET /api/health`: `{status:"ok"}`.
- CORS: 프론트 개발 서버(`localhost:5173`) 허용.
- Pydantic 모델로 요청/응답 검증.

### Firebase
- `firebase.json`: Hosting은 `frontend/dist`를 public으로, Firestore rules/indexes 연결.
- `firestore.rules`: 최소 규칙(개발용, 주석으로 프로덕션 강화 안내).
- `.firebaserc`: 프로젝트 alias 플레이스홀더(`your-project-id`).

## 테스트
- 백엔드: `pytest` — generate 엔드포인트(제너레이터 목), cardnews 저장/조회(인메모리 목), health.
- 프론트엔드: 최소 1개 컴포넌트 렌더 테스트(vitest) 또는 `npm run build` 통과로 갈음.

## 비기능/제약
- 비밀키 커밋 금지. `backend/.env.example`, `frontend/.env.example` 제공.
- 실제 Claude 호출·Firebase 배포는 수행하지 않음 (CLAUDE.md 규칙 준수).
- 커밋은 의미 단위로. (Stop 훅이 자동 커밋·푸시함)

## 완료 정의
CLAUDE.md의 "완료 기준" 6개를 모두 만족하고, 각 항목을 실제 명령 실행으로 검증했을 때 완료.
