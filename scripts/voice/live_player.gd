class_name LivePlayer
extends Node
## Plays the assistant's streamed voice (PCM16 LE mono 24 kHz) on the Voice bus, and knows
## how much of the current answer the user actually heard, for clean interruptions.

const RATE := 24000.0

var _player: AudioStreamPlayer
var _playback: AudioStreamGeneratorPlayback
var _queue := PackedVector2Array()
var _pushed := 0          # frames handed to the generator for the current answer
var _capacity := 0


func _ready() -> void:
	var gen := AudioStreamGenerator.new()
	gen.mix_rate = RATE
	gen.buffer_length = 0.5
	_player = AudioStreamPlayer.new()
	_player.stream = gen
	_player.bus = "Voice"
	add_child(_player)


## Same speed as the read-aloud voice (the Voice bus corrects the pitch).
func set_speed(speed: float) -> void:
	_player.pitch_scale = speed


func _ensure() -> void:
	if not _player.playing:
		_player.play()
		_playback = _player.get_stream_playback() as AudioStreamGeneratorPlayback
		_capacity = _playback.get_frames_available()


func push_pcm(pcm: PackedByteArray) -> void:
	var n := pcm.size() / 2
	var frames := PackedVector2Array()
	frames.resize(n)
	for i in n:
		var v := float(pcm.decode_s16(i * 2)) / 32768.0
		frames[i] = Vector2(v, v)
	_queue.append_array(frames)
	_ensure()


func new_answer() -> void:
	_pushed = 0


## Frames still waiting (ours plus those inside the generator).
func buffered_frames() -> int:
	var inside := 0
	if _playback != null and _player.playing:
		inside = maxi(0, _capacity - _playback.get_frames_available())
	return _queue.size() + inside


func is_playing() -> bool:
	return buffered_frames() > int(RATE * 0.03)


## Milliseconds of the current answer that actually came out of the speakers.
func heard_ms() -> int:
	var inside := 0
	if _playback != null and _player.playing:
		inside = maxi(0, _capacity - _playback.get_frames_available())
	return int(float(maxi(0, _pushed - inside)) / RATE * 1000.0)


func clear() -> void:
	_queue = PackedVector2Array()
	if _player.playing:
		_player.stop()
	_playback = null


func _process(_delta: float) -> void:
	if _playback == null or _queue.is_empty():
		return
	var room := _playback.get_frames_available()
	if room <= 0:
		return
	var n := mini(room, _queue.size())
	_playback.push_buffer(_queue.slice(0, n))
	_queue = _queue.slice(n)
	_pushed += n
