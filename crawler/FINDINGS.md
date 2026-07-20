# 크롤링 탐색 결과 (Phase 0)

- 실행일: 2026-07-19
- **로컬(내 PC) 결과** (아래 전체). GitHub Actions 환경에서의 재현 여부는 미확인 — Task 5 에서 검증.
- 사용 도구: `crawler/probe.py discover`(Playwright 로 실제 페이지 로드 후 XHR 채집) / `crawler/probe.py direct`(requests 로 브라우저 없이 재현).
- 요청 매너: 프리셋 discover 각 1회, 상품 페이지 discover 각 1회, direct 호출 4회 + 보조 확인 2회 — 실행 사이 최소 3~5초 대기. 403/429/캡차는 한 번도 발생하지 않음.

## 무신사

### 랭킹 엔드포인트
- 페이지: `https://www.musinsa.com/main/musinsa/ranking` (프리셋 URL 그대로 유효, 리다이렉트 없음)
- 실제 상품 목록 API: `GET https://client.musinsa.com/api/home/web/v5/pans/ranking/sections/200`
  - (참고: `.../ranking?storeCode=...` 는 탭/모듈 메타데이터만 주는 "컨테이너" 응답이고, 실제 상품 배열은 `sections/200`에 있음 — index.json 상 이 두 URL이 세트로 호출됨)
- 파라미터 (실측, 쿼리스트링):
  | 파라미터 | 예시 값 | 의미 |
  |---|---|---|
  | storeCode | musinsa | 스토어 구분 |
  | gf | A | 성별 필터 (A=전체, 확인된 다른 값 미탐색) |
  | ageBand | AGE_BAND_ALL | 연령대 필터 |
  | period | REALTIME | 집계 주기 |
  | eventPeriod | BASIC_REALTIME | 이벤트 주기 |
  | categoryCode | 000(전체) / 001(상의) 등 | 카테고리 코드 — 목록은 아래 표 참고 |
  | contentsId | (빈 값 가능) | |
  | variantValue | (빈 값 가능) | |
  | page | 1, 2, 3 ... | 페이지 번호 |
  | startRank | 1, 102, 204 ... | 시작 순위 (offset+1) |
  | offset | 0, 101, 203 ... | 오프셋 |
  - 실측: `categoryCode=001`(상의)로 direct 호출 시 응답 데이터가 실제로 상의 상품(예: "언더오프 롤업 슬리브 크롭 반팔 티셔츠", category_id="001")으로 바뀌는 것을 확인함 → 카테고리 파라미터 정상 동작.
  - 페이지당 상품 수는 응답 상 rank 구간(예 page=2 → startRank=102)으로 미루어 약 100개/페이지로 추정(정확한 size 파라미터는 없고 startRank/offset 조합으로 페이징).
- 필요 헤더: **없음** — `direct` 커맨드의 기본 헤더(User-Agent, Accept: application/json, Accept-Language: ko-KR)만으로 200 OK. Referer, 쿠키, 인증 토큰 불필요.
- 응답 구조 (summarize_json, 실측):
  ```json
  {"meta": {"result": "str", "errorCode": "str", "message": "str"}, "data": {"modules": "list"}, "hasNext": "bool", "link": {"next": "str"}}
  ```
  `data.modules[]` 중 `type == "MULTICOLUMN"` 인 모듈의 `items[]`가 실제 상품 배열.
