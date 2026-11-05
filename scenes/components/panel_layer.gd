class_name SbPanelLayer
extends Control
## Arranges SbFloatingPanels over the graph: panels docked on the same edge share it (stacked), a shrunk docked
## panel keeps only its title bar in the stack, free panels stay inside the screen. Tells the screen how much of
## the left and right edges is taken, so the graph's toolbars can move aside.

signal edges_changed(left: float, right: float)

var margin_top := 92.0
var margin_bottom := 112.0
var margin_side := 24.0
var gap := 12.0
var left_extent := 0.0
var right_extent := 0.0
var _queued := false


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	resized.connect(relayout)


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


## The room panels may use (below the top bar, above the capture bar).
func area() -> Rect2:
	return Rect2(Vector2(margin_side, margin_top), size - Vector2(margin_side * 2.0, margin_top + margin_bottom))


func queue_layout() -> void:
	if _queued:
		return
	_queued = true
	(func() -> void:
		_queued = false
		relayout()).call_deferred()


func relayout() -> void:
	var a := area()
	if a.size.x <= 0 or a.size.y <= 0:
		return
	left_extent = 0.0
	right_extent = 0.0
	for side in ["left", "right"]:
		var stack: Array[SbFloatingPanel] = []
		for p in panels():
			if p.visible and p.dock == side:
				stack.append(p)
		if stack.is_empty():
			continue
		var width := 0.0
		var open_count := 0
		var fixed := 0.0
		for p in stack:
			width = maxf(width, p.dock_size)
			if p.minimized:
				fixed += _bar(p)
			else:
				open_count += 1
		width = minf(width, a.size.x * 0.45)
		var free_h := a.size.y - fixed - gap * float(stack.size() - 1)
		var each := free_h / float(maxi(open_count, 1))
		var y := a.position.y
		var x := a.position.x if side == "left" else a.end.x - width
		for p in stack:
			var h := _bar(p) if p.minimized else each
			_place(p, Rect2(x, y, width, h))
			y += h + gap
		if side == "left":
			left_extent = width + gap
		else:
			right_extent = width + gap
	var bottom: Array[SbFloatingPanel] = []
	for p in panels():
		if p.visible and p.dock == "bottom":
			bottom.append(p)
	if not bottom.is_empty():
		var x0 := a.position.x + left_extent
		var w := (a.size.x - left_extent - right_extent - gap * float(bottom.size() - 1)) / float(bottom.size())
		for p in bottom:
			var h := _bar(p) if p.minimized else minf(p.dock_size, a.size.y * 0.6)
			_place(p, Rect2(x0, a.end.y - h, w, h))
			x0 += w + gap
	for p in panels():
		if p.visible and p.dock == "free":
			var r := p.free_rect
			if p.minimized:
				r.size = Vector2(minf(r.size.x, 260.0), _bar(p))
			r.size = Vector2(minf(r.size.x, a.size.x), minf(r.size.y, a.size.y))
			r.position = Vector2(clampf(r.position.x, a.position.x, a.end.x - r.size.x),
				clampf(r.position.y, a.position.y, a.end.y - r.size.y))
			_place(p, r)
	edges_changed.emit(left_extent, right_extent)


## A shrunk panel's height: its title bar and the panel's padding.
func _bar(p: SbFloatingPanel) -> float:
	return maxf(SbFloatingPanel.HEADER_H, p.get_combined_minimum_size().y)


func _place(p: SbFloatingPanel, r: Rect2) -> void:
	p.position = r.position
	p.size = r.size
	p.custom_minimum_size = Vector2.ZERO


func reset_all() -> void:
	for p in panels():
		p.reset()
	queue_layout()
