// Second Brain GD — service worker.
// Keeps one WebSocket to the local engine (127.0.0.1) and answers its commands: open a tab, capture a tab,
// close the tabs it opened. Also sends pages when you click, use the shortcut or the right-click menu.
// It only reads a page you send yourself or a tab the Brain opened; it never touches your other tabs.
import { base, browserName, canReadTabs, DEFAULT_PORT, grabPage, pictureData, post, settings, t, VERSION } from "./brain.js";

let ws = null;
let retryMs = 2000;
let retryTimer = null;

// ---------------------------------------------------------------- tabs the Brain opened
async function opened() {
  const s = await chrome.storage.session.get(["opened", "last"]);
  return { opened: s.opened || {}, last: s.last || "" };
}

async function saveOpened(o, last) {
  await chrome.storage.session.set({ opened: o, last });
  send({ type: "tabs", opened: o });
}

chrome.tabs.onRemoved.addListener(async (tabId) => {
  const { opened: o, last } = await opened();
  const ref = String(tabId);
  if (o[ref]) {
    delete o[ref];
    await saveOpened(o, last === ref ? Object.keys(o).pop() || "" : last);
  }
});

chrome.tabs.onUpdated.addListener(async (tabId, info, tab) => {
  if (!info.title && !info.url) return;
  const { opened: o, last } = await opened();
  const ref = String(tabId);
  if (o[ref]) {
    o[ref] = { ...o[ref], url: tab.url || o[ref].url, title: tab.title || o[ref].title };
    await saveOpened(o, last);
  }
});

// ---------------------------------------------------------------- link with the engine
function send(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
}

async function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;
  const { port, token } = await settings();
  if (!token) return;
  clearTimeout(retryTimer);
  const sock = new WebSocket(base(port).replace("http", "ws") + "/browser/ws");
  ws = sock;
  sock.onopen = async () => {
    retryMs = 2000;
    sock.send(JSON.stringify({ type: "hello", token, browser: browserName(), version: VERSION,
                               can_read_tabs: await canReadTabs() }));
    const { opened: o } = await opened();
    send({ type: "tabs", opened: o });
    setBadge("", "#2b3c54");
  };
  sock.onmessage = async (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.type === "ping") return send({ type: "pong" });
    if (msg.type === "error" && msg.error === "not paired") {
      await chrome.storage.local.remove("token");
      return;
    }
    if (msg.type === "command") {
      try {
        const data = await run(msg);
        send({ type: "result", id: msg.id, ok: true, data });
      } catch (e) {
        send({ type: "result", id: msg.id, ok: false, error: String(e.message || e) });
      }
    }
  };
  sock.onclose = (ev) => {
    if (ws === sock) ws = null;
    if (ev.code === 4401) {  // unpaired from the app
      chrome.storage.local.remove("token");
      return;
    }
    retryTimer = setTimeout(connect, retryMs);
    retryMs = Math.min(retryMs * 2, 30000);
  };
  sock.onerror = () => {};  // onclose follows and retries
}

// The service worker can be stopped by the browser: an alarm wakes it and reconnects if needed.
chrome.alarms.create("sbgd-link", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => { if (a.name === "sbgd-link") connect(); });
chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(() => { connect(); menus(); });
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === "local" && (changes.token || changes.port)) {
    if (ws) ws.close();
    connect();
  }
});
chrome.permissions.onAdded.addListener(async () => send({ type: "permissions", can_read_tabs: await canReadTabs() }));
chrome.permissions.onRemoved.addListener(async () => send({ type: "permissions", can_read_tabs: await canReadTabs() }));
connect();

// ---------------------------------------------------------------- pairing
// Done here, not in the popup: the browser's permission prompt (asked at the same click) closes the popup, and
// whatever the popup was still doing dies with it.
async function pair(code, port) {
  let res;
  try {
    res = await fetch(base(port) + "/browser/pair", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, browser: browserName() }),
    });
  } catch {
    return pairFailed(t("unreachablePair", port));
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok || !data.token) return pairFailed(data.detail || t("pairingFailedCode", res.status));
  await chrome.storage.session.remove("pairError");
  await chrome.storage.local.set({ port, token: data.token });  // the storage listener connects
  return { ok: true };
}

async function pairFailed(error) {
  await chrome.storage.session.set({ pairError: error });
  return { ok: false, error };
}

