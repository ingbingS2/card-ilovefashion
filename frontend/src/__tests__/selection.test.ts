import { expect, it, vi, afterEach } from "vitest";
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
