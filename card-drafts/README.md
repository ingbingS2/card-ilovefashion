# card-drafts — 카드뉴스 디자인과 제작 방법

> 정책(무엇을 써야 하나)은 [KEYWORD-POLICY.md](../KEYWORD-POLICY.md). 여기는 **어떻게 만드나**.

## 폴더

| 경로 | 역할 |
|---|---|
| `early-autumn-denim/` | **최신 회차(게시 대기).** 새 회차는 이 폴더를 복제한다. `verify.py`(무신사 재검증) 포함. |
| `early-autumn-outer/` | 전면 이미지형 **첫 적용·확정 회차**(09-04 게시). 디자인 원본. |
| `uvparasol-insta.html` | `pipeline/renderer.py`가 읽는 파이프라인 템플릿 — **구 레이아웃**(사진 프레임형). 전면 이미지형 이식은 미완. `uvparasol-insta.backup-20260819.html`은 폰트 축소 전 백업. |

## 새 회차 만드는 순서
```bash
export PATH="/c/Users/yepdo/AppData/Local/Programs/Python/Python312:$PATH" PYTHONIOENCODING=utf-8
cd card-drafts && cp -r early-autumn-denim <new-slug> && cd <new-slug>
rm -rf _old assets/cand/* ; # 사진은 무신사 _big 원본을 assets/cand/{goodsNo}/ 에 받아 고른다
# index.html: <title>·.head 문구·const cards=[…] 만 교체. CSS·JS는 건드리지 않는다.
# verify.py: CARDS 딕셔너리를 새 5종으로 교체.
python render.py      # 1~7.jpg (1080×1350)
python verify.py      # 전부 [OK] 여야 게시 가능
```
그 다음 caption.txt · _preview.html · result.md 작성 → 바탕화면 `카드뉴스\YYYYMMDD 키워드\`에 1~7.jpg+caption.txt+_preview.html+result.md 복사 → README.md는 회차 상태·상품표·사진 매핑·캡션만 담아 갱신.

Playwright는 시스템 Python 3.12에 설치돼 있고 `C:\Program Files\Google\Chrome\Application\chrome.exe`를 쓴다. DPR 2로 540×675 카드를 캡처하므로 결과가 정확히 1080×1350이다.

## `cards` 배열 필드
```js
{kind:'cover', img:'assets/cover-x.jpg', pos:'50% 50%', lab:'표지', kicker:'EARLY AUTUMN DENIM',
 title:'여름엔 뺐던 청바지<br><em>이제 꺼낼 때</em>', sub:'커브드 · 와이드 · 부츠컷 · 플레어 · 벌룬'},
{kind:'item', img:'assets/01-x.jpg', pos:'50% 50%', lab:'브랜드', badge:'31%',
 prod:'브랜드 · <b>상품명</b>', title:'헤드라인 1줄<br><em>강조 2줄</em>',
 meta:'무신사 <s>66,000원</s> 45,540원',            // 이 형식 필수 — JS가 정규식으로 쪼갠다
 proof:'후기 99개 · ⭐ 4.9', sp:'“후기 원문 통인용” —&nbsp;실제&nbsp;후기'},
{kind:'cta', img:'../../CARD/zzal/<최신>.jpg', lab:'CTA', title:'…<br><em>…</em>', sub:'…<br>…'}
```
`pos`는 `object-position`(세로 착용컷 1500×1800은 4:5 카드에 거의 안 잘려 보통 `50% 50%`). `badge`는 판매가 옆 `31%↓` 노란 타이포로 렌더된다. `&nbsp;`로 "실제 후기"가 줄 끝에서 고아가 되지 않게 한다.

## 전면 이미지형 스펙 (2026-09-04 사용자 확정 · CSS 원문은 `early-autumn-outer/index.html`의 마지막 `<style>` 블록)

| 요소 | 값 |
|---|---|
| 카드 | 540×675 (×2 = 1080×1350). 표지·상품 공통, CTA만 예외 |
| 사진 | `position:absolute; inset:0; object-fit:cover; object-position:var(--pos)` |
| 그라데이션 | `linear-gradient(to top, rgba(10,10,12,.9) 0%, .66 24%, .22 46%, 0 62%)` |
| 텍스트 블록 | `left/right:32px; bottom:24px; color:#fff` |
| 상품명 줄 | 12px 흰 78% — `브랜드 · <b>상품명</b>` |
| 헤드라인 | 상품 30px/1.3/-.3px · 표지 42px/1.22/-.5px. `<em>`은 **노란 글자 #ffe14d**(밑줄 아님) |
| 가격 블록 | `무신사 ~~정가~~` 12px 62% → 판매가 **24px 굵게** + `31%↓` 17px #ffe14d. 후기 칩(반투명 흰, 12px)은 같은 줄 오른쪽 끝 |
| 출처 | `이미지 출처 : 무신사` 8px 흰 50% |
| 인용문 | 12.5px/1.65, 위에 1px 흰 22% 구분선, 끝에 `— 실제 후기` |
| 마지막 줄 | 왼쪽 `옆으로 넘기기 →`, 오른쪽 `@i_s2_fashion` 11.5px. **페이지 번호·상단 계정명 줄 없음** |
| 표지 추가 | 키커 13px #ff5c85 자간 .14em · 서브 15px 흰 85% |
| CTA | 흰 배경·가운데 정렬·짤 400×380·노란 밑줄 강조·계정명 오른쪽 하단 |
| 폰트·색 | Pretendard Variable(CDN) · 악센트 #ff3366 · 노랑 #ffe14d |

**기각된 시도(다시 하지 말 것)** — 블러 배경 확장("이질감") · 좌우 70px 인셋(오독) · 가로 풀블리드 540×340(옷이 안 보임) · 디테일 클로즈업 나열(옷 형태가 안 읽힘) · 세로 2단 270px 사진 기둥("어중간하게 잘린 느낌") · 사진 위 할인 배지("붕 뜬 느낌") · 가격 앞 핑크 칩("아쉽다") · 페이지 번호 · 상단 계정명 줄. 채택된 것: 전면 이미지형 + 가격 옆 노란 `36%↓`("훨씬 낫다").

## 사진 고르는 법
- 무신사 상세 API `goods-detail.musinsa.com/api2/goods/{no}`의 `goodsImages[]` → `https://image.msscdn.net` + 경로, `_500` 대신 `_big`(1500×1800)으로 받는다(requests 가능).
- 표지: 얼굴 보이는 착용컷, 상품 카드와 **다른 원본**. 상품 카드: 옷이 어깨~밑단까지 통째로 보이는 세로 착용컷. 흰 여백 있는 원본은 PIL bbox로 여백을 먼저 잘라낸다.
- 헤드라인이 가리키는 것(소매 안감·밑단 등)이 그 사진에 실제로 보여야 한다.

## 파이프라인 템플릿(`uvparasol-insta.html`) 주의
`renderer.build_html()`이 `var IMAGES = {` / `var META   = {` / `var CARDS  = [` 세 문자열을 앵커로 치환한다 — 표기(공백 포함)를 바꾸면 `템플릿 앵커를 찾지 못했습니다`로 실패. 회귀 테스트 `pipeline/tests/test_renderer.py`. 결과는 `renderer._crop_to_1080x1350`이 검증한다.
