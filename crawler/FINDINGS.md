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
- **GitHub Actions 실행 가능 여부: 아니오(이번 브랜치 상태 기준) — 크롤러는 내 PC 작업 스케줄러로 실행, 워크플로 파일은 수동 트리거용으로만 유지.**
  - 근거: `.github/workflows/probe.yml` 은 `feature/phase0-crawl-probe` 브랜치에는 존재(Contents API `GET /repos/ingbingS2/card-ilovefashion/contents/.github/workflows/probe.yml?ref=feature/phase0-crawl-probe` → 200)하지만, 저장소의 Actions 워크플로 목록에는 등록되어 있지 않음: `GET /repos/ingbingS2/card-ilovefashion/actions/workflows` 응답이 `ci.yml`, `deploy.yml` 두 개뿐(`total_count: 2`)이고 `probe.yml` 이 없음.
  - 이 상태에서 `POST /repos/ingbingS2/card-ilovefashion/actions/workflows/probe.yml/dispatches` (body `{"ref":"feature/phase0-crawl-probe","inputs":{"mode":"musinsa_ranking"}}`, 이어서 `mode=cm29_best`)를 각각 1회 호출한 결과 **둘 다 HTTP 404** `{"message":"Not Found","documentation_url":".../workflow-dispatch-event"}` — 워크플로 실행(run)이 아예 생성되지 않음. 두 시도 모두 동일하게 실패하여 run ID 자체가 존재하지 않음(재시도해도 구조적 원인이 동일하므로 반복 호출은 의미 없다고 판단, 몰당 1회로 종료).
  - 원인: GitHub REST API 의 workflow_dispatch 는 워크플로 파일이 **저장소의 기본 브랜치(default branch, 이 저장소는 `main`)** 에 존재해야 해당 워크플로가 "등록"되어 dispatch 대상이 되는 GitHub 사양 때문. 이 저장소의 `main` 에는 `probe.yml` 이 없고(Phase 0 전용 브랜치에만 존재), 따라서 `ref` 파라미터로 feature 브랜치를 지정해도 dispatch 자체가 404 로 거부됨. 사이트 차단(403/429/캡차)이 아니라 GitHub 플랫폼의 사전 조건 미충족.
  - 인증/자격증명: 문제 없음 — Git Credential Manager 에 저장된 토큰(`git credential fill`)으로 REST API 호출 자체는 정상 동작(`GET .../actions/workflows` 200, `GET .../contents/...` 200), dispatch 만 404.
  - 데이터 검증(로컬 vs Actions): Actions 상에서 실제 실행/아티팩트 자체가 생성되지 않았으므로 이번 라운드에서 "봇 차단 페이지 vs 실제 상품 데이터" 대조는 수행 불가. 크롤링 성공 여부 자체는 Task 3 로컬 결과(무신사 랭킹/후기, 29CM 랭킹(POST)/후기 4개 엔드포인트 모두 200 + 실제 상품ID/가격/후기수 확인)만이 근거임.
  - 결론적 실행 위치: 위 조건(워크플로가 default 브랜치에 없어 미등록) 은 이 워크플로 파일을 `main` 에 병합하면 해소 가능한 조건이지만, 이번 태스크 범위(브랜치 병합/워크플로 수정 금지)를 벗어나므로 시도하지 않음. 현재 시점 결론은 **"크롤러는 내 PC 작업 스케줄러로 실행, `probe.yml` 워크플로 파일은 (향후 `main` 병합 후) 수동 트리거용으로만 유지"**.
