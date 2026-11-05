class_name SbPanelLayer
extends Control
## Arranges SbFloatingPanels over the graph.
## - Panels docked on the same edge share it by weight; the line between two of them is a splitter you can drag.
## - While a panel is dragged, the place it would land lights up; moves and size changes glide (animate = false
##   in tests).
## - A shrunk panel leaves the layout and waits as an icon on the rail at the left edge; a click opens it again.
## - Free panels stay inside the screen. Tells the screen how much of each side edge is taken (edges_changed).

signal edges_changed(left: float, right: float)
signal create_requested                # the rail's « + »: create an agent with the Agent Builder

const RAIL_W := 44.0
const SPLIT_H := 10.0
const GLIDE_S := 0.18

var margin_top := 92.0
var margin_bottom := 112.0
var margin_side := 24.0
var gap := 12.0
var left_extent := 0.0
var right_extent := 0.0
var animate := true
var rail: VBoxContainer
var _queued := false
var _laid_out := false
var _drop_rect := Rect2()
var _splitters: Array[Control] = []


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(relayout)
	rail = VBoxContainer.new()
	rail.add_theme_constant_override("separation", 8)
	rail.visible = false
	add_child(rail)


func add_panel(p: SbFloatingPanel) -> SbFloatingPanel:
	add_child(p)
	p.layout_changed.connect(queue_layout)
	p.visibility_changed.connect(queue_layout)
	queue_layout()
	return p


func panels() -> Array[SbFloatingPanel]:
	var out: Array[SbFloatingPanel] = []
	for c in get_children():
		if c is SbFloatingPanel:
			out.append(c)
	return out


func shrunk() -> Array[SbFloatingPanel]:
	var out: Array[SbFloatingPanel] = []
	for p in panels():
		if p.minimized:
			out.append(p)
	return out


## The room panels may use (below the top bar, above the capture bar, right of the rail).
func area() -> Rect2:
	var rail_w := RAIL_W  # the rail is always there: shrunk panels, and « + » to create an agent
	return Rect2(Vector2(margin_side + rail_w, margin_top),
		size - Vector2(margin_side * 2.0 + rail_w, margin_top + margin_bottom))


func queue_layout() -> void:
	if _queued:
		return
	_queued = true
	(func() -> void:
		_queued = false
		relayout()).call_deferred()


func relayout() -> void:
	_build_rail()
	var a := area()
	if a.size.x <= 0 or a.size.y <= 0:
		return
	for sp in _splitters:
		sp.queue_free()
	_splitters.clear()
	left_extent = 0.0
	right_extent = 0.0
	for side in ["left", "right"]:
		var stack := _stack(side)
		if stack.is_empty():
			continue
		var width := 0.0
		var total_w := 0.0
		for p in stack:
			width = maxf(width, maxf(p.dock_size, p.get_combined_minimum_size().x))  # never narrower than its title bar
			total_w += p.weight
		width = minf(width, a.size.x * 0.45)
		var free_h := a.size.y - gap * float(stack.size() - 1)
		var y := a.position.y
		var x := a.position.x if side == "left" else a.end.x - width
		for i in stack.size():
			var p: SbFloatingPanel = stack[i]
			var h := free_h * p.weight / total_w
			_place(p, Rect2(x, y, width, h))
			y += h + gap
			if i < stack.size() - 1:
				_add_splitter(stack[i], stack[i + 1], Rect2(x, y - gap - SPLIT_H * 0.5 + gap * 0.5, width, SPLIT_H), free_h, total_w)
		if side == "left":
			left_extent = width + gap
		else:
			right_extent = width + gap
	var bottom := _stack("bottom")
	if not bottom.is_empty():
		var x0 := a.position.x + left_extent
		var w := (a.size.x - left_extent - right_extent - gap * float(bottom.size() - 1)) / float(bottom.size())
		for p in bottom:
			var h := minf(p.dock_size, a.size.y * 0.6)
			_place(p, Rect2(x0, a.end.y - h, w, h))
			x0 += w + gap
	for p in panels():
		if p.visible and not p.minimized and p.dock == "free":
			var r := p.free_rect
			r.size = Vector2(minf(r.size.x, a.size.x), minf(r.size.y, a.size.y))
			r.position = Vector2(clampf(r.position.x, a.position.x, a.end.x - r.size.x),
				clampf(r.position.y, a.position.y, a.end.y - r.size.y))
			_place(p, r)
	_laid_out = true
	edges_changed.emit((RAIL_W if rail.visible else 0.0) + left_extent, right_extent)


func _stack(side: String) -> Array[SbFloatingPanel]:
	var out: Array[SbFloatingPanel] = []
	for p in panels():
		if p.visible and not p.minimized and p.dock == side:
			out.append(p)
	return out


## Moves glide, except at start-up, while dragging, and in tests.
func _place(p: SbFloatingPanel, r: Rect2) -> void:
	p.custom_minimum_size = Vector2.ZERO
	var old: Variant = p.get_meta("glide") if p.has_meta("glide") else null
	if old is Tween and (old as Tween).is_valid():
		(old as Tween).kill()
	if not animate or not _laid_out or p._dragging or not p.is_inside_tree() \
			or (p.position.distance_to(r.position) < 1.0 and p.size.distance_to(r.size) < 1.0):
		p.position = r.position
		p.size = r.size
		return
	var t := p.create_tween().set_parallel(true).set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	t.tween_property(p, "position", r.position, GLIDE_S)
	t.tween_property(p, "size", r.size, GLIDE_S)
	p.set_meta("glide", t)


