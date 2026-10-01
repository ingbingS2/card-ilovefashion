# PROJECT-BRIEF — 새 에이전트는 이것부터 (세션 시작 시 자동 주입됨)

> 마지막 갱신: 2026-09-11. 규칙 원본은 [KEYWORD-POLICY.md](KEYWORD-POLICY.md), 개발 규칙은 [CLAUDE.md](CLAUDE.md). 이 문서는 **지도**다.

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
scripts/   post_ig.py — 인스타 캐러셀 게시 (pipeline·autopost가 재사용)
autopost/  ★ 매일 자동 제작(2026-10-01~): 클라우드 루틴이 .claude/skills/daily-feed 절차로 키워드→후보(collect)→episode.json→build(검사·렌더)→승인 요청.
           사용자가 그 세션에서 '승인' → verify → publish. 데이터는 claude/autopost-data 브랜치(worktree autopost-data/). measure로 +72h.
card-drafts/  카드 디자인. ★ 현행 디자인 = early-autumn-skirt/index.html (전면 이미지형 · 09-11 하단 그라데이션 완화판). uvparasol-insta.html은 파이프라인용 구 레이아웃
CARD/zzal/    CTA 카드용 무한도전 짤 — 수정일 최신 파일을 쓴다
backend/      초기 웹앱 API — 사실상 미사용
```
**실제로 카드뉴스는 지금 `card-drafts/<회차>/` 폴더를 복제해 수동 제작한다**(index.html의 `cards` 배열 교체 → `render.py`). 파이프라인 템플릿에 새 디자인을 이식하는 것은 미완 과제.

**2026-09-07부터 작업 본체는 USB(D:)다**: `D:\fashion-cardnews`(저장소) + `D:\카드뉴스`(산출물) + `D:\_claude\memory`(클로드 메모리 백업). `frontend/node_modules`는 복사하지 않았으니 프론트 작업 전 `npm install`. `.venv`는 이 PC의 Python 3.12를 가리키므로 다른 PC에서는 `python -m venv .venv && pip install -r requirements.txt`로 다시 만든다. OneDrive 원본은 사용자 확인 전까지 남겨 둔다.

산출물과 데이터는 저장소 밖의 **`카드뉴스` 폴더**. 코드(`scripts/post_ig.py`·`pipeline/app.py`·`pipeline/qa.py`)는 이 순서로 찾는다: 환경변수 `CARDNEWS_DIR` → **저장소 바로 옆의 `카드뉴스`**(USB면 `D:\카드뉴스`) → `C:\Users\yepdo\OneDrive\Desktop\카드뉴스`(원래 위치). 회차 폴더 README의 복사 명령은 아직 C: 경로 문자열이니 D:에서는 경로만 바꿔 쓴다.
- `YYYYMMDD 키워드\` 1~7.jpg · caption.txt · result.md · _preview.html
- `_dashboard.html`(사용자용 대시보드, "실험 노트" 코너 유지) · `_qa.json` · `ig_api_token.txt`(🔑 만료 ~09-17)

## 4. 카드뉴스 표준 절차
1. KEYWORD-POLICY §10 최신 행에서 지정 키워드 확인. 직전 게시물 2~3개 `caption.txt`와 `result.md`를 읽는다.
2. 상품 5종 선정(축 하나) → 무신사 상세에서 가격·후기·소재·**구매 가능** 확인, 착용컷 `_big` 다운로드.
3. `card-drafts/early-autumn-skirt/`(가장 최근 회차)을 복제 → `cards` 배열·`assets/`·캡션 교체 → `python render.py`.
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
| 게시 전 재검증 | `cd card-drafts/<최신 회차> && python verify.py` (Chrome 확장 불필요, Playwright 필요) |
| 인스타 게시 | `python scripts/post_ig.py "<폴더명>" --dry-run` → 승인 후 `--dry-run` 없이 |
| 카드뉴스 앱 | `cd pipeline && ../crawler/.venv/Scripts/python.exe app.py` → http://127.0.0.1:8787/dashboard |
| 테스트 | pipeline `../crawler/.venv/Scripts/python.exe -m pytest -q` · crawler `./.venv/Scripts/python.exe -m pytest -q` · backend `./.venv/Scripts/python.exe -m pytest -q` |
| 프론트 빌드 | `cd frontend && npm run build` |
| 로컬 크롤 | `cd crawler && ./.venv/Scripts/python.exe main.py --store json` |

## 6. 현재 상태 (2026-09-11)
- **2026-10-01 매일 자동 제작 시스템(autopost) 구축** — Claude 구독 사용량으로 돈다(API 비용 0). **무신사 + 29CM 두 몰**에서 후보를 모으고, 같은 상품이 다른 몰에서 더 싸면 표시한다. 신규 브랜드 핸들은 KEYWORD-POLICY §7-4대로 3곳 이상 독립 출처에서 확인될 때만 태그. 절차·승인 규칙은 `.claude/skills/daily-feed/SKILL.md`.
  - **10-02 실행 위치 = Claude 클라우드 루틴**(사용자 지시 "PC 안 켜도 매일"): 제작 `trig_01Makuzx6T1CTzXLsQ19WEZ4`(07:00 KST, Opus — **사용자가 클라우드 환경 허용 도메인·폰트를 넣을 때까지 꺼 둠**) + 게시·측정 `trig_01NLWt3pcfZF8gx7PPgvDg3e`(11:30·16:30·20:30·23:30 KST, Sonnet: `measure --check` → `measure` → 월요일 `--token` → `publish --pending`). 승인은 세션에서 '승인' → `publish --approve --quote "<원문>"`(fingerprint에 묶임, 48h 만료, 데이터 브랜치에 푸시) → `publish --pending`. 게시 직전 '게시 중'을 데이터 브랜치에 먼저 푸시하는 잠금(fast-forward 푸시 = compare-and-swap)으로 세션·루틴 동시 게시를 막는다. PC 예약 작업은 대체용(오늘 폴더가 있으면 건너뜀) — 클라우드 제작 루틴을 켜면 PC 예약은 끈다.
  - autopost 명령은 `sh autopost/ap.sh <모듈>`(Bash 호출마다 셸 변수가 사라져서 `$PY` 방식은 깨졌다).
  - 무신사 API는 데이터센터 IP를 Cloudflare로 막는다(crawler/FINDINGS 맨 위) → 코드는 그 실행 동안 무신사를 건너뛰고 29CM 후보로 채운다. **10-02부터 헤드리스 브라우저 위장(Playwright 페이지 안 fetch·자동화 탐지 회피 플래그)으로 뚫지 않는다** — 봇 차단 우회 금지. 클라우드 회차는 29CM 위주, PC 회차는 두 몰. **첫 회차 `20261001 가을 니트` 게시 완료 10-01 23:31** → https://www.instagram.com/p/Dd9IRTljzJp/ (무신사 3 + 29CM 2, 사진 태그 4/5 — 커스텀어클락은 태그 불가 계정). +72h 측정 10-04 23:31 이후.
  - ⛔ **매시간 크롤러(crawl.yml)도 같은 이유로 09월 말부터 실패 중** — Actions IP에서 무신사 후기 API 403.
  - 10-01 토큰 갱신 완료(만료 ~11-30). 클라우드는 환경변수 `IG_ACCESS_TOKEN`, PC는 `D:\카드뉴스\ig_api_token.txt`. 만료 2주 전부터 `measure --check`가 경고.
- **`20260908 가을 스커트` 게시 완료 2026-09-11 11:57** → https://www.instagram.com/p/DdIZA3wE6J8/ · **+72h 측정 09-14 11:57 이후**(`result.md` §5). 산출물 `카드뉴스\20260908 가을 스커트\`. 5종 전부 29CM(드로우핏·노티아·로에일·커스텀어클락·노우드), 로스터 1(노우드)+신규 4. 회차 폴더 `card-drafts/early-autumn-skirt/`(README 참고). 09-11 변경: 하단 그라데이션 완화(텍스트 상단 이동안은 기각), 3번 틸아이다이→노티아(밝은 베이지) 교체, 피드백 수정. **새 회차는 이 폴더를 복제한다.** **미치코런던은 10-05까지 상품·태그 제외**(사용자 지시).
- **측정 완료**: `20260831 초가을 아우터` → 09-08 조회 도달 **119**·공유 0 → 판정 기준(200+·공유 1+) **미달**, result.md §5~§8 작성 완료. 로스터 0곳으로 짠 유일한 회차였다.
- **09-16 측정 완료**: 초가을 데님 누적 도달 **373**·공유 2(통과) · 가을 스커트 +5일 도달 **57**·공유 0(기각). 두 result.md §5~§8 작성. 스냅샷 `카드뉴스\_insights-20260916.json`. 브랜드 반응(§7)은 사용자 앱 확인 대기.
- **`20260917 가을 부츠` 게시 완료 2026-09-17 11:42** → https://www.instagram.com/p/DdX0FHPGNdU/ · **+72h 측정 09-20 11:42 이후** — 회차 폴더 `card-drafts/autumn-boots/`(README 참고, **새 회차는 이 폴더를 복제**), 산출물 `카드뉴스\20260917 가을 부츠\`. 무신사 2 + 29CM 3, 신규 5곳. 09-17 신상 범위를 '전년도 1월 1일 이후'로 확대(KEYWORD-POLICY §2). 09-17 디자인 변경: `이미지 출처`를 정가 줄 오른쪽으로 옮기고 상품명·정가 줄에 글자 그림자 추가(텍스트 블록 전부 35% 이하).
- 인사이트 전수 재조회 스냅샷: `카드뉴스\_insights-20260908.json`(20건). **KEYWORD-POLICY §10 표의 도달 값은 측정 시점이 섞여 있으니 축 비교는 §10 맨 아래 재조회 줄을 본다** — 특히 비키니는 표에 15로 적혀 있으나 누적 1,260(계정 최고)이다.
- 진행 중 실험 #5 브랜드 반응·공유. 반응 브랜드 9곳(BRAND-ROSTER). 게시 실적·도달은 KEYWORD-POLICY §10.
- **🏆 `20260917 가을 부츠`가 계정 최고 기록 — 09-23 측정 도달 1,718 · 조회수 2,077 · 공유 1 · 저장 2 · 댓글 1(에트오소메) → 판정 통과.** 종전 최고는 비키니 1,328. result.md §5~§8 작성 완료.
- ~~⛔ 인스타 Graph 토큰 만료 — 2026-09-17~~ → **10-01 새 토큰 발급·게시 성공**(위 autopost 항목). 측정의 다른 경로: 소유자 계정으로 로그인된 브라우저에서 `https://www.instagram.com/insights/media/{media_id}/` 를 열면 된다(`media_id`는 `/api/v1/oembed/?url={permalink}`). 토큰보다 정보가 많다 — **유입 경로(기타/프로필/홈)** 가 나온다. KEYWORD-POLICY §8.
- **09-23 전수 재조회 11건** (`카드뉴스\_insights-20260923.json`) → KEYWORD-POLICY §10 맨 아래 표. **핵심: 도달을 가르는 건 좋아요가 아니라 유입 '기타'(알고리즘 노출)이고, 그 문을 여는 건 공유·저장·댓글이다.** 공유 0인 회차는 한 번도 도달 420을 넘지 못했다. 좋아요는 부츠 7·데님 10·아우터 8로 같은데 도달은 1,718/419/147이다.
- **09-23 지정 키워드 = `가을 재킷`**(KEYWORD-POLICY §10 맨 위 행). 축 = 보온 정도 순서, 트렌치코트·패딩 제외, 품목어는 '아우터'가 아니라 '재킷'. 아직 미제작 — 새 회차는 `card-drafts/autumn-boots/`를 복제한다.
- **09-23 브랜드 반응 전수 확인 — 게시물 22개 전부**(BRAND-ROSTER): 로스터 9곳 → **18곳**. 신규 = 에트오소메·노티아·세컨드솔트·데꼬로소·얀13·누스·하루타·오베르·쿠피도·앤니즈. 컴포트랩 핸들은 `@comfortlab_kr`로 정정. **비키니는 태그한 5곳이 전부 반응(5/5)한 유일한 회차**다. 대형 계정(아디다스·에잇세컨즈·미쏘·무신사 스탠다드·스컬프터)은 한 곳도 반응하지 않았다.
- ⚠️ **09-23 중간에 낸 오류**: 로스터에 이미 적힌 핸들 목록과 대조하는 바람에 아우터·아가일·로퍼가 "브랜드 반응 0곳"으로 잘못 나왔다. 실제로는 셋 다 반응이 있었다(데꼬로소·얀13·누스+하루타). **대조 기준은 그 게시물 캡션의 `@멘션`이어야 한다** — BRAND-ROSTER §확인 방법.
- 미완 과제: 전면 이미지형을 `pipeline` 템플릿(`uvparasol-insta.html`)에 이식.

