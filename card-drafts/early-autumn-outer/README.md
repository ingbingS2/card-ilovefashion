# 20260831 초가을 아우터 — 재현 가이드 (READ ME FIRST)

> 이 폴더만 읽으면 **같은 카드뉴스를 똑같이 다시 만들 수 있게** 쓴 문서다.
> 게시 완료: **2026-09-04 02:49** → https://www.instagram.com/p/Dc1YqVAgT-J/
> 완성본(1.jpg~7.jpg · caption.txt · _preview.html · result.md)은 `바탕화면\카드뉴스\20260831 초가을 아우터\` 에 있다.
> 이 디자인은 2026-09-04 사용자 피드백으로 확정된 **현행 카드뉴스 디자인**이다. 새 주제도 이 폴더를 복제해 `cards` 배열과 `assets/`만 바꾸면 된다.
> (현역 파이프라인 템플릿 `card-drafts/uvparasol-insta.html` 은 아직 구 레이아웃 — 이식 전까지는 이 폴더가 디자인 원본이다.)

## 1. 폴더 구조

| 경로 | 역할 |
|---|---|
| `index.html` | **디자인 원본.** CSS + `cards` 데이터 배열 + 렌더용 마크업 생성 JS가 한 파일에 들어 있다. |
| `render.py` | Playwright(Chrome 헤드리스, DPR 2)로 `#card0`~`#card6`을 540×675 → **1080×1350 JPG** 로 캡처. `python render.py` 한 줄. |
| `assets/` | 카드에 실제로 쓰인 사진 6장(표지 1 + 상품 5). CTA 짤은 `../../CARD/zzal/20260830.jpg` 참조. |
| `assets/_unused/` | 제작 중 시도했다가 안 쓴 컷들(폴로·캘빈클라인·클로즈업 등). 참고용, 삭제 가능. |
| `assets/cand/` | 무신사에서 받은 원본 후보(`_big`). 재선정할 때 여기서 고른다. |
| `caption.txt` | 인스타 캡션 원문(UTF-8). |
| `_preview.html` | 7장 + 캡션 미리보기(F5 캐시 우회). 사용자에게 보여줄 때 이 파일 경로를 알린다 — 창은 사용자가 연다. |
| `result.md` | 실험 로그(가설·상품표·핸들 검증·게시 정보·측정값). 게시 폴더에도 같은 파일을 복사한다. |
| `review-selection.md` | 인용한 후기 원문과 선정 기준. |
| `HISTORY.md` | 08-31→09-04 수정 20건 시간순 + **기각된 디자인 시도 목록**. |
| `_old/` | 구 레이아웃 시절 미리보기 PNG·이미지 선정용 컨택트 시트. 참고용. |

## 2. 실행 순서 (처음부터 다시 만들 때)

```bash
export PATH="/c/Users/yepdo/AppData/Local/Programs/Python/Python312:$PATH" PYTHONIOENCODING=utf-8
cd card-drafts/early-autumn-outer
python render.py                       # 1.jpg~7.jpg (1080×1350) 생성
mkdir -p "/c/Users/yepdo/OneDrive/Desktop/카드뉴스/20260831 초가을 아우터"
cp [1-7].jpg caption.txt _preview.html result.md "/c/Users/yepdo/OneDrive/Desktop/카드뉴스/20260831 초가을 아우터/"
python ../../scripts/post_ig.py "20260831 초가을 아우터" --dry-run   # 절차 확인
python ../../scripts/post_ig.py "20260831 초가을 아우터"             # ★ 사용자 승인 후에만. 되돌릴 수 없다.
```
Playwright는 시스템 Python 3.12 site-packages에 설치돼 있고, 브라우저는 `C:\Program Files\Google\Chrome\Application\chrome.exe` 를 그대로 쓴다.

## 3. 레이아웃 스펙 — 전면 이미지형 (2026-09-04 확정)

