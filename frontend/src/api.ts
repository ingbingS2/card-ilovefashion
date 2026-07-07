import type { CardNews, GenerateRequest, GenerateResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export async function generateCardNews(
  req: GenerateRequest,
): Promise<GenerateResponse> {
  const res = await fetch(`${API_BASE}/api/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return handle<GenerateResponse>(res);
}

export async function saveCardNews(cardnews: CardNews): Promise<CardNews> {
  const res = await fetch(`${API_BASE}/api/cardnews`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cardnews),
  });
  return handle<CardNews>(res);
}

export async function listCardNews(): Promise<CardNews[]> {
  const res = await fetch(`${API_BASE}/api/cardnews`);
  return handle<CardNews[]>(res);
}