- 필드 경로 (실측, item = `data.modules[i].items[j]`, i는 MULTICOLUMN 모듈 인덱스):
  | 항목 | 필드 경로 | 비고 |
  |---|---|---|
  | 상품ID | `item.id` (문자열) | 예: `"5928448"`. 상품 URL은 `https://www.musinsa.com/products/{id}` 로 조립 가능 |
  | 순위 | `item.image.rank` | |
  | 브랜드명 | `item.info.brandName` | 한글명. 브랜드 코드는 `item.image.onClickLike.eventLog.amplitude.payload.brand_id` |
  | 상품명 | `item.info.productName` | |
  | 가격 | `item.info.finalPrice` (최종 표시가) + `item.info.discountRatio`(할인율%) | **주의**: 같은 아이템의 `item.image.onClickLike.eventLog.{ga4,amplitude}.payload` 안에도 `price`/`original_price`/`best_price`/`discount_rate` 필드가 있는데 `info.finalPrice`와 값이 다를 수 있음(실측: info.finalPrice=46800/discountRatio=28% vs eventLog.price=58500/original_price=65000/best_price=52650/discount_rate=10%) — 할인 종류(기본가/멤버십가/쿠폰적용 최종가)가 다른 것으로 추정되나 문서화된 정의는 없음. 크롤러는 `info.finalPrice`를 화면 표시가 기준값으로 채택 권장, 정확한 정가 검증이 필요하면 상품 상세 API 추가 확인 필요. |
  | 평점 | `item.image.onClickLike.eventLog.amplitude.payload.reviewScore` | **주의**: 별도 전용 필드가 아니라 이벤트 로그(analytics payload) 안에만 존재. 값은 문자열(예: `"96"`), 100점 만점 스케일. 후기 요약 API의 `satisfactionScore`(5점 만점, 예: 4.8) × 20 과 일치함을 실측 확인(4.8×20=96). |
  | 후기수 | 위와 동일 경로의 `reviewCount` (문자열, 예: `"53"`) | 상품 상세 후기 요약 API의 `totalCount`와 일치 확인 |
  | 썸네일 | `item.image.url` | 500px CDN 이미지 |
  | 카테고리코드 | `item.image.onClickLike.eventLog.amplitude.payload.category_id` | 요청 파라미터 categoryCode와 동일 값 |

### 후기 엔드포인트
- 상품: 무신사 랭킹에서 뽑은 상품ID `5928448` (Low Rise Capri Jeans DCWPT023CPBLACK), 페이지 `https://www.musinsa.com/products/5928448`
- 핵심 URL: `GET https://goods.musinsa.com/api2/review/v1/view/list`
- 파라미터 (실측): `page`(0-base), `pageSize`(예 10), `goodsNo`(상품ID), `sort`(예 `up_cnt_desc`), `myFilter`, `hasPhoto`, `isExperience` (모두 `false` 로 기본 동작 확인)
- 보조 엔드포인트(같은 상품 페이지에서 함께 채집됨, 참고용):
  - `GET https://goods.musinsa.com/api2/review/v1/goods/{goodsNo}/reviews/summary` → 집계값(`totalCount`, `satisfactionScore` 등)
  - `GET https://goods.musinsa.com/api2/review/v1/picture-reviews?goodsNo=...&size=20&page=1` → 포토리뷰만
- 필요 헤더: **없음** — direct 기본 헤더만으로 200 OK.
- 응답 구조 (summarize_json, 실측):
  ```json
  {"data": {"list": "list", "total": "int", "page": "dict"}, "meta": {"result": "str", "errorCode": "NoneType", "message": "NoneType"}}
  ```
- 필드 경로 (item = `data.list[]`):
  | 항목 | 필드 경로 |
  |---|---|
  | 후기 개별 평점 | `item.grade` (문자열, 1~5) |
  | 후기 본문 | `item.content` |
  | 작성일 | `item.createDate` |
  | 좋아요수 | `item.likeCount` |
  | 이미지 | `item.images[].imageUrl` |
  | 작성자 | `item.userProfileInfo.userNickName` 등 |
- 집계값(요약 API `reviews/summary`, 실측): `data.totalCount`(=53, 랭킹 응답의 reviewCount와 일치), `data.satisfactionScore`(=4.8, 5점 만점)

## 29CM

### 랭킹 엔드포인트
- 페이지: 프리셋 URL `https://www.29cm.co.kr/home/best` 는 **홈(`/`)으로 리다이렉트됨**(빈 채집, 실측 확인). 브라우저에서 페이지 내 링크(`href="https://www.29cm.co.kr/best-products"`, 링크텍스트 "베스트")를 찾아 `probe_targets.py` 를 `https://www.29cm.co.kr/best-products` 로 갱신 후 재실행 → 정상 채집됨.
- 실제 상품 목록 API: `POST https://display-bff-api.29cm.co.kr/api/v1/plp/best/items`
  - **주의: GET 이 아니라 POST**이며, 파라미터가 쿼리스트링이 아니라 JSON 바디로 전달됨 (URL 자체에는 쿼리스트링이 없음).
