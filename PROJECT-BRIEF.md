# PROJECT-BRIEF — 새 에이전트는 이것부터 (세션 시작 시 자동 주입됨)

> 마지막 갱신: 2026-09-05. 규칙 원본은 [KEYWORD-POLICY.md](KEYWORD-POLICY.md), 개발 규칙은 [CLAUDE.md](CLAUDE.md). 이 문서는 **지도**다.

## 1. 30초 요약
인스타그램 패션 계정 **@i_s2_fashion** 운영 자동화 저장소. 무신사·29CM 랭킹을 매시간 크롤링해 Firestore에 쌓고 → 상품 5종을 고르고 → 후기를 근거로 문구를 써서 1080×1350 카드 7장(표지+상품 5+CTA)을 렌더하고 → 미리보기 승인 후 인스타 캐러셀로 게시하고 → +72시간 뒤 인사이트를 조회해 실험 로그를 갱신한다.
**코드가 맞게 도는 것보다 게시물이 정확하고 정책에 맞는 것이 중요하다.**

## 2. 절대 규칙 (어기면 사고)
1. 카드뉴스 작업은 [KEYWORD-POLICY.md](KEYWORD-POLICY.md) 전문을 읽고 따른다. 랭킹 키워드 금지, 시즌성 키워드.
2. **실제 게시(`scripts/post_ig.py`, `POST /api/jobs/{id}/publish`)는 사용자 승인 없이 절대 실행 금지.** 되돌릴 수 없다.
3. 테스트에서 Claude API·Firestore 실호출 금지(목 처리). `firebase deploy/login` 금지. 비밀키 커밋 금지(`.env.example`만).
4. 사용자 노출 UI 텍스트는 한국어.
5. "피드백" 요청 = 수정 완료까지. 완성본은 3+1회 검토 후 `_preview.html` 경로만 알린다(창은 사용자가 연다).
6. 프로세스를 싹 죽이지 않는다 — 내가 띄운 PID만 종료.
7. npm/python 명령 전 PATH export(§5). 저장소에 임시 파일을 남기지 않는다 — 턴마다 자동 커밋·푸시된다.

## 3. 지도
```
crawler/   무신사·29CM 랭킹/후기 수집 → Firestore   (GitHub Actions 매시 7분, 가동 중)
frontend/  React+Vite 대시보드 https://fashion-cardnews.web.app (랭킹 비교·상품 선택) + 레거시 생성기 탭
pipeline/  로컬 원클릭 앱 127.0.0.1:8787 (/dashboard) — reader → copywriter → renderer → 미리보기 → publisher
scripts/   post_ig.py — 인스타 캐러셀 게시 (pipeline이 재사용)
card-drafts/  카드 디자인. ★ 현행 디자인 = early-autumn-outer/index.html (전면 이미지형). uvparasol-insta.html은 파이프라인용 구 레이아웃
CARD/zzal/    CTA 카드용 무한도전 짤 — 수정일 최신 파일을 쓴다
backend/      초기 웹앱 API — 사실상 미사용
```
**실제로 카드뉴스는 지금 `card-drafts/<회차>/` 폴더를 복제해 수동 제작한다**(index.html의 `cards` 배열 교체 → `render.py`). 파이프라인 템플릿에 새 디자인을 이식하는 것은 미완 과제.

