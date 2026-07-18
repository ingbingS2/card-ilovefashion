# QA 보고서 — AI 카드뉴스 자동 생성기

실제 브라우저(Playwright + Chromium)로 앱을 조작해 기능별로 검증한 결과입니다.
단위 테스트가 아니라 **사용자가 실제로 클릭하는 경로**를 그대로 따라갔습니다.

- 검증일: 2026-07-17
- 대상: `frontend/` (React + Vite), `backend/` (FastAPI), `card-drafts/bags-cardnews.html`
- 도구: Playwright 1.x (Chromium), Pillow, pytest
- 결과 요약: **기능 14개 통과 · 경고 2 · 실패 0**, 다만 **SPEC 위반 이슈 1건 발견** (PNG 해상도)

---

## 1. 검증 환경과 원칙

CLAUDE.md 규칙에 따라 **실제 Claude API 호출과 Firebase 접속은 하지 않았습니다.**

| 항목 | 처리 |
|---|---|
| Anthropic API | `dependency_overrides[get_generator]` 로 목 주입 (`tests/conftest.py` 와 동일 방식) |
| Firestore | `STORAGE_BACKEND=memory` — 인메모리 저장소 |
| 제품 코드 | **수정 없음** — QA용 서버는 `app.main:create_app()` 을 import 해 의존성만 갈아끼움 |
| 백엔드 | `uvicorn` 127.0.0.1:8000 |
| 프론트 | `vite dev` localhost:5173 (`VITE_API_BASE` 기본값이 8000) |

목 제너레이터는 `주제 헤드라인 N` 형태의 슬라이드를 요청한 장수만큼 돌려주고,
주제가 `서버오류테스트` 일 때만 `RuntimeError` 를 던져 **500 에러 경로**를 재현합니다.

---

## 2. 프론트엔드 기능별 결과

| # | 기능 | 검증 방법 | 결과 |
|---|---|---|---|
| 1 | 초기 로드 · 한국어 UI | `h1` 텍스트 확인 | ✅ `AI 카드뉴스 자동 생성기` |
| 2 | 입력 폼 필드 | 라벨 6종 존재 확인 | ✅ 주제/타깃/목표/톤/CTA/슬라이드 수 |
| 3 | 주제 필수 검증 | 빈 주제로 제출 | ✅ 생성 안 됨 (HTML5 `required`) |
| 4 | 슬라이드 수 슬라이더 | range 값 변경 | ✅ 라벨에 `10장` 반영 (범위 1~20) |
| 5 | 카드뉴스 생성 | 폼 입력 후 제출 | ✅ `POST /api/generate` → 10장 렌더 |
| 6 | 폼 값 전달 | 응답 본문에 톤/타깃 포함 확인 | ✅ 입력이 백엔드까지 전달됨 |
| 7 | 슬라이드 4:5 비율 | `boundingBox` 실측 | ✅ 327×409 = 비율 0.800 |
| 8 | 슬라이드 순번 | `.slide-index` 전체 텍스트 | ✅ `1장`~`10장` 순서대로 |
| 9 | 개별 PNG 내보내기 | 다운로드 이벤트 수신 + 파일 열기 | ✅ `cardnews-1.png` 저장됨 |
| 10 | 전체 PNG 내보내기 | 다운로드 10회 수신 | ✅ `cardnews-1` … `cardnews-10` |
| 11 | 생성 결과 저장 | 저장 버튼 클릭 | ✅ `POST /api/cardnews` → 목록에 `여름 가방 트렌드 · 10장` |
| 12 | 이력 목록 조회 | 새로고침 후 확인 | ✅ `GET /api/cardnews` 로 복원 |
| 13 | 이력 다시 열기 | 목록 항목 클릭 | ✅ 슬라이드 10장 복원 |
| 14 | 에러 처리 | 500 유발 | ✅ 화면에 `⚠️ ANTHROPIC_API_KEY 가 설정되지 않았습니다.` |

### 경고 2건

| 항목 | 내용 | 판단 |
|---|---|---|
| PNG 해상도 | 981×1227 로 내보내짐 (SPEC 은 1080×1350) | **실제 이슈 — 아래 4장 참고** |
| 콘솔 에러 1건 | `Failed to load resource: 500` | **정상** — 14번 에러 처리 테스트가 의도적으로 유발한 것 |

---

## 3. 백엔드 API 기능별 결과

