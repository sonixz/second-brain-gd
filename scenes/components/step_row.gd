class_name StepRow
extends PanelContainer
## One setup step: status dot, label, latest message, state tag.

var step_id := ""
var status := "pending"
var _dot: StatusDot
var _label: Label
var _message: Label
var _tag: Label


func setup(id: String, label: String) -> StepRow:
	step_id = id
	theme_type_variation = "Inset"
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	add_child(row)
	_dot = StatusDot.new()
	_dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(_dot)
	var col := VBoxContainer.new()
	col.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	col.add_theme_constant_override("separation", 2)
	row.add_child(col)
	_label = Label.new()
	_label.text = label
	_label.add_theme_font_override("font", SbTheme.font(600))
	col.add_child(_label)
	_message = Label.new()
	_message.theme_type_variation = "Muted"
	_message.text = "Waiting"
	_message.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	_message.clip_text = true
	col.add_child(_message)
	_tag = Label.new()
	_tag.theme_type_variation = "Muted"
	_tag.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	row.add_child(_tag)
	set_state("pending", "Waiting")
	return self


func set_state(value: String, message: String = "") -> void:
	if value == "log":
		return
	# "unavailable" ends a step that is optional: shown as a finished warning, setup goes on.
	var optional_failed := value == "unavailable"
	if optional_failed:
		value = "warning"
		status = "done"
	# A warning inside a running step keeps the step running.
	if value == "warning" and status in ["started", "progress"]:
		_message.text = message
		_message.add_theme_color_override("font_color", SbTheme.WARN)
		return
	status = value
	_dot.set_status(value)
	if message != "":
		_message.text = message
		_message.tooltip_text = message
	_message.remove_theme_color_override("font_color")
	if value == "error":
		_message.add_theme_color_override("font_color", SbTheme.ERROR)
	var tags := {"pending": "", "started": "Running", "progress": "Running", "ok": "Done",
		"skipped": "Already done", "warning": "Not available" if optional_failed else "Warning", "error": "Failed", "checking": "Checking"}
	_tag.text = str(tags.get(value, value))
	_tag.add_theme_color_override("font_color", SbTheme.status_color(value))
