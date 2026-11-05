// Shared helpers (service worker and popup): settings, the engine's address, and calls to it.
export const DEFAULT_PORT = 8765;
export const VERSION = chrome.runtime.getManifest().version;

// A message in the browser's language (_locales/en, _locales/fr): t("stateConnected", port).
export function t(key, ...subs) {
  return chrome.i18n.getMessage(key, subs.map(String)) || key;
}

export async function settings() {
  const s = await chrome.storage.local.get(["port", "token"]);
  return { port: Number(s.port) || DEFAULT_PORT, token: s.token || "" };
}

export function base(port) {
  return `http://127.0.0.1:${port}`;
}

export function browserName() {
  const ua = navigator.userAgent;
  const edge = ua.match(/Edg\/(\d+)/);
  if (edge) return `Edge ${edge[1]}`;
  const chrome = ua.match(/Chrome\/(\d+)/);
  return chrome ? `Chrome ${chrome[1]}` : "Chromium";
}

export async function canReadTabs() {
  return chrome.permissions.contains({ origins: ["<all_urls>"] });
}

// POST to the engine with the browser token. Returns the JSON, or throws an Error with the engine's reason.
export async function post(path, body) {
  const { port, token } = await settings();
  if (!token) throw new Error(t("notPairedYet"));
  let res;
  try {
    res = await fetch(base(port) + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
  } catch (e) {
    throw new Error(t("unreachable", port));
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) await chrome.storage.local.remove("token");
    throw new Error(data.detail || t("errorStatus", res.status));
  }
  return data;
}

// Runs inside the page: what the user sees, after login, scripts and checks.
export function grabPage() {
  const sel = String(window.getSelection ? window.getSelection() : "").slice(0, 20000);
  if (document.contentType === "application/pdf") {  // the browser's PDF viewer: the engine downloads the file
    return { url: location.href, title: document.title || "", html: "", text: "", selection: "" };
  }
  return {
    url: location.href,
    title: document.title || "",
    html: document.documentElement ? document.documentElement.outerHTML.slice(0, 3000000) : "",
    text: document.body ? document.body.innerText.slice(0, 1000000) : "",
    selection: sel,
    lang: document.documentElement.lang || "",
    pictures: pickPictures(),
  };

  // The few pictures worth keeping, best first (the page's main image first): its main image and its figures,
  // as displayed (real sizes). Never logos, icons, avatars, ads, menus or tiny pictures. Same rules as the engine
  // (engine/sources/images.py). Defined inside grabPage: the browser runs this function alone in the page.
  function pickPictures() {
    const NOISE = /logo|icon|sprite|avatar|badge|emoji|spinner|loader|pixel|tracking|beacon|\/ads?\/|advert|banner|gravatar|placeholder|blank\.|spacer|share|social|button|arrow|1x1/i;
    const INFO = /diagram|chart|graph|figure|fig\.|table|map|plan|schema|infographic|comparison|curve|schéma|graphique|tableau|carte|courbe|comparatif|données|data/i;
    const meta = document.querySelector('meta[property="og:image"], meta[name="twitter:image"]');
    const hero = meta ? new URL(meta.content, location.href).href.split("?")[0] : "";
    const seen = new Set();
    const out = [];
    [...document.images].forEach((img, order) => {
      const url = img.currentSrc || img.src || "";
      const key = url.split("?")[0];
      if (!/^https?:/.test(url) || seen.has(key)) return;
      const w = img.naturalWidth, h = img.naturalHeight, shown = img.getBoundingClientRect();
      if (Math.min(w, h) < 160 || w * h < 200 * 150 || shown.width < 120 || shown.height < 90) return;
      if (NOISE.test(key) || /\.(svg|ico)$/i.test(key) || img.closest("header, nav, footer, aside, form")) return;
      const fig = img.closest("figure");
      const caption = (fig && fig.querySelector("figcaption") ? fig.querySelector("figcaption").innerText : "").trim().slice(0, 400);
      const alt = (img.alt || "").trim().slice(0, 300);
      const isHero = !!hero && key === hero;
      let score = (isHero ? 3 : 0) + (caption ? 3 : fig ? 1 : 0) + (img.closest("article, main") ? 2 : 0)
        + (INFO.test(alt + " " + caption) ? 2 : 0) + (alt.length > 12 ? 1 : 0) + (w * h >= 400 * 300 ? 1 : 0);
      if (score < 1) return;
      seen.add(key);
      out.push({ url, alt, caption, hero: isHero, score, order });
    });
    out.sort((a, b) => (b.hero - a.hero) || (b.score - a.score) || (a.order - b.order));
    return out.slice(0, 5).map(({ url, alt, caption }) => ({ url, alt, caption }));
  }
}

// A picture's bytes as base64 (the engine keeps the picture as the browser had it). "" when it cannot be read
// here (another site without the permission): the engine then downloads it itself.
export async function pictureData(url, maxBytes = 8 * 1024 * 1024) {
  try {
    const res = await fetch(url, { credentials: "include" });
    if (!res.ok) return "";
    const buf = new Uint8Array(await res.arrayBuffer());
    if (buf.length > maxBytes) return "";
    let bin = "";
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000));
    return btoa(bin);
  } catch {
    return "";
  }
}