카드 540×675 (렌더 시 ×2 = 1080×1350). 표지·상품 카드 공통, CTA만 예외.

| 요소 | 값 |
|---|---|
| 사진 | `position:absolute; inset:0; object-fit:cover; object-position: 50% 12%`(얼굴이 위에 오게). 무신사 착용컷 1500×1800(5:6)은 4:5 카드에 거의 잘리지 않는다. |
| 그라데이션 | `linear-gradient(to top, rgba(10,10,12,.9) 0%, .66 24%, .22 46%, 0 62%)` — 하단 62%까지만. |
| 텍스트 블록 | `position:absolute; left:32px; right:32px; bottom:24px; color:#fff` |
| 상품명 줄 | 12px, 흰색 78% (`브랜드 · <b>상품명</b>`) |
| 헤드라인 | 상품 30px/행간 1.3/자간 -.3px, 표지 42px/1.22/-.5px. 강조 `<em>`은 **노란 글자 #ffe14d** (밑줄 하이라이트 아님). |
| 가격 블록 | 위 줄 `무신사 ~~정가~~` 12px 흰색 62% → 아래 줄 판매가 **24px 굵게** + 바로 옆 `36%↓` **17px #ffe14d**. 후기 칩(`후기 N개 · ⭐ 4.9`, 반투명 흰 배경 12px)은 같은 줄 오른쪽 끝(`margin-left:auto`). |
| 출처 | `이미지 출처 : 무신사` 8px 흰색 50% |
| 인용문 | 12.5px/행간 1.65, 위에 `1px rgba(255,255,255,.22)` 구분선. 원문 통인용, 끝에 `—&nbsp;실제&nbsp;후기`. |
| 마지막 줄 | 왼쪽 `옆으로 넘기기 →`, 오른쪽 `@i_s2_fashion` 11.5px. **페이지 번호(N/7)와 상단 계정명 줄은 없다.** |
| 표지 추가 | 키커 `EARLY AUTUMN OUTER` 13px #ff5c85 자간 .14em, 서브 15px 흰색 85%. |
| CTA | 구 C안 그대로(흰 배경·가운데 정렬·짤 400×380·노란 밑줄 강조). 상단 줄은 비우고 `@i_s2_fashion`을 오른쪽 하단에. |
| 폰트 | Pretendard Variable (CDN), 악센트 #ff3366, 노랑 #ffe14d. |

CSS 원문(그대로 복사해도 됨):

