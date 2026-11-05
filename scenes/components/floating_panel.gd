class_name SbFloatingPanel
extends PanelContainer
## A panel you can move (drag its title bar: the place it will land lights up), dock against an edge (left, right,
## bottom), shrink into the icon rail (–, double-click the title, or Ctrl+number), and resize (bottom-right corner;
## the line between two stacked panels is a splitter). Its place is remembered in the settings ("panels" section).
## An SbPanelLayer arranges docked panels, animates the moves and holds the rail.

signal layout_changed
signal focused                     # its title bar was pressed

const HEADER_H := 40.0
const SNAP_PX := 72.0
const MIN_SIZE := Vector2(240, 160)

var panel_id := ""
var dock := "left"           # left | right | bottom | free
var dock_size := 340.0       # width when docked left/right, height when docked bottom
var free_rect := Rect2(420, 120, 360, 420)
var minimized := false        # shrunk into the rail (hidden); reveal() brings it back where it was
var weight := 1.0             # share of the edge when stacked with other panels (the splitter changes it)
var icon_text := ""           # its letter on the rail
var header: HBoxContainer
var title_label: Label
var extra: HBoxContainer      # room for the panel's own small controls, left of the minimize button
var min_button: Button
var body: Control
var footer: HBoxContainer
var _dragging := false
var _resizing := false
var _grab := Vector2.ZERO
var _defaults: Dictionary = {}


func setup(id: String, title: String, content: Control, defaults: Dictionary) -> SbFloatingPanel:
	panel_id = id
	_defaults = defaults
	theme_type_variation = "Glass"
	mouse_filter = Control.MOUSE_FILTER_STOP
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	add_child(col)
	header = HBoxContainer.new()
	header.custom_minimum_size = Vector2(0, HEADER_H - 12)
	header.mouse_filter = Control.MOUSE_FILTER_STOP
	header.mouse_default_cursor_shape = Control.CURSOR_MOVE
	header.tooltip_text = I18n.t("Drag to move · drop near an edge to dock · double-click to shrink")
	header.gui_input.connect(_on_header_input)
	col.add_child(header)
	var grip_dots := Label.new()
	grip_dots.text = "⠿"
	grip_dots.theme_type_variation = "Muted"
	grip_dots.mouse_filter = Control.MOUSE_FILTER_IGNORE
	header.add_child(grip_dots)
	title_label = Label.new()
	title_label.text = title
	title_label.theme_type_variation = "Overline"
	title_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	title_label.clip_text = false  # the whole title stays readable; the extra controls take what is left
	header.add_child(title_label)
	extra = HBoxContainer.new()
	extra.add_theme_constant_override("separation", 4)
	header.add_child(extra)
	min_button = Button.new()
	min_button.text = "–"
	min_button.theme_type_variation = "GhostButton"
	min_button.tooltip_text = I18n.t("Shrink into the rail on the left")
	min_button.pressed.connect(func() -> void: set_minimized(not minimized))
	header.add_child(min_button)
	body = content
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	col.add_child(body)
	footer = HBoxContainer.new()
	footer.alignment = BoxContainer.ALIGNMENT_END
	footer.custom_minimum_size = Vector2(0, 10)
	col.add_child(footer)
	var grip := Control.new()
	grip.custom_minimum_size = Vector2(16, 12)
	grip.mouse_default_cursor_shape = Control.CURSOR_FDIAGSIZE
	grip.tooltip_text = I18n.t("Drag to resize")
	grip.gui_input.connect(_on_grip_input)
	grip.draw.connect(func() -> void:
		for i in 3:
			var o := float(i) * 4.0
			grip.draw_line(Vector2(16 - o, 12), Vector2(16, 12 - o), Color(SbTheme.MUTED, 0.7), 1.0, true))
	footer.add_child(grip)
	_load()
	return self


func set_minimized(on: bool) -> void:
	minimized = on
	visible = not on  # the rail shows it while it is shrunk
	_save()
	layout_changed.emit()


## Opens it if it was shrunk or closed (e.g. F8 talks to the archivist).
func reveal() -> void:
	if minimized:
		set_minimized(false)
	visible = true


func reset() -> void:
	var closed := not visible and not minimized  # a closed panel (the item tile with nothing open) stays closed
	dock = str(_defaults.get("dock", "left"))
	weight = 1.0
	dock_size = float(_defaults.get("size", 340.0))
	free_rect = _defaults.get("free", Rect2(420, 120, 360, 420))
	minimized = bool(_defaults.get("minimized", false))
	set_minimized(minimized)
	if closed and not minimized:
		visible = false


