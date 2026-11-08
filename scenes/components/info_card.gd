class_name InfoCard
extends PanelContainer
## Titled card with a status dot and key/value rows.

var _title: Label
var _dot: StatusDot
var _state: Label
var _grid: GridContainer
var _footer: Label


func setup(title: String) -> InfoCard:
	theme_type_variation = "Card"
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	add_child(col)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 10)
	col.add_child(head)
	_dot = StatusDot.new()
	_dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	head.add_child(_dot)
	_title = Label.new()
	_title.text = title
	_title.theme_type_variation = "Heading"
	_title.add_theme_font_size_override("font_size", SbTheme.fs(16))
	_title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(_title)
	_state = Label.new()
	_state.theme_type_variation = "Muted"
	head.add_child(_state)
	_grid = GridContainer.new()
	_grid.columns = 2
	_grid.add_theme_constant_override("h_separation", 16)
	_grid.add_theme_constant_override("v_separation", 6)
	col.add_child(_grid)
	_footer = Label.new()
	_footer.theme_type_variation = "Muted"
	_footer.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_footer.visible = false
	col.add_child(_footer)
	set_state("pending", I18n.t("Waiting for data"))
	return self


func set_state(status: String, text: String) -> void:
	_dot.set_status(status)
	_state.text = text
	_state.add_theme_color_override("font_color", SbTheme.status_color(status))


## rows: Array of [key, value] or [key, value, Color]
func set_rows(rows: Array) -> void:
	for c in _grid.get_children():
		_grid.remove_child(c)
		c.queue_free()
	for r in rows:
		var k := Label.new()
		k.theme_type_variation = "Muted"
		k.text = str(r[0])
		_grid.add_child(k)
		var v := Label.new()
		v.text = str(r[1])
		v.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		v.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		v.clip_text = true
		v.tooltip_text = str(r[1])
		v.mouse_filter = Control.MOUSE_FILTER_PASS
		if str(r[1]) == SbFormat.na() or str(r[1]) == SbFormat.NA:
			v.add_theme_color_override("font_color", SbTheme.FAINT)
		elif is_local_path(str(r[1])):  # a folder or file on this computer: a click opens it
			make_openable(v, str(r[1]))
		elif r.size() > 2:
			v.add_theme_color_override("font_color", r[2])
		_grid.add_child(v)


## An absolute path that exists on this computer ("C:\…", "/home/…"), not a web address.
static func is_local_path(text: String) -> bool:
	var t := text.strip_edges()
	if t == "" or t.contains("://") or t.contains("\n"):
		return false
	var absolute := t.begins_with("/") or (t.length() > 2 and t[1] == ":" and (t[2] == "\\" or t[2] == "/"))
	return absolute and (DirAccess.dir_exists_absolute(t) or FileAccess.file_exists(t))


## The label opens its path when clicked: a folder in the file manager, a file shown in its folder.
static func make_openable(v: Label, path: String) -> void:
	v.add_theme_color_override("font_color", SbTheme.MINT)
	v.mouse_filter = Control.MOUSE_FILTER_STOP
	v.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	v.tooltip_text = path + "\n" + I18n.t("Click to open in your file manager")
	v.gui_input.connect(func(e: InputEvent) -> void:
		if e is InputEventMouseButton and (e as InputEventMouseButton).pressed \
				and (e as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
			open_path(path))


static func open_path(path: String) -> void:
	if OS.get_environment("SBGD_TEST_NO_SHELL") == "1":
		return
	if DirAccess.dir_exists_absolute(path):
		OS.shell_open(path)
	else:
		OS.shell_show_in_file_manager(path)


func set_footer(text: String) -> void:
	_footer.text = text
	_footer.visible = text != ""
