# Second Brain GD — browser extension (Edge, Chrome)

Connects your browser to your local Second Brain GD: send the page you read (or a selection) in one click, and let
the assistant open, add and close tabs by voice. It talks only to the engine on `127.0.0.1`.

**Install (once):** `edge://extensions` or `chrome://extensions` (Chrome 116+) → Developer mode → **Load unpacked**
→ choose this folder. After updating the project, click **Reload** on the extension's card.

**Pair:** in the app, *Captures → Send from browser… → Pair a browser*; type the code in the extension's popup.

**Use:** the icon → *Send this page*; `Alt+Shift+B`; right-click a selection → *Send the selection to the Brain*;
by voice (F8): “open the first one”, “add it”, “close it” (or in French: « ouvre la première », « ajoute-la », « ferme-la »).

Full guide, permissions, security and troubleshooting: `public/docs.html#extension`.

| File | Role |
|---|---|
| `manifest.json` | Manifest V3: permissions, shortcut, icons |
| `background.js` | Service worker: WebSocket to the engine, commands (open, capture, close), clicks and menus |
| `brain.js` | Shared helpers: settings, calls to the engine, the page reader injected in a tab |
| `popup.html/.js/.css` | Pairing, status, send page / selection, permission |