```css
/* ===== 2026-09-04 전면 이미지형: 사진이 카드 전체, 멘트는 사진 위 하단 오버레이, 숫자 제거, 계정명 오른쪽 하단 ===== */
.card.item,.card.cover{padding:0;display:block}
.card.item .photo,.card.cover .photo{position:absolute;inset:0;width:540px;height:675px;margin:0;border-radius:0;background:#fff;box-shadow:none}
.card.item .photo img,.card.cover .photo img{width:100%;height:100%;object-fit:cover;object-position:var(--pos,50% 15%)}
.card.item .photo .badge,.card.cover .photo .badge{left:32px;top:28px;font-size:15px;padding:7px 11px}
.card .shade{position:absolute;inset:0;background:linear-gradient(to top,rgba(10,10,12,.9) 0%,rgba(10,10,12,.66) 24%,rgba(10,10,12,.22) 46%,rgba(10,10,12,0) 62%)}
.card .over{position:absolute;left:32px;right:32px;bottom:24px;color:#fff}
.card .over .prodline{font-size:12px;color:rgba(255,255,255,.78);margin-bottom:8px}
.card .over .prodline b{color:#fff}
.card .over .title{font-size:30px;line-height:1.3;letter-spacing:-.3px;color:#fff}
.card .over .title em{box-shadow:none;color:#ffe14d}
.card .over .metarow{margin-top:12px;gap:10px}
.card .over .pricebox{margin-top:14px}
.card .over .was{font-size:12px;font-weight:600;color:rgba(255,255,255,.62)}
.card .over .was s{color:rgba(255,255,255,.62);margin-left:2px}
.card .over .now{display:flex;align-items:baseline;gap:10px;margin-top:2px}
.card .over .now b{font-size:24px;font-weight:800;letter-spacing:-.3px;color:#fff}
.card .over .off{font-size:17px;font-weight:800;color:#ffe14d;letter-spacing:-.2px}
.card .over .off i{font-style:normal;font-size:14px;margin-left:1px}
.card .over .now .proof{margin-left:auto;align-self:center}
.card .over .meta{font-size:14px;color:#fff}
.card .over .meta s{color:rgba(255,255,255,.55)}
.card .over .proof{background:rgba(255,255,255,.16);color:#fff;font-size:12px}
.card .over .credit{color:rgba(255,255,255,.5);margin-top:8px}
.card .over .selling{color:rgba(255,255,255,.92);border-top:1px solid rgba(255,255,255,.22);font-size:12.5px;line-height:1.65;margin-top:10px;padding-top:10px}
.card .over .bottom{display:flex;justify-content:space-between;align-items:center;margin-top:16px;font-size:11px;font-weight:700;color:rgba(255,255,255,.8)}
.card .over .bottom .handle{font-size:11.5px;letter-spacing:.08em;color:#fff}
.card.cover .over .kicker{font-size:13px;letter-spacing:.14em;color:#ff5c85;margin-bottom:10px}
.card.cover .over .title{font-size:42px;line-height:1.22;letter-spacing:-.5px}
.card.cover .over .sub{font-size:15px;color:rgba(255,255,255,.85);margin-top:14px;line-height:1.65}
.card.cta .foot{text-align:right;color:#101012;letter-spacing:.08em}
```

## 4. 카드 데이터 (index.html 의 `cards` 배열 원문)

```js
const cards=[
{kind:'cover',img:'assets/cover-decoroso.jpg',pos:'50% 10%',lab:'표지',kicker:'EARLY AUTUMN OUTER',title:'반팔 위에 바로,<br><em>초가을 아우터</em>',sub:'두껍지 않게 분위기만 먼저 바꾸는 다섯 벌'},
{kind:'item',img:'assets/01-eightseconds-cardigan-crop.jpg',pos:'50% 12%',lab:'에잇세컨즈',badge:'9%',prod:'에잇세컨즈 · <b>러플 긴소매 카디건</b>',title:'진주 단추는 뻑뻑해도<br><em>디자인이 이긴다</em>',meta:'무신사 <s>69,900원</s> 63,610원',proof:'후기 3개 · ⭐ 5.0',sp:'“디자인도 맘에 들고 느낌도 좋아요 단점이라면 단추가 진주라서 좀 빡셉니다. 그래도 그런 단점을 상쇄하는 디자인이에요.” —&nbsp;실제&nbsp;후기'},
{kind:'item',img:'assets/02-decoroso.jpg',pos:'50% 12%',lab:'데꼬로소',badge:'36%',prod:'데꼬로소 · <b>스웨이드 집업 블루종 자켓</b>',title:'툭 걸쳐도<br><em>가을 무드 완성</em>',meta:'무신사 <s>154,000원</s> 98,500원',proof:'후기 59개 · ⭐ 4.9',sp:'“스웨이드 자켓의 근본은 역시 카멜이죠 차분하고 깊이감 있는 톤 다운된 카멜 컬러라 부드러운 스웨이드 질감과 따뜻한 카멜 색상이 만나니 자켓 하나만 툭 걸쳐도 가을에 괜찮게 꾸민느낌으로 멋 낼 수 있어서서 좋더라고요” —&nbsp;실제&nbsp;후기'},
{kind:'item',img:'assets/03-mixxo-cuff.jpg',pos:'50% 12%',lab:'미쏘',badge:'24%',prod:'미쏘 · <b>하프 트렌치코트</b>',title:'소매를 접으면<br><em>디테일이 보여</em>',meta:'무신사 <s>129,000원</s> 98,040원',proof:'후기 15개 · ⭐ 5.0',sp:'“봄가을에 너무너무 잘 입을거 같아요! 소매 안감 디테일도 너무 귀엽구 .. 색도 맘에들어요🫰🏻🤍 사이즈 s인데도 겁나 커요,, 매장에서 입어보고 온라인주문 추천합니댜 ㅎㅎ” —&nbsp;실제&nbsp;후기'},
{kind:'item',img:'assets/04-chicks.jpg',pos:'50% 12%',lab:'칙스',badge:'56%',prod:'칙스 · <b>데일리 윈드브레이커</b>',title:'모델 핏 그대로<br><em>방수천 바람막이</em>',meta:'무신사 <s>103,000원</s> 45,520원',proof:'후기 46개 · ⭐ 4.8',sp:'“사진 모델처럼 핏이 예뻐요 방수천이라 에어컨 추위 많이 타는 사람에게 추천해요” —&nbsp;실제&nbsp;후기'},
{kind:'item',img:'assets/05-adidas-big.jpg',pos:'50% 12%',lab:'아디다스',badge:'17%',prod:'아디다스 · <b>클래식 트랙탑</b>',title:'색감 진짜 예쁜<br><em>하늘색 트랙탑</em>',meta:'무신사 <s>109,000원</s> 90,470원',proof:'후기 9개 · ⭐ 5.0',sp:'“디자인이랑 색감 진짜 이뻐요! 그리고 밑단 시보리가 엄청 짱짱해서 골반에 딱 걸쳐요 이 부분 고려해서 사이즈 선택해야 할 것 같아요” —&nbsp;실제&nbsp;후기'},
{kind:'cta',img:'../../CARD/zzal/20260830.jpg',lab:'CTA',title:'다 사고 싶지만<br><em>통장은 하나</em>',sub:'이번 가을 가장 먼저 살 한 벌부터<br>골라서 저장해두세요'}];
```

