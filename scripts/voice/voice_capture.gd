class_name VoiceCapture
extends Node
## Microphone capture: AudioStreamMicrophone on a silent "Mic" bus with an
## AudioEffectCapture. Frames are mixed to mono, resampled to 24 kHz and encoded
## as PCM16 little-endian, the format the OpenAI Realtime API expects.

signal chunk(pcm: PackedByteArray)
signal level(rms: float)

const TARGET_RATE := 24000.0
const CHUNK_S := 0.1

var recording := false
var _capture: AudioEffectCapture
var _player: AudioStreamPlayer
var _state: Dictionary = {"pos": 0.0, "prev": 0.0}
var _pending := PackedByteArray()


func _ready() -> void:
	var idx := AudioServer.get_bus_index("Mic")
	if idx == -1:
		AudioServer.add_bus()
		idx = AudioServer.bus_count - 1
		AudioServer.set_bus_name(idx, "Mic")
		_capture = AudioEffectCapture.new()
		_capture.buffer_length = 1.0
		AudioServer.add_bus_effect(idx, _capture)
		# Never play the microphone back through the speakers.
		AudioServer.set_bus_send(idx, "Mic")
		AudioServer.set_bus_volume_db(idx, -80.0)
	else:
		_capture = AudioServer.get_bus_effect(idx, 0) as AudioEffectCapture
	_player = AudioStreamPlayer.new()
	_player.bus = "Mic"
	add_child(_player)


func start() -> void:
	_state = {"pos": 0.0, "prev": 0.0}
	_pending = PackedByteArray()
	_capture.clear_buffer()
	_player.stream = AudioStreamMicrophone.new()
	_player.play()
	recording = true


func stop() -> void:
	recording = false
	_player.stop()
	_player.stream = null
	_flush()


func _process(_delta: float) -> void:
	if not recording:
		return
	var n := _capture.get_frames_available()
	if n > 0:
		feed_frames(_capture.get_buffer(n), AudioServer.get_mix_rate())


## Also used by tests to push synthetic audio through the same path.
func feed_frames(frames: PackedVector2Array, src_rate: float) -> void:
	var sum := 0.0
	for f in frames:
		var m := (f.x + f.y) * 0.5
		sum += m * m
	if frames.size() > 0:
		level.emit(sqrt(sum / frames.size()))
	_pending.append_array(encode(frames, src_rate, _state))
	if _pending.size() >= int(TARGET_RATE * 2.0 * CHUNK_S):
		_flush()


func _flush() -> void:
	if _pending.size() > 0:
		chunk.emit(_pending)
		_pending = PackedByteArray()


## Stereo float frames at src_rate -> mono PCM16 LE at 24 kHz, by linear
## interpolation over an extended buffer e[0] = last sample of the previous
## call, e[k] = frame k-1 of this call. `state` carries position and that sample.
static func encode(frames: PackedVector2Array, src_rate: float, state: Dictionary) -> PackedByteArray:
	var out := PackedByteArray()
	var count := frames.size()
	if count == 0:
		return out
	var step := src_rate / TARGET_RATE
	var pos: float = state.get("pos", 0.0)
	var prev: float = state.get("prev", 0.0)
	out.resize(int(ceil(float(count) / step)) * 2 + 4)
	var w := 0
	while pos + 1.0 <= float(count):
		var i := int(pos)
		var frac := pos - float(i)
		var a := prev if i == 0 else (frames[i - 1].x + frames[i - 1].y) * 0.5
		var b := (frames[i].x + frames[i].y) * 0.5
		out.encode_s16(w, int(round(clampf(lerpf(a, b, frac), -1.0, 1.0) * 32767.0)))
		w += 2
		pos += step
	state["pos"] = pos - float(count)
	state["prev"] = (frames[count - 1].x + frames[count - 1].y) * 0.5
	out.resize(w)
	return out
