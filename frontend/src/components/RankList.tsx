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
      {doc?.items?.map((item) => (
        <RankCard key={selKey(item)} item={item} checked={!!selected[selKey(item)]}
          onToggle={onToggle} onOpen={onOpen} />
      ))}
    </section>
  );
}
