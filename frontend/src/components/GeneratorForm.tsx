import { useState } from "react";
import type { GenerateRequest } from "../types";

interface Props {
  onSubmit: (req: GenerateRequest) => void;
  loading: boolean;
}

export default function GeneratorForm({ onSubmit, loading }: Props) {
  const [topic, setTopic] = useState("");
  const [target, setTarget] = useState("");
  const [goal, setGoal] = useState("");
  const [tone, setTone] = useState("");
  const [cta, setCta] = useState("");
  const [slideCount, setSlideCount] = useState(10);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim()) return;
    onSubmit({
      topic: topic.trim(),
      target: target.trim() || undefined,
      goal: goal.trim() || undefined,
      tone: tone.trim() || undefined,
      cta: cta.trim() || undefined,
      slide_count: slideCount,
    });
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      <label className="field">
        <span>주제 *</span>
        <input
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          placeholder="예: AI 카드뉴스 자동화"
          required
        />
      </label>
      <div className="field-row">
        <label className="field">
          <span>타깃</span>
          <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="예: 1인 크리에이터" />
        </label>
        <label className="field">
          <span>목표</span>
          <input value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="예: 저장 유도" />
        </label>
      </div>
      <div className="field-row">
        <label className="field">
          <span>톤</span>
          <input value={tone} onChange={(e) => setTone(e.target.value)} placeholder="예: 실용적이고 세련된" />
        </label>
        <label className="field">
          <span>CTA</span>
          <input value={cta} onChange={(e) => setCta(e.target.value)} placeholder="예: 댓글에 카드뉴스" />
        </label>
      </div>
      <label className="field">
        <span>슬라이드 수: {slideCount}장</span>
        <input
          type="range"
          min={1}
          max={20}
          value={slideCount}
          onChange={(e) => setSlideCount(Number(e.target.value))}
        />
      </label>
      <button className="btn-primary" type="submit" disabled={loading}>
        {loading ? "생성 중…" : "카드뉴스 생성"}
      </button>
    </form>
  );
}