func _on_header_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		var mb := event as InputEventMouseButton
		if mb.double_click and mb.pressed:
			set_minimized(not minimized)
			_dragging = false
			return
		if mb.pressed:
			focused.emit()
			_dragging = true
			_grab = mb.global_position - global_position
			if get_parent() != null:
				get_parent().move_child(self, -1)  # in front of the other panels
		elif _dragging:
			_dragging = false
			if get_parent() != null and get_parent().has_method("show_drop"):
				get_parent().call("show_drop", self, "")
			_drop(mb.global_position - _parent_origin())
		accept_event()
	elif event is InputEventMouseMotion and _dragging and get_parent() != null and get_parent().has_method("show_drop"):
		get_parent().call("show_drop", self, _target((event as InputEventMouseMotion).global_position - _parent_origin()))
		_drag_move(event as InputEventMouseMotion)
	elif event is InputEventMouseMotion and _dragging:
		_drag_move(event as InputEventMouseMotion)


func _drag_move(event: InputEventMouseMotion) -> void:
	if dock != "free":  # leaving a dock: back to a window-sized panel under the cursor
		var fsize: Rect2 = _defaults.get("free", Rect2(0, 0, 360, 480))
		free_rect.size = Vector2(maxf(free_rect.size.x, MIN_SIZE.x), maxf(free_rect.size.y, MIN_SIZE.y)) \
			if free_rect.size.y < 700.0 else fsize.size
		size = free_rect.size
		_grab = Vector2(minf(_grab.x, free_rect.size.x - 40.0), _grab.y)
		dock = "free"
	position = event.global_position - _grab - _parent_origin()
	free_rect.position = position
	accept_event()


## Where a drop with the cursor here would dock it.
func _target(cursor: Vector2) -> String:
	var area: Rect2 = get_parent().call("area") if get_parent() != null and get_parent().has_method("area") else get_viewport_rect()
	if cursor.x < area.position.x + SNAP_PX:
		return "left"
	if cursor.x > area.end.x - SNAP_PX:
		return "right"
	if cursor.y > area.end.y - SNAP_PX:
		return "bottom"
	return "free"


func _on_grip_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and (event as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		_resizing = (event as InputEventMouseButton).pressed
		if not _resizing:
			_save()
			layout_changed.emit()
		accept_event()
	elif event is InputEventMouseMotion and _resizing:
		var rel := (event as InputEventMouseMotion).relative
		match dock:
			"left":
				dock_size = maxf(MIN_SIZE.x, dock_size + rel.x)
			"right":
				dock_size = maxf(MIN_SIZE.x, dock_size - rel.x)
			"bottom":
				dock_size = maxf(MIN_SIZE.y, dock_size - rel.y)
			_:
				free_rect.size = Vector2(maxf(MIN_SIZE.x, free_rect.size.x + rel.x), maxf(MIN_SIZE.y, free_rect.size.y + rel.y))
		layout_changed.emit()
		accept_event()


## Dropped: with the cursor near an edge it docks there, otherwise it floats where it was left.
func _drop(cursor: Vector2) -> void:
	var r := Rect2(position, size)
	var t := _target(cursor)
	if t == "left" or t == "right":
		dock = t
		dock_size = clampf(r.size.x, MIN_SIZE.x, 520.0)
		weight = 1.0
	elif t == "bottom":
		dock = "bottom"
		dock_size = clampf(minf(r.size.y, 320.0), MIN_SIZE.y, 420.0)
	else:
		dock = "free"
		free_rect = Rect2(position, size)
	_save()
	layout_changed.emit()


func _parent_origin() -> Vector2:
	var p := get_parent() as Control
	return p.global_position if p != null else Vector2.ZERO


func _load() -> void:
	var saved: Variant = SbSettings.get_value("panels", panel_id, {})
	var d: Dictionary = saved if saved is Dictionary else {}
	dock = str(d.get("dock", _defaults.get("dock", "left")))
	if not dock in ["left", "right", "bottom", "free"]:
		dock = "left"
	dock_size = float(d.get("size", _defaults.get("size", 340.0)))
	var fr: Variant = _defaults.get("free", Rect2(420, 120, 360, 420))
	if d.has("x"):
		fr = Rect2(float(d["x"]), float(d["y"]), float(d.get("w", 360)), float(d.get("h", 420)))
	free_rect = fr
	minimized = bool(d.get("min", _defaults.get("minimized", false)))
	weight = clampf(float(d.get("weight", 1.0)), 0.15, 6.0)
	icon_text = str(_defaults.get("icon", title_label.text.left(1)))
	if minimized:
		visible = false


func _save() -> void:
	SbSettings.set_value("panels", panel_id, {"dock": dock, "size": dock_size, "x": free_rect.position.x, "y": free_rect.position.y,
		"w": free_rect.size.x, "h": free_rect.size.y, "min": minimized, "weight": weight})
