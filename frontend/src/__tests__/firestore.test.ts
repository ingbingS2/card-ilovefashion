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
