# Phase 2: 랭킹 대시보드 정식판 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 React 앱을 무신사·29CM 통합 비교 대시보드로 개편 — 카테고리 탭, 2열 비교 리스트, 상품 상세 패널(후기 10개·순위 이력), 상품 선택→로컬 파이프라인 연동 버튼, 기존 카드뉴스 생성기는 별도 탭 유지.

**Architecture:** Firestore 접근은 `rankings.html`에서 검증된 REST + 웹 API 키 방식을 타입스크립트 모듈로 정리(파이어베이스 SDK 의존성 없음). 화면은 상단 앱 탭(대시보드/생성기) + 대시보드 내 카테고리 칩 → 좌 무신사 · 우 29CM 베스트 2열. 상세는 오버레이 패널. 선택 상태는 App 레벨 state, "카드뉴스 만들기"는 `http://localhost:8787/api/selections` POST(Phase 3 로컬 앱)이며 미기동 시 한국어 안내.

**Tech Stack:** React 18 + Vite 5 + TS (기존), vitest(신규, 순수 모듈 테스트), Firestore REST.

## Global Constraints

- 모든 사용자 노출 UI 텍스트 한국어 — CLAUDE.md.
- 셸은 Bash 툴, npm 명령 전 `export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:/c/Users/yepdo/AppData/Local/Programs/Python/Python312:/c/Users/yepdo/AppData/Local/Programs/Python/Python312/Scripts:$PATH"` — CLAUDE.md.
- vitest 는 네트워크 금지 — fetch 는 목/픽스처. `npm run build`(tsc --noEmit 포함) 통과가 각 태스크 완료 조건.
- Firestore 웹 API 키는 공개키(규칙으로 보호)이며 이미 저장소에 커밋돼 있음(`frontend/public/rankings.html`) — 새 모듈에서도 상수로 사용, 비밀키 아님.
- 데이터 형태(크롤러 산출, 변경 금지): `rankings/{mall}_{cat}` = `{updatedAt, items[]}`, item = `{mall, product_id, rank, brand, name, price, original_price, discount_rate, review_score, review_count, thumbnail, product_url, category_code, category_name}`; `products/{mall}_{pid}` = item 필드 + `{reviews[]: {score,text,date,likes}, history[]: {t,rank,price,review_score,review_count}, updatedAt}`.
- 커밋 트레일러 2줄: `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` / `Claude-Session: https://claude.ai/code/session_01PgitEtAu5cwDBPf5BsKcLr`

## File Structure

```
frontend/src/
  firestore.ts            # [신규] REST 클라이언트: fv 디코더 + fetchRanking/fetchProduct
  rankTypes.ts            # [신규] RankItem/ProductDoc/RankingDoc 타입
  selection.ts            # [신규] 선택 로직 (토글·목록·전송 payload 빌드) — 순수 함수
  App.tsx                 # [개조] 앱 탭 셸 (대시보드 | 카드뉴스 생성기)
  Generator.tsx           # [신규] 기존 App.tsx 본문을 이동한 생성기 화면
  components/
    Dashboard.tsx         # [신규] 카테고리 칩 + 2열 비교 + 선택 바
    RankList.tsx          # [신규] 한 몰의 랭킹 리스트 (열 1개)
    RankCard.tsx          # [신규] 상품 한 줄 (체크박스 포함)
    ProductPanel.tsx      # [신규] 상세 오버레이 (후기·이력·링크)
  styles.css              # [확장] 대시보드 스타일 추가
frontend/src/__tests__/
  firestore.test.ts       # [신규] fv 디코더/URL 빌드
  selection.test.ts       # [신규] 선택 로직
frontend/package.json     # [수정] vitest 추가, test 스크립트
```

## 공통 타입 (`rankTypes.ts` — Task 1 에서 생성, 전 태스크 공통)

```ts
export interface RankItem {
  mall: "musinsa" | "cm29";
  product_id: string;
  rank: number;
  brand: string;
  name: string;
  price: number | null;
  original_price: number | null;
  discount_rate: number | null;
  review_score: number | null;
  review_count: number | null;
  thumbnail: string | null;
  product_url: string;
  category_code: string | null;
  category_name: string | null;
}

export interface RankingDoc { updatedAt: string; items: RankItem[]; }

export interface Review { score: number | null; text: string; date: string | null; likes: number | null; }
export interface HistoryPoint { t: string; rank: number | null; price: number | null; review_score: number | null; review_count: number | null; }
export interface ProductDoc extends RankItem { reviews: Review[]; history: HistoryPoint[]; updatedAt: string; }
```

---

### Task 1: Firestore REST 클라이언트 + vitest 기반

