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
| `autopost/` + `.claude/skills/daily-feed/` | **매일 자동 제작**: 클라우드 루틴(07:00 KST)이 키워드 선정 → 무신사 후보 수집 → 7장 렌더·검사 → 승인 요청. 사용자가 그 세션에서 '승인'하면 재검증 후 게시. 결과물은 `claude/autopost-data` 브랜치 | ★ 신규 |
| `card-drafts/` | 카드 디자인 원본. 회차 폴더(`early-autumn-*`)를 복제해 수동 제작 | 수동 제작용 |
| `scripts/post_ig.py` | 인스타 캐러셀 게시 (litterbox/uguu 임시 호스팅 → Graph API) | 가동 |
| `backend/` | 초기 웹앱 API(FastAPI + Claude) | 사실상 미사용 |
| `CARD/zzal/` | CTA 카드용 짤 (수정일 최신 파일 사용) | |

산출물은 저장소 밖 `카드뉴스\YYYYMMDD 키워드\`. 위치 탐색 순서: `CARDNEWS_DIR` 환경변수 → 저장소 옆 `카드뉴스` 폴더(USB `D:\카드뉴스`) → `C:\Users\yepdo\OneDrive\Desktop\카드뉴스`. 2026-09-07부터 작업 본체는 `D:\fashion-cardnews` + `D:\카드뉴스`.

## 실행

모든 명령 앞에 (Git Bash):
```bash
export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
export PYTHONIOENCODING=utf-8
```

카드뉴스 수동 제작·게시:
```bash
cd card-drafts/early-autumn-skirt                       # 최신 회차 (새 회차는 이 폴더를 복제)
python render.py                                        # index.html cards → 1~7.jpg (Playwright 필요)
python verify.py                                        # 29CM·무신사 가격·후기·품절·인용문 재검증
python ../../scripts/post_ig.py "20260908 가을 스커트" --dry-run
```

매일 자동 제작(autopost) — 보통은 클라우드 루틴이 돌리고, 절차는 `.claude/skills/daily-feed/SKILL.md`:
```bash
pip install -r autopost/requirements.txt && python -m playwright install chromium
python -m autopost.collect signals                                         # 날씨·랭킹·최근 성과
python -m autopost.collect candidates --folder "20261002 가을 니트" -q "가을 니트" --gf F
python -m autopost.build "20261002 가을 니트"                               # episode.json → 검사 → 1~7.jpg·caption.txt
python -m autopost.verify "20261002 가을 니트"                              # 게시 직전 재검증 (0=통과, 2=숫자 변경, 1=막힘)
python -m autopost.publish "20261002 가을 니트" --user-approved             # 사용자 승인 후에만
python -m autopost.measure                                                  # +72h 측정
python -m pytest -q autopost/tests
```
- 데이터는 `claude/autopost-data` 브랜치를 `autopost-data/`에 worktree로 붙여 쓴다(main에 커밋하지 않음). 이력·핸들 시드는 `autopost/seed/`.
- 클라우드 환경 설정: 네트워크 **Custom** 허용 도메인 — `api.musinsa.com` `goods-detail.musinsa.com` `goods.musinsa.com` `client.musinsa.com` `image.msscdn.net` `graph.instagram.com` `raw.githubusercontent.com` `litterbox.catbox.moe` `uguu.se` `api.open-meteo.com` `cdn.jsdelivr.net` `playwright.azureedge.net` `cdn.playwright.dev` `playwright.download.prss.microsoft.com`. 환경변수 `IG_ACCESS_TOKEN`. 설정 스크립트 `pip install requests pillow playwright pytest && python -m playwright install --with-deps chromium`.

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
- 인스타 토큰 `카드뉴스\ig_api_token.txt`(로컬) · 클라우드 루틴은 환경변수 `IG_ACCESS_TOKEN`, Firebase 서비스 계정 `C:\Users\yepdo\.firebase-keys\`

## CI/CD (GitHub Actions)
- `ci.yml` 빌드·테스트 / `deploy.yml` main push 시 Firebase Hosting 배포 / `crawl.yml` 매시간 크롤.
- 배포·크롤에 필요한 Secrets: `FIREBASE_SERVICE_ACCOUNT`(서비스 계정 JSON 전체), `FIREBASE_PROJECT_ID`(`fashion-cardnews`). 없으면 배포는 자동 스킵. 등록됨(2026-07-21).
- Hosting은 `frontend/dist` 서빙(`firebase.json`). firestore.rules 수정 시 Rules API로 재배포 필요.
- Claude Code 턴 종료마다 자동 커밋·푸시(`.claude/hooks/auto-commit-push.sh`) → main push가 곧 배포다.
