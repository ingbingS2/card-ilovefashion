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
| `autopost/` + `.claude/skills/daily-feed/` | **매일 자동 제작**: 클라우드 제작 루틴(07:00 KST)이 키워드 선정 → 무신사·29CM 후보 수집 → 7장 렌더·검사 → 승인 요청. 사용자가 '승인'하면 게시·측정 루틴(하루 4회)이 재검증 후 게시·+72h 측정. 결과물은 `claude/autopost-data` 브랜치 | ★ 신규 |
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

매일 자동 제작(autopost) — **Claude 클라우드 루틴**이 돌린다(PC 꺼져 있어도):
1. 제작 루틴 "매일 피드 제작"(07:00 KST, Opus) — 키워드 → 후보 → 7장 렌더·검사 → 폰으로 승인 요청. 게시하지 않는다.
2. 사용자가 그 세션에서 '승인' → `publish --approve --quote "<원문>"`(승인 기록, 48시간 유효) → `publish --pending`.
3. 게시·측정 루틴(11:30·16:30·20:30·23:30 KST, Sonnet) — 승인된 회차를 재검증 → 간격·연속 규칙 → 게시(데이터 브랜치에 '게시 중'을 먼저 푸시하는 잠금으로 동시 게시 방지), +72h 측정, 월요일 토큰 연장.
절차는 `.claude/skills/daily-feed/SKILL.md`. 무신사·29CM 두 몰. PC(Windows) 예약 작업은 대체 실행용.
```bash
python -m venv .venv && ./.venv/Scripts/python.exe -m pip install -r autopost/requirements.txt   # PC 한 번
sh autopost/ap.sh collect signals                                         # 날씨·랭킹·최근 성과 (ap.sh가 PC .venv / 클라우드 python을 고른다)
sh autopost/ap.sh collect candidates --folder "20261002 가을 니트" -q "가을 니트" --gf F   # --append: 기존 후보에 덧붙임
sh autopost/ap.sh build "20261002 가을 니트"                               # episode.json → 검사 → 1~7.jpg·caption.txt
sh autopost/ap.sh verify "20261002 가을 니트"                              # 재검증 (0=통과, 1=막힘·파일 변경, 3=숫자 변경(--apply로 갱신), 4=몰 조회 실패)
sh autopost/ap.sh publish "20261002 가을 니트" --approve --quote "승인"     # 사용자 승인 기록(fingerprint에 묶임, 48h 만료) + 푸시
sh autopost/ap.sh publish --pending                                        # 승인된 회차 재검증 → 숫자 갱신 → 게시(하루 한 건)
sh autopost/ap.sh publish --next                                           # 다음 게시 가능 시각(직전 게시 +20h·다른 날)
sh autopost/ap.sh measure                                                  # +72h 측정 · --check 토큰 확인 · --token 연장
./.venv/Scripts/python.exe -m pytest -q autopost/tests
```
- 데이터는 `claude/autopost-data` 브랜치를 `autopost-data/`에 worktree로 붙여 쓴다(main에 커밋하지 않음). 이력·핸들 시드는 `autopost/seed/`. 인터넷에서 채택한 CTA 짤도 `autopost-data/zzal/`에 쌓인다.
- **클라우드 환경 설정**(claude.ai → Code → 환경) — 네트워크 **사용자 지정(Custom)** 허용 도메인(한 줄에 하나):
  `www.musinsa.com` `api.musinsa.com` `goods-detail.musinsa.com` `goods.musinsa.com` `client.musinsa.com` `image.msscdn.net` `www.29cm.co.kr` `product.29cm.co.kr` `search-api.29cm.co.kr` `bff-api.29cm.co.kr` `review-api.29cm.co.kr` `img.29cm.co.kr` `graph.instagram.com` `raw.githubusercontent.com` `github.com` `api.open-meteo.com` `cdn.jsdelivr.net` `www.jjalbang.today` `litterbox.catbox.moe` `uguu.se` `playwright.azureedge.net` `cdn.playwright.dev` `playwright.download.prss.microsoft.com`
  + "일반적인 패키지 매니저 기본 목록 포함" 체크. 설정 스크립트: `pip install -q requests pillow playwright pytest || true` / `python -m playwright install --with-deps chromium || true` / `apt-get install -y fonts-noto-cjk fonts-noto-color-emoji || true`.
- **토큰은 게시 루틴 전용 환경에만**: 환경을 하나 더 만들어(예: "autopost-publish", 같은 도메인·설정 스크립트) 거기에만 `IG_ACCESS_TOKEN=<인스타 장기 토큰>`을 넣고 게시·측정 루틴을 그 환경으로 돌린다. 웹 글·후기를 읽는 제작 세션에는 토큰이 없어서 인젝션으로 토큰이 새거나 직접 게시될 수 없다(승인 기록만 하고 게시는 루틴이 한다). 환경변수 값은 그 환경을 쓰는 모든 세션에 보인다.
- 무신사 검색·상세·후기 API는 데이터센터 IP를 Cloudflare 403으로 막는다(랭킹만 열림). 코드는 차단을 받으면 그 실행 동안 무신사를 건너뛰고 29CM로 채운다 — 브라우저 위장·프록시·캡차 같은 우회는 하지 않는다(crawler/FINDINGS). PC(가정용 회선)에서 돌면 두 몰 다 된다.

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
