# PROJECT-BRIEF — 새 에이전트 온보딩 (제일 먼저 읽을 것)

> 이 저장소에서 처음 작업하는 에이전트를 위한 단일 진입 문서.
> 여기를 읽고 나면 **무엇을 하는 프로젝트인지 / 어디를 건드려야 하는지 / 무엇을 절대 하면 안 되는지**를 안다.
> 마지막 갱신: 2026-08-02

---

## 1. 30초 요약

인스타그램 패션 계정 **@i_s2_fashion** 운영 자동화 저장소다.

무신사·29CM 랭킹을 매시간 크롤링해 Firestore에 쌓고 → 대시보드에서 사람이 상품을 고르면
→ 로컬 파이프라인이 문구를 쓰고 1080×1350 카드뉴스 7장을 렌더하고 → 미리보기 승인 후
→ 인스타그램에 캐러셀로 게시하고 → +72시간 뒤 인사이트를 조회해 실험 로그를 갱신한다.

**핵심: 이건 "코드 프로젝트"이자 "콘텐츠 운영 프로젝트"다.** 코드가 맞게 도는 것보다
게시물이 정책에 맞고 사실이 정확한 것이 더 중요하다.

---

## 2. 🚨 시작 전 필독 — 어기면 사고

| # | 규칙 | 근거 |
|---|---|---|
| 1 | **[KEYWORD-POLICY.md](KEYWORD-POLICY.md)를 반드시 읽고 따른다.** 카드뉴스 관련 작업은 예외 없이. | CLAUDE.md 절대 규칙 |
| 2 | **랭킹 키워드 금지** (랭킹픽·TOP 50·베스트). 사용자가 명시 요청할 때만 허용. 항상 시즌성 키워드. | KEYWORD-POLICY §규칙 |
| 3 | **사용자 노출 UI 텍스트는 전부 한국어.** 코드 식별자·주석은 영어 허용. | CLAUDE.md |
| 4 | **실제 게시(`POST /api/jobs/{id}/publish`, `scripts/post_ig.py`)는 되돌릴 수 없다.** Graph API로 수정·삭제 불가 — 인스타 앱에서 수동 삭제해야 한다. 사용자 승인 없이 절대 실행 금지. | pipeline/publisher.py |
| 5 | **테스트에서 Claude API·Firestore 실호출 금지.** 전부 목 처리. `firebase deploy`/`firebase login` 금지. | CLAUDE.md |
| 6 | **비밀키 커밋 금지.** `.env.example`로만 문서화. | CLAUDE.md 완료 기준 6 |
| 7 | **"피드백" 요청 = 지적이 아니라 수정 완료까지.** 선택지를 되묻지 말고 판단해서 고친 뒤 보고한다. | KEYWORD-POLICY §완성본 피드백 처리 규칙 |
| 8 | **완성본은 보여주기 전 3+1회 검토.** 맞춤법 / 사실 대조 / 정책·형식 / 브랜드 핸들 3중 검증. | KEYWORD-POLICY §완성본 검토 규칙 |
| 9 | **프로세스를 싹 죽이지 않는다.** `python` 전체 kill 금지 — 내가 띄운 PID만 종료 (다른 AI 작업물 보호). | 사용자 지시 |
| 10 | **셸 명령 전 PATH 선행 export** (npm/vite/python 계열). 아래 §6 참조. | CLAUDE.md |

---

## 3. 저장소에 제품이 **둘** 들어있다 — 헷갈리지 말 것

```
① 원래 웹앱 (SPEC.md 가 정의한 것 — 지금은 거의 안 씀)
   frontend/src/Generator.tsx  ──►  backend/  ──►  Claude  ──►  10장 카드 미리보기 → PNG 내보내기
   * 주제를 입력하면 Claude가 슬라이드를 만들어주는 초기 버전.
   * 실제 인스타 운영에는 쓰이지 않는다. 손대기 전에 정말 이쪽이 맞는지 확인할 것.

② 실제 운영 라인 (매일 도는 것) ★
   crawler/ ──매시간──► Firestore(rankings, products)
                              │
                              ├──► frontend/src/Dashboard.tsx (랭킹 비교·상품 선택·코멘트)
                              │         │ POST localhost:8787/api/selections
                              │         ▼
                              └──► pipeline/  reader → copywriter → renderer → [미리보기 승인] → publisher
                                        │                                              │
                                        ▼                                              ▼
                              바탕화면\카드뉴스\YYYYMMDD 키워드\1~7.jpg              Instagram 캐러셀
                                        │
                                        └──► +72h 인사이트 조회 → result.md 갱신 → 표지 풀 누적 저장률
```

**"카드뉴스 만들어줘 / 고쳐줘"는 거의 항상 ②다.**