**Files:**
- Create: `frontend/src/rankTypes.ts` (위 공통 타입 그대로)
- Create: `frontend/src/firestore.ts`
- Create: `frontend/src/__tests__/firestore.test.ts`
- Modify: `frontend/package.json` (devDependencies 에 `"vitest": "^2.1.9"`, scripts 에 `"test": "vitest run"`)

**Interfaces:**
- Produces:
  - `fv(v: unknown): unknown` — Firestore REST 값 디코더 (rankings.html 의 JS 판을 TS 로)
  - `decodeDoc(doc: { fields?: Record<string, unknown> }): Record<string, unknown>`
  - `fetchRanking(docId: string): Promise<RankingDoc>` — `rankings/{docId}` GET+디코드
  - `fetchProduct(mall: string, productId: string): Promise<ProductDoc>` — `products/{mall}_{productId}`
  - `MUSINSA_TABS: {code: string; label: string}[]` — 001 상의/002 아우터/003 바지/100 원피스·스커트/004 가방/103 신발

- [ ] **Step 1: vitest 설치**

```bash
export PATH="/c/Users/yepdo/tools/node-v22.23.1-win-x64:$PATH"
cd "C:/Users/yepdo/OneDrive/Desktop/fashion-cardnews/frontend" && npm install -D vitest@^2.1.9
```

- [ ] **Step 2: 실패하는 테스트 작성**

`frontend/src/__tests__/firestore.test.ts`:

```ts
import { describe, expect, it, vi, afterEach } from "vitest";
import { decodeDoc, fetchRanking, fv } from "../firestore";

afterEach(() => vi.unstubAllGlobals());

describe("fv", () => {
  it("스칼라 타입 해제", () => {
    expect(fv({ stringValue: "가방" })).toBe("가방");
    expect(fv({ integerValue: "42" })).toBe(42);
    expect(fv({ doubleValue: 4.8 })).toBe(4.8);
    expect(fv({ booleanValue: true })).toBe(true);
    expect(fv({ nullValue: null })).toBeNull();
  });
  it("map/array 재귀 해제", () => {
    expect(
      fv({ arrayValue: { values: [{ mapValue: { fields: { rank: { integerValue: "1" } } } }] } }),
    ).toEqual([{ rank: 1 }]);
    expect(fv({ arrayValue: {} })).toEqual([]);
  });
});

describe("decodeDoc", () => {
  it("fields 전체 디코드", () => {
    expect(
      decodeDoc({ fields: { updatedAt: { stringValue: "t" }, items: { arrayValue: { values: [] } } } }),
    ).toEqual({ updatedAt: "t", items: [] });
  });
  it("fields 없으면 빈 객체", () => {
    expect(decodeDoc({})).toEqual({});
  });
});

describe("fetchRanking", () => {
  it("rankings 문서 URL 호출 + 디코드", async () => {
    const body = {
      fields: {
        updatedAt: { stringValue: "2026-07-21T00:00:00+00:00" },
        items: { arrayValue: { values: [{ mapValue: { fields: {
          mall: { stringValue: "musinsa" }, product_id: { stringValue: "1" },
          rank: { integerValue: "1" }, brand: { stringValue: "b" }, name: { stringValue: "n" },
          price: { integerValue: "1000" }, product_url: { stringValue: "u" },
        } } } ] } },
      },
    };
    const mock = vi.fn().mockResolvedValue({ ok: true, json: async () => body });
    vi.stubGlobal("fetch", mock);
    const doc = await fetchRanking("musinsa_001");
    expect(mock.mock.calls[0][0]).toContain("/documents/rankings/musinsa_001?key=");
    expect(doc.updatedAt).toBe("2026-07-21T00:00:00+00:00");
    expect(doc.items[0]).toMatchObject({ mall: "musinsa", rank: 1, price: 1000 });
  });
  it("HTTP 오류 시 한국어 에러", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));
    await expect(fetchRanking("musinsa_001")).rejects.toThrow("랭킹을 불러오지 못했습니다");
  });
});
```

- [ ] **Step 3: 실패 확인**

Run: `cd frontend && npm test`
Expected: FAIL — `Cannot find module '../firestore'` 계열

- [ ] **Step 4: 구현**

`frontend/src/firestore.ts`:

```ts
// Firestore REST 읽기 전용 클라이언트 (공개 웹 API 키 — 규칙으로 보호됨)
import type { ProductDoc, RankingDoc } from "./rankTypes";

const PROJECT = "fashion-cardnews";
const KEY = "AIzaSyBZIp-NLD8rw6asKSAwIOH-4I4hg9ecALo";
const BASE = `https://firestore.googleapis.com/v1/projects/${PROJECT}/databases/(default)/documents`;

