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

## 랭킹 크롤러 (crawler/)
무신사 카테고리별 TOP 50 + 29CM 베스트 TOP 50 의 순위·가격·평점·후기(상품당 10개)를
매시간 수집한다 (`.github/workflows/crawl.yml`, 매시간 7분).

```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest -q   # 테스트 (네트워크 없음)
./.venv/Scripts/python.exe main.py --store json         # 로컬 실크롤 → out/
./.venv/Scripts/python.exe main.py --store firestore    # Firestore 적재 (ADC 필요)
```

- Firestore 모드는 GitHub Secret `FIREBASE_SERVICE_ACCOUNT` 등록 시 자동 활성화 (없으면 JSON 아티팩트 모드).
- 엔드포인트 실측 문서: [crawler/FINDINGS.md](crawler/FINDINGS.md)

## 원클릭 파이프라인 (pipeline/)
대시보드에서 상품을 골라 "카드뉴스 만들기" 를 누르면, 로컬 앱이 문구를 만들고 C안 템플릿으로
1080×1350 카드뉴스를 렌더한 뒤 미리보기를 띄운다. 미리보기에서 "인스타에 게시" 를 누르면
캐러셀로 업로드된다 (게시 전 미리보기 확인 필수).

```bash
# 로컬 앱 실행 (포트 8787). ANTHROPIC_API_KEY 있으면 Claude 문구, 없으면 규칙 기반 폴백.
cd pipeline && ../crawler/.venv/Scripts/python.exe app.py
```

- 결과물 저장: `바탕화면\카드뉴스\YYYYMMDD 랭킹픽.jpg~N.jpg` + `caption.txt`
- 게시는 `scripts/post_ig.py` 재사용 (토큰: `카드뉴스\ig_api_token.txt`)
- CORS 로 `https://fashion-cardnews.web.app` 에서 직접 호출 허용

## 개발 자동화
- Claude Code 코드 수정 시 턴 종료마다 자동 커밋·푸시 (`.claude/hooks/auto-commit-push.sh`)
- 개발 규칙: **[CLAUDE.md](CLAUDE.md)**, 스펙: **[SPEC.md](SPEC.md)**