필드: `img` 사진 경로 · `pos` object-position · `badge` 할인율(→ `36%↓` 타이포) · `prod` 상품명 줄 · `title` 헤드라인(`<br>`, `<em>`) · `meta` `'무신사 <s>정가</s> 판매가'` 형식 필수(JS가 정규식으로 쪼갠다) · `proof` 후기 칩 · `sp` 인용문.

## 5. 상품·사진 출처 (2026-09-04 실측, 전부 무신사 · 전부 구매 가능 확인)

| 카드 | 브랜드 · 상품 | goodsNo | 가격 | 후기 | 사진 파일 ← 원본 |
|---|---|---|---|---|---|
| 표지 | 데꼬로소 스웨이드 집업 블루종 [카멜] (3번과 다른 컷) | 5359892 | — | — | `cover-decoroso.jpg` ← goods_img `5359892_17569655295178_big` |
| 2 | 에잇세컨즈 [민주킴] 러플 긴소매 카디건 브라운 | 7112376 | 69,900→63,610 (9%) | 3 · 5.0 | `01-eightseconds-cardigan-crop.jpg` ← detail `17872120891873_big` **양옆 흰 여백 잘라냄**(PIL bbox) |
| 3 | 데꼬로소 스웨이드 집업 블루종 [카멜] (무신사 단독) | 5359892 | 154,000→98,500 (36%) | 59 · 4.9 | `02-decoroso.jpg` ← detail `17568872743754_big` |
| 4 | 미쏘 하프 트렌치코트 | 6914777 | 129,000→98,040 (24%) | 15 · 5.0 | `03-mixxo-cuff.jpg` ← detail `17872988729780_big` (접은 소매 안감 보이는 컷) |
| 5 | 칙스 데일리 윈드브레이커 블랙 (무신사 단독) | 5915063 | 103,000→45,520 (56%) | 46 · 4.8 | `04-chicks.jpg` ← detail `17714709710903_big` |
| 6 | 아디다스 클래식 트랙탑 KZ1210 | 6831825 | 109,000→90,470 (17%) | 9 · 5.0 | `05-adidas-big.jpg` ← goods_img `6831825_17841931876646_big` |
| 7 | CTA 짤 | — | — | — | `CARD/zzal/20260830.jpg` (zzal 폴더 최신 파일) |