산출물과 데이터는 저장소 밖: `C:\Users\yepdo\OneDrive\Desktop\카드뉴스\`
- `YYYYMMDD 키워드\` 1~7.jpg · caption.txt · result.md · _preview.html
- `_dashboard.html`(사용자용 대시보드, "실험 노트" 코너 유지) · `_qa.json` · `ig_api_token.txt`(🔑 만료 ~09-17)

## 4. 카드뉴스 표준 절차
1. KEYWORD-POLICY §10 최신 행에서 지정 키워드 확인. 직전 게시물 2~3개 `caption.txt`와 `result.md`를 읽는다.
2. 상품 5종 선정(축 하나) → 무신사 상세에서 가격·후기·소재·**구매 가능** 확인, 착용컷 `_big` 다운로드.
3. `card-drafts/early-autumn-denim/`(가장 최근 회차)을 복제 → `cards` 배열·`assets/`·캡션 교체 → `python render.py`.
4. 3+1회 검토(맞춤법 / 사실 / 정책 / 핸들 3중) → `result.md` 작성 → 바탕화면 폴더에 복사 → `_preview.html` 경로 보고.
5. 승인 후 `post_ig.py --dry-run` → 게시 직전 재검증(`verify.py`) → 게시 → result.md에 시각·permalink.
6. +72h 인사이트 API 조회 → result.md·KEYWORD-POLICY 표·BRAND-ROSTER 갱신.

## 5. 실행 명령
```bash
export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
export PYTHONIOENCODING=utf-8
```
| 목적 | 명령 |
|---|---|
| 카드 렌더 (수동 제작) | `cd card-drafts/<회차> && python render.py` |
| 게시 전 재검증 | `cd card-drafts/early-autumn-denim && python verify.py` (Chrome 확장 불필요) |
| 인스타 게시 | `python scripts/post_ig.py "<폴더명>" --dry-run` → 승인 후 `--dry-run` 없이 |
| 카드뉴스 앱 | `cd pipeline && ../crawler/.venv/Scripts/python.exe app.py` → http://127.0.0.1:8787/dashboard |
| 테스트 | pipeline `../crawler/.venv/Scripts/python.exe -m pytest -q` · crawler `./.venv/Scripts/python.exe -m pytest -q` · backend `./.venv/Scripts/python.exe -m pytest -q` |
| 프론트 빌드 | `cd frontend && npm run build` |
| 로컬 크롤 | `cd crawler && ./.venv/Scripts/python.exe main.py --store json` |

## 6. 현재 상태 (2026-09-05)
- **측정 대기 2건**: `20260831 초가을 아우터`(09-04 02:49 게시 → 09-07 02:49 이후) · `20260904 초가을 데님`(09-05 21:24 게시 → 09-08 21:24 이후). 각 폴더 `result.md` §5 를 인사이트 API로 채운다.
- 다음 키워드 미지정 — 사용자와 정한다. 새 회차는 `card-drafts/early-autumn-denim/` 복제. **미치코런던은 10-05까지 상품·태그 제외**(사용자 지시).
- 진행 중 실험 #5 브랜드 반응·공유. 반응 브랜드 9곳(BRAND-ROSTER). 게시 실적·도달은 KEYWORD-POLICY §10.
- 인스타 토큰 만료 ~09-17 — 갱신 필요 시 사용자에게.
- 미완 과제: 전면 이미지형을 `pipeline` 템플릿(`uvparasol-insta.html`)에 이식.

## 7. 살아있는 함정
- **무신사는 `requests`로 403.** Chrome 확장 또는 Playwright+실제 Chrome으로 페이지를 열고 페이지 안에서 API fetch. 확장은 `goods-detail.musinsa.com`·`instagram.com` 이동이 막혀 있고, Playwright 경로는 막히지 않는다. 인스타 프로필·공식몰 footer는 WebFetch.
- 무신사 페이지가 크게 보여주는 가격은 쿠폰가일 수 있다. 카드는 `goodsPrice.salePrice`. 29CM은 `displayPrice`(08-06 이전 크롤 스냅샷은 `sellPrice`가 담겨 실제보다 높다 — 소급 보정 안 됨).
- 가격·품절은 하루 사이에도 바뀐다. **게시 직전 재검증 필수**, 구매하기 버튼까지 본다.
- 게시 호스팅(litterbox/uguu 무료)이 둘 다 죽으면 게시 불가(07-27 실장애).
- `pipeline/jobs.py`의 잡은 인메모리 — 서버 재시작 시 소실. copywriter는 API 키 없으면 경고 한 줄 후 규칙 기반 폴백(자동 카피를 그대로 쓰지 않는다).
- `.claude/hooks/auto-commit-push.sh`가 턴마다 `git add -A` 후 main 푸시 → `deploy.yml` 자동 배포.
- Firebase 웹 API 키가 `frontend/src/firestore.ts`, `frontend/public/rankings.html`, `pipeline/reader.py` 3곳에 하드코딩(공개 키, Firestore 규칙으로 보호하는 구조). 모델 ID `claude-sonnet-5`가 backend/pipeline 4곳에 분산.
- 템플릿 `uvparasol-insta.html`의 `var IMAGES = {` / `var META   = {` / `var CARDS  = [` 표기(공백 포함)를 바꾸면 렌더러가 앵커를 못 찾는다.
- BRAND-ROSTER의 좋아요 목록은 API로 못 받는다 — 사용자가 앱에서 확인해 알려준 것만.

## 8. 작업 유형별 시작점
| 요청 | 먼저 읽을 것 | 건드릴 곳 |
|---|---|---|
| 카드뉴스 만들기/고치기/이어서 | KEYWORD-POLICY 전문 + 최신 회차 `card-drafts/*/README.md` + 직전 caption.txt 2~3개 | `card-drafts/<회차>/`, `바탕화면\카드뉴스\` |
| 완성본 피드백 | KEYWORD-POLICY §6·§7 | 렌더 이미지를 직접 열어본다 |
| 게시 / 게시 실패 | KEYWORD-POLICY §9, §7 함정(토큰·호스팅) | `scripts/post_ig.py` |
| 성과 측정·분석 | RESULT-TEMPLATE.md + 각 폴더 result.md + KEYWORD-POLICY §8·§10 | `바탕화면\카드뉴스\*\result.md` |
| 브랜드 태그 전략 | BRAND-ROSTER.md | 캡션 `📌 브랜드 계정` |
| 크롤러 오류 | crawler/FINDINGS.md | `crawler/fetchers.py`, `parsers.py` |
| 대시보드 UI | — | `frontend/src/Dashboard.tsx`, `styles.css` |
| 카드 디자인 구현 | card-drafts/README.md | `card-drafts/early-autumn-*/index.html` |

## 9. 갱신 규칙
구조가 바뀌거나 함정을 새로 발견하면 이 파일을, 정책이 바뀌면 KEYWORD-POLICY.md를, 회차 상태는 KEYWORD-POLICY §10 표를 갱신한다. 이력·경위는 각 회차 폴더 README 끝에 몇 줄로만 남긴다 — 별도 HISTORY 파일을 만들지 않는다.
