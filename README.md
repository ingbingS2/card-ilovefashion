# fashion-cardnews — @i_s2_fashion 카드뉴스 운영 자동화

무신사·29CM 랭킹을 매시간 수집해 Firestore에 쌓고, 상품 5종을 골라 후기 근거로 1080×1350 카드뉴스 7장을 만들고, 인스타그램 캐러셀로 게시한 뒤 +72시간 인사이트로 실험을 기록하는 저장소.

- 에이전트 온보딩: **[PROJECT-BRIEF.md](PROJECT-BRIEF.md)** · 카드뉴스 규칙: **[KEYWORD-POLICY.md](KEYWORD-POLICY.md)** · 개발 규칙: [CLAUDE.md](CLAUDE.md)
- 브랜드 반응 명단: [BRAND-ROSTER.md](BRAND-ROSTER.md) · 실험 로그 양식: [RESULT-TEMPLATE.md](RESULT-TEMPLATE.md)
- 디자인 구현: [card-drafts/README.md](card-drafts/README.md) · 몰 API 실측: [crawler/FINDINGS.md](crawler/FINDINGS.md)

## 구성

| 디렉토리 | 역할 | 상태 |
|---|---|---|
| `crawler/` | 무신사·29CM 랭킹/후기 → Firestore. `.github/workflows/crawl.yml` 매시 7분 | 가동 중 |
| `frontend/` | React+Vite+TS. 랭킹 대시보드(https://fashion-cardnews.web.app) + 레거시 생성기 탭 | 대시보드 사용 |
| `pipeline/` | 로컬 FastAPI(127.0.0.1:8787, UI `/dashboard`): 상품 선택 → 문구 → 렌더 → 미리보기 → 게시 | 템플릿이 구 레이아웃 |
| `card-drafts/` | 카드 디자인 원본. 회차 폴더(`early-autumn-*`)를 복제해 수동 제작 | ★ 주력 |
| `scripts/post_ig.py` | 인스타 캐러셀 게시 (litterbox/uguu 임시 호스팅 → Graph API) | 가동 |
| `backend/` | 초기 웹앱 API(FastAPI + Claude) | 사실상 미사용 |
| `CARD/zzal/` | CTA 카드용 짤 (수정일 최신 파일 사용) | |

산출물은 저장소 밖 `C:\Users\yepdo\OneDrive\Desktop\카드뉴스\YYYYMMDD 키워드\`.

## 실행

모든 명령 앞에 (Git Bash):
```bash
export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
export PYTHONIOENCODING=utf-8
```

카드뉴스 수동 제작·게시:
```bash
cd card-drafts/early-autumn-denim
python render.py                                        # index.html cards → 1~7.jpg
python verify.py                                        # 무신사 가격·후기·품절 재검증
python ../../scripts/post_ig.py "20260904 초가을 데님" --dry-run
```

크롤러:
```bash
cd crawler && ./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe main.py --store json         # 로컬 → out/
./.venv/Scripts/python.exe main.py --store firestore    # ADC 필요
```

파이프라인 앱 / 프론트 / 백엔드:
```bash
cd pipeline && ../crawler/.venv/Scripts/python.exe app.py        # http://127.0.0.1:8787/dashboard
cd frontend && npm install && npm run dev                          # :5173 · npm run build → dist/
cd backend && python -m venv .venv && source .venv/Scripts/activate && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000
```

## 환경변수·비밀 (커밋 금지)
- `backend/.env.example` — `ANTHROPIC_API_KEY`, `STORAGE_BACKEND=memory|firestore`
- `frontend/.env.example` — `VITE_API_BASE`, `VITE_PIPELINE_URL`
- 인스타 토큰 `카드뉴스\ig_api_token.txt`, Firebase 서비스 계정 `C:\Users\yepdo\.firebase-keys\`

## CI/CD (GitHub Actions)
- `ci.yml` 빌드·테스트 / `deploy.yml` main push 시 Firebase Hosting 배포 / `crawl.yml` 매시간 크롤.
- 배포·크롤에 필요한 Secrets: `FIREBASE_SERVICE_ACCOUNT`(서비스 계정 JSON 전체), `FIREBASE_PROJECT_ID`(`fashion-cardnews`). 없으면 배포는 자동 스킵. 등록됨(2026-07-21).
- Hosting은 `frontend/dist` 서빙(`firebase.json`). firestore.rules 수정 시 Rules API로 재배포 필요.
- Claude Code 턴 종료마다 자동 커밋·푸시(`.claude/hooks/auto-commit-push.sh`) → main push가 곧 배포다.
