import { base, browserName, DEFAULT_PORT, settings } from "./brain.js";

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
  $("dot").title = st.connected ? "Connected to the Brain" : st.paired ? "Paired, not connected (is the app open?)" : "Not paired";
  if (st.paired) {
    $("state").textContent = st.connected ? `Connected to your Brain (port ${st.port}).`
      : `Paired, but the Brain is not reachable on port ${st.port}. Open the app; it reconnects by itself.`;
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
  if (!code) return error("Enter the code shown in the app.");
  // The permission prompt must come straight from the click, before anything else is awaited.
  const asked = $("allow").checked ? chrome.permissions.request({ origins: ["<all_urls>"] }) : Promise.resolve(false);
  $("pairBtn").disabled = true;
  try {
    await asked.catch(() => false);
    let res;
    try {
      res = await fetch(base(port) + "/browser/pair", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code, browser: browserName() }),
      });
    } catch {
      throw new Error(`The Brain is not reachable on 127.0.0.1:${port}. Is the app open, and is the port right?`);
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.token) throw new Error(data.detail || `Pairing failed (${res.status})`);
    await chrome.storage.local.set({ port, token: data.token });
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
  btn.textContent = "Sending…";
  const out = await chrome.runtime.sendMessage({ type: "send", selectionOnly });
  btn.disabled = false;
  btn.textContent = label;
  if (!out.ok) return error(out.error);
  $("result").textContent = out.duplicate ? `Already in your Brain: « ${out.title} »` : `✓ ${out.receipt || "Added."}`;
  show("result", true);
}

$("send").addEventListener("click", () => sendPage(false));
$("sendSel").addEventListener("click", () => sendPage(true));
$("allowBtn").addEventListener("click", async () => {
  const ok = await chrome.permissions.request({ origins: ["<all_urls>"] }).catch(() => false);
  if (!ok) error("Without it, voice commands cannot add the pages the Brain opens; clicking Send still works.");
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

render();
