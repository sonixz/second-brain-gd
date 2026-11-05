import { DEFAULT_PORT, settings, t } from "./brain.js";

// The popup's texts, in the browser's language (French in a French Edge).
for (const el of document.querySelectorAll("[data-i18n]")) el.textContent = t(el.dataset.i18n);
for (const el of document.querySelectorAll("[data-i18n-html]")) el.innerHTML = t(el.dataset.i18nHtml);  // our own messages
document.documentElement.lang = chrome.i18n.getUILanguage();

const $ = (id) => document.getElementById(id);
const show = (id, on) => { $(id).hidden = !on; };

function error(msg) {
  $("error").textContent = msg || "";
  show("error", !!msg);
}

async function status() {
  return chrome.runtime.sendMessage({ type: "status" });
}

async function render() {
  const st = await status();
  show("pair", !st.paired);
  show("ready", st.paired);
  $("dot").className = "dot " + (st.connected ? "on" : st.paired ? "off" : "");
  $("dot").title = st.connected ? t("dotConnected") : st.paired ? t("dotPaired") : t("dotNotPaired");
  if (st.paired) {
    $("state").textContent = st.connected ? t("stateConnected", st.port) : t("stateUnreachable", st.port);
    show("allowBtn", !st.canRead);
  } else {
    const { port } = await settings();
    $("port").value = port || DEFAULT_PORT;
  }
}

$("pairBtn").addEventListener("click", async () => {
  error("");
  const code = $("code").value.trim();
  const port = Number($("port").value) || DEFAULT_PORT;
  if (!code) return error(t("enterCode"));
  // Both start at the click: the permission prompt must come straight from it, and it closes this popup, so the
  // pairing itself runs in the service worker and finishes even if the popup is gone.
  const paired = chrome.runtime.sendMessage({ type: "pair", code, port });
  const asked = $("allow").checked ? chrome.permissions.request({ origins: ["<all_urls>"] }) : Promise.resolve(false);
  $("pairBtn").disabled = true;
  try {
    await asked.catch(() => false);
    const out = await paired;
    if (!out || !out.ok) throw new Error((out && out.error) || t("pairingFailed"));
    await new Promise((r) => setTimeout(r, 600));
    await render();
  } catch (e) {
    error(e.message);
  } finally {
    $("pairBtn").disabled = false;
  }
});

async function sendPage(selectionOnly) {
  error("");
  show("result", false);
  const btn = selectionOnly ? $("sendSel") : $("send");
  btn.disabled = true;
  const label = btn.textContent;
  btn.textContent = t("sending");
  const out = await chrome.runtime.sendMessage({ type: "send", selectionOnly });
  btn.disabled = false;
  btn.textContent = label;
  if (!out.ok) return error(out.error);
  $("result").textContent = out.duplicate ? t("alreadyIn", out.title) : `✓ ${out.receipt || t("added")}`;
  show("result", true);
}

$("send").addEventListener("click", () => sendPage(false));
$("sendSel").addEventListener("click", () => sendPage(true));
$("allowBtn").addEventListener("click", async () => {
  const ok = await chrome.permissions.request({ origins: ["<all_urls>"] }).catch(() => false);
  if (!ok) error(t("withoutPermission"));
  render();
});
$("reconnect").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "reconnect" });
  setTimeout(render, 800);
});
$("unpair").addEventListener("click", async () => {
  await chrome.storage.local.remove("token");
  render();
});

render().then(async () => {  // a pairing that failed after the permission prompt closed the popup
  const st = await status();
  if (!st.paired) {
    const { error: e } = await chrome.runtime.sendMessage({ type: "pairError" });
    if (e) error(e);
  }
});