이미지 원본 URL 규칙: `https://image.msscdn.net/images/prd_img/{yyyymmdd}/{goodsNo}/detail_{goodsNo}_{id}_big.jpg` (goods_img 도 동일 패턴). 상품 페이지의 `img[src*="/{goodsNo}/"]` 에서 id를 읽는다. `requests` 로 받아진다(500px 썸네일은 쓰지 않는다).

## 6. 검증 절차 (게시 전 반드시 · 이번에 실제로 사고를 잡은 항목)

1. **무신사 접근은 Chrome(claude-in-chrome)으로.** `requests` 는 Cloudflare 403. 검색 `https://www.musinsa.com/search/goods?keyword=…&gf=A`, 상품 `https://www.musinsa.com/products/{goodsNo}`.
2. 상품 페이지 텍스트에서 `정가 % 판매가`, `후기 N (개수)` 를 읽고 **`구매하기` 버튼이 있는지 확인** — 없고 `재입고 알림 신청`만 있으면 품절(캘빈클라인 진이 이렇게 걸렸다).
3. 후기 원문은 무신사 페이지 안에서 `fetch('https://goods.musinsa.com/api2/review/v1/view/list?page=0&pageSize=20&goodsNo=…&sort=up_cnt_desc&selectedSimilarNo=…&myFilter=false&hasPhoto=false&isExperience=false')` (pageSize 50은 빈 목록). 인용문은 **목록에 실제로 있는 문장을 통째로**(아디다스 1차 인용은 존재하지 않는 문장이었다).
4. 헤드라인은 인용 후기에서만 뽑고, **사진에서 실제로 보이는 것**을 가리키게 한다(밑단이 안 보이면 "밑단 시보리" 헤드라인 금지).
5. 브랜드 핸들 3중 검증: 웹검색 + 공식몰 footer(WebFetch) + 인스타 프로필(WebFetch). 브라우저 툴은 instagram.com 이동이 차단돼 있다.
6. 렌더 결과 7장을 **실제로 열어** 보고(사진·헤드라인 일치, 가격, 인용, 계정명 위치) 사용자에게 `_preview.html` 경로만 알린다.

## 7. 캡션 (caption.txt 원문)

```
반팔 하나로 나서기엔 저녁 공기가 서늘해졌습니다 🍂

두꺼운 옷을 꺼낼 때는 아니라서, 티셔츠 위에 한 장만 더하는 아우터로 범위를 좁혔습니다. 카디건과 트렌치, 트랙탑이 서로 같은 얼굴이 되지 않게 다섯을 남겼습니다 🧥

지금 바로 걸치고 나가고 싶은 건 몇 번인가요 🍁

📌 브랜드 계정
에잇세컨즈 @8seconds_official
데꼬로소 @decoroso_official
미쏘 @mixxo_korea
칙스 @chicks.co.kr
아디다스 @adidaskr
```
규칙: 2단락 + 질문 + `📌 브랜드 계정` 목록(카드 순서). 이모지 3~5개, 해시태그 없음, 직전 2~3개 캡션과 문형·시그니처 어휘 중복 금지.

## 8. 하지 말 것 (이번에 기각된 것 — 근거는 HISTORY.md)
블러 배경 확장 · 좌우 인셋 · 가로 풀블리드 크롭 · 클로즈업만 나열 · 세로 2단 · 사진 위 할인 배지 · 가격 앞 핑크 칩 · 페이지 번호 · 상단 계정명 줄.