export const MUSINSA_TABS = [
  { code: "001", label: "상의" },
  { code: "002", label: "아우터" },
  { code: "003", label: "바지" },
  { code: "100", label: "원피스/스커트" },
  { code: "004", label: "가방" },
  { code: "103", label: "신발" },
];

type RestValue = Record<string, unknown>;

export function fv(v: unknown): unknown {
  if (v == null || typeof v !== "object") return null;
  const o = v as RestValue;
  if ("stringValue" in o) return o.stringValue;
  if ("integerValue" in o) return Number(o.integerValue);
  if ("doubleValue" in o) return o.doubleValue;
  if ("booleanValue" in o) return o.booleanValue;
  if ("nullValue" in o) return null;
  if ("mapValue" in o) {
    const fields = (o.mapValue as RestValue)?.fields as Record<string, unknown> | undefined;
    return Object.fromEntries(Object.entries(fields ?? {}).map(([k, x]) => [k, fv(x)]));
  }
  if ("arrayValue" in o) {
    const values = (o.arrayValue as RestValue)?.values as unknown[] | undefined;
    return (values ?? []).map(fv);
  }
  return null;
}

export function decodeDoc(doc: { fields?: Record<string, unknown> }): Record<string, unknown> {
  return Object.fromEntries(Object.entries(doc.fields ?? {}).map(([k, x]) => [k, fv(x)]));
}