`pytest` 8개 전부 통과 (목 기반, 0.16초). 엔드포인트별로는:

| 메서드 | 경로 | 기능 | 결과 |
|---|---|---|---|
| GET | `/api/health` | 헬스체크 | ✅ `{"status":"ok"}` |
| POST | `/api/generate` | 카드뉴스 생성 | ✅ 슬라이드 N장 반환, `meta.topic` 포함 |
| POST | `/api/generate` | 주제 누락 | ✅ 422 (Pydantic 검증) |
| POST | `/api/generate` | 키 없음 | ✅ 500 + 한국어 detail |
| POST | `/api/cardnews` | 저장 | ✅ `id` 부여 후 반환 |
| GET | `/api/cardnews` | 목록 | ✅ 저장 항목 반환 |
| GET | `/api/cardnews/{id}` | 단건 조회 | ✅ 정상 |
| GET | `/api/cardnews/{id}` | 없는 id | ✅ 404 `카드뉴스를 찾을 수 없습니다.` |

구조상 좋은 점: Anthropic 호출이 `services/generator.py` 한 곳에만 있고,
저장소가 `storage/base.py` 인터페이스로 추상화돼 있어 **목 주입이 제품 코드 수정 없이 됩니다.**

---

## 4. 발견된 이슈 — PNG 내보내기 해상도가 SPEC과 다름

**심각도: 중** · 기능은 동작하지만 결과물 규격이 어긋납니다.

SPEC 은 슬라이드를 **4:5, 1080×1350** 으로 내보내도록 정하고 있습니다.
실제로는 화면에 렌더된 카드에 `pixelRatio: 3` 을 곱해 내보내는데,
화면 카드 크기가 CSS 그리드(`repeat(auto-fill, minmax(260px,1fr))`)라 **뷰포트에 따라 변합니다.**

`frontend/src/App.tsx:56`
```ts
const dataUrl = await toPng(node, { pixelRatio: 3, cacheBust: true });
```

### 재현 — 창 크기만 바꿔가며 같은 버튼을 눌렀을 때

| 뷰포트 폭 | 화면 카드 | 내보낸 PNG | SPEC 1080×1350 |
|---|---|---|---|
| 1280 | 327×409 | **981×1227** | 불일치 |
| 1024 | 302×378 | **906×1134** | 불일치 |
| 768 | 334×418 | **1002×1254** | 불일치 |
| 1600 | 327×409 | **981×1227** | 불일치 |

비율(4:5)은 `aspect-ratio: 4/5` 덕분에 항상 맞지만, **절대 크기가 3종으로 갈리고 어느 것도 1080×1350이 아닙니다.**
인스타그램 권장 규격보다 작아 업로드 시 화질 손실이 생깁니다.

### 수정 방향

내보낼 때만 1080 기준으로 스케일을 고정하면 됩니다.

```ts
const scale = 1080 / node.offsetWidth;
const dataUrl = await toPng(node, {
  width: 1080,
  height: 1350,
  style: {
    transform: `scale(${scale})`,
    transformOrigin: "top left",
    width: `${node.offsetWidth}px`,
    height: `${node.offsetHeight}px`,
  },
});
```

> 주의: 이렇게 하면 폰트도 함께 확대되므로, 실제 1080 기준에서 헤드라인이 의도한 크기로 보이는지
> 눈으로 한 번 더 확인해야 합니다. 아직 적용하지 않았습니다.

---

## 5. 카드뉴스 초안 QA — `card-drafts/bags-cardnews.html`

`CARD/2` 가방 이미지 5장으로 만든 7장짜리 카드뉴스입니다.
요구사항은 **가방이 잘리지 않을 것**이었습니다.

기존 `bags-5types.html` 은 `object-fit: cover` + `transform: scale(1.06)` 조합이라 원본을 잘라내고 있었습니다.
새 파일은 `object-fit: contain` + 사진 박스를 원본과 같은 비율(`aspect-ratio: 1200/1440`)로 고정했습니다.
박스 비율 = 원본 비율이므로 **레터박스도 0**입니다.

| 검사 | 결과 |
|---|---|
| 원본 전체 렌더 (렌더 크기 == 박스 크기) | ✅ 7장 모두 레터박스 0 |
| `object-fit` | ✅ 전부 `contain` |
| 확대 크롭 (`transform`) | ✅ 없음 |
| 종횡비 왜곡 | ✅ 원본 0.833 == 렌더 0.833 |
| 카드 밖 텍스트 넘침 | ✅ 0px |
| 내보내기 규격 | ✅ 1080×1350 (`pixelRatio: 2` × 540×675 고정) |