// ---------------------------------------------------------------- commands from the Brain
async function run(cmd) {
  if (cmd.action === "open") {
    if (!/^https?:\/\//i.test(cmd.url || "")) throw new Error(t("onlyHttpOpen"));
    const tab = await chrome.tabs.create({ url: cmd.url, active: true });
    const { opened: o } = await opened();
    const ref = String(tab.id);
    o[ref] = { url: cmd.url, title: "" };
    await saveOpened(o, ref);
    return { ref, url: cmd.url };
  }
  if (cmd.action === "close") {
    const { opened: o, last } = await opened();
    const refs = cmd.which === "all" ? Object.keys(o) : (last ? [last] : []);
    if (!refs.length) return { closed: 0, note: "no tab opened by the Brain is still open" };
    await chrome.tabs.remove(refs.map(Number)).catch(() => {});
    return { closed: refs.length };
  }
  if (cmd.action === "capture") {
    let tabId;
    if (cmd.tab === "active") {
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      tabId = tab && tab.id;
    } else {
      const { opened: o, last } = await opened();
      tabId = o[last] ? Number(last) : undefined;
      if (tabId === undefined) throw new Error(t("noOpenedPage"));
    }
    if (tabId === undefined) throw new Error(t("noTab"));
    return capture(tabId, { selectionOnly: !!cmd.selection_only, place: cmd.place || "", byVoice: true });
  }
  if (cmd.action === "read") return readPage(cmd.url);
  throw new Error(`unknown command ${cmd.action}`);
}

// A mission reads a page as the user's browser shows it (pages built by script, flyers, sites that block robots):
// opened in a background tab, scrolled to the end so lazy parts load, its text read, then closed. Nothing is sent
// to the Brain as a capture. Needs the optional “read the pages the Brain opens” permission.
async function readPage(url) {
  if (!/^https?:\/\//i.test(url || "")) throw new Error(t("onlyHttpOpen"));
  if (!(await canReadTabs())) throw new Error(t("mayNotRead"));
  const tab = await chrome.tabs.create({ url, active: false });
  try {
    await waitLoaded(tab.id, 30000);
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: scrollAndRead });
    const page = (res && res.result) || {};
    return { url: page.url || url, title: page.title || "", text: page.text || "" };
  } finally {
    await chrome.tabs.remove(tab.id).catch(() => {});
  }
}

// Runs inside the page: scrolls down step by step (up to ~20 s), waits for content to settle, returns the text.
async function scrollAndRead() {
  const pause = (ms) => new Promise((r) => setTimeout(r, ms));
  await pause(1500);
  let last = -1;
  for (let i = 0; i < 40; i++) {
    window.scrollBy(0, Math.max(400, window.innerHeight * 0.9));
    await pause(450);
    const h = document.documentElement.scrollHeight;
    if (window.innerHeight + window.scrollY >= h - 4) {
      if (h === last) break;
      last = h;
      await pause(900);
    }
  }
  return { url: location.href, title: document.title || "",
           text: document.body ? document.body.innerText.slice(0, 400000) : "" };
}

async function waitLoaded(tabId, ms = 15000) {
  const end = Date.now() + ms;
  for (;;) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete" || Date.now() > end) return tab;
    await new Promise((r) => setTimeout(r, 300));
  }
}

