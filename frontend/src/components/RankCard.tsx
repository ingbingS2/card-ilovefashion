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