원본 5장 모두 1200×1440 입니다.
이 초안은 카드 크기가 **540×675로 고정**이라 4장의 해상도 이슈가 없습니다 — 앱 쪽과 대조적입니다.

---

## 6. QA 과정에서 잡은 하네스 버그 (제품 아님)

측정 자체가 틀렸던 경우가 있어 기록해 둡니다. 처음 결과를 그대로 믿었으면 오판할 뻔했습니다.

| 버그 | 증상 | 원인 |
|---|---|---|
| 축소 상태 측정 | 여백 42px 를 0 으로 오독할 뻔 | 카드가 `transform: scale(0.44)` 상태라 `getBoundingClientRect` 가 축소 좌표 반환 → 측정 전 `transform: none` 으로 복원 |
| 스크린샷 오염 | 옆 카드까지 같이 찍힘 | 실제 크기(540px)가 그리드 칸(360px)을 넘쳐 겹침 → 촬영 전 1열 레이아웃으로 전환 |
| 목 저장소 주입 실패 | 저장이 500 으로 실패 | `lambda store=InMemoryStore(): store` — **FastAPI 가 오버라이드 콜러블의 기본 인자를 요청 파라미터로 해석**해 본문 파싱이 깨짐 → 인자 없는 콜러블로 수정 |
| curl 한글 본문 깨짐 | `There was an error parsing the body` | Git Bash 에서 `-d '{"topic":"한글"}'` 인라인 전달 시 인코딩 손상 → `--data-binary @file` 로 우회 |

마지막 두 개는 **제품 버그로 오해하기 쉬운 항목**입니다. 실제 API 는 정상입니다.

---

## 7. 재현 방법

```bash
export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:$PATH"

# 1) 목 백엔드 (실제 Claude 호출 없음)
cd backend && ./.venv/Scripts/python.exe <스크래치패드>/qa_server.py

# 2) 프론트 dev 서버
cd frontend && npm run dev -- --port 5173 --strictPort

# 3) QA 실행
PYTHONIOENCODING=utf-8 python qa_frontend.py     # 프론트 기능 14종
PYTHONIOENCODING=utf-8 python qa_export_size.py  # PNG 해상도 뷰포트 의존성
PYTHONIOENCODING=utf-8 python qa_bags.py         # 카드뉴스 초안 크롭 검증
```

> `PYTHONIOENCODING=utf-8` 없으면 Windows 콘솔이 cp949 라 한글/`—` 출력에서 `UnicodeEncodeError` 가 납니다.

---

## 8. 검증하지 못한 영역

정직하게 남겨둡니다. 아래는 **확인되지 않았습니다.**

- **실제 Claude API 응답** — 목으로만 검증. `parse_slides()` 가 실제 모델 출력(코드펜스, 스키마 이탈, 토큰 잘림)을 견디는지는 미검증.
- **Firestore 저장소** — `storage/firestore.py` 는 실행된 적 없음. 인메모리만 검증.
- **실제 배포** — Firebase Hosting 배포와 GitHub Actions 워크플로는 미실행 (시크릿 없음).
- **크로스 브라우저** — Chromium 만. Safari/Firefox 의 `html-to-image` 동작 차이는 미확인.
- **한글 폰트 임베딩** — 로컬에 Pretendard 가 없으면 PNG 내보내기 시 폰트가 대체될 수 있음. 미검증.
- **대량 슬라이드** — 20장 상한에서의 전체 내보내기 성능 미측정.

---

## 9. 결론

핵심 기능 — 생성 · 미리보기 · PNG 내보내기 · 저장 · 이력 조회 — 은 **전부 실제로 동작합니다.**
CLAUDE.md 완료 기준 6가지도 실행으로 확인했습니다 (빌드 성공, pytest 8개 통과, import 정상,
Firebase 설정 유효, README 문서화, 비밀키 미커밋).

조치가 필요한 항목은 **PNG 내보내기 해상도 1건**입니다. 기능은 되지만 SPEC 규격을 못 맞추고 있고,
사용자 창 크기에 따라 결과물이 달라져 재현성이 없습니다.