- 요청 바디 (실측, Playwright 로 request.post_data 캡처):
  ```json
  {"pageRequest":{"page":1,"size":100},"userSegment":{"gender":"F","age":"THIRTIES"},"facets":{"periodFacetInput":{"type":"HOURLY","order":"DESC"},"rankingFacetInput":{"type":"POPULARITY"}}}
  ```
  | 필드 | 예시 값 | 의미 |
  |---|---|---|
  | pageRequest.page / size | 1 / 100 | 페이지네이션 |
  | userSegment.gender | F | 성별 세그먼트(페이지 URL의 `gender=F` 쿼리와 연동) |
  | userSegment.age | THIRTIES | 연령대(페이지 URL의 `age=30` 과 연동) |
  | facets.periodFacetInput.type | HOURLY | 집계 주기 |
  | facets.rankingFacetInput.type | POPULARITY | 정렬 기준 |
  - **카테고리 필터**: 이 요청 바디에는 카테고리 관련 필드가 없음(=미확인). 응답 각 아이템에 카테고리 코드가 포함될 뿐, 요청 시 카테고리로 필터링하는 파라미터는 이번 탐색 범위에서 발견하지 못함.
- 필요 헤더: `Content-Type: application/json` 만 있으면 됨. **Referer 없이도, 로그인 쿠키 없이도 200 OK** (requests.post 로 직접 실측 확인 — 아래 direct replay 참고).
- 응답 구조 (summarize_json, 실측):
  ```json
  {"meta": {"result": "str"}, "data": {"list": "list", "pagination": "dict"}}
  ```
- 필드 경로 (item = `data.list[]`):
  | 항목 | 필드 경로 |
  |---|---|
  | 상품ID | `item.itemId` (숫자) |
  | 상품 URL | `item.itemUrl.webLink` (`https://product.29cm.co.kr/catalog/{itemId}`) |
  | 브랜드명 | `item.itemInfo.brandName` (또는 `item.itemEvent.eventProperties.brandName`) |
  | 상품명 | `item.itemInfo.productName` |
  | 가격 | `item.itemInfo.originalPrice`(정가) / `displayPrice`(즉시할인가) / `sellPrice`(멤버십 등 추가할인가) / `saleRate`(할인율%) |
  | 평점 | `item.itemInfo.reviewScore` (숫자, 5점 만점, 예: 5.0) |
  | 후기수 | `item.itemInfo.reviewCount` (숫자, 예: 3442) |
  | 썸네일 | `item.itemInfo.thumbnailUrl` |
  | 카테고리코드 | `item.itemEvent.eventProperties.{largeCategoryNo, largeCategoryName, middleCategoryNo, middleCategoryName, smallCategoryNo, smallCategoryName}` |
  - 무신사와 달리 평점·후기수가 이벤트 로그가 아닌 `itemInfo` 에 바로 노출되어 있어 필드 경로가 더 단순함.
  - `data.pagination` = `{"page": 1, "size": 100, "hasNext": true}` (실측)

### 후기 엔드포인트
- 상품: 29CM 베스트 목록 1위 근처 아이템ID `3334217` (PWC EVERYDAY BALLOON JOGGER PANTS_18COLOR), 페이지 `https://product.29cm.co.kr/catalog/3334217`
- 핵심 URL: `GET https://review-api.29cm.co.kr/api/v4/reviews`
- 파라미터 (실측): `itemId`, `page`(0-base), `size`(예 20), `sort`(예 `BEST`)
- 보조 엔드포인트(같은 상품 페이지에서 함께 채집됨, 참고용):
  - `GET https://review-api.29cm.co.kr/api/v4/reviews/count?itemId=...` → 후기수만
  - `GET https://review-api.29cm.co.kr/api/v4/reviews/photo?itemId=...&page=0&size=6` → 포토리뷰만
  - `GET https://review-api.29cm.co.kr/item-qna/front/?item_no=...` → Q&A(후기 아님, 별개)
- 필요 헤더: **없음** — direct 기본 헤더만으로 200 OK.
- 응답 구조 (summarize_json, 실측):
  ```json
  {"result": "str", "data": {"count": "int", "giftCount": "int", "averagePoint": "float", "results": "list"}, "message": "NoneType", "errorCode": "NoneType"}
  ```