# ---------------------------------------------------------------- drop preview
## Called while a panel is dragged: dock is where it would land ("" or "free": nothing to show).
func show_drop(p: SbFloatingPanel, dock: String) -> void:
	var a := area()
	match dock:
		"left":
			_drop_rect = Rect2(a.position, Vector2(minf(maxf(p.dock_size, 300.0), a.size.x * 0.45), a.size.y))
		"right":
			var w := minf(maxf(p.dock_size, 300.0), a.size.x * 0.45)
			_drop_rect = Rect2(Vector2(a.end.x - w, a.position.y), Vector2(w, a.size.y))
		"bottom":
			var h := clampf(minf(p.size.y, 320.0), SbFloatingPanel.MIN_SIZE.y, 420.0)
			_drop_rect = Rect2(Vector2(a.position.x + left_extent, a.end.y - h), Vector2(a.size.x - left_extent - right_extent, h))
		_:
			_drop_rect = Rect2()
	queue_redraw()


func drop_preview() -> Rect2:
	return _drop_rect


func _draw() -> void:
	if _drop_rect.size == Vector2.ZERO:
		return
	draw_rect(_drop_rect, Color(SbTheme.MINT, 0.12))
	draw_rect(_drop_rect, Color(SbTheme.MINT, 0.7), false, 2.0)


# ---------------------------------------------------------------- splitters
func _add_splitter(above: SbFloatingPanel, below: SbFloatingPanel, r: Rect2, free_h: float, total_w: float) -> void:
	var sp := Control.new()
	sp.position = r.position
	sp.size = r.size
	sp.mouse_filter = Control.MOUSE_FILTER_STOP
	sp.mouse_default_cursor_shape = Control.CURSOR_VSPLIT
	sp.tooltip_text = I18n.t("Drag to share the height between these panels")
	sp.set_meta("pair", [above, below])
	var hovered := [false]
	sp.mouse_entered.connect(func() -> void:
		hovered[0] = true
		sp.queue_redraw())
	sp.mouse_exited.connect(func() -> void:
		hovered[0] = false
		sp.queue_redraw())
	sp.draw.connect(func() -> void:
		var c := sp.size * 0.5
		var col := Color(SbTheme.MINT, 0.9) if hovered[0] else Color(SbTheme.MUTED, 0.45)
		sp.draw_line(Vector2(c.x - 22, c.y), Vector2(c.x + 22, c.y), col, 3.0 if hovered[0] else 2.0, true))
	sp.gui_input.connect(func(ev: InputEvent) -> void:
		if ev is InputEventMouseMotion and ((ev as InputEventMouseMotion).button_mask & MOUSE_BUTTON_MASK_LEFT):
			move_split(above, below, (ev as InputEventMouseMotion).relative.y, free_h, total_w)
		elif ev is InputEventMouseButton and not (ev as InputEventMouseButton).pressed:
			above._save()
			below._save())
	add_child(sp)
	move_child(sp, -1)
	_splitters.append(sp)


## Gives dy pixels of height from one stacked panel to its neighbour (both keep a usable minimum).
func move_split(above: SbFloatingPanel, below: SbFloatingPanel, dy: float, free_h: float = -1.0, total_w: float = -1.0) -> void:
	if free_h <= 0.0:
		var stack := _stack(above.dock)
		free_h = area().size.y - gap * float(stack.size() - 1)
		total_w = 0.0
		for p in stack:
			total_w += p.weight
	var h1 := free_h * above.weight / total_w
	var h2 := free_h * below.weight / total_w
	var min_h := SbFloatingPanel.MIN_SIZE.y
	var n1 := clampf(h1 + dy, min_h, h1 + h2 - min_h)
	var pair_w := above.weight + below.weight
	above.weight = pair_w * n1 / (h1 + h2)
	below.weight = pair_w - above.weight
	var was := animate
	animate = false  # the line follows the mouse exactly
	relayout()
	animate = was


# ---------------------------------------------------------------- the rail
func _build_rail() -> void:
	for c in rail.get_children():
		c.queue_free()
	var list := shrunk()
	rail.visible = true
	rail.position = Vector2(margin_side * 0.5, margin_top)
	rail.size = Vector2(RAIL_W - 8.0, 0)
	for p in list:
		var b := Button.new()
		b.text = p.icon_text
		b.custom_minimum_size = Vector2(RAIL_W - 8.0, RAIL_W - 8.0)
		b.tooltip_text = I18n.t("%s (shrunk) · click to open") % p.title_label.text.capitalize()
		b.set_meta("panel", p)
		b.pressed.connect(func() -> void: p.reveal())
		rail.add_child(b)
	var plus := Button.new()
	plus.text = "+"
	plus.custom_minimum_size = Vector2(RAIL_W - 8.0, RAIL_W - 8.0)
	plus.theme_type_variation = "GhostButton"
	plus.tooltip_text = I18n.t("Create an agent: the Agent Builder interviews you and writes its instructions")
	plus.pressed.connect(func() -> void: create_requested.emit())
	rail.add_child(plus)


func rail_buttons() -> Array:  # the shrunk panels (not « + »)
	return rail.get_children().filter(func(c: Node) -> bool: return not c.is_queued_for_deletion() and c.has_meta("panel"))


func reset_all() -> void:
	for p in panels():
		p.reset()
	queue_layout()
