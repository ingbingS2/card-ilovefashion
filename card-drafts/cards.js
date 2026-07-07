/* =========================================================================
   슬라임 카드뉴스 공통 렌더러 + PNG 내보내기
   - 각 HTML은 window.META, window.CARDS 를 정의하고 이 파일을 불러온다.
   - 카드는 window.CARDS 배열로부터 생성된다(문구 수정은 그 배열만 고치면 됨).
   ========================================================================= */

const HANDLE = "@your_trend"; // 인스타 핸들 — 원하는 계정명으로 교체

/* html-to-image 로드 (PNG 내보내기용) */
function loadScript(src) {
  return new Promise((res, rej) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = res;
    s.onerror = rej;
    document.head.appendChild(s);
  });
}

/* DungGeunMo 폰트를 base64 로 임베드 → PNG 에도 픽셀 폰트가 확실히 들어가게 */
async function embedFont() {
  try {
    const url =
      "https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/DungGeunMo.woff";
    const buf = await (await fetch(url)).arrayBuffer();
    const bytes = new Uint8Array(buf);
    let bin = "";
    const CH = 0x8000;
    for (let i = 0; i < bytes.length; i += CH) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + CH));
    }
    const b64 = btoa(bin);
    const style = document.createElement("style");
    style.textContent =
      '@font-face{font-family:"DungGeunMo";src:url(data:font/woff;base64,' +
      b64 +
      ') format("woff");}';
    document.head.appendChild(style);
  } catch (e) {
    console.warn("폰트 임베드 실패(화면 표시는 CDN 폰트 사용):", e);
  }
}

/* ---- 카드 HTML 조립 ---- */
function decoHTML() {
  return `
    <div class="deco">
      <div class="clock"></div>
      <div class="cloud c1"></div>
      <div class="cloud c2"></div>
      <div class="block b1"></div>
      <div class="block b2"></div>
      <div class="block b3"></div>
      <div class="floor"></div>
    </div>`;
}

function footHTML(i, total) {
  return `<div class="foot"><span class="handle">${HANDLE}</span><span class="pages">${String(
    i + 1
  ).padStart(2, "0")} / ${String(total).padStart(2, "0")}</span></div>`;
}

function styleVars(c) {
  const v = [];
  if (c.blob) v.push(`--blob:${c.blob}`);
  if (c.titleShadow) v.push(`--title-shadow:${c.titleShadow}`);
  return v.length ? ` style="${v.join(";")}"` : "";
}

function cardInner(c, i, total) {
  const tag = c.tag ? `<div class="tag">${c.tag}</div>` : "";

  if (c.kind === "cover") {
    return `
      ${decoHTML()}
      <div class="stage">
        ${c.kicker ? `<div class="kicker">${c.kicker}</div>` : ""}
        <div class="slime"${styleVars(c)}>
          <span class="shine"></span>
          <span class="food">${c.emoji || "🍮"}</span>
          <span class="drip d1"></span><span class="drip d2"></span>
        </div>
        <h1 class="title">${c.title}</h1>
        ${c.body ? `<p class="body">${c.body}</p>` : ""}
      </div>
      ${footHTML(i, total)}`;
  }

  if (c.kind === "list") {
    const rows = (c.items || [])
      .map(
        (it, n) => `
        <div class="row">
          <div class="no">${n + 1}</div>
          <div class="info">
            <div class="name">${it.name}</div>
            <div class="meta">${it.meta}</div>
          </div>
        </div>`
      )
      .join("");
    return `
      ${decoHTML()}
      ${tag}
      <div class="stage">
        <div class="list-emoji">${c.emoji || "🍡"}</div>
        <h2 class="list-title">${c.title}</h2>
        ${c.sub ? `<p class="sub">${c.sub}</p>` : ""}
        <div class="rows">${rows}</div>
      </div>
      ${footHTML(i, total)}`;
  }

  // content / cta 공통
  return `
    ${decoHTML()}
    ${tag}
    <div class="stage">
      <div class="slime"${styleVars(c)}>
        <span class="shine"></span>
        <span class="food">${c.emoji || "🍮"}</span>
        <span class="drip d1"></span><span class="drip d2"></span>
      </div>
      <h2 class="title">${c.title}</h2>
      ${c.body ? `<p class="body">${c.body}</p>` : ""}
    </div>
    ${footHTML(i, total)}`;
}

function render() {
  const deck = document.getElementById("deck");
  const total = window.CARDS.length;
  window.CARDS.forEach((c, i) => {
    const slot = document.createElement("div");
    slot.className = "slot";
    const card = document.createElement("div");
    card.className = "card " + (c.kind || "content");
    card.id = "card-" + i;
    card.innerHTML = cardInner(c, i, total);
    const cap = document.createElement("div");
    cap.className = "cap";
    cap.innerHTML = `<span>${String(i + 1).padStart(2, "0")}장</span>`;
    const btn = document.createElement("button");
    btn.textContent = "이 장 PNG";
    btn.onclick = () => exportCard(i);
    cap.appendChild(btn);
    slot.appendChild(card);
    slot.appendChild(cap);
    deck.appendChild(slot);
  });
  fitCards();
  window.addEventListener("resize", fitCards);
}

/* 화면에서는 슬롯 폭에 맞게 축소(카드 원본은 540 유지 → PNG는 1080x1350) */
function fitCards() {
  document.querySelectorAll(".slot").forEach((slot) => {
    const card = slot.querySelector(".card");
    const avail = slot.clientWidth;
    const scale = Math.min(1, avail / 540);
    card.style.transform = `scale(${scale})`;
    // 축소된 높이만큼 슬롯 높이 보정
    slot.style.height = 675 * scale + "px";
  });
}

async function exportCard(i) {
  const card = document.getElementById("card-" + i);
  const prev = card.style.transform;
  card.style.transform = "none"; // 원본 540x675 로 캡처
  await document.fonts.ready;
  const dataUrl = await window.htmlToImage.toPng(card, {
    pixelRatio: 2, // 540x675 * 2 = 1080x1350
    cacheBust: true,
    backgroundColor: "#eaf8ff",
  });
  card.style.transform = prev;
  const a = document.createElement("a");
  a.download = `${window.META.slug}-${String(i + 1).padStart(2, "0")}.png`;
  a.href = dataUrl;
  a.click();
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
  await loadScript(
    "https://cdn.jsdelivr.net/npm/html-to-image@1.11.13/dist/html-to-image.js"
  );
  await embedFont();
  await (document.fonts ? document.fonts.ready : Promise.resolve());
  render();
  const allBtn = document.getElementById("export-all");
  if (allBtn) allBtn.onclick = exportAll;
})();
