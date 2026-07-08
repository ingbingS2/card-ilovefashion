/* =========================================================================
   슬라임 카드뉴스 공통 렌더러 + PNG 내보내기  (세련된 Y2K 테마)
   - 각 HTML은 window.META, window.CARDS 를 정의하고 이 파일을 불러온다.
   - 문구 수정은 각 HTML 의 window.CARDS 배열만 고치면 됨.
   ========================================================================= */

const HANDLE = "@your_trend"; // 인스타 핸들 — 원하는 계정명으로 교체

/* ---------- 픽셀 도트 아이콘 (레트로 서포트) ---------- */
const PALETTE = {
  ".": null,
  k: "#3a2f5e", w: "#ffffff", s: "#ffffff", l: "#cbb6ff",
  r: "#ff6b8a", R: "#e23d64", g: "#8be0a0", G: "#57c07a",
  y: "#ffe08a", Y: "#e8b84e", c: "#fbe6c4", C: "#ecc79a",
  b: "#d9a05a", B: "#a8703a", h: "#6b4423", i: "#f6d79a",
  p: "#ffb3c7", P: "#ff7ea6", u: "#9db4ff", U: "#5a6bd6",
};

const ICONS = {
  apple: [
    "....kB......", "....BGg.....", "...RRRRR....", "..RRRRRRR...",
    ".RRsRRRRRR..", ".RssRRRRRR..", ".RRRRRRRRR..", ".RRRRRRRRR..",
    "..RRRRRRR...", "..RRRRRRR...", "...RRRRR....",
  ],
  butter: [
    "...sssss....", "..yyyyyyy...", ".YYYYYYYYY..", ".YYYYYYYYY..",
    ".YYYYYYYYY..", ".YYYYYYYYY..", "..YYYYYYY...",
  ],
  cookie: [
    "..bbbbbb....", ".bbbbbbbb...", "bbhbbbbbhb..", "bbbbbbbbbb..",
    "bbbbhbbbbb..", "bhbbbbbbbb..", "bbbbbbhbbb..", ".bbbbbbbb...",
    "..bbbbbb....",
  ],
  croissant: [
    "...ii.......", "..iibb......", ".iibbbb.....", "iibbbbbb....",
    "iibbbbbbb...", ".iibbbbbbb..", "..iibbbbbb..", "...iibbbbb..",
    "....iiiii...",
  ],
  bread: [
    "...ccccc....", "..cccsccc...", ".ccccccccc..", "ccccccccccc.",
    "ccccccccccc.", "CCCCCCCCCCC.", ".CCCCCCCCC..", "..CCCCCCC...",
  ],
  cake: [
    ".....RR.....", "...ppppp....", "..PPPPPPP...", ".PPPPPPPPP..",
    ".wwwwwwwww..", ".yyyyyyyyy..", ".wwwwwwwww..", ".yyyyyyyyy..",
    ".bbbbbbbbb..",
  ],
  star: [
    "......l......", ".....lwl.....", "....lwwwl....", "..llwwwwwll..",
    "lwwwwwwwwwwl.", "..llwwwwwll..", "....lwwwl....", ".....lwl.....",
    "......l......",
  ],
  heart: [
    ".RR...RR....", "RRRRRRRRR...", "RRsRRRRRR...", "RssRRRRRR...",
    "RRRRRRRRR...", ".RRRRRRR....", "..RRRRR.....", "...RRR......",
    "....R.......",
  ],
  headphone: [
    "..uuuuuuu...", ".u.......u..", "u.........u.", "u.........u.",
    "UU.......UU.", "UU.......UU.", "UU.......UU.", ".U.......U..",
  ],
  eye: [
    "...kkkkk....", ".kkwwwwwkk..", "kwwuuuuwwwk.", "kwuuUUUuuwk.",
    "kwuUkkkUuwk.", "kwuuUUUuuwk.", "kwwuuuuwwwk.", ".kkwwwwwkk..",
    "...kkkkk....",
  ],
};

function pixelSVG(key, size) {
  const g = ICONS[key];
  if (!g) return "";
  const h = g.length;
  const w = Math.max.apply(null, g.map((r) => r.length));
  let rects = "";
  for (let y = 0; y < h; y++) {
    const row = g[y];
    for (let x = 0; x < row.length; x++) {
      const col = PALETTE[row[x]];
      if (col) rects += `<rect x="${x}" y="${y}" width="1.03" height="1.03" fill="${col}"/>`;
    }
  }
  const px = size || 98;
  const hpx = Math.round((px * h) / w);
  return `<svg class="pix" width="${px}" height="${hpx}" viewBox="0 0 ${w} ${h}" shape-rendering="crispEdges" xmlns="http://www.w3.org/2000/svg">${rects}</svg>`;
}

function sparkleSVG(size, color) {
  const c = color || "#ffffff";
  return `<svg width="${size}" height="${size}" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M12 0 C13 8 16 11 24 12 C16 13 13 16 12 24 C11 16 8 13 0 12 C8 11 11 8 12 0 Z" fill="${c}"/></svg>`;
}

/* 루디브리엄 하트 구름(표지 데코) */
function heartSVG(size) {
  const s = size || 58;
  return `<svg width="${s}" height="${Math.round(s * 0.94)}" viewBox="0 0 32 30" xmlns="http://www.w3.org/2000/svg"><path d="M16 29C6 22 1 16 1 9.5 1 4.8 4.8 1 9.5 1 12.4 1 15 2.6 16 5 17 2.6 19.6 1 22.5 1 27.2 1 31 4.8 31 9.5 31 16 26 22 16 29Z" fill="#ffd0e2" stroke="#ffffff" stroke-width="2"/></svg>`;
}