## 7. 살아있는 함정
- **무신사는 데이터센터 IP에서 Cloudflare 403**(PC 가정용 IP의 `requests`는 열린다). 자동화 탐지 회피(Playwright 위장·`AutomationControlled` 끄기·헤드리스 UA 숨기기)로 뚫지 않는다(10-02 — autopost는 그 몰을 건너뛴다). 수동 확인은 사람이 쓰는 브라우저(claude-in-chrome)로. 인스타 프로필·공식몰 footer는 WebFetch.
- **29CM은 쿠폰가 함정이 더 크다(09-08 발견)**: 상품 페이지 대표가·랭킹 `displayPrice`·검색 `totalSellPrice` 전부 쿠폰 반영가다. 카드에 쓸 정상가는 `bff-api.29cm.co.kr/api/v5/product-detail/{no}` 의 **`sellPrice`**. 무신사 랭킹 API `info.finalPrice`도 쿠폰가.
- 무신사 페이지가 크게 보여주는 가격은 쿠폰가일 수 있다. 카드는 `goodsPrice.salePrice`. 29CM은 `displayPrice`(08-06 이전 크롤 스냅샷은 `sellPrice`가 담겨 실제보다 높다 — 소급 보정 안 됨).
- 가격·품절은 하루 사이에도 바뀐다. **게시 직전 재검증 필수**, 구매하기 버튼까지 본다.
- 게시 호스팅(litterbox/uguu 무료)이 둘 다 죽으면 게시 불가(07-27 실장애).
- `pipeline/jobs.py`의 잡은 인메모리 — 서버 재시작 시 소실. copywriter는 API 키 없으면 경고 한 줄 후 규칙 기반 폴백(자동 카피를 그대로 쓰지 않는다).
- `.claude/hooks/auto-commit-push.sh`가 턴마다 `git add -A` 후 main 푸시 → `deploy.yml` 자동 배포.
- Firebase 웹 API 키가 `frontend/src/firestore.ts`, `frontend/public/rankings.html`, `pipeline/reader.py` 3곳에 하드코딩(공개 키, Firestore 규칙으로 보호하는 구조). 모델 ID `claude-sonnet-5`가 backend/pipeline 4곳에 분산.
- 템플릿 `uvparasol-insta.html`의 `var IMAGES = {` / `var META   = {` / `var CARDS  = [` 표기(공백 포함)를 바꾸면 렌더러가 앵커를 못 찾는다.
- ~~BRAND-ROSTER의 좋아요 목록은 API로 못 받는다~~ → **09-23 해결.** 인스타에 로그인된 브라우저(소유자 아니어도 됨)에서 게시물을 열고 페이지 안에서 `/api/v1/media/{media_id}/likers/` 를 fetch 한다. 헤더 `x-ig-app-id: 936619743392459` · `x-csrftoken`(쿠키 `csrftoken`에서) · `x-requested-with: XMLHttpRequest`, `credentials:'include'`. 개인 계정까지 긁으면 PII로 차단되니 **태그한 브랜드 핸들만 대조**한다. 방법 전문은 BRAND-ROSTER 상단.
- **claude-in-chrome은 다른 PC의 Chrome에 붙어 있을 수 있다(09-23 실제 발생).** `list_connected_browsers`로 확인하고 `select_browser`로 이 PC 것을 고른다 — 브라우저마다 로그인된 인스타 계정이 달라서, 소유자 계정이 아닌 쪽에서는 인사이트가 안 보인다. `instagram.com` 이동 자체는 이제 막히지 않는다(옛 함정 해제).
- **USB(D:) 저장소는 git이 "dubious ownership"으로 거부한다(09-11 확인)** — 자동 커밋·푸시 훅이 오류를 삼켜 조용히 실패하고, 09-08 이후 커밋이 origin에 올라가지 않았다. 읽기만 할 땐 `git -c safe.directory=D:/fashion-cardnews …`, 고치려면 사용자 승인 후 `git config --global --add safe.directory D:/fashion-cardnews`.
- **09-17 D: 작업 PC에는 `requests`·PIL도 없다.** 게시는 스크래치 폴더에 표준 라이브러리로 만든 `requests` 대체 모듈(GET/POST·multipart만)을 `PYTHONPATH`로 얹어 `post_ig.py`를 실행했고, JPG 변환은 PowerShell `System.Drawing`으로 했다. 패키지를 새로 내려받으려면 사용자 확인.
- **Playwright가 없는 PC(09-11 D: 작업 PC, Python 3.14)** 에선 `render.py`·`verify.py`가 안 돈다. 렌더는 실제 Chrome 헤드리스 CLI(`--screenshot --force-device-scale-factor=2 --window-size=540,675`, 카드를 `position:fixed;transform:none!important`로 고정), 검증은 앱 브라우저로 29CM·무신사 페이지를 열고 같은 API를 페이지 안에서 fetch 했다. `crawler/.venv`는 다른 PC의 Python을 가리켜 깨져 있다.
- 셸 문자열에 `카드뉴스\20260908` 같은 경로를 쓰면 `\202`가 8진 이스케이프로 먹혀 제어문자(`\x82`)가 된다(KEYWORD-POLICY §10·PROJECT-BRIEF §6에서 실제 발생). 문서 수정은 Edit 도구로 하거나 `chr(92)`로 백슬래시를 만든다.

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
