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
// topic: 대시보드 상단에서 고른 주제. 결과 폴더명·카피 주제가 된다.
//   안 보내면 파이프라인이 "여름 무드" 같은 계절 기본값으로 떨어진다 (폴더명이 매번 겹치는 원인).
export function buildSelectionPayload(
  map: Record<string, RankItem>,
  notes: Record<string, string> = {},
  topic?: { label: string; note: string } | null,
) {
  return {
    createdAt: new Date().toISOString(),
    topic: topic?.label?.trim() || null,
    topicNote: topic?.note?.trim() || null,
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
