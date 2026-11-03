class_name StatusDot
extends Control
## Small coloured dot; pulses while a status is in progress.

var status := "pending"
var _t := 0.0


func _init() -> void:
	custom_minimum_size = Vector2(14, 14)
	mouse_filter = Control.MOUSE_FILTER_IGNORE


func set_status(value: String) -> void:
	status = value
	queue_redraw()


func _process(delta: float) -> void:
	if status in ["started", "progress", "checking"]:
		_t += delta
		queue_redraw()


func _draw() -> void:
	var c := SbTheme.status_color(status)
	var center := size * 0.5
	var r := minf(size.x, size.y) * 0.32
	if status in ["started", "progress", "checking"]:
		var p := fmod(_t * 1.4, 1.0)
		draw_circle(center, r * (1.0 + 1.2 * p), Color(c, 0.35 * (1.0 - p)))
	if status == "pending":
		draw_arc(center, r, 0, TAU, 24, c, 1.5, true)
	else:
		draw_circle(center, r, c)
