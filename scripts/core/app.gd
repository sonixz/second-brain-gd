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

var backend: Backend
var current_screen := ""
var _current: Control
var _layer: Control
var _quitting := false


func _ready() -> void:
	set_anchors_preset(Control.PRESET_FULL_RECT)
	theme = SbTheme.build()
	get_tree().auto_accept_quit = false
	var bg := ColorRect.new()
	bg.color = SbTheme.BG
	bg.set_anchors_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bg)
	var glow := _Backdrop.new()
	glow.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(glow)
	_layer = Control.new()
	_layer.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(_layer)
	backend = Backend.new()
	backend.name = "Backend"
	add_child(backend)
	show_welcome()
	if "--autosetup" in OS.get_cmdline_user_args():
		start_setup()


func show_welcome() -> void:
	_switch(WELCOME.instantiate(), "welcome")


func start_setup() -> void:
	_switch(SETUP.instantiate(), "setup")


func show_console() -> void:
	_switch(CONSOLE.instantiate(), "console")


func current() -> Control:
	return _current


func _switch(screen: Control, screen_name: String) -> void:
	if screen.has_method("bind"):
		screen.call("bind", self)
	var old := _current
	_current = screen
	current_screen = screen_name
	screen.set_anchors_preset(Control.PRESET_FULL_RECT)
	screen.modulate.a = 0.0
	_layer.add_child(screen)
	var tw := create_tween()
	tw.tween_property(screen, "modulate:a", 1.0, 0.28).set_trans(Tween.TRANS_SINE)
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
	await backend.shutdown_engine(2.5)
	get_tree().quit()


class _Backdrop:
	extends Control
	## Soft radial glows so the dark background is not flat.
	func _ready() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE
		resized.connect(queue_redraw)

	func _draw() -> void:
		for i in 12:
			var f := float(i) / 12.0
			draw_circle(Vector2(size.x * 0.82, size.y * 0.08), size.x * 0.45 * (1.0 - f),
				Color(SbTheme.FOREST, 0.012))
			draw_circle(Vector2(size.x * 0.08, size.y * 0.95), size.x * 0.35 * (1.0 - f),
				Color(SbTheme.FOREST_LIGHT, 0.008))
