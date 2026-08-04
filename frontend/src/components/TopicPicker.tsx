import { useState } from "react";
import { TOPICS, TOPICS_REVIEWED_AT, type Topic } from "../topics";

type Props = {
  value: Topic | null;
  onChange: (topic: Topic | null) => void;
};

/**
 * 대시보드 최상단 주제 선택기.
 * 고른 주제는 결과 폴더명이자 카피 생성의 주제가 되고, 카드 정보 블록의 근거(note)가 된다.
 */
export default function TopicPicker({ value, onChange }: Props) {
  const [openId, setOpenId] = useState<string | null>(null);

  return (
    <section className="topicbar">
      <div className="topic-head">
        <span className="topic-title">이번 카드뉴스 주제</span>
        <span className="topic-guide">
          매체에서 확인한 트렌드입니다. 하나를 고르면 상품 고를 탭을 안내하고, 결과 폴더명도 이 이름이 됩니다.
        </span>
        <span className="topic-stamp">리서치 {TOPICS_REVIEWED_AT}</span>
      </div>

      <div className="topic-list">
        {TOPICS.map((t) => {
          const on = value?.id === t.id;
          return (
            <button
              key={t.id}
              type="button"
              className={"topic-chip" + (on ? " topic-on" : "")}
              aria-pressed={on}
              onClick={() => onChange(on ? null : t)}
              onMouseEnter={() => setOpenId(t.id)}
              onMouseLeave={() => setOpenId(null)}
              onFocus={() => setOpenId(t.id)}
              onBlur={() => setOpenId(null)}
            >
              <span className={"topic-when" + (t.timing === "지금" ? " when-now" : "")}>{t.timing}</span>
              <span className="topic-label">{t.label}</span>
            </button>
          );
        })}
      </div>

      {(() => {
        const shown = TOPICS.find((t) => t.id === (openId ?? value?.id));
        if (!shown) {
          return <p className="topic-empty">주제를 고르면 왜 지금 이게 보이는지, 어느 탭에서 상품을 고르면 되는지 알려드려요.</p>;
        }
        return (
          <div className="topic-detail">
            <p className="topic-note">{shown.note}</p>
            <p className="topic-where">
              <b>고를 곳</b> {shown.where.join(" · ")} 탭
            </p>
            <p className="topic-src">
              <b>근거</b>{" "}
              {shown.sources.map((s, i) => (
                <span key={s.url}>
                  {i > 0 && " · "}
                  <a href={s.url} target="_blank" rel="noreferrer noopener">{s.name}</a>
                </span>
              ))}
            </p>
          </div>
        );
      })()}
    </section>
  );
}