---

## 4. 서브시스템 지도

| 디렉토리 | 역할 | 진입점 | 상태 |
|---|---|---|---|
| `crawler/` | 무신사·29CM 랭킹/후기 수집 → Firestore | `main.py --store json\|firestore` | ✅ 가동 중 (매시 7분 cron) |
| `pipeline/` | **카드뉴스 생성 원클릭 앱** (127.0.0.1:8787) | `python app.py` | ✅ 주력 |
| `frontend/` | 랭킹 대시보드 + (레거시)생성기 SPA | `npm run dev` (5173) | ✅ 대시보드만 활용 |
| `backend/` | Claude 카드뉴스 생성 API | `uvicorn app.main:app` (8000) | ⚠️ 사실상 미사용 |
| `scripts/` | 인스타 게시 (`post_ig.py`) | `python post_ig.py "<폴더명>"` | ✅ pipeline이 재사용 |
| `card-drafts/` | **렌더 템플릿**(`uvparasol-insta.html`) + 과거 초안 | — | ✅ 템플릿은 현역 |
| `CARD/zzal/` | CTA 카드용 무한도전 짤 | — | ✅ **수정일 최신 파일**을 씀 |
| `docs/`, `.superpowers/sdd/` | Phase 0~3 계획서·작업 리포트 | — | 이력 |

### 파일 단위 요점 (자주 건드리는 것만)

- `pipeline/app.py` — 라우트 + `run_pipeline` 오케스트레이션. `/` 는 404가 정상, UI는 **`/dashboard`**.
- `pipeline/copywriter.py` — 문구 생성. Claude 우선, 실패 시 **조용히** 규칙 기반 폴백. 후기 선별 휴리스틱(부정어 37종 등)이 여기 하드코딩.
- `pipeline/renderer.py` — `card-drafts/uvparasol-insta.html`의 `IMAGES`/`META`/`CARDS` JS 블록을 치환 → Playwright 스크린샷 → Pillow 1080×1350 크롭.
- `pipeline/publisher.py` → `scripts/post_ig.py` — litterbox(→uguu 폴백) 임시 호스팅 후 Graph API 캐러셀 게시.
- `crawler/FINDINGS.md` — 두 몰의 내부 API 엔드포인트·파라미터 실측 문서. 크롤러 고칠 땐 여기부터.
- `frontend/src/firestore.ts`, `selection.ts` — 대시보드의 읽기/선택 로직.

---

## 5. 산출물과 데이터는 **저장소 밖**에 있다

```
C:\Users\yepdo\OneDrive\Desktop\카드뉴스\
├── YYYYMMDD 키워드\          ← 완성본. 1.jpg~N.jpg (1080×1350) + caption.txt + result.md + _preview.html
├── _assets\{job_id}\         ← 파이프라인이 받아둔 상품 썸네일
├── _dashboard.html           ← 사용자용 바탕화면 대시보드 ("실험 노트" 코너 유지할 것)
├── _qa.json                  ← 대시보드 질문/답변 로그
└── ig_api_token.txt          ← 🔑 인스타 장기 토큰 (커밋 금지, 만료 예상 2026-09-17경)
```

크롤 결과 로컬 사본: `crawler/out/rankings`, `crawler/out/products` (gitignore 대상).

---

## 6. 실행 명령

```bash
# npm/python 계열 명령 전에 반드시 선행
export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"
```

| 목적 | 명령 |
|---|---|
| 카드뉴스 앱 기동 | `cd pipeline && ../crawler/.venv/Scripts/python.exe app.py` → http://127.0.0.1:8787/dashboard |
| 파이프라인 테스트 | `cd pipeline && ../crawler/.venv/Scripts/python.exe -m pytest -q` (67개) |
| 크롤러 테스트 | `cd crawler && ./.venv/Scripts/python.exe -m pytest -q` (약 45개, 네트워크 없음) |
| 백엔드 테스트 | `cd backend && ./.venv/Scripts/python.exe -m pytest -q` (8개) |
| 프론트 빌드 | `cd frontend && npm run build` |
| 로컬 크롤 | `cd crawler && ./.venv/Scripts/python.exe main.py --store json` |
| 인스타 게시 | `python scripts/post_ig.py "<폴더명>" --dry-run` ← **먼저 dry-run** |

---

## 7. 카드뉴스 제작 표준 절차 (가장 자주 하는 작업)

1. **지정 키워드 확인** — KEYWORD-POLICY.md 맨 아래 표의 최신 행.
2. **직전 게시물 2~3개의 `caption.txt` 를 먼저 읽는다** — 문형·어휘 중복 회피용. 필수.
3. **직전 `result.md` 로 표지 유형 확인** — 무드형 ↔ 가격형을 **번갈아** 간다.
4. 상품 선정 → **상세 페이지를 WebFetch로 직접 열어** 소재·가격·후기 확인 (상품명 추정 금지).
   29CM은 JS 렌더라 안 잡히면 무신사에서 같은 상품 검색.
