# 20260904 초가을 데님 — 재현 가이드

> 디자인·절차는 [`../early-autumn-outer/README.md`](../early-autumn-outer/README.md) (전면 이미지형 원본)와 같다. 이 문서는 **이 회차에서 다른 것만** 적는다.
> 상태: **렌더·검증 완료, 게시 대기(사용자 승인 필요)**. 완성본은 `바탕화면\카드뉴스\20260904 초가을 데님\`.

## 1. 폴더
| 경로 | 역할 |
|---|---|
| `index.html` | 디자인 원본 (아우터 index.html 복제 + `cards` 교체). |
| `render.py` | 아우터와 동일. `python render.py` → 1~7.jpg (1080×1350). |
| `assets/` | 표지 1 + 상품 5. `assets/cand/{goodsNo}/NN.jpg` 는 무신사 원본 후보(1500×1800). |
| `_old/` | 09-04 구 레이아웃 초안(`index-oldlayout-20260904.html`, 렌더 시트, 후보 컨택트 시트). |
| `caption.txt` · `_preview.html` · `result.md` · `review-selection.md` · `HISTORY.md` | 아우터 폴더와 같은 역할. |

## 2. 실행
```bash
export PATH="/c/Users/yepdo/AppData/Local/Programs/Python/Python312:$PATH" PYTHONIOENCODING=utf-8
cd card-drafts/early-autumn-denim
python render.py
cp [1-7].jpg caption.txt _preview.html result.md "/c/Users/yepdo/OneDrive/Desktop/카드뉴스/20260904 초가을 데님/"
python ../../scripts/post_ig.py "20260904 초가을 데님" --dry-run
python ../../scripts/post_ig.py "20260904 초가을 데님"      # ★ 사용자 승인 후에만
```

## 3. 사진 매핑 (카드 데이터 원문은 `index.html` 의 `const cards=[…]`)

| 카드 | 파일 | 원본 |
|---|---|---|
| 표지 | `cover-secondsalt.jpg` | `cand/6507751/00` (벤치 정면 착용컷, 얼굴) |
| 2 아워데이즈 | `01-ourdayz.jpg` | `cand/7009519/09` |
| 3 미치코런던 | `02-michiko.jpg` | `cand/5984093/00` (유일한 착용컷, 얼굴 없음) |
| 4 미레코 | `03-mireco.jpg` | `cand/6026753/01` |
| 5 낫포너드 | `04-notfornerd.jpg` | `cand/6135920/05` |
| 6 세컨드솔트 | `05-secondsalt.jpg` | `cand/6507751/04` |
| 7 CTA | `../../CARD/zzal/20260905.jpg` | zzal 최신 (09-05 추가 · "도움 필요하신 분 연락주세요") |

## 6. 검증 — Chrome 확장 없이 (2026-09-05 실제 사용)
Playwright + 실제 Chrome 헤드리스로 `https://www.musinsa.com/products/{goodsNo}` 를 열고(`--disable-blink-features=AutomationControlled`, 일반 Chrome UA), 페이지 안에서 fetch:
- 가격: `https://goods-detail.musinsa.com/api2/goods/{no}` → `data.goodsPrice.salePrice / normalPrice / discountRate` (카드 표기). `finalPrice` 는 쿠폰가 — 쓰지 않는다.
- 후기 수·평점: `https://goods.musinsa.com/api2/review/v1/goods/{no}/reviews/summary` → `totalCount`, `satisfactionScore`.
- 후기 원문: `…/review/v1/view/list?page=N&pageSize=20&goodsNo={no}&sort=up_cnt_desc&selectedSimilarNo={no}&myFilter=false&hasPhoto=false&isExperience=false` 를 빈 목록까지 순회.
- 품절: `document.body.innerText` 에 `구매하기` 가 있는지 (없고 `재입고 알림 신청`만 있으면 품절).
- 핸들: 웹검색 + 공식몰 footer(WebFetch) + 인스타 프로필(WebFetch) 3중.