- 필드 경로 (item = `data.results[]`):
  | 항목 | 필드 경로 |
  |---|---|
  | 후기 개별 평점 | `item.point` (1~5) |
  | 후기 본문 | `item.contents` |
  | 작성일 | `item.insertTimestamp` |
  | 도움돼요 수 | `item.helpfulCount` |
  | 이미지 | `item.uploadFiles[].url` |
  | 작성자 | `item.userId` (마스킹됨, 예: `"ang*******"`) |
- 집계값: `data.count`(=3443, 랭킹 응답의 reviewCount=3442와 거의 일치 — 실시간 변동 추정), `data.averagePoint`(=5.0)

## 카테고리 코드 (확인분)

무신사는 랭킹 컨테이너 응답(`.../ranking?...`)에 카테고리 탭 전체 목록이 인라인으로 포함되어 있어 실측 전량 확보(227개). 29CM은 이번 탐색 범위에서 카테고리 필터 API/목록을 찾지 못했고, 실제 상품 응답에 붙어있는 분류 코드만 확인함(아래는 그중 일부).

| 카테고리 | 무신사 코드 | 29CM 코드(참고, 필터 불가 확인) |
|---|---|---|
| 상의(전체) | 001 | 268103100 (여성의류 하위, large=268100100) |
| 아우터 | 002 | 확인 불가 (샘플 100건 내 미노출) |
| 바지 | 003 | 268106100 |
| 원피스/스커트 | 100 (원피스/스커트 대분류) | 268107100 (스커트만 확인, 원피스 코드 미노출) |
| 신발 | 103 (대분류), 103004=스니커즈 | 270103100 (여성슈즈>부츠만 확인) |
| 가방 | 004 | 269100100 (여성가방, 대분류만 확인) |
| 뷰티 | 104 (대분류), 104001=스킨케어 등 | 확인 불가 |

- 무신사 카테고리 코드 전체 목록(227건)은 `crawler/samples/musinsa_ranking/009_...json` 원본에서 재추출 가능(로컬에만 존재, 커밋 대상 아님).
- 29CM은 카테고리가 "필터 파라미터"가 아니라 "응답에 붙는 분류 메타데이터"로 보이며, 카테고리별 수집이 필요하면 별도의 카테고리 목록/필터 API를 추가 탐색해야 함(이번 탐색 범위 밖).

