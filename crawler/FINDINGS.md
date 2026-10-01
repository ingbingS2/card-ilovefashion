# crawler/FINDINGS — 무신사·29CM API 실측 (크롤러·재검증에 쓰는 엔드포인트)

> 2026-07-19 실측, 이후 정정 반영(가격 필드 08-06, 검색 API 08-25, 상세 API 08-11, Playwright 경로 09-05). 크롤러 고칠 때·게시 전 가격 재확인할 때 여기부터.
> 크롤러(GitHub Actions 러너)에서는 `requests`만으로 전부 200 — Referer·쿠키·인증 불필요. **내 PC에서 `www.musinsa.com` 페이지는 Cloudflare 403**(API는 열린다).

## 무신사

**랭킹** `GET https://client.musinsa.com/api/home/web/v5/pans/ranking/sections/200`
- 파라미터: `storeCode=musinsa gf=A ageBand=AGE_BAND_ALL period=REALTIME eventPeriod=BASIC_REALTIME categoryCode=000|001|… page startRank offset`(약 100개/페이지)
- 상품 배열: `data.modules[type=="MULTICOLUMN"].items[]`

| 항목 | 경로 |
|---|---|
| 상품ID | `item.id` → `https://www.musinsa.com/products/{id}` |
| 순위 | `item.image.rank` |
| 브랜드·상품명 | `item.info.brandName` · `item.info.productName` |
| **표시가·할인율** | `item.info.finalPrice` · `item.info.discountRatio` (eventLog payload의 price 값들과 다를 수 있음 — info 쪽이 표시가) |
| 평점·후기수 | `item.image.onClickLike.eventLog.amplitude.payload.reviewScore`(100점 스케일 문자열, ÷20) · `.reviewCount` |
| 썸네일 | `item.image.url` |
| 카테고리 | `…payload.category_id` |

카테고리 코드: 상의 001 · 아우터 002 · 바지 003 · 가방 004 · 원피스/스커트 100 · 신발 103(스니커즈 103004) · 뷰티 104 · 수영복/비치웨어 017022. 전체 227개는 랭킹 컨테이너 응답(`…/ranking?storeCode=…`)에 인라인.

**상품 상세** `GET https://goods-detail.musinsa.com/api2/goods/{goodsNo}` (인증 불필요)
- `data.goodsPrice.salePrice`(**카드에 쓰는 표시가**) · `normalPrice`(정가) · `discountRate` · `couponPrice`/`finalPrice`(쿠폰 다운로드 필요한 값 — 카드·몰 간 비교에 쓰지 않는다)
- `data.goodsImages[].imageUrl` 추가 컷(상대경로, 앞에 `https://image.msscdn.net`). 원본 `_big`은 `…/prd_img/{yyyymmdd}/{goodsNo}/detail_{goodsNo}_{id}_big.jpg`(1500×1800), requests로 받아진다.
- `data.goodsMaterial` 소재 · `data.goodsNm` · `data.brandInfo`
- 옵션·재고: `…/api2/goods/{goodsNo}/options?goodsSaleType=SALE`
- ⚠️ 랭킹 API의 price가 정가로 오는 경우가 있다 — 카드 가격은 상세에서 재확인.

**후기** `GET https://goods.musinsa.com/api2/review/v1/view/list?page=0&pageSize=20&goodsNo={no}&sort=up_cnt_desc&selectedSimilarNo={no}&myFilter=false&hasPhoto=false&isExperience=false`
- `data.list[]`: `grade`(1~5 문자열) · `content` · `createDate` · `likeCount` · `images[].imageUrl`. pageSize 50은 빈 목록 → 20으로 페이징.
- 요약 `GET …/review/v1/goods/{no}/reviews/summary` → `data.totalCount` · `satisfactionScore`(5점)

