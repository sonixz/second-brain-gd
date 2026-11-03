class_name SbAudio
extends Node
## Music playlists per theme (crossfaded), ambience loops, UI sound effects.
## Three buses (Music, SFX, Ambience) with persistent volumes. Every Button in
## the tree gets hover/click sounds automatically.

signal track_changed(title: String)

const AUDIO_DIR := "res://assets/audio"
const BUSES := ["Music", "SFX", "Ambience"]
const DEFAULTS := {"Music": 0.45, "SFX": 0.7, "Ambience": 0.35}
const FADE_S := 2.5
const TRACK_TITLES := {
	"morning_1": "Sunrise Coffee", "morning_2": "Open Window",
	"focus_1": "Deep Field", "focus_2": "Flow State",
	"evening_1": "Late Rhodes", "evening_2": "Wind Down",
	"forest_1": "Kalimba Grove", "forest_2": "Green Room",
}

var theme_name := "morning"
var playlist: Array[String] = []
var track_index := -1
var current_title := ""
var music_enabled := true
var ambience_enabled := false
var muted := false
var _music: Array[AudioStreamPlayer] = []
var _active := 0
var _ambience: AudioStreamPlayer
var _sfx_pool: Array[AudioStreamPlayer] = []
var _sfx_cache: Dictionary = {}
var _last_hover_ms := 0


func _ready() -> void:
	process_mode = Node.PROCESS_MODE_ALWAYS
	for bus in BUSES:
		if AudioServer.get_bus_index(bus) == -1:
			AudioServer.add_bus()
			var idx := AudioServer.bus_count - 1
			AudioServer.set_bus_name(idx, bus)
			AudioServer.set_bus_send(idx, "Master")
		set_volume(bus, float(SbSettings.get_value("audio", bus, DEFAULTS[bus])), false)
	music_enabled = bool(SbSettings.get_value("audio", "music_enabled", true))
	ambience_enabled = bool(SbSettings.get_value("audio", "ambience_enabled", false))
	set_muted(bool(SbSettings.get_value("audio", "muted", false)), false)
	for i in 2:
		var p := AudioStreamPlayer.new()
		p.bus = "Music"
		p.volume_db = -80.0
		p.finished.connect(_on_track_finished.bind(i))
		add_child(p)
		_music.append(p)
	_ambience = AudioStreamPlayer.new()
	_ambience.bus = "Ambience"
	add_child(_ambience)
	for i in 6:
		var s := AudioStreamPlayer.new()
		s.bus = "SFX"
		add_child(s)
		_sfx_pool.append(s)
	get_tree().node_added.connect(_on_node_added)


# ------------------------------------------------------------------ volumes
func volume(bus: String) -> float:
	var idx := AudioServer.get_bus_index(bus)
	if idx < 0:
		return 0.0
	return db_to_linear(AudioServer.get_bus_volume_db(idx))


func set_volume(bus: String, linear: float, save: bool = true) -> void:
	var idx := AudioServer.get_bus_index(bus)
	if idx < 0:
		return
	var v := clampf(linear, 0.0, 1.0)
	AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(v, 0.0001)))
	AudioServer.set_bus_mute(idx, v <= 0.001)
	if save:
		SbSettings.set_value("audio", bus, v)


func set_muted(value: bool, save: bool = true) -> void:
	muted = value
	AudioServer.set_bus_mute(0, value)
	if save:
		SbSettings.set_value("audio", "muted", value)


func set_music_enabled(value: bool) -> void:
	music_enabled = value
	SbSettings.set_value("audio", "music_enabled", value)
	if value:
		_start_playlist()
	else:
		_fade_out_all()
		current_title = ""
		track_changed.emit("")


func set_ambience_enabled(value: bool) -> void:
	ambience_enabled = value
	SbSettings.set_value("audio", "ambience_enabled", value)
	_update_ambience()


# -------------------------------------------------------------------- music
static func tracks_for(theme: String) -> Array[String]:
	var out: Array[String] = []
	for i in range(1, 7):
		var path := "%s/music/%s_%d.mp3" % [AUDIO_DIR, theme, i]
		if ResourceLoader.exists(path):
			out.append(path)
	return out


