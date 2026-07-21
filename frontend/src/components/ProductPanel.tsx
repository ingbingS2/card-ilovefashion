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
                {/^https?:\/\//.test(doc.product_url) && (
                  <a href={doc.product_url} target="_blank" rel="noopener noreferrer">상품 페이지 열기 ↗</a>
                )}
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