**검색(goodsNo 찾기)** `GET https://api.musinsa.com/api2/dp/v1/plp/goods?gf=A&keyword=…&sortCode=POPULAR&page=1&size=60&caller=SEARCH` — 무신사 페이지 안에서 fetch하면 200(09-17 확인). `data.list[]`: `goodsNo`·`brandName`·`goodsName`·`normalPrice`·`price`(쿠폰가일 수 있음 — 비교는 상세 `salePrice`)·`reviewCount`. 검색 페이지 HTML 파싱은 추천 상품만 잡혀 쓸모없었다.

**내 PC에서 페이지 접근**: Playwright + 실제 Chrome(`executable_path=C:\Program Files\Google\Chrome\Application\chrome.exe`, `headless=True`, `--disable-blink-features=AutomationControlled`, 일반 UA, `locale=ko-KR`)로 `www.musinsa.com/products/{no}`를 열면 통과. 그 페이지 안에서 `page.evaluate("fetch(...)")`로 위 API 전부 동작. 구매 영역은 늦게 렌더되므로 `wait_for_function`으로 `구매하기|재입고 알림` 텍스트를 최대 20초 기다린다(없고 `재입고 알림 신청`만 있으면 품절). 동작 스크립트: `card-drafts/early-autumn-denim/verify.py`.

## 29CM

**베스트 랭킹** `POST https://display-bff-api.29cm.co.kr/api/v1/plp/best/items` (`Content-Type: application/json`, GET은 405)
```json
{"pageRequest":{"page":1,"size":100},"userSegment":{"gender":"F","age":"THIRTIES"},
 "facets":{"periodFacetInput":{"type":"HOURLY","order":"DESC"},"rankingFacetInput":{"type":"POPULARITY"},
           "categoryFacetInputs":[{"largeId":268100100,"middleId":268106100}]}}
```
- `data.list[]`: `itemId` · `itemUrl.webLink`(`https://product.29cm.co.kr/catalog/{itemId}`) · `itemInfo.brandName/productName` · **`itemInfo.displayPrice`(표시가 — 크롤러 채택)** · `originalPrice`(정가) · `saleRate` · `sellPrice`(즉시할인 **전** 금액, 표시가 아님) · `reviewScore` · `reviewCount` · `thumbnailUrl` · `itemEvent.eventProperties.{large,middle,small}Category{No,Name}`
- 🚨 2026-07-20~08-06 크롤은 `sellPrice`를 price로 담았다 → 그 기간 29CM 가격은 실제보다 높다. 소급 보정 안 됨.
- 카테고리: 여성의류 268100100(상의 268103100 · 바지 268106100 · 원피스 268104100 · 스커트 268107100) · 여성가방 269100100 · 여성슈즈 270100100 · 액세서리 271100100 · 주얼리 305100100 · 모자 310100100. 가방·슈즈는 largeId만.

**후기** `GET https://review-api.29cm.co.kr/api/v4/reviews?itemId=…&page=0&size=20&sort=BEST`
- `data.results[]`: `point`(1~5) · `contents` · `insertTimestamp` · `helpfulCount` · `uploadFiles[].url`. 집계 `data.count` · `data.averagePoint`. 후기수만: `…/reviews/count?itemId=`

**검색(게시 직전 가격 재확인)** `GET https://search-api.29cm.co.kr/api/v4/products/search?keyword=…&page=1&size=20`
- `data.products[]`: `itemNo`(=itemId) · `itemName` · `frontBrandNameKor` · `consumerPrice`(정가) · **`saleInfoV2.totalSellPrice`(표시가, displayPrice와 일치 검산됨)** · `saleInfoV2.totalSaleRate` · `reviewCount` · `reviewAveragePoint` · `isSoldOut`
- ⚠️ 2026-09-05: 이 검색 API도 내 PC `requests`에는 **403**. Playwright로 `www.29cm.co.kr`를 연 뒤 페이지 안에서 fetch하면 200(무신사와 같은 방식). 29CM 상품 페이지(`product.29cm.co.kr/catalog/{itemNo}`)는 Playwright로 열리고 `img.29cm.co.kr/item/…` 이미지가 DOM에 있다(갤러리 1000×1000 + 상세 착용컷 2333×3500, requests로 받아진다). 페이지의 큰 가격은 쿠폰·첫구매가 — 표시가는 `totalSellPrice`.
- 29CM 상세 페이지는 JS 렌더 — WebFetch로 소재표가 안 잡히면 무신사에서 같은 상품을 찾는다.

