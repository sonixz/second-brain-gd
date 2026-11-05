class_name VoiceStream
extends Node
## WebSocket client to the engine's /voice/stream. The engine holds the API key
## and talks to OpenAI; Godot only ever talks to 127.0.0.1 with the local token.

signal session_ready(model: String, provider: String)
signal delta(text: String)
signal final(text: String)
signal failed(message: String)
signal closed

var _ws: WebSocketPeer
var _open := false
var _was_open := false


func connect_to(port: int, token: String) -> Error:
	_ws = WebSocketPeer.new()
	_ws.handshake_headers = PackedStringArray(["Authorization: Bearer " + token])
	_ws.inbound_buffer_size = 1 << 20
	_ws.outbound_buffer_size = 1 << 22
	_open = false
	_was_open = false
	return _ws.connect_to_url("ws://127.0.0.1:%d/voice/stream" % port)


func is_open() -> bool:
	return _ws != null and _ws.get_ready_state() == WebSocketPeer.STATE_OPEN


func send_audio(pcm: PackedByteArray) -> void:
	if is_open():
		_ws.send(pcm, WebSocketPeer.WRITE_MODE_BINARY)


func commit() -> void:
	if is_open():
		_ws.send_text(JSON.stringify({"type": "commit"}))


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
			var text := _ws.get_packet().get_string_from_utf8()
			var parsed: Variant = JSON.parse_string(text)
			if parsed is Dictionary:
				_handle(parsed)
	elif state == WebSocketPeer.STATE_CLOSED:
		var code := _ws.get_close_code()
		_ws = null
		if not _was_open:
			failed.emit(I18n.t("Cannot reach the local voice service (code %d).") % code)
		elif code == 4403:
			failed.emit(I18n.t("No OpenAI key configured."))
		closed.emit()


func _handle(msg: Dictionary) -> void:
	match str(msg.get("type", "")):
		"ready":
			_open = true
			session_ready.emit(str(msg.get("model", "")), str(msg.get("provider", "")))
		"delta":
			delta.emit(str(msg.get("text", "")))
		"final":
			final.emit(str(msg.get("text", "")))
		"error":
			failed.emit(str(msg.get("message", I18n.t("Voice error"))))
