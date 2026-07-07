import { useEffect, useRef, useState } from "react";
import { toPng } from "html-to-image";
import GeneratorForm from "./components/GeneratorForm";
import SlideCard from "./components/SlideCard";
import { generateCardNews, listCardNews, saveCardNews } from "./api";
import type { CardNews, GenerateRequest, Slide } from "./types";

export default function App() {
  const [slides, setSlides] = useState<Slide[]>([]);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<CardNews[]>([]);

  const slideRefs = useRef<Record<number, HTMLDivElement | null>>({});

  async function refreshSaved() {
    try {
      setSaved(await listCardNews());
    } catch {
      /* 목록 조회 실패는 무시(백엔드 미기동 등) */
    }
  }

  useEffect(() => {
    void refreshSaved();
  }, []);

  async function handleGenerate(req: GenerateRequest) {
    setLoading(true);
    setError(null);
    try {
      const res = await generateCardNews(req);
      setSlides(res.slides);
      setTopic(req.topic);
    } catch (e) {
      setError(e instanceof Error ? e.message : "생성에 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave() {
    if (slides.length === 0) return;
    try {
      await saveCardNews({ topic, slides });
      await refreshSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "저장에 실패했습니다.");
    }
  }

  async function exportSlide(slide: Slide) {
    const node = slideRefs.current[slide.index];
    if (!node) return;
    const dataUrl = await toPng(node, { pixelRatio: 3, cacheBust: true });
    const link = document.createElement("a");
    link.download = `cardnews-${slide.index}.png`;
    link.href = dataUrl;
    link.click();
  }

  async function exportAll() {
    for (const slide of slides) {
      // eslint-disable-next-line no-await-in-loop
      await exportSlide(slide);
    }
  }

  function openSaved(item: CardNews) {
    setSlides(item.slides);
    setTopic(item.topic);
  }

  return (
    <div className="app">
      <header className="header">
        <h1>AI 카드뉴스 자동 생성기</h1>
        <p>주제만 입력하면 한국어 10장 카드뉴스를 만들어 드립니다.</p>
      </header>

      <section className="panel">
        <GeneratorForm onSubmit={handleGenerate} loading={loading} />
        {error && <p className="error">⚠️ {error}</p>}
      </section>

      {slides.length > 0 && (
        <section className="result">
          <div className="result-toolbar">
            <h2>{topic}</h2>
            <div className="toolbar-actions">
              <button className="btn" onClick={handleSave}>저장</button>
              <button className="btn" onClick={exportAll}>전체 PNG 내보내기</button>
            </div>
          </div>
          <div className="slide-grid">
            {slides.map((slide) => (
              <div key={slide.index} className="slide-wrap">
                <SlideCard
                  slide={slide}
                  ref={(el) => {
                    slideRefs.current[slide.index] = el;
                  }}
                />
                <button className="btn-ghost" onClick={() => exportSlide(slide)}>
                  {slide.index}장 PNG
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {saved.length > 0 && (
        <section className="saved">
          <h2>저장된 카드뉴스</h2>
          <ul className="saved-list">
            {saved.map((item) => (
              <li key={item.id}>
                <button className="link" onClick={() => openSaved(item)}>
                  {item.topic} · {item.slides.length}장
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