async function getDoc(path: string, errMsg: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/${path}?key=${KEY}`);
  if (!res.ok) throw new Error(`${errMsg} (HTTP ${res.status})`);
  return decodeDoc(await res.json());
}

export async function fetchRanking(docId: string): Promise<RankingDoc> {
  return (await getDoc(`rankings/${docId}`, "랭킹을 불러오지 못했습니다")) as unknown as RankingDoc;
}

export async function fetchProduct(mall: string, productId: string): Promise<ProductDoc> {
  return (await getDoc(`products/${mall}_${productId}`, "상품 정보를 불러오지 못했습니다")) as unknown as ProductDoc;
}
```

`frontend/src/rankTypes.ts` 는 계획 상단 "공통 타입" 블록 그대로.

`frontend/package.json` scripts 에 `"test": "vitest run"` 추가.

- [ ] **Step 5: 통과 + 빌드 + 커밋**

```bash
cd frontend && npm test && npm run build
git add src/rankTypes.ts src/firestore.ts src/__tests__/firestore.test.ts package.json package-lock.json
git commit -m "feat(frontend): Firestore REST 클라이언트 + vitest 기반"
```

Expected: 테스트 6개 통과, 빌드 성공.

---

### Task 2: 선택 로직 모듈 (`selection.ts`)

**Files:**
- Create: `frontend/src/selection.ts`
- Test: `frontend/src/__tests__/selection.test.ts`

**Interfaces:**
- Produces:
  - `selKey(item: RankItem): string` — `"{mall}_{product_id}"`
  - `toggleSelection(map: Record<string, RankItem>, item: RankItem): Record<string, RankItem>` — 불변 토글
  - `buildSelectionPayload(map: Record<string, RankItem>): { createdAt: string; items: RankItem[] }` — rank 순 정렬
  - `sendSelection(payload): Promise<void>` — `POST http://localhost:8787/api/selections` (JSON). 연결 실패 시 `Error("로컬 파이프라인 앱이 꺼져 있습니다. PC에서 앱을 켠 뒤 다시 눌러 주세요.")`

- [ ] **Step 1: 실패하는 테스트 작성**

`frontend/src/__tests__/selection.test.ts`:

```ts
import { describe, expect, it, vi, afterEach } from "vitest";
import { buildSelectionPayload, selKey, sendSelection, toggleSelection } from "../selection";
import type { RankItem } from "../rankTypes";

const item = (pid: string, rank = 1): RankItem => ({
  mall: "musinsa", product_id: pid, rank, brand: "b", name: "n", price: 1,
  original_price: null, discount_rate: null, review_score: null, review_count: null,
  thumbnail: null, product_url: "u", category_code: null, category_name: null,
});

afterEach(() => vi.unstubAllGlobals());

it("selKey", () => expect(selKey(item("7"))).toBe("musinsa_7"));

it("toggleSelection 추가/제거 (불변)", () => {
  const m0 = {};
  const m1 = toggleSelection(m0, item("a"));
  expect(Object.keys(m1)).toEqual(["musinsa_a"]);
  expect(m0).toEqual({});
  const m2 = toggleSelection(m1, item("a"));
  expect(m2).toEqual({});
});

it("buildSelectionPayload rank 순 정렬", () => {
  const m = toggleSelection(toggleSelection({}, item("x", 9)), item("y", 2));
  const p = buildSelectionPayload(m);
  expect(p.items.map((i) => i.product_id)).toEqual(["y", "x"]);
  expect(typeof p.createdAt).toBe("string");
});

it("sendSelection: POST 성공", async () => {
  const mock = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", mock);
  await sendSelection(buildSelectionPayload(toggleSelection({}, item("a"))));
  const [url, init] = mock.mock.calls[0];
  expect(url).toBe("http://localhost:8787/api/selections");
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body).items).toHaveLength(1);
});

it("sendSelection: 연결 실패 시 한국어 안내", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fail")));
  await expect(sendSelection(buildSelectionPayload({}))).rejects.toThrow("로컬 파이프라인 앱이 꺼져");
});
```

- [ ] **Step 2: 실패 확인** — `npm test` → `Cannot find module '../selection'`

- [ ] **Step 3: 구현**

`frontend/src/selection.ts`:

```ts
// 상품 선택 상태 + Phase 3 로컬 파이프라인 연동 (POST localhost:8787)
import type { RankItem } from "./rankTypes";

const PIPELINE_URL = "http://localhost:8787/api/selections";

export const selKey = (item: RankItem): string => `${item.mall}_${item.product_id}`;

export function toggleSelection(
  map: Record<string, RankItem>, item: RankItem,
): Record<string, RankItem> {
  const next = { ...map };
  const key = selKey(item);
  if (next[key]) delete next[key];
  else next[key] = item;
  return next;
}

export function buildSelectionPayload(map: Record<string, RankItem>) {
  return {
    createdAt: new Date().toISOString(),
    items: Object.values(map).sort((a, b) => a.rank - b.rank),
  };
}

export async function sendSelection(payload: ReturnType<typeof buildSelectionPayload>) {
  let res: Response;
  try {
    res = await fetch(PIPELINE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("로컬 파이프라인 앱이 꺼져 있습니다. PC에서 앱을 켠 뒤 다시 눌러 주세요.");
  }
  if (!res.ok) throw new Error(`전송 실패 (HTTP ${res.status})`);
}
```

- [ ] **Step 4: 통과 + 커밋**

```bash
cd frontend && npm test && npm run build
git add src/selection.ts src/__tests__/selection.test.ts
git commit -m "feat(frontend): 상품 선택 로직 + 로컬 파이프라인 연동"
```

Expected: 테스트 11개 통과.

---

### Task 3: 대시보드 화면 (2열 비교 + 상세 패널 + 선택 바)

**Files:**
- Create: `frontend/src/components/RankCard.tsx`, `RankList.tsx`, `ProductPanel.tsx`, `Dashboard.tsx`
- Modify: `frontend/src/styles.css` (스타일 추가)

**Interfaces:**
- Consumes: Task 1 `fetchRanking/fetchProduct/MUSINSA_TABS` + 타입, Task 2 선택 모듈 전부.
- Produces: `<Dashboard />` (props 없음) — Task 4 의 App 셸이 마운트.

**컴포넌트 계약:**
- `RankCard({ item, checked, onToggle, onOpen })` — 순위(1~3 강조)·썸네일·브랜드·상품명·가격(정가 취소선)·할인율·⭐평점·후기수·체크박스. 카드 클릭=상세(onOpen), 체크박스 클릭=선택(onToggle, 이벤트 전파 차단).
- `RankList({ title, docId, selected, onToggle, onOpen })` — fetchRanking 후 RankCard 목록. 로딩("불러오는 중…")/오류(한국어) 상태 표시. docId 변경 시 재조회.
- `ProductPanel({ mall, productId, onClose })` — fetchProduct 후: 상단 상품 요약(썸네일·브랜드명·가격·원본 링크 버튼 "상품 페이지 열기"), 순위 변동(history 마지막 2개 비교 → "▲3 / ▼2 / – 변동 없음 / 신규"), 후기 목록(reviews: ⭐score, text, likes "도움 N"). 후기 없으면 "수집된 후기가 없습니다". 배경 클릭/✕ 로 닫기.
- `Dashboard()` — 상태: `cat`(기본 "001"), `selected: Record<string, RankItem>`, `openProduct: {mall, productId} | null`, `sending/notice`. 레이아웃: 카테고리 칩(MUSINSA_TABS) → 2열 그리드(좌 `musinsa_{cat}` "무신사 {label}", 우 `cm29_best` "29CM 베스트"; 모바일 1열) → 하단 고정 선택 바(선택 N개 · "카드뉴스 만들기" 버튼 · "비우기"). 버튼: `sendSelection(buildSelectionPayload(selected))` → 성공 시 "로컬 파이프라인으로 전송했습니다 (N개)" / 실패 시 에러 메시지 표시(alert 아닌 바 내 텍스트).

- [ ] **Step 1: 4개 컴포넌트 구현** (계약대로. 스타일 클래스는 Step 2 에서 추가하는 이름 사용: `dash-tabs`,`chip`,`chip-on`,`dash-grid`,`ranklist`,`rankcard`,`rc-rank`,`rc-top`,`rc-thumb`,`rc-info`,`rc-brand`,`rc-name`,`rc-meta`,`rc-price`,`rc-strike`,`rc-sale`,`rc-review`,`rc-check`,`sel-bar`,`sel-info`,`sel-btn`,`sel-clear`,`sel-notice`,`panel-back`,`panel`,`panel-head`,`panel-close`,`panel-summary`,`panel-delta`,`review-item`,`review-score`,`review-text`,`review-likes`)

핵심 코드 골격 (그대로 구현):

`RankCard.tsx`:

```tsx
import type { RankItem } from "../rankTypes";

interface Props {
  item: RankItem;
  checked: boolean;
  onToggle: (item: RankItem) => void;
  onOpen: (item: RankItem) => void;
}

const won = (n: number | null) => (n == null ? "" : n.toLocaleString("ko-KR") + "원");

export default function RankCard({ item, checked, onToggle, onOpen }: Props) {
  return (
    <div className="rankcard" onClick={() => onOpen(item)}>
      <input
        type="checkbox"
        className="rc-check"
        checked={checked}
        onClick={(e) => e.stopPropagation()}
        onChange={() => onToggle(item)}
        aria-label="카드뉴스 후보로 선택"
      />
      <div className={"rc-rank" + (item.rank <= 3 ? " rc-top" : "")}>{item.rank}</div>
      {item.thumbnail ? (
        <img className="rc-thumb" loading="lazy" src={item.thumbnail} alt="" />
      ) : (
        <div className="rc-thumb" />
      )}
      <div className="rc-info">
        <div className="rc-brand">{item.brand}</div>
        <div className="rc-name">{item.name}</div>
        <div className="rc-meta">
          {item.original_price != null && item.original_price !== item.price && (
            <span className="rc-strike">{won(item.original_price)}</span>
          )}
          <span className="rc-price">{won(item.price)}</span>
          {item.discount_rate ? <span className="rc-sale">{item.discount_rate}%</span> : null}
          {item.review_count ? (
            <span className="rc-review">⭐ {item.review_score ?? "-"} · 후기 {item.review_count.toLocaleString()}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
```

`RankList.tsx`:

```tsx
import { useEffect, useState } from "react";
import { fetchRanking } from "../firestore";
import type { RankingDoc, RankItem } from "../rankTypes";
import RankCard from "./RankCard";
import { selKey } from "../selection";

interface Props {
  title: string;
  docId: string;
  selected: Record<string, RankItem>;
  onToggle: (item: RankItem) => void;
  onOpen: (item: RankItem) => void;
}

export default function RankList({ title, docId, selected, onToggle, onOpen }: Props) {
  const [doc, setDoc] = useState<RankingDoc | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setDoc(null);
    setError(null);
    fetchRanking(docId)
      .then((d) => alive && setDoc(d))
      .catch((e) => alive && setError(e instanceof Error ? e.message : "불러오지 못했습니다"));
    return () => { alive = false; };
  }, [docId]);

  return (
    <section className="ranklist">
      <h2>{title}</h2>
      {doc?.updatedAt && (
        <p className="rl-updated">
          {new Date(doc.updatedAt).toLocaleString("ko-KR", { month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" })} 기준
        </p>
      )}
      {error && <p className="rl-error">⚠️ {error}</p>}
      {!doc && !error && <p className="rl-loading">불러오는 중…</p>}
      {doc?.items.map((item) => (
        <RankCard key={selKey(item)} item={item} checked={!!selected[selKey(item)]}
          onToggle={onToggle} onOpen={onOpen} />
      ))}
    </section>
  );
}
```

`ProductPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { fetchProduct } from "../firestore";
import type { ProductDoc } from "../rankTypes";

interface Props { mall: string; productId: string; onClose: () => void; }

function rankDelta(doc: ProductDoc): string {
  const h = doc.history ?? [];
  if (h.length < 2) return "신규 진입";
  const prev = h[h.length - 2].rank, cur = h[h.length - 1].rank;
  if (prev == null || cur == null) return "–";
  if (prev === cur) return "– 변동 없음";
  return prev > cur ? `▲ ${prev - cur} 상승` : `▼ ${cur - prev} 하락`;
}

export default function ProductPanel({ mall, productId, onClose }: Props) {
  const [doc, setDoc] = useState<ProductDoc | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchProduct(mall, productId).then(setDoc).catch((e) =>
      setError(e instanceof Error ? e.message : "불러오지 못했습니다"));
  }, [mall, productId]);

  return (
    <div className="panel-back" onClick={onClose}>
      <div className="panel" onClick={(e) => e.stopPropagation()}>
        <div className="panel-head">
          <h3>상품 상세</h3>
          <button className="panel-close" onClick={onClose} aria-label="닫기">✕</button>
        </div>
        {error && <p className="rl-error">⚠️ {error}</p>}
        {!doc && !error && <p className="rl-loading">불러오는 중…</p>}
        {doc && (
          <>
            <div className="panel-summary">
              {doc.thumbnail && <img src={doc.thumbnail} alt="" />}
              <div>
                <div className="rc-brand">{doc.brand}</div>
                <div className="rc-name">{doc.name}</div>
                <div className="rc-meta">
                  <span className="rc-price">{doc.price?.toLocaleString("ko-KR")}원</span>
                  {doc.review_count ? (
                    <span className="rc-review">⭐ {doc.review_score ?? "-"} · 후기 {doc.review_count.toLocaleString()}</span>
                  ) : null}
                </div>
                <div className="panel-delta">순위 {doc.rank}위 · {rankDelta(doc)}</div>
                <a href={doc.product_url} target="_blank" rel="noopener noreferrer">상품 페이지 열기 ↗</a>
              </div>
            </div>
            <h4>후기</h4>
            {(doc.reviews ?? []).length === 0 && <p className="rl-loading">수집된 후기가 없습니다</p>}
            {(doc.reviews ?? []).map((r, i) => (
              <div className="review-item" key={i}>
                <span className="review-score">{r.score != null ? "⭐".repeat(Math.round(r.score)) : ""}</span>
                <p className="review-text">{r.text}</p>
                {r.likes ? <span className="review-likes">도움 {r.likes}</span> : null}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
```

`Dashboard.tsx`:

```tsx
import { useState } from "react";
import { MUSINSA_TABS } from "../firestore";
import type { RankItem } from "../rankTypes";
import { buildSelectionPayload, sendSelection, toggleSelection } from "../selection";
import ProductPanel from "./ProductPanel";
import RankList from "./RankList";

export default function Dashboard() {
  const [cat, setCat] = useState("001");
  const [selected, setSelected] = useState<Record<string, RankItem>>({});
  const [open, setOpen] = useState<{ mall: string; productId: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const count = Object.keys(selected).length;
  const label = MUSINSA_TABS.find((t) => t.code === cat)?.label ?? "";

  const onToggle = (item: RankItem) => setSelected((m) => toggleSelection(m, item));
  const onOpen = (item: RankItem) => setOpen({ mall: item.mall, productId: item.product_id });

  async function submit() {
    setSending(true);
    setNotice(null);
    try {
      await sendSelection(buildSelectionPayload(selected));
      setNotice(`로컬 파이프라인으로 전송했습니다 (${count}개)`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "전송에 실패했습니다");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="dashboard">
      <div className="dash-tabs">
        {MUSINSA_TABS.map((t) => (
          <button key={t.code} className={"chip" + (t.code === cat ? " chip-on" : "")}
            onClick={() => setCat(t.code)}>{t.label}</button>
        ))}
      </div>
      <div className="dash-grid">
        <RankList title={`무신사 ${label}`} docId={`musinsa_${cat}`}
          selected={selected} onToggle={onToggle} onOpen={onOpen} />
        <RankList title="29CM 베스트" docId="cm29_best"
          selected={selected} onToggle={onToggle} onOpen={onOpen} />
      </div>
      {open && <ProductPanel mall={open.mall} productId={open.productId} onClose={() => setOpen(null)} />}
      {count > 0 && (
        <div className="sel-bar">
          <span className="sel-info">선택 {count}개</span>
          <button className="sel-btn" onClick={submit} disabled={sending}>
            {sending ? "전송 중…" : "카드뉴스 만들기"}
          </button>
          <button className="sel-clear" onClick={() => { setSelected({}); setNotice(null); }}>비우기</button>
          {notice && <span className="sel-notice">{notice}</span>}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: styles.css 에 대시보드 스타일 추가** (기존 스타일 유지, 아래 추가 — 톤은 기존 앱과 동일 계열, 악센트 #ff3366)

```css
/* ── 랭킹 대시보드 ── */
.dash-tabs { display:flex; gap:6px; flex-wrap:wrap; margin-bottom:14px; }
.chip { font-size:13px; font-weight:600; padding:8px 13px; border-radius:99px;
        border:1px solid #e3e3e6; background:#fff; cursor:pointer; }
.chip-on { background:#101012; color:#fff; border-color:#101012; }
.dash-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; align-items:start; }
@media (max-width: 860px) { .dash-grid { grid-template-columns:1fr; } }
.ranklist h2 { font-size:16px; margin:0 0 2px; }
.rl-updated { font-size:11.5px; color:#8b8b90; margin:0 0 10px; }
.rl-loading, .rl-error { color:#8b8b90; font-size:13px; padding:20px 0; }
.rankcard { display:flex; gap:10px; align-items:center; background:#fff; border:1px solid #ececef;
            border-radius:10px; padding:8px 10px; margin-bottom:6px; cursor:pointer; }
.rankcard:hover { border-color:#cfcfd4; }
.rc-check { width:16px; height:16px; flex:none; accent-color:#ff3366; cursor:pointer; }
.rc-rank { width:24px; text-align:center; font-weight:800; font-size:14px; flex:none;
           font-variant-numeric:tabular-nums; }
.rc-top { color:#ff3366; }
.rc-thumb { width:46px; height:55px; border-radius:7px; object-fit:cover; background:#f4f3f1; flex:none; }
.rc-info { min-width:0; flex:1; }
.rc-brand { font-size:10.5px; font-weight:700; color:#8b8b90; }
.rc-name { font-size:12.5px; font-weight:600; line-height:1.3; overflow:hidden; display:-webkit-box;
           -webkit-line-clamp:2; -webkit-box-orient:vertical; word-break:keep-all; }
.rc-meta { display:flex; gap:6px; align-items:center; margin-top:3px; font-size:11.5px; flex-wrap:wrap; }
.rc-strike { color:#b6b3ac; text-decoration:line-through; }
.rc-price { font-weight:800; }
.rc-sale { color:#ff3366; font-weight:800; }
.rc-review { color:#8b8b90; }
.sel-bar { position:fixed; left:0; right:0; bottom:0; display:flex; gap:10px; align-items:center;
           background:#101012; color:#fff; padding:12px 18px; z-index:30; flex-wrap:wrap; }
.sel-info { font-weight:700; font-size:14px; }
.sel-btn { background:#ff3366; color:#fff; border:none; border-radius:8px; padding:10px 16px;
           font-weight:800; font-size:14px; cursor:pointer; }
.sel-btn:disabled { opacity:.6; }
.sel-clear { background:transparent; color:#bbb; border:1px solid #444; border-radius:8px;
             padding:9px 12px; font-size:13px; cursor:pointer; }
.sel-notice { font-size:12.5px; color:#ffd7e1; }
.panel-back { position:fixed; inset:0; background:rgba(0,0,0,.45); z-index:40;
              display:flex; justify-content:flex-end; }
.panel { width:min(440px, 100%); height:100%; background:#fff; overflow-y:auto; padding:18px; }
.panel-head { display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; }
.panel-head h3 { margin:0; font-size:16px; }
.panel-close { background:none; border:none; font-size:18px; cursor:pointer; }
.panel-summary { display:flex; gap:12px; margin-bottom:14px; }
.panel-summary img { width:110px; height:132px; border-radius:10px; object-fit:cover; background:#f4f3f1; }
.panel-delta { font-size:12.5px; color:#55555a; margin:6px 0; }
.panel h4 { margin:14px 0 8px; font-size:14px; }
.review-item { border-top:1px solid #f0f0f2; padding:10px 2px; }
.review-score { font-size:11px; }
.review-text { font-size:13px; line-height:1.6; margin:4px 0; word-break:keep-all; }
.review-likes { font-size:11px; color:#8b8b90; }
```

- [ ] **Step 3: 빌드 확인 + 커밋**

```bash
cd frontend && npm test && npm run build
git add src/components/RankCard.tsx src/components/RankList.tsx src/components/ProductPanel.tsx src/components/Dashboard.tsx src/styles.css
git commit -m "feat(frontend): 대시보드 — 2열 비교·상세 패널·선택 바"
```

Expected: 빌드 성공 (tsc 오류 0).

---

### Task 4: 앱 셸 개편 (대시보드 메인 + 생성기 탭 이동)

**Files:**
- Create: `frontend/src/Generator.tsx` (기존 App.tsx 본문 이동)
- Modify: `frontend/src/App.tsx` (탭 셸로 교체), `frontend/src/styles.css` (앱 탭 스타일), `frontend/index.html` (title → "패션 랭킹 대시보드")

**Interfaces:**
- Consumes: Task 3 `<Dashboard />`.
- Produces: App = 헤더("패션 랭킹 대시보드" / 부제 "무신사 · 29CM 통합 비교 — 매시간 자동 갱신") + 탭 2개("랭킹 비교" 기본 | "카드뉴스 생성기") 전환.

- [ ] **Step 1: 기존 App.tsx 내용을 `Generator.tsx` 로 이동** — 컴포넌트명 `Generator` 로 바꾸는 것 외 로직 무변경 (import 경로 유지: `./components/...`, `./api`, `./types`).

- [ ] **Step 2: App.tsx 를 탭 셸로 교체**

```tsx
import { useState } from "react";
import Dashboard from "./components/Dashboard";
import Generator from "./Generator";

export default function App() {
  const [view, setView] = useState<"dash" | "gen">("dash");
  return (
    <div className="app">
      <header className="header">
        <h1>패션 랭킹 대시보드</h1>
        <p>무신사 · 29CM 통합 비교 — 매시간 자동 갱신</p>
        <nav className="app-tabs">
          <button className={"chip" + (view === "dash" ? " chip-on" : "")} onClick={() => setView("dash")}>랭킹 비교</button>
          <button className={"chip" + (view === "gen" ? " chip-on" : "")} onClick={() => setView("gen")}>카드뉴스 생성기</button>
        </nav>
      </header>
      {view === "dash" ? <Dashboard /> : <Generator />}
    </div>
  );
}
```

styles.css 에 `.app-tabs { display:flex; gap:6px; justify-content:center; margin-top:10px; }` 추가. `index.html` 의 `<title>` 을 `패션 랭킹 대시보드`로.

주의: Generator.tsx 는 자체 `<div className="app"><header>...` 래퍼를 갖고 있던 기존 구조라면 **내부 래퍼/헤더를 제거**하고 본문(section 들)만 남긴다 — 헤더 중복 방지.

- [ ] **Step 3: 검증 + 커밋**

```bash
cd frontend && npm test && npm run build
git add src/App.tsx src/Generator.tsx src/styles.css index.html
git commit -m "feat(frontend): 앱 셸 개편 — 대시보드 메인, 생성기 탭 분리"
```

---

### Task 5: 운영 검증 — 실데이터 렌더 확인 + 배포

운영 실행 태스크 (실데이터·실배포).

- [ ] **Step 1: 로컬 빌드 산출물을 Playwright 로 실데이터 렌더 확인**

`npm run build` 후, crawler venv 파이썬으로:

```python
# 검증 항목: (파일이 아니라 vite preview 로 서빙 — file:// 에선 모듈 스크립트 차단됨)
# 1) 두 열에 각 50개 카드 렌더  2) 카테고리 칩 클릭 시 좌측 열 갱신
# 3) 카드 클릭 → 상세 패널에 후기 텍스트 표시  4) 체크 2개 → 선택 바 "선택 2개"
# 5) "카드뉴스 만들기" 클릭 → 로컬 앱 미기동 안내 문구 표시
```

`npx vite preview --port 4173` 백그라운드 기동 후 `http://localhost:4173` 대상 위 5개를 Playwright 스크립트로 확인, 스크린샷 저장. (스크립트는 스크래치패드에 작성 — 커밋 안 함)

- [ ] **Step 2: 커밋·푸시 → deploy.yml 자동 배포 → 라이브 확인**

```bash
git push
```

배포 워크플로 완료 후 `https://fashion-cardnews.web.app` 이 새 대시보드로 열리는지 확인 (HTTP 200 + Playwright 로 카드 렌더 확인). 기존 `/rankings.html` 은 맛보기 페이지로 그대로 유지.

- [ ] **Step 3: 완료 기준 대조** — 스펙 Phase 2 "배포된 사이트에서 실데이터 조회 가능": 라이브 URL 에서 2열 비교·상세·선택 UI 동작 확인 기록.

---

## Self-Review 결과

- **스펙 커버리지**: §4 조회 사이트 요구 — 카테고리 탭(T3), 2열 나란히 비교(T3), 순위·썸네일·브랜드·상품명·가격/할인·평점·후기수(T3 RankCard), 순위 변동(T3 ProductPanel: 이력 기반 — 목록 단 ▲▼는 크롤러에 prev_rank 필드 추가 후 후속), 상세 패널 후기 10개+원본 링크(T3), 체크박스+"선택 N개 카드뉴스 만들기"(T2+T3), 로컬 앱 미기동 안내(T2), 진행 상태 표시는 Phase 3 에서 로컬 앱과 함께, 기존 생성기 별도 탭(T4), 한국어(전체). 완료 기준 "배포된 사이트에서 실데이터 조회"(T5).
- **플레이스홀더**: 코드 블록 전부 실코드. Task 5 의 Playwright 스크립트는 검증 항목 5개를 명시(운영 실행 절차).
- **타입 일관성**: rankTypes 공통 블록 ↔ firestore.ts 반환 캐스팅 ↔ selection.ts ↔ 컴포넌트 props 일치. selKey 가 RankList key 와 선택 map 키로 동일 사용.
