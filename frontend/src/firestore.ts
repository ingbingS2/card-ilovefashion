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