// Reads the tab as the user sees it and sends it. byVoice: the user did not click, so the extension needs the
// optional “read the pages the Brain opens” permission (a click grants access to that one tab by itself).
export async function capture(tabId, { selectionOnly = false, place = "", byVoice = false } = {}) {
  const tab = await waitLoaded(tabId);
  const url = tab.url || "";
  if (!/^https?:\/\//i.test(url)) throw new Error(t("cannotSend"));
  if (byVoice && !(await canReadTabs())) {
    throw new Error(t("mayNotRead"));
  }
  let page;
  try {
    const [res] = await chrome.scripting.executeScript({ target: { tabId }, func: grabPage });
    page = res && res.result;
  } catch (e) {
    page = null;  // a PDF or a protected page: the engine downloads it instead
  }
  if (!page) page = { url, title: tab.title || "", html: "", text: "", selection: "" };
  if (selectionOnly && !page.selection.trim()) throw new Error(t("nothingSelected"));
  const { pictures = [], ...rest } = page;
  const images = [];
  let total = 0;
  for (const p of selectionOnly ? [] : pictures) {  // its main image and figures, as the browser has them
    const data = total < 20 * 1024 * 1024 ? await pictureData(p.url) : "";
    total += data.length;
    images.push({ ...p, data });  // no data: the engine downloads that one itself
  }
  return post("/browser/capture", { ...rest, images, selection_only: selectionOnly, place });
}

// ---------------------------------------------------------------- clicks, shortcut, right-click
function setBadge(text, color, tabId) {
  chrome.action.setBadgeBackgroundColor({ color, ...(tabId ? { tabId } : {}) });
  chrome.action.setBadgeText({ text, ...(tabId ? { tabId } : {}) });
  if (text) setTimeout(() => chrome.action.setBadgeText({ text: "", ...(tabId ? { tabId } : {}) }), 5000);
}

async function sendFromUser(tab, selectionOnly) {
  try {
    const out = await capture(tab.id, { selectionOnly });
    setBadge(out.duplicate ? "=" : "✓", "#3d8b5a", tab.id);
    return { ok: true, ...out };
  } catch (e) {
    setBadge("!", "#b4572e", tab.id);
    return { ok: false, error: String(e.message || e) };
  }
}

// A picture the user chose: an item of its own, that remembers the page it came from.
async function sendImage(tab, srcUrl) {
  try {
    let alt = "", lang = "";
    try {
      const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, args: [srcUrl],
        func: (src) => { const i = [...document.images].find((x) => x.currentSrc === src || x.src === src);
                         return { alt: i ? (i.alt || "") : "", lang: document.documentElement.lang || "" }; } });
      alt = (res && res.result && res.result.alt) || "";
      lang = (res && res.result && res.result.lang) || "";
    } catch { /* a page the extension may not read: the picture goes without its alt text */ }
    const data = await pictureData(srcUrl);
    if (!data && srcUrl.startsWith("data:")) throw new Error(t("pictureUnreadable"));
    const out = await post("/browser/image", { page_url: tab.url || "", page_title: tab.title || "",
                                               image_url: srcUrl.startsWith("data:") ? "" : srcUrl, alt, lang, data });
    setBadge(out.duplicate ? "=" : "✓", "#3d8b5a", tab.id);
    return { ok: true, ...out };
  } catch (e) {
    setBadge("!", "#b4572e", tab.id);
    return { ok: false, error: String(e.message || e) };
  }
}

function menus() {
  chrome.contextMenus.removeAll(() => {
    chrome.contextMenus.create({ id: "sbgd-image", title: t("menuImage"), contexts: ["image"] });
    chrome.contextMenus.create({ id: "sbgd-page", title: t("menuPage"), contexts: ["page"] });  // not on links or pictures: there, the picture item stands alone
    chrome.contextMenus.create({ id: "sbgd-selection", title: t("menuSelection"), contexts: ["selection"] });
  });
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (!tab) return;
  if (info.menuItemId === "sbgd-image" && info.srcUrl) sendImage(tab, info.srcUrl);
  else sendFromUser(tab, info.menuItemId === "sbgd-selection");
});

chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command !== "send-page") return;
  const t = tab || (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0];
  if (t) sendFromUser(t, false);
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  (async () => {
    if (msg.type === "status") {
      const { token, port } = await settings();
      return { paired: !!token, connected: !!(ws && ws.readyState === WebSocket.OPEN), port, canRead: await canReadTabs() };
    }
    if (msg.type === "send") {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      return tab ? sendFromUser(tab, !!msg.selectionOnly) : { ok: false, error: "no tab" };
    }
    if (msg.type === "sendImage") {  // what the right-click menu does (also used by the How-to guide's script)
      const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      return tab ? sendImage(tab, String(msg.srcUrl || "")) : { ok: false, error: "no tab" };
    }
    if (msg.type === "pair") return pair(String(msg.code || ""), Number(msg.port) || DEFAULT_PORT);
    if (msg.type === "pairError") {  // what went wrong while the popup was closed (Edge's permission prompt closes it)
      const { pairError } = await chrome.storage.session.get("pairError");
      await chrome.storage.session.remove("pairError");
      return { error: pairError || "" };
    }
    if (msg.type === "reconnect") {
      if (ws) ws.close();
      await connect();
      return { ok: true };
    }
    return { ok: false };
  })().then(reply);
  return true;  // the answer is asynchronous
});
