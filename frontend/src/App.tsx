import { useState } from "react";
import Dashboard from "./components/Dashboard";
import Generator from "./Generator";

export default function App() {
  const [view, setView] = useState<"dash" | "gen">("dash");
  return (
    <div className="app">
      <header className="header">
        <h1>패션 랭킹 대시보드</h1>
        <p>무신사 · 29CM 통합 비교 — 매시간 자동 갱신</p>
        <nav className="app-tabs">
          <button className={"chip" + (view === "dash" ? " chip-on" : "")} onClick={() => setView("dash")}>랭킹 비교</button>
          <button className={"chip" + (view === "gen" ? " chip-on" : "")} onClick={() => setView("gen")}>카드뉴스 생성기</button>
        </nav>
      </header>
      {view === "dash" ? <Dashboard /> : <Generator />}
    </div>
  );
}
