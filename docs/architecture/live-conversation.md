# Live conversation (Loop 7b)

A spoken conversation with the assistant: speech in, speech out, interruptions, and the same tools as the
text chat. Press **F9** (or **Talk live** in the assistant panel) to start, and press F9 again, or say
« merci, c'est tout », to end.

## Path

```
mic (Godot, PCM16 24 kHz) ─▶ ws://127.0.0.1/voice/live ─▶ engine ─▶ wss://api.openai.com/v1/realtime?model=…
speakers (AudioStreamGenerator) ◀─ binary PCM ◀────────── engine ◀── response.output_audio.delta
```

- **The engine holds the key.** Godot only talks to 127.0.0.1, with the local token.
- **Session.** `engine/voice/live.py` opens a Realtime session (`type: realtime`, audio in and out at
  24 kHz).
  - It uses `semantic_vad` with `interrupt_response`, input transcription for the on-screen transcript,
    and `near_field` noise reduction.
  - The voice is the assistant's own (`marin`).
- **Instructions.** The text assistant's `PERSONA`, plus live rules: short spoken sentences, listen when
  interrupted.
- **Tools.** `core.TOOLS` are converted to the flat Realtime format, plus two live-only tools:
  - `focus_project` loads a project's context into the session and opens its card. This is the
    voice-driven project mode, « on travaille sur Atlas ».
  - `end_conversation` handles goodbyes.
- **Tool calls run through `core.run_tool`.** Notes, tasks and interface actions are therefore the same,
  visible and undoable. Interface actions go to Godot as `ui_actions`.
- **Transcripts.** Both sides are saved in today's conversation, with `meta.live`, so the text chat
  remembers them.

## Ownership in Godot

`LiveConversation` (`scripts/voice/live_conversation.gd`) belongs to the app, not to a screen. A theme
change or a trip to the engine room rebuilds the screens, and the conversation continues. It owns its
`LiveStream` (WebSocket), `LivePlayer` (streaming playback on the Voice bus, which ducks the music) and
`VoiceCapture`. The status pill sits above the capture bar and shows listening, speaking or looking up,
plus this conversation's cost and length.

## Interruptions and echo

Godot has no echo cancellation:
- **Speakers (default).** The microphone is paused while the assistant speaks, so it never hears itself.
  F8 interrupts: playback stops, and the engine sends `response.cancel` and
  `conversation.item.truncate` with the milliseconds actually heard.
- **Headphones** (Voice settings). The microphone stays open, and talking over the assistant interrupts it
  (`input_audio_buffer.speech_started`).

## Money

- **Running total.** Every `response.done` carries OpenAI's usage. The engine prices it with the
  Realtime list prices and shows the running total for this conversation only. It stores nothing; the real
  bill is in the Real costs card (Loop 8a).
- **Default model.** `gpt-realtime-2.1-mini` (the owner's choice, 2026-11-03). `gpt-realtime-2.1` is
  selectable. To change it: `PATCH /voice/settings {live_model}`.
- **Limits** (settings):

  | Setting | Default | Effect |
  |---|---|---|
  | `live_session_cap_usd` | 1.00 | Ends the conversation politely when its running cost reaches this |
  | `live_max_minutes` | 20 | Ends the conversation at this length |
  | `live_idle_minutes` | 3 | Ends the conversation after this long with no speech |

## Status (2026-11-03)

Built and tested end to end against a scripted fake Realtime server (`SBGD_VOICE_PROVIDER=fake`). The fake
uses the same events, tool calls, audio and usage as the real server. The test covers a spoken request,
the Today view opening, the answer reaching the panel, streamed voice, the running cost, a theme change
mid-conversation, and the goodbye. Tests pass on Linux and native Windows.

**Real run pending.** The owner's OpenAI project has no speech-to-speech model enabled yet. A real probe
got `model_not_found` for `gpt-realtime-2.1-mini`; the only realtime models listed are
`gpt-realtime-whisper` and `gpt-live-transcribe`. The app says so in plain words. To unblock it, enable
`gpt-realtime-2.1-mini` (and optionally `gpt-realtime-2.1`) for the project on platform.openai.com.
Points to confirm on the first real run:
- that `gpt-realtime-whisper` is accepted as the input transcription model inside a realtime session;
- the turn timing with `semantic_vad`;
- the voice quality.
