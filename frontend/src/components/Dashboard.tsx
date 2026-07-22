import { useState } from "react";
import { CM29_TABS, MUSINSA_TABS } from "../firestore";
import type { RankItem } from "../rankTypes";
import { buildSelectionPayload, selKey, sendSelection, toggleSelection } from "../selection";
import ProductPanel from "./ProductPanel";
import RankList from "./RankList";

export default function Dashboard() {
  const [cat, setCat] = useState("001");
  const [cmCat, setCmCat] = useState("best");
  const [selected, setSelected] = useState<Record<string, RankItem>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [panelOpen, setPanelOpen] = useState(false);
  const [open, setOpen] = useState<{ mall: string; productId: string } | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const count = Object.keys(selected).length;
  const label = MUSINSA_TABS.find((t) => t.code === cat)?.label ?? "";
  const cmLabel = CM29_TABS.find((t) => t.code === cmCat)?.label ?? "";

  const onToggle = (item: RankItem) => setSelected((m) => toggleSelection(m, item));
  const onOpen = (item: RankItem) => setOpen({ mall: item.mall, productId: item.product_id });

  async function submit() {
    setSending(true);
    setNotice(null);
    try {
      await sendSelection(buildSelectionPayload(selected, notes));
      setNotice(`로컬 파이프라인으로 전송했습니다 (${count}개)`);
    } catch (e) {
      setNotice(e instanceof Error ? e.message : "전송에 실패했습니다");
    } finally {
      setSending(false);
    }
  }

  // rank 순으로 정렬된 선택 상품 (코멘트 패널 표시용)
  const selectedList = Object.values(selected).sort((a, b) => a.rank - b.rank);
  const withNote = selectedList.filter((it) => (notes[selKey(it)] || "").trim()).length;

  return (
    <div className="dashboard">
      <div className="dash-tabs">
        <span className="tabs-label">무신사</span>
        {MUSINSA_TABS.map((t) => (
          <button key={t.code} className={"chip" + (t.code === cat ? " chip-on" : "")}
            onClick={() => setCat(t.code)}>{t.label}</button>
        ))}
      </div>
      <div className="dash-tabs">
        <span className="tabs-label">29CM</span>
        {CM29_TABS.map((t) => (
          <button key={t.code} className={"chip cm-chip" + (t.code === cmCat ? " chip-on" : "")}
            onClick={() => setCmCat(t.code)}>{t.label}</button>
        ))}
      </div>
      <div className="dash-grid">
        <RankList title={`무신사 ${label}`} docId={`musinsa_${cat}`}
          selected={selected} onToggle={onToggle} onOpen={onOpen} />
        <RankList title={`29CM ${cmLabel}`} docId={cmCat === "best" ? "cm29_best" : `cm29_${cmCat}`}
          selected={selected} onToggle={onToggle} onOpen={onOpen} />
      </div>
      {open && <ProductPanel mall={open.mall} productId={open.productId} onClose={() => setOpen(null)} />}

      {/* 내 코멘트 패널: 고른 상품마다 한 줄 의견을 적는다 (카드 본문의 핵심) */}
      {count > 0 && panelOpen && (
        <div className="note-panel">
          <div className="note-head">
            <strong>내 코멘트</strong>
            <span className="note-guide">상품마다 왜 골랐는지·어떤 상황에 좋은지 한 줄로 적으면 카드 문구가 돼요</span>
            <button className="note-close" onClick={() => setPanelOpen(false)} aria-label="접기">✕</button>
          </div>
          <ul className="note-list">
            {selectedList.map((it) => {
              const k = selKey(it);
              return (
                <li key={k} className="note-row">
                  {it.thumbnail ? <img src={it.thumbnail} alt="" /> : <div className="note-thumb" />}
                  <div className="note-meta">
                    <span className="note-brand">{it.brand}</span>
                    <span className="note-name">{it.name}</span>
                  </div>
                  <input
                    className="note-input"
                    value={notes[k] || ""}
                    maxLength={60}
                    placeholder="예: 장마철 출근할 때 딱, 색이 실물이 더 예뻐요"
                    onChange={(e) => setNotes((n) => ({ ...n, [k]: e.target.value }))}
                  />
                  <button className="note-remove" onClick={() => onToggle(it)} aria-label="제외">✕</button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {count > 0 && (
        <div className="sel-bar">
          <span className="sel-info">선택 {count}개 · 내 코멘트 {withNote}개</span>
          <button className="sel-comment" onClick={() => setPanelOpen((v) => !v)}>
            {panelOpen ? "코멘트 접기" : "내 의견 적기"}
          </button>
          <button className="sel-btn" onClick={submit} disabled={sending}>
            {sending ? "전송 중…" : "카드뉴스 만들기"}
          </button>
          <button className="sel-clear" onClick={() => { setSelected({}); setNotes({}); setNotice(null); }}>비우기</button>
          {notice && <span className="sel-notice">{notice}</span>}
        </div>
      )}
    </div>
  );
}