## 결론
- **브라우저 없이 requests 만으로 수집 가능 여부: 예.** 무신사 랭킹(GET)·무신사 후기(GET)·29CM 후기(GET) 는 물론, 29CM 랭킹(POST + JSON 바디)까지 포함해 4개 핵심 엔드포인트 전부 `requests` 로 200 OK 및 정상 JSON 응답을 실측 확인했다(직접 GET/POST 재현, Playwright 불필요). 필요 헤더는 29CM 랭킹의 `Content-Type: application/json` 정도이며, Referer·쿠키·인증 토큰은 4개 엔드포인트 어디에도 필요하지 않았다. 단, 29CM 랭킹은 GET 이 아니라 POST + JSON 바디라는 점을 크롤러 구현 시 반드시 반영해야 한다(GET 시도 시 405 확인).
- **GitHub Actions 실행 가능 여부: 예 (확정, 2026-07-20 3차 확인) — 크롤러는 GitHub Actions 매시간 스케줄로 실행한다.**
  - **3차 확인(최종)**: 2차 시도에서 큐에 걸려 있던 두 run 이 이후 자연 해소되어 **둘 다 `completed / success`** 로 종료됨(musinsa_ranking `29714495056` started 03:21:52Z, cm29_best `29714513646` started 03:22:24Z). 아티팩트를 내려받아 본문 대조 완료 — 무신사 `sections/200` 응답에 실상품 102개(브랜드·finalPrice 정상), 29CM `plp/best/items` 응답에 실상품 100개(itemId·sellPrice·reviewCount 정상). **봇 차단·캡차 페이지 아님, 데이터센터 IP 차단 없음.** 2차 시도의 큐 정체는 일시적 러너 배정 지연이었음이 확인됨.
  - **1차 시도(브랜치 미병합 시점)**: `probe.yml` 이 `feature/phase0-crawl-probe` 에만 존재하고 `main`(기본 브랜치)에는 없어 Actions 워크플로 목록에 미등록 상태였음 → dispatch 2건(musinsa_ranking, cm29_best) 모두 HTTP 404(run 자체가 생성 안 됨). 이후 `feature/phase0-crawl-probe` 가 `main` 에 병합됨(main HEAD `fa99642`).
  - **2차 시도(main 병합 후 재검증)**: `GET /repos/ingbingS2/card-ilovefashion/actions/workflows` → `probe.yml`(id `316439675`) 정상 등록 확인(`total_count: 3`). `POST .../workflows/probe.yml/dispatches` body `{"ref":"main","inputs":{"mode":"musinsa_ranking"}}` → **HTTP 204**(성공), 이어서 `mode=cm29_best` → **HTTP 204**. → 1차 시도의 404 원인(파일이 default 브랜치에 없어 미등록)이 정확했고, main 병합으로 실제 해소됨을 확인.
  - 생성된 run: musinsa_ranking → run id `29714495056`(created `2026-07-20T03:21:52Z`), cm29_best → run id `29714513646`(created `2026-07-20T03:22:24Z`). 두 run 모두 즉시 `status=queued` 로 생성됨(정상).
  - **문제**: 이후 foreground 로 약 13~14분(30초 간격, 총 2회 루프) 폴링했으나 두 run 모두 `status=queued` 에서 전혀 진행되지 않음(`updated_at` 이 `created_at` 과 동일 — job 이 러너에 배정된 적조차 없음, `started_at` 없음). **완료(completed)에 도달하지 못해 아티팩트가 생성되지 않았고, 실제 상품 데이터 대조(봇 차단 페이지 여부 확인)를 이번 세션에서 수행할 수 없었음.**
  - **원인 진단**: 이 정체가 `probe.yml` 고유 문제가 아님을 확인 — 같은 시각(03:20:19Z)에 무관한 `ci.yml` 워크플로 run(`29714442024`, 우리가 트리거하지 않은 별개 이벤트로 생성됨)도 동일하게 `queued` 에서 멈춰 있었음(직전 `ci.yml` run 들은 07-18 에 정상 `completed/success`). 즉 **이 저장소/계정에 대한 GitHub-hosted 러너 배정이 이번 관찰 시점에 전반적으로 정체**된 것으로 보이며, 우리 워크플로나 대상 사이트의 차단과는 무관함. `GET https://www.githubstatus.com/api/v2/status.json` 은 `"All Systems Operational"` 로 응답해 GitHub 공식 장애 공지와는 불일치 — 계정/저장소 단위의 일시적 배정 지연일 가능성이 높으나 이번 세션 내에서 원인을 확정하지 못함. Actions 권한(`GET .../actions/permissions` → `enabled: true, allowed_actions: all`), 인증 토큰(다른 API 호출은 모두 200)에는 문제 없음.
  - **재시도 판단**: 지침에 따라 "인프라 실패 시 몰당 1회 재시도" 를 검토했으나, 증상이 개별 run 의 실패가 아니라 **큐 자체가 이 저장소의 어떤 job 도 배정하지 못하는 상태**(무관한 ci.yml 도 동일 증상)이므로 재디스패치는 새로운 정보를 주지 못할 것으로 판단해 추가 재시도는 생략함(이미 생성된 두 run 은 취소하지 않고 그대로 둠 — 이후 자연 해소되면 별도로 결과 확인 가능).
  - **데이터 검증**: 이번 세션에서는 Actions 상의 "실제 상품 데이터 vs 봇 차단 페이지" 대조를 수행하지 못함(run 이 완료되지 않아 아티팩트 없음). 크롤링 자체의 성공 여부는 여전히 **Task 3 로컬 결과**(무신사 랭킹/후기, 29CM 랭킹(POST)/후기 4개 엔드포인트 모두 200 + 실제 상품ID/가격/후기수 확인)만이 근거임.
  - **결론적 실행 위치**: dispatch 메커니즘 자체(브랜치 등록, 인증, 트리거)는 main 병합 후 정상 동작함을 확인했으나, 이번 세션에서는 러너 정체로 실제 실행 완료·데이터 검증까지 도달하지 못했다. 따라서 현재 시점 결론은 **"크롤러는 당분간 내 PC 작업 스케줄러로 실행, `probe.yml` 은 수동 트리거용으로 유지하되, 러너 정체가 해소된 이후(또는 다른 시간대에) 동일 절차로 재검증해 최종 확정할 것"**. run id `29714495056`/`29714513646` 은 나중에 `GET /repos/ingbingS2/card-ilovefashion/actions/runs/<id>` 로 사후 확인 가능.
