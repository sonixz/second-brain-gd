class_name SbApp
extends Control
## Root of the application: theme, background, screen switching and the
## engine shutdown when the window closes.
##
## Command-line user args (after `--`):
##   --autosetup   start setup (or the fast start) right away (used by tests)

signal screen_changed(screen_name: String)

const WELCOME := preload("res://scenes/startup/welcome.tscn")
const SETUP := preload("res://scenes/startup/setup.tscn")
const CONSOLE := preload("res://scenes/dashboard/system_console.tscn")
const BRAIN := preload("res://scenes/brain/brain.tscn")
const VOICE_ONBOARDING := preload("res://scenes/startup/voice_onboarding.tscn")

var backend: Backend
var audio: SbAudio
var live: LiveConversation
var state: Dictionary = {}   # survives screen rebuilds (theme switch)
var theme_choice := "auto"
var _backdrop: Control
var _widget: AudioWidget
var current_screen := ""
var _current: Control
var _layer: Control
var _quitting := false


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	I18n.load_saved()
	theme_choice = str(SbSettings.get_value("ui", "theme", "auto"))
	SbTheme.apply(theme_choice)
	theme = SbTheme.build()
	get_tree().auto_accept_quit = false
	_backdrop = _Backdrop.new()
	_backdrop.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_backdrop)
	_layer = Control.new()
	_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_layer)
	backend = Backend.new()
	backend.name = "Backend"
	add_child(backend)
	audio = SbAudio.new()
	audio.name = "Audio"
	add_child(audio)
	audio.set_theme(SbTheme.sound_of(SbTheme.current))
	show_welcome()
	_widget = AudioWidget.new().setup(self)
	add_child(_widget)
	live = LiveConversation.new().setup(self)
	live.name = "LiveConversation"
	add_child(live)
	if "--autosetup" in OS.get_cmdline_user_args():
		start_setup()


func show_welcome() -> void:
	_switch(WELCOME.instantiate(), "welcome")


func start_setup() -> void:
	_switch(SETUP.instantiate(), "setup")


## "Repair the installation" (engine room, Your data): the setup runs again with --repair, which rebuilds the
## Python environment; the data is not touched.
var setup_repair := false


func repair_installation() -> void:
	setup_repair = true
	start_setup()


func show_console() -> void:
	_switch(CONSOLE.instantiate(), "console")


func show_brain() -> void:
	_switch(BRAIN.instantiate(), "brain")


## After setup: the voice onboarding step once, then the brain.
func after_setup() -> void:
	if bool(SbSettings.get_value("onboarding", "voice_done", false)):
		show_brain()
	else:
		_switch(VOICE_ONBOARDING.instantiate(), "onboarding")


## Theme choice from the ambiance panel ("auto" or a theme name).
func set_theme_choice(choice: String) -> void:
	theme_choice = choice
	SbSettings.set_value("ui", "theme", choice)
	var before := SbTheme.current
	SbTheme.apply(choice)
	if SbTheme.current == before:
		return
	audio.play("theme_switch")
	audio.set_theme(SbTheme.sound_of(SbTheme.current))
	theme = SbTheme.build()
	_backdrop.queue_redraw()
	# Rebuild the current screen so every colour follows the new palette.
	match current_screen:
		"welcome":
			_switch(WELCOME.instantiate(), "welcome", 0.5)
		"console":
			_switch(CONSOLE.instantiate(), "console", 0.5)
		"brain":
			_switch(BRAIN.instantiate(), "brain", 0.5)


## The FR / EN switch: the whole interface is rebuilt in the other language, and the engine is told (agents'
## default language, Live transcription, its own words).
func set_language(code: String) -> void:
	if code == I18n.lang:
		return
	I18n.use(code)
	SbSettings.set_value("ui", "language", I18n.lang)
	await tell_engine_language()
	match current_screen:
		"welcome":
			_switch(WELCOME.instantiate(), "welcome", 0.3)
		"console":
			_switch(CONSOLE.instantiate(), "console", 0.3)
		"brain":
			_switch(BRAIN.instantiate(), "brain", 0.3)


func tell_engine_language() -> void:
	if backend != null and backend.api.port > 0:
		await backend.api.call_api("/assistant/settings", true, HTTPClient.METHOD_PATCH, JSON.stringify({"language": I18n.lang}))


func current() -> Control:
	return _current


func _switch(screen: Control, screen_name: String, fade_s: float = 0.28) -> void:
	if current_screen != "" and audio != null:
		audio.play("whoosh", 0.05, -6.0)
	if screen.has_method("bind"):
		screen.call("bind", self)
	var old := _current
	_current = screen
	current_screen = screen_name
	screen.set_anchors_preset(Control.PRESET_FULL_RECT)
	screen.modulate.a = 0.0
	_layer.add_child(screen)
	var tw := create_tween()
	tw.tween_property(screen, "modulate:a", 1.0, fade_s).set_trans(Tween.TRANS_SINE)
	if old != null:
		old.mouse_filter = Control.MOUSE_FILTER_IGNORE
		var tw_old := create_tween()
		tw_old.tween_property(old, "modulate:a", 0.0, 0.18)
		tw_old.tween_callback(old.queue_free)
	screen_changed.emit(screen_name)


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		quit_app()


## Stops the engine we started, then quits. The engine would also stop by
## itself (parent-pid watchdog) if Godot crashed instead.
func quit_app() -> void:
	if _quitting:
		return
	_quitting = true
	if live != null and live.active:
		live.stop("closed")
	audio.stop_all()
	await backend.shutdown_engine(2.5)
	# Let the audio thread release its playbacks before the engine shuts down.
	await get_tree().process_frame
	await get_tree().process_frame
	get_tree().quit()


class _Backdrop:
	extends Control
	## Soft radial glows so the dark background is not flat.
	func _ready() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		resized.connect(queue_redraw)

	func _draw() -> void:
		draw_rect(Rect2(Vector2.ZERO, size), SbTheme.BG)
		for i in 12:
			var f := float(i) / 12.0
			draw_circle(Vector2(size.x * 0.82, size.y * 0.08), size.x * 0.45 * (1.0 - f),
				Color(SbTheme.FOREST, 0.012))
			draw_circle(Vector2(size.x * 0.08, size.y * 0.95), size.x * 0.35 * (1.0 - f),
				Color(SbTheme.FOREST_LIGHT, 0.008))
