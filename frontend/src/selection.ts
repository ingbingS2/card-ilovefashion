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

// notes: selKey → 사용자가 상품별로 적은 한 줄 코멘트(에디터 의견). 카드 본문의 핵심이 된다.
export function buildSelectionPayload(
  map: Record<string, RankItem>,
  notes: Record<string, string> = {},
) {
  return {
    createdAt: new Date().toISOString(),
    items: Object.values(map)
      .sort((a, b) => a.rank - b.rank)
      .map((item) => ({ ...item, note: (notes[selKey(item)] || "").trim() })),
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