5. 카피 작성 → 렌더 → **CTA 카드 이미지는 `CARD/zzal/` 최신 파일**.
6. **캡션은 자동 생성본을 절대 그대로 두지 않는다** — 이모지 3~5개, 브랜드 계정 목록(핸들 3회 독립 검증), 해시태그 금지.
7. **게시 전 `result.md` 작성** (양식: RESULT-TEMPLATE.md) — 가설·바꾼 변수 1개·판정 기준.
8. **3+1회 검토** → `_preview.html` 생성 → 브라우저로 사용자에게 확인.
9. 승인 후 게시 → **+72시간** 인사이트 API 조회 → result.md 갱신 → 표지 풀 누적 저장률 반영.

---

## 8. 알려진 함정 (밟지 말 것)

**운영**
- `ANTHROPIC_API_KEY`가 없으면 copywriter가 **로그 한 줄 없이** 규칙 기반 폴백으로 떨어진다. 헤드라인이 몇 종류로만 반복되면 이걸 의심할 것. 키가 없으면 **에이전트가 직접 카피를 쓴다.**
- `pipeline/jobs.py`의 `JOBS`는 인메모리 dict. 서버 재시작 시 잡·선정 상품 데이터가 **소실**된다 → 나중에 가격 대조가 불가능해진다.
- `renderer._crop_to_1080x1350`은 실패해도 `print` 한 줄 남기고 통과한다 → 규격 미달 이미지가 게시될 수 있다.
- `/cardnews-files`가 카드뉴스 폴더 전체를 인증 없이 마운트한다. 그 폴더에 **인스타 토큰이 있다.** 127.0.0.1 바인딩이 유일한 방어선.
- 게시는 litterbox/uguu 무료 호스팅에 의존한다. 둘 다 죽으면 게시 불가 (2026-07-27 실장애 이력).

**코드**
- `.claude/hooks/auto-commit-push.sh`가 **턴 종료마다 `git add -A` 후 main에 자동 push**한다 → `deploy.yml`이 걸려 검토 없이 배포된다. CI 실패와 무관하게 배포된다. 저장소에 임시 파일 남기지 말 것.
- `frontend/src/styles.css`의 `.panel`이 두 번 정의돼 충돌 — Generator 폼이 좁은 흰 박스로 깨진다.
- `selection.ts`의 `PIPELINE_URL`이 `http://localhost:8787` 하드코딩 → 배포본에서는 mixed-content로 항상 실패.
- Firebase 웹 API 키가 `frontend/src/firestore.ts`, `public/rankings.html`, `pipeline/reader.py` **3곳**에 하드코딩.
- 모델 ID `claude-sonnet-5`가 `backend/app/config.py`, `pipeline/copywriter.py`, `pipeline/qa.py`, `.env.example`에 분산 하드코딩.
**템플릿 (card-drafts/)**
- **현역 템플릿은 `uvparasol-insta.html` 하나뿐이다.** 같은 C안 템플릿이 5개 파일에 복붙 복제돼 있고, 2026-07-28 디자인 피드백(표지 줌 크롭 `scale(1.45)`, CTA 짤 확대 `pw 400`)이 **uvparasol에만** 반영돼 이미 갈라졌다. 디자인을 고치려면 렌더러가 쓰는 uvparasol을 고쳐야 한다.
- `version-b-vendors.html`은 업체명이 전부 `업체명 ①` **플레이스홀더** — 그대로 쓰면 허위 정보다. `cards.js`의 핸들도 `@your_trend` 플레이스홀더(실제는 `@i_s2_fashion`).
- `ably-parasol-insta.html` / `uvparasol-insta.html` / `rehearsal_build.html`의 `<title>`이 전부 "카시오 시계"로 남아 있다.
- `.superpowers/rehearsal_build.html`은 리허설 산출물인데 랭킹 키워드("오늘의 픽, 가방 랭킹", "랭킹 1위")를 쓰고 후기를 원문 그대로 인용했다. **참고용으로 쓰면 안 된다** (정책 위반 샘플).

