"""The browser extension (Edge, Chrome): pairing, a live command channel, and pages captured from your tabs.

The extension talks only to this engine on 127.0.0.1. It holds its own token, obtained once with a short pairing
code shown in the app; that token can only send pages and answer commands, and the app can revoke it.
"""