/* html-to-image 로드 */
function loadScript(src) {
  return new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = src; s.onload = res; s.onerror = rej;
    document.head.appendChild(s);
  });
}

/* DotLabel(둥근모) 폰트를 base64 로 임베드 → PNG 에도 픽셀 폰트가 확실히 들어가게 */
async function embedFont() {
  try {
    const url = "https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/DungGeunMo.woff";
    const buf = await (await fetch(url)).arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = "";
    const CH = 0x8000;
    for (let i = 0; i < bytes.length; i += CH) bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    const style = document.createElement("style");
    style.textContent =
      '@font-face{font-family:"DotLabel";src:url(data:font/woff;base64,' + btoa(bin) + ') format("woff");}';
    document.head.appendChild(style);
  } catch (e) {
    console.warn("폰트 임베드 실패(화면 표시는 CDN 폰트 사용):", e);
  }
}

/* ---------- 카드 조립 ---------- */
function decoHTML(cover) {
  const tint = cover ? "#ffffff" : "#cbb6ff";
  return `
    <div class="deco">
      <div class="cloud c1"></div>
      <div class="cloud c2"></div>
      ${cover ? `<div class="heart-cloud">${heartSVG(58)}</div>` : `<div class="cloud c3"></div>`}
      <span class="spark" style="top:56px;left:44px">${sparkleSVG(16, tint)}</span>
      <span class="spark" style="bottom:180px;right:52px">${sparkleSVG(13, tint)}</span>
    </div>`;
}

function orbHTML(icon, size) {
  return `<div class="orb"><span class="hi"></span>${pixelSVG(icon, size)}</div>`;
}

function footHTML(i, total) {
  return `<div class="foot"><span class="handle">${HANDLE}</span><span class="pages">${String(i + 1).padStart(2, "0")} / ${String(total).padStart(2, "0")}</span></div>`;
}

function cardInner(c, i, total) {
  const tag = c.tag ? `<div class="tag">${c.tag}</div>` : "";

  if (c.kind === "cover") {
    return `${decoHTML(true)}
      <div class="stage">
        ${c.kicker ? `<div class="kicker">${c.kicker}</div>` : ""}
        ${orbHTML(c.icon || "cake", 96)}
        <h1 class="title">${c.title}</h1>
        ${c.body ? `<p class="body">${c.body}</p>` : ""}
      </div>${footHTML(i, total)}`;
  }

  if (c.kind === "list") {
    const rows = (c.items || []).map(
      (it, n) => `<div class="row"><div class="no">${n + 1}</div><div class="info"><div class="name">${it.name}</div><div class="meta">${it.meta}</div></div></div>`
    ).join("");
    return `${decoHTML(false)}${tag}
      <div class="stage">
        ${orbHTML(c.icon || "cake", 98)}
        <h2 class="list-title">${c.title}</h2>
        ${c.sub ? `<p class="sub">${c.sub}</p>` : ""}
        <div class="rows">${rows}</div>
      </div>${footHTML(i, total)}`;
  }

  return `${decoHTML(false)}${tag}
    <div class="stage">
      ${orbHTML(c.icon || "star", 98)}
      <h2 class="title">${c.title}</h2>
      ${c.body ? `<p class="body">${c.body}</p>` : ""}
    </div>${footHTML(i, total)}`;
}

function render() {
  const deck = document.getElementById("deck");
  const total = window.CARDS.length;
  window.CARDS.forEach((c, i) => {
    const slot = document.createElement("div");
    slot.className = "slot";
    const card = document.createElement("div");
    card.className = "card " + (c.kind || "content") + " theme-" + (c.theme || "pink");
    card.id = "card-" + i;
    card.innerHTML = cardInner(c, i, total);
    const cap = document.createElement("div");
    cap.className = "cap";
    cap.innerHTML = `<span>${String(i + 1).padStart(2, "0")}장</span>`;
    const btn = document.createElement("button");
    btn.textContent = "이 장 PNG";
    btn.onclick = () => exportCard(i);
    cap.appendChild(btn);
    slot.appendChild(card); slot.appendChild(cap);
    deck.appendChild(slot);
  });
  fitCards();
  window.addEventListener("resize", fitCards);
}

function fitCards() {
  document.querySelectorAll(".slot").forEach((slot) => {
    const card = slot.querySelector(".card");
    const scale = Math.min(1, slot.clientWidth / 540);
    card.style.transform = `scale(${scale})`;
    slot.style.height = 675 * scale + "px";
  });
}

async function exportCard(i) {
  const card = document.getElementById("card-" + i);
  const prev = card.style.transform;
  card.style.transform = "none";
  await document.fonts.ready;
  const dataUrl = await window.htmlToImage.toPng(card, {
    pixelRatio: 2, cacheBust: true, backgroundColor: "#ffffff",
  });
  card.style.transform = prev;
  const a = document.createElement("a");
  a.download = `${window.META.slug}-${String(i + 1).padStart(2, "0")}.png`;
  a.href = dataUrl; a.click();
}

async function exportAll() {
  for (let i = 0; i < window.CARDS.length; i++) {
    // eslint-disable-next-line no-await-in-loop
    await exportCard(i);
    // eslint-disable-next-line no-await-in-loop
    await new Promise((r) => setTimeout(r, 350));
  }
}

(async function init() {
  await loadScript("https://cdn.jsdelivr.net/npm/html-to-image@1.11.13/dist/html-to-image.js");
  await embedFont();
  await (document.fonts ? document.fonts.ready : Promise.resolve());
  render();
  const allBtn = document.getElementById("export-all");
  if (allBtn) allBtn.onclick = exportAll;
})();