func set_theme(theme: String) -> void:
	if theme == theme_name and track_index >= 0:
		return
	theme_name = theme
	playlist = tracks_for(theme)
	track_index = -1
	if music_enabled:
		_start_playlist()
	_update_ambience()


func _start_playlist() -> void:
	if playlist.is_empty():
		playlist = tracks_for(theme_name)
	if playlist.is_empty():
		return
	next_track()


func next_track() -> void:
	if playlist.is_empty():
		return
	track_index = (track_index + 1) % playlist.size()
	var path := playlist[track_index]
	var stream: AudioStreamMP3 = load(path)
	if stream == null:
		return
	stream.loop = false
	var old := _music[_active]
	_active = 1 - _active
	var p := _music[_active]
	p.stream = stream
	p.volume_db = -40.0
	p.play()
	create_tween().tween_property(p, "volume_db", 0.0, FADE_S).set_trans(Tween.TRANS_SINE)
	if old.playing:
		var tw := create_tween()
		tw.tween_property(old, "volume_db", -60.0, FADE_S)
		tw.tween_callback(old.stop)
	var key := path.get_file().get_basename()
	current_title = str(TRACK_TITLES.get(key, key.capitalize()))
	track_changed.emit(current_title)


func _on_track_finished(i: int) -> void:
	if i == _active and music_enabled:
		next_track()


func _fade_out_all() -> void:
	for p in _music:
		if p.playing:
			var tw := create_tween()
			tw.tween_property(p, "volume_db", -60.0, 1.2)
			tw.tween_callback(p.stop)


func _update_ambience() -> void:
	var path := "%s/ambience/%s.mp3" % [AUDIO_DIR, theme_name]
	if not ambience_enabled or not ResourceLoader.exists(path):
		if _ambience.playing:
			var tw := create_tween()
			tw.tween_property(_ambience, "volume_db", -60.0, 1.5)
			tw.tween_callback(_ambience.stop)
		return
	var stream: AudioStreamMP3 = load(path)
	stream.loop = true
	_ambience.stream = stream
	_ambience.volume_db = -40.0
	_ambience.play()
	create_tween().tween_property(_ambience, "volume_db", 0.0, 3.0)


# ---------------------------------------------------------------------- sfx
func play(sfx_name: String, pitch_jitter: float = 0.0, volume_db: float = 0.0) -> void:
	var stream: AudioStream = _sfx_cache.get(sfx_name)
	if stream == null:
		var path := "%s/sfx/%s.mp3" % [AUDIO_DIR, sfx_name]
		if not ResourceLoader.exists(path):
			return
		stream = load(path)
		_sfx_cache[sfx_name] = stream
	for p in _sfx_pool:
		if not p.playing:
			p.stream = stream
			p.pitch_scale = 1.0 + randf_range(-pitch_jitter, pitch_jitter)
			p.volume_db = volume_db
			p.play()
			return


func _on_node_added(node: Node) -> void:
	if node is BaseButton and not node.has_meta("sb_audio"):
		node.set_meta("sb_audio", true)
		var b: BaseButton = node
		b.mouse_entered.connect(_on_hover.bind(b))
		b.pressed.connect(_on_press.bind(b))


func _on_hover(b: BaseButton) -> void:
	if b.disabled:
		return
	var now := Time.get_ticks_msec()
	if now - _last_hover_ms < 60:
		return
	_last_hover_ms = now
	play("hover", 0.08, -6.0)


func _on_press(b: BaseButton) -> void:
	var custom := str(b.get_meta("sfx", ""))
	if custom == "none":
		return
	play(custom if custom != "" else "click", 0.05)


func stop_all() -> void:
	for p in _music:
		p.stop()
		p.stream = null
	for p in _sfx_pool:
		p.stop()
		p.stream = null
	_ambience.stop()
	_ambience.stream = null
	_sfx_cache.clear()


func _exit_tree() -> void:
	stop_all()
