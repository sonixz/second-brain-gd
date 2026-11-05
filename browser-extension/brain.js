// Shared helpers (service worker and popup): settings, the engine's address, and calls to it.
export const DEFAULT_PORT = 8765;
export const VERSION = chrome.runtime.getManifest().version;

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
  if (!token) throw new Error("Not paired yet: open this extension and enter the code shown in the app.");
  let res;
  try {
    res = await fetch(base(port) + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
      body: JSON.stringify(body),
    });
  } catch (e) {
    throw new Error(`The Brain is not reachable on 127.0.0.1:${port}. Is the app open?`);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401) await chrome.storage.local.remove("token");
    throw new Error(data.detail || `Error ${res.status}`);
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
  };
}
