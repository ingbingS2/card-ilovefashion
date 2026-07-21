import { useState } from "react";
import { CM29_TABS, MUSINSA_TABS } from "../firestore";
import type { RankItem } from "../rankTypes";
import { buildSelectionPayload, sendSelection, toggleSelection } from "../selection";
import ProductPanel from "./ProductPanel";
import RankList from "./RankList";

export default function Dashboard() {
  const [cat, setCat] = useState("001");
  const [cmCat, setCmCat] = useState("best");
  const [selected, setSelected] = useState<Record<string, RankItem>>({});
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
