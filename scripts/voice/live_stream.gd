class_name LiveStream
extends Node
## WebSocket client to the engine's /voice/live (Loop 7b). Binary frames both ways are
## PCM16 LE mono 24 kHz: the microphone up, the assistant's voice down. JSON messages carry
## transcripts, interface actions and the running cost. The engine holds the API key.

signal session_ready(model: String, voice: String)
signal speech_started
signal user_text(text: String)
signal assistant_delta(text: String)
signal assistant_text(text: String)
signal audio(pcm: PackedByteArray)
signal audio_start
signal audio_done
signal tool(name: String)
signal ui_actions(actions: Array)
signal cost(usd: Variant, minutes: float)
signal ended(reason: String)
signal failed(message: String)
signal closed

var _ws: WebSocketPeer
var _was_open := false
var is_ready := false


func connect_to(port: int, token: String) -> Error:
	_ws = WebSocketPeer.new()
	_ws.handshake_headers = PackedStringArray(["Authorization: Bearer " + token])
	_ws.inbound_buffer_size = 1 << 22
	_ws.outbound_buffer_size = 1 << 22
	_was_open = false
	is_ready = false
	return _ws.connect_to_url("ws://127.0.0.1:%d/voice/live" % port)


func is_open() -> bool:
	return _ws != null and _ws.get_ready_state() == WebSocketPeer.STATE_OPEN


func send_audio(pcm: PackedByteArray) -> void:
	if is_open() and is_ready:
		_ws.send(pcm, WebSocketPeer.WRITE_MODE_BINARY)


func interrupt(audio_end_ms: int) -> void:
	if is_open():
		_ws.send_text(JSON.stringify({"type": "interrupt", "audio_end_ms": audio_end_ms}))


func stop() -> void:
	if is_open():
		_ws.send_text(JSON.stringify({"type": "stop"}))
		_ws.close(1000, "done")


func _process(_delta: float) -> void:
	if _ws == null:
		return
	_ws.poll()
	var state := _ws.get_ready_state()
	if state == WebSocketPeer.STATE_OPEN:
		_was_open = true
		while _ws.get_available_packet_count() > 0:
			var pkt := _ws.get_packet()
			if not _ws.was_string_packet():
				audio.emit(pkt)
				continue
			var parsed: Variant = JSON.parse_string(pkt.get_string_from_utf8())
			if parsed is Dictionary:
				_handle(parsed)
	elif state == WebSocketPeer.STATE_CLOSED:
		var code := _ws.get_close_code()
		_ws = null
		is_ready = false
		if not _was_open:
			failed.emit("Cannot reach the local voice service (code %d)." % code)
		elif code == 4403:
			failed.emit("No OpenAI key configured.")
		closed.emit()


func _handle(msg: Dictionary) -> void:
	match str(msg.get("type", "")):
		"ready":
			is_ready = true
			session_ready.emit(str(msg.get("model", "")), str(msg.get("voice", "")))
		"speech_started":
			speech_started.emit()
		"user_text":
			user_text.emit(str(msg.get("text", "")))
		"assistant_delta":
			assistant_delta.emit(str(msg.get("text", "")))
		"assistant_text":
			assistant_text.emit(str(msg.get("text", "")))
		"audio_start":
			audio_start.emit()
		"audio_done":
			audio_done.emit()
		"tool":
			tool.emit(str(msg.get("name", "")))
		"ui_actions":
			ui_actions.emit(msg.get("actions", []))
		"cost":
			cost.emit(msg.get("usd"), float(msg.get("minutes", 0.0)))
		"ended":
			ended.emit(str(msg.get("reason", "")))
		"error":
			failed.emit(str(msg.get("message", "Live conversation error")))
