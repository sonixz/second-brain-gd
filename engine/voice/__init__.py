"""Voice capture: per-user API keys and realtime transcription.

Each user brings their own OpenAI key (entered once during onboarding). The key
is stored by the engine in the OS credential store and never reaches Godot,
logs, events or SQLite. Godot streams microphone audio to the engine over a
local WebSocket; the engine relays it to the OpenAI Realtime transcription API.
"""