## 운영 확인
- 크롤러는 GitHub Actions 매시 7분(`crawl.yml`)에서 두 몰 모두 실데이터 수집 확인(봇 차단 없음). 13 랭킹/650 상품/0 오류 수준.
- 몰 간 최저가 비교는 `salePrice`(무신사) vs `totalSellPrice`/`displayPrice`(29CM) — 쿠폰가끼리 비교하면 무신사가 부당하게 싸 보인다(08-25 위띠아 121,130 vs 쿠폰가 96,910).

## 상품 나이(신상 판별) — 2026-09-13 실측

| 몰 | 쓸 필드 | 비고 |
|---|---|---|
| 29CM | `bff-api…/api/v5/product-detail/{no}` → **`availableBeginTimestamp`** | 판매 개시일. 같은 응답의 `visibleBeginTimestamp`는 **재진열일**이라 오래된 상품이 최신으로 보인다(노티아 3007788: avail 2025-01-16 / visible 2025-12-01) |
| 무신사 | 상세 응답 `goodsImages[].imageUrl`의 **`/prd_img/{yyyymmdd}/`** | `sellStartDate`·`saleStartDate`는 null, `seasonYear`는 `"0000"`, `isFirst`/`isDrop`는 false 고정이라 못 쓴다 |

두 몰 교차 대조 5건(가을 스커트 회차): 드로우핏 2024-01-09/2024-01-23 · 노티아 2025-01-06/2025-01-16 · 로에일 2022-10-25/2022-10-25 · 커스텀어클락 2025-08-26/2025-09-05 · 노우드 2026-02-05/2026-01-26 → **2주 이내 일치**. 신상 기준은 [KEYWORD-POLICY.md](../KEYWORD-POLICY.md) §2.

부가 필드: 29CM `soldQty`·`heartCount`·`reviewAggregation` · 무신사 `labels[]`(무신사단독 등)·`goodsSaleType`.

## ⚠️ 29CM API 연속 호출 차단 (2026-09-13)

`bff-api.29cm.co.kr` 상세를 **수백 건 빠르게 치면 차단**된다. 차단되면 CORS 헤더 없는 응답이 와서 브라우저에는 `TypeError: Failed to fetch`로 보인다(HTTP 상태를 못 읽으니 CORS 문제로 오해하기 쉽다). 한동안 같은 오리진에서 전부 실패한다.
- 대응: 상세 조회는 **동시 1건, 간격 300ms 이상**, 한 번에 40건 이하로 끊는다. 검색 API(`search-api`)는 이때도 살아 있었다.
- 브라우저 안에서 오래 도는 스크립트는 도구 타임아웃(45초)에 걸린다 — 후보 목록을 `window.__cand`에 두고 호출을 여러 번 나눠 처리한다.

**보조 신호 — 무신사 `styleNo`**: 제조사 품번이 그대로 온다(신발 상품코드 규칙에 쓰는 값, KEYWORD-POLICY §3). 브랜드에 따라 시즌이 박혀 있어 신상 교차 확인에 쓸 수 있다 — 에트오소메 `ET26FWASO42BR` · 블랙퍼플 `BP26FWSH01_BK` · 기호 `K26-SH045 BR` · 엘리자베스 스튜어트 `EBAL165523`(시즌 없음). 규칙이 브랜드마다 달라 단독 근거로는 쓰지 않는다.
⚠️ `goodsMaterial`은 문자열이 아니라 `{maxLowCount, materials[]}` 객체다(`.slice()` 하면 TypeError). 신발은 `materials`가 비어 있는 경우가 많고, 채워질 땐 `굽 높이` 같은 항목이 `items[].isSelected`로 온다 — 소재는 상세 페이지에서 확인한다.
