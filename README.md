# card-ilovefashion — AI 카드뉴스 자동 생성기

주제를 입력하면 **한국어 10장 카드뉴스(4:5, 1080×1350)** 를 자동 생성하고,
미리보기 후 PNG로 내보내며 생성 이력을 저장하는 웹앱.

- 프론트엔드: **React + Vite + TypeScript** (`frontend/`)
- 백엔드: **FastAPI (Python 3.12)** + Anthropic Claude (`backend/`)
- DB/호스팅: **Firebase** (Firestore + Hosting)

## 로컬 실행

### 1) 백엔드 (FastAPI)
```bash
cd backend
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
pip install -r requirements.txt
cp .env.example .env               # ANTHROPIC_API_KEY 등 입력
uvicorn app.main:app --reload --port 8000
```
테스트:
```bash
pytest                             # 실제 API 호출 없이 목 기반
```

### 2) 프론트엔드 (React + Vite)
```bash
cd frontend
npm install
cp .env.example .env               # VITE_API_BASE=http://localhost:8000
npm run dev                        # http://localhost:5173
npm run build                      # 프로덕션 빌드 → dist/
```

## API 요약
| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/health` | 헬스체크 |
| POST | `/api/generate` | 주제 등으로 10장 카드뉴스 생성 |
| POST | `/api/cardnews` | 생성 결과 저장 |
| GET | `/api/cardnews` | 저장 목록 |
| GET | `/api/cardnews/{id}` | 단건 조회 |

## 환경변수 (비밀키는 커밋 금지)
- 백엔드: `backend/.env.example` 참고 (`ANTHROPIC_API_KEY`, `STORAGE_BACKEND=memory|firestore` 등)
- 프론트: `frontend/.env.example` 참고 (`VITE_API_BASE`)

## CI/CD (GitHub Actions)
- `.github/workflows/ci.yml` — push/PR 시 프론트 빌드 + 백엔드 pytest
- `.github/workflows/deploy.yml` — `main` push 시 Firebase Hosting 자동 배포
  (Secrets `FIREBASE_SERVICE_ACCOUNT`, `FIREBASE_PROJECT_ID` 필요 — 없으면 자동 스킵)
- 배포 1회 설정: **[DEPLOY.md](DEPLOY.md)** 참고

## 개발 자동화
- Claude Code 코드 수정 시 턴 종료마다 자동 커밋·푸시 (`.claude/hooks/auto-commit-push.sh`)
- 개발 규칙: **[CLAUDE.md](CLAUDE.md)**, 스펙: **[SPEC.md](SPEC.md)**