**문서 vs 현실**
- `RESULT-TEMPLATE.md`가 "48시간 측정" 구 정책 그대로 — KEYWORD-POLICY는 **+72h 통일**로 개정됨. 템플릿이 뒤처져 있다.
- `CLAUDE.md`의 "디렉토리 구조(목표)"는 초기 상태라 실제와 다르다. `QA-REPORT.md`도 2026-07-17 기준으로 stale.
- **계획 문서(`docs/superpowers/plans/`)를 계약으로 믿지 말 것.** Phase 3 계획서는 아직 "캡션 해시태그 10개", "셀링포인트 = 첫 후기"로 적혀 있는데 둘 다 실사고 후 정반대로 바뀌었다(해시태그 전면 금지 / 긍정 후기 선별). `.superpowers/sdd/progress.md`와 실제 코드·테스트가 진실이다.
- `.superpowers/sdd/task-N-report.md`는 **페이즈 구분 없이 파일명이 재사용·덮어쓰기**됐다. 파일명만으로 어느 페이즈 기록인지 알 수 없다.
- 계획서상 "Phase 4(실전 게시) 미착수"로 적혀 있으나 **실제로는 이미 여러 건 게시됐다**(예: 20260728 여름 티셔츠 → 인스타 permalink 존재). 진행 상태는 계획서가 아니라 `바탕화면\카드뉴스\*\result.md`로 판단할 것.
- 스펙이 규정한 Firestore `selections` 컬렉션은 **구현되지 않았다.** 프론트가 localhost:8787로 직접 POST하고 잡은 인메모리에만 있다 → "실패 단계부터 재시도"는 불가능.
- Firebase 웹 API 키는 `.superpowers/webapp_config.json`까지 포함해 **4곳**에 커밋돼 있다.

---

## 9. 현재 상태 (2026-08-02)

- **Phase 0~3 완료** — 프로브 → 크롤러 → 대시보드 → 파이프라인까지 구축됨. 매시간 크롤 가동 중.
- **현재 지정 키워드**: 2026-07-28 **여름 티셔츠** (그 이전 2026-07-24 여름 슈즈).
- **게시 실적**: 9개 (2026-07-14 ~ 08-03). 누적 도달 1,302 · 저장 1 · 팔로우 0 · 팔로워 4.
  로컬 폴더 13개 중 4개(`20260720 우양산`, `20260722 랭킹픽`×3, `블랙슈즈`, `여름 신발`)는 미게시.
- 🚨 **2026-08-04 피드 전수 분석 — 실험 설계 변경됨** (`카드뉴스\_feed-analysis-20260804.md`)
  - **실험 #1(표지 무드형 vs 가격형)은 보류.** 게시 시각이 통제되지 않아 오염됐고,
    저장률은 현 도달 규모(누적 1,302)에서 측정 자체가 불가능하다.
  - **진행 중 실험은 #4 — 게시 시각 저녁 19:00~21:00 KST 고정, 판정 지표 = 도달.**
    관측상 저녁 게시(207/330/647) vs 그 외(2~48)로 **도달이 30배** 갈렸다.
  - 대조군 수치 갱신: 무드형 풀 저장 1 ÷ 도달 **1,261 = 0.079%** (기존 0.10%는 폐기).
  - **8/02 게시물은 도달 2 (+39h)** — 8/06 00:17 이후 재측정 필요. 10 미만이면 계정 단위
    배포 제한 의심.
- **실험 백로그** (#4 판정 후 착수): #1 표지 유형 재설계, #2 사이즈 팁 한 줄 추가, #3 검색 질문형 캡션.
- **콘텐츠 포지션**: "예쁜 것 골라주는 계정"이 아니라 **"구매 불안을 후기·평점 데이터로 대신 검증해주는 에디터"**.

---

## 10. 작업 유형별 시작점

| 요청 | 먼저 읽을 것 | 건드릴 곳 |
|---|---|---|
| 카드뉴스 만들기/고치기 | KEYWORD-POLICY.md 전문 + 직전 caption.txt 2~3개 | `pipeline/`, `바탕화면\카드뉴스\` |
| 완성본 피드백 | KEYWORD-POLICY §완성본 검토·피드백 처리 규칙 | 렌더 이미지 직접 열어볼 것 |
| 크롤러 오류 | `crawler/FINDINGS.md` | `crawler/fetchers.py`, `parsers.py` |
| 대시보드 UI | — | `frontend/src/Dashboard.tsx`, `styles.css` |
| 게시 실패 | §8 함정 (토큰 만료·호스팅 장애) | `scripts/post_ig.py` |
| 실험/성과 분석 | RESULT-TEMPLATE.md + 각 폴더 result.md | `바탕화면\카드뉴스\*\result.md` |

---

## 11. 이 문서 갱신 규칙

구조가 바뀌거나(새 서브시스템, 진입점 변경) 함정을 새로 발견하면 **이 파일을 갱신한다.**
정책 규칙 자체는 여기가 아니라 `KEYWORD-POLICY.md`에 쓴다 — 이 문서는 **지도**이고, 정책의 원본이 아니다.
