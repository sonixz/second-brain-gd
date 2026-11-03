class_name GraphView
extends Control
## The living knowledge graph: force-directed layout, pan/zoom camera, nodes
## that bloom when born, links that pulse, neighbours that light up on hover.
##
## Input: wheel = zoom, drag empty space = pan, drag a node = move it,
## click = select (signal node_selected), double-click empty = recentre.

signal node_selected(id: String, type: String)
signal background_clicked

const REPULSION := 5200.0
const SPRING := 0.035
const DAMPING := 0.86
const GRAVITY := 0.012
const BIRTH_S := 1.1
const REST := {"space": 150.0, "link": 120.0, "tag": 85.0}

var nodes: Dictionary = {}      # id -> Dictionary (see _make_node)
var edges: Array[Dictionary] = []
var selected := ""
var hovered := ""
var highlight: Dictionary = {}  # id -> true; empty = no filter
var cam := Vector2.ZERO          # world point at the centre of the view
var zoom := 1.0
var heat := 1.0
var _t := 0.0
var _dragging_node := ""
var _panning := false
var _press_pos := Vector2.ZERO
var _moved := false
var _stars: Array[Vector3] = []
var _font: Font
var _neighbors: Dictionary = {}


func _ready() -> void:
	clip_contents = true
	mouse_filter = Control.MOUSE_FILTER_STOP
	focus_mode = Control.FOCUS_CLICK
	_font = SbTheme.font(500)
	var rng := RandomNumberGenerator.new()
	rng.seed = 7
	for i in 140:
		_stars.append(Vector3(rng.randf(), rng.randf(), rng.randf()))


## Merges a /brain/graph payload. Existing nodes keep their positions; new
## nodes are born next to their space. Returns the ids of new note nodes.
func set_graph(data: Dictionary) -> Array[String]:
	var born: Array[String] = []
	var incoming: Dictionary = {}
	var raw_nodes: Array = data.get("nodes", [])
	for item in raw_nodes:
		var n: Dictionary = item
		incoming[str(n["id"])] = n
	for id in nodes.keys():
		if not incoming.has(id):
			nodes.erase(id)
	var first_load := nodes.is_empty()
	var i := 0
	for id in incoming:
		var src: Dictionary = incoming[id]
		if nodes.has(id):
			var existing: Dictionary = nodes[id]
			existing["label"] = str(src.get("label", ""))
			existing["kind"] = str(src.get("kind", ""))
			existing["weight"] = int(src.get("weight", 0))
			existing["space_id"] = str(src.get("space_id", ""))
			existing["color"] = src.get("color")
		else:
			var n := _make_node(src, i, raw_nodes.size(), first_load)
			nodes[id] = n
			if not first_load and str(n["type"]) == "note":
				born.append(str(id))
		i += 1
	edges.clear()
	var raw_edges: Array = data.get("edges", [])
	for item in raw_edges:
		var e: Dictionary = item
		if nodes.has(str(e["from"])) and nodes.has(str(e["to"])):
			edges.append({"from": str(e["from"]), "to": str(e["to"]), "type": str(e.get("type", "link"))})
	# New nodes start next to their space hub.
	for id in born:
		var n: Dictionary = nodes[id]
		var hub_id := "space:" + str(n["space_id"])
		if nodes.has(hub_id):
			var hub: Dictionary = nodes[hub_id]
			n["pos"] = (hub["pos"] as Vector2) + Vector2.from_angle(randf() * TAU) * 40.0
	_rebuild_neighbors()
	heat = 1.0
	return born


func _make_node(src: Dictionary, i: int, total: int, first_load: bool) -> Dictionary:
	var type := str(src.get("type", "note"))
	var angle := TAU * float(i) / maxf(1.0, float(total)) + randf() * 0.3
	var radius := 120.0 if type == "space" else 260.0 + randf() * 120.0
	return {
		"id": str(src["id"]), "type": type, "label": str(src.get("label", "")), "kind": str(src.get("kind", "")),
		"space_id": str(src.get("space_id", "")), "weight": int(src.get("weight", 0)), "color": src.get("color"),
		"pos": Vector2.from_angle(angle) * radius, "vel": Vector2.ZERO,
		"born": (_t - BIRTH_S * randf() * 0.6) if first_load else _t, "pinned": false,
	}


func _rebuild_neighbors() -> void:
	_neighbors.clear()
	for e in edges:
		var a := str(e["from"])
		var b := str(e["to"])
		if not _neighbors.has(a):
			_neighbors[a] = {}
		if not _neighbors.has(b):
			_neighbors[b] = {}
		(_neighbors[a] as Dictionary)[b] = true
		(_neighbors[b] as Dictionary)[a] = true


func node_count(type: String = "") -> int:
	if type == "":
		return nodes.size()
	var c := 0
	for id in nodes:
		var n: Dictionary = nodes[id]
		if str(n["type"]) == type:
			c += 1
	return c


func select(id: String) -> void:
	selected = id
	queue_redraw()


func focus_on(id: String) -> void:
	if not nodes.has(id):
		return
	var n: Dictionary = nodes[id]
	var tw := create_tween().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	tw.tween_property(self, "cam", n["pos"] as Vector2, 0.7)


func set_highlight(ids: Array) -> void:
	highlight.clear()
	for id in ids:
		highlight[str(id)] = true
	queue_redraw()


# --------------------------------------------------------------- simulation
func _process(delta: float) -> void:
	_t += delta
	if heat > 0.02:
		_simulate(minf(delta, 0.05) * 60.0)
		heat *= 0.995
	queue_redraw()


func _simulate(step: float) -> void:
	var ids := nodes.keys()
	var count := ids.size()
	var forces: Dictionary = {}
	for id in ids:
		forces[id] = Vector2.ZERO
	for a in count:
		var na: Dictionary = nodes[ids[a]]
		var pa: Vector2 = na["pos"]
		for b in range(a + 1, count):
			var nb: Dictionary = nodes[ids[b]]
			var d: Vector2 = pa - (nb["pos"] as Vector2)
			var dist2 := maxf(d.length_squared(), 100.0)
			if dist2 > 640000.0:
				continue
			var mult := 2.2 if str(na["type"]) == "space" or str(nb["type"]) == "space" else 1.0
			var f := d.normalized() * REPULSION * mult / dist2
			forces[ids[a]] += f
			forces[ids[b]] -= f
	for e in edges:
		var na: Dictionary = nodes[e["from"]]
		var nb: Dictionary = nodes[e["to"]]
		var d: Vector2 = (nb["pos"] as Vector2) - (na["pos"] as Vector2)
		var rest: float = REST.get(str(e["type"]), 120.0)
		var f := d.normalized() * (d.length() - rest) * SPRING
		forces[e["from"]] += f
		forces[e["to"]] -= f
	for id in ids:
		var n: Dictionary = nodes[id]
		if bool(n["pinned"]) or id == _dragging_node:
			n["vel"] = Vector2.ZERO
			continue
		var p: Vector2 = n["pos"]
		var f: Vector2 = forces[id] - p * GRAVITY * (2.0 if str(n["type"]) == "space" else 1.0)
		var v: Vector2 = ((n["vel"] as Vector2) + f * step * heat) * DAMPING
		n["vel"] = v.limit_length(18.0)
		n["pos"] = p + (n["vel"] as Vector2) * step


# ------------------------------------------------------------------ drawing
func world_to_screen(p: Vector2) -> Vector2:
	return (p - cam) * zoom + size * 0.5


func screen_to_world(s: Vector2) -> Vector2:
	return (s - size * 0.5) / zoom + cam


func _radius(n: Dictionary) -> float:
	match str(n["type"]):
		"space":
			return 20.0 + minf(14.0, float(n["weight"]) * 1.2)
		"tag":
			return 5.0 + minf(5.0, float(n["weight"]))
	return 8.0 + minf(9.0, float(n["weight"]) * 1.6)


func _color(n: Dictionary) -> Color:
	match str(n["type"]):
		"space":
			var c: Variant = n.get("color")
			if c != null and str(c) != "" and str(c) != "<null>":
				return Color(str(c)).lerp(SbTheme.MINT, 0.25)
			return SbTheme.FOREST_LIGHT
		"tag":
			return SbTheme.MUTED
	return SbTheme.kind_color(str(n["kind"]))


func _is_dim(id: String) -> bool:
	if not highlight.is_empty():
		return not highlight.has(id)
	var focus := hovered if hovered != "" else selected
	if focus == "":
		return false
	return id != focus and not (_neighbors.get(focus, {}) as Dictionary).has(id)


func _draw() -> void:
	# Background: soft vignette glow and slow parallax stars.
	draw_rect(Rect2(Vector2.ZERO, size), SbTheme.BG)
	var c := size * 0.5
	for i in 10:
		var f := float(i) / 10.0
		draw_circle(c + Vector2(-size.x * 0.18, -size.y * 0.1), size.x * 0.55 * (1.0 - f), Color(SbTheme.FOREST, 0.018))
	draw_circle(Vector2(size.x * 0.85, size.y * 0.95), size.x * 0.35, Color(SbTheme.WARM, 0.025))
	for s in _stars:
		var depth := 0.15 + s.z * 0.35
		var sp := Vector2(fposmod(s.x * size.x - cam.x * depth * 0.3, size.x), fposmod(s.y * size.y - cam.y * depth * 0.3, size.y))
		var tw := 0.5 + 0.5 * sin(_t * (0.6 + s.z) + s.x * 40.0)
		draw_circle(sp, 0.8 + s.z * 1.3, Color(SbTheme.MINT_SOFT, 0.10 + 0.18 * tw * s.z))

	# Edges
	for e in edges:
		var a: Dictionary = nodes[e["from"]]
		var b: Dictionary = nodes[e["to"]]
		var pa := world_to_screen(a["pos"] as Vector2)
		var pb := world_to_screen(b["pos"] as Vector2)
		var grow := minf(_birth(a), _birth(b))
		var dim := _is_dim(str(e["from"])) or _is_dim(str(e["to"]))
		var type := str(e["type"])
		var col := SbTheme.FOREST_LIGHT
		var alpha := 0.22
		var width := 1.2
		if type == "link":
			col = SbTheme.MINT
			alpha = 0.55
			width = 1.8
		elif type == "tag":
			col = SbTheme.MUTED
			alpha = 0.16
		if dim:
			alpha *= 0.25
		elif hovered != "" and (str(e["from"]) == hovered or str(e["to"]) == hovered):
			alpha = minf(1.0, alpha * 2.2)
		var end := pa.lerp(pb, grow)
		draw_line(pa, end, Color(col, alpha * grow), width * clampf(zoom, 0.6, 1.4), true)
		if type == "link" and not dim and grow >= 1.0:
			var k := fmod(_t * 0.35 + float(hash(str(e["from"])) % 97) / 97.0, 1.0)
			draw_circle(pa.lerp(pb, k), 2.2, Color(SbTheme.MINT_SOFT, 0.75))

	# Nodes
	for id in nodes:
		var n: Dictionary = nodes[id]
		var p := world_to_screen(n["pos"] as Vector2)
		if p.x < -80 or p.y < -80 or p.x > size.x + 80 or p.y > size.y + 80:
			continue
		var g := _birth(n)
		var bloom := _ease_out_back(g)
		var r := _radius(n) * zoom * bloom
		var col := _color(n)
		var dim := _is_dim(str(id))
		var a := 0.28 if dim else 1.0
		var breathe := 0.5 + 0.5 * sin(_t * 1.3 + float(hash(str(id)) % 50))
		if g < 1.0:
			# Birth ripple
			draw_arc(p, _radius(n) * zoom * (1.0 + g * 3.5), 0, TAU, 48, Color(col, 0.6 * (1.0 - g)), 2.0, true)
			for k in 6:
				var ang := TAU * float(k) / 6.0 + g * 2.0
				draw_circle(p + Vector2.from_angle(ang) * r * (1.6 + g * 2.2), 2.0 * (1.0 - g), Color(SbTheme.MINT_SOFT, 1.0 - g))
		draw_circle(p, r * 2.2, Color(col, (0.05 + 0.06 * breathe) * a))
		match str(n["type"]):
			"space":
				draw_circle(p, r, Color(SbTheme.PANEL_2, 0.92 * a))
				draw_arc(p, r, 0, TAU, 64, Color(col, 0.95 * a), 2.5, true)
				draw_arc(p, r + 6.0 * zoom, _t * 0.4, _t * 0.4 + PI * 0.6, 32, Color(col, 0.45 * a), 1.5, true)
			"tag":
				draw_arc(p, r, 0, TAU, 24, Color(col, 0.8 * a), 1.5, true)
			_:
				draw_circle(p, r, Color(col, 0.95 * a))
				draw_circle(p + Vector2(-r * 0.3, -r * 0.3), r * 0.35, Color(1, 1, 1, 0.25 * a))
		if str(id) == selected:
			draw_arc(p, r + 7.0, 0, TAU, 48, SbTheme.MINT_SOFT, 2.0, true)
			draw_arc(p, r + 12.0 + 2.0 * breathe, 0, TAU, 48, Color(SbTheme.MINT_SOFT, 0.35), 1.5, true)
		_draw_label(n, p, r, dim)


func _draw_label(n: Dictionary, p: Vector2, r: float, dim: bool) -> void:
	var id := str(n["id"])
	var type := str(n["type"])
	var important := type == "space" or id == hovered or id == selected or highlight.has(id)
	var neighbor := hovered != "" and (_neighbors.get(hovered, {}) as Dictionary).has(id)
	if not (important or neighbor or (zoom >= 0.85 and type == "note")):
		return
	var text := str(n["label"])
	if text.length() > 34:
		text = text.left(32) + "…"
	var fs := 15 if type == "space" else 13
	var w := _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	var pos := p + Vector2(-w * 0.5, r + 16.0)
	var a := 0.35 if dim else (1.0 if important else 0.8)
	draw_string(_font, pos + Vector2(0, 1), text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs, Color(SbTheme.BG, 0.8 * a))
	draw_string(_font, pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs,
		Color(SbTheme.TEXT if type != "tag" else SbTheme.MUTED, a))


func _birth(n: Dictionary) -> float:
	return clampf((_t - float(n["born"])) / BIRTH_S, 0.0, 1.0)


static func _ease_out_back(x: float) -> float:
	var c1 := 1.70158
	var c3 := c1 + 1.0
	return 1.0 + c3 * pow(x - 1.0, 3.0) + c1 * pow(x - 1.0, 2.0)


# -------------------------------------------------------------------- input
func node_at(screen_pos: Vector2) -> String:
	var best := ""
	var best_d := 1e9
	for id in nodes:
		var n: Dictionary = nodes[id]
		var d := world_to_screen(n["pos"] as Vector2).distance_to(screen_pos)
		var r := maxf(_radius(n) * zoom, 10.0) + 4.0
		if d < r and d < best_d:
			best = str(id)
			best_d = d
	return best


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb: InputEventMouseButton = event
		if mb.button_index == MOUSE_BUTTON_WHEEL_UP or mb.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			if mb.pressed:
				var before := screen_to_world(mb.position)
				zoom = clampf(zoom * (1.12 if mb.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0 / 1.12), 0.35, 2.6)
				cam += before - screen_to_world(mb.position)
			accept_event()
		elif mb.button_index == MOUSE_BUTTON_LEFT:
			if mb.pressed:
				_press_pos = mb.position
				_moved = false
				_dragging_node = node_at(mb.position)
				_panning = _dragging_node == ""
				if mb.double_click and _dragging_node == "":
					create_tween().tween_property(self, "cam", Vector2.ZERO, 0.6).set_trans(Tween.TRANS_CUBIC)
			else:
				if not _moved:
					var hit := node_at(mb.position)
					if hit != "":
						var n: Dictionary = nodes[hit]
						selected = hit
						node_selected.emit(hit, str(n["type"]))
					else:
						background_clicked.emit()
				_dragging_node = ""
				_panning = false
			accept_event()
	elif event is InputEventMouseMotion:
		var mm: InputEventMouseMotion = event
		if mm.button_mask & MOUSE_BUTTON_MASK_LEFT:
			if mm.position.distance_to(_press_pos) > 4.0:
				_moved = true
			if _dragging_node != "" and _moved:
				var n: Dictionary = nodes[_dragging_node]
				n["pos"] = screen_to_world(mm.position)
				heat = maxf(heat, 0.6)
			elif _panning:
				cam -= mm.relative / zoom
		else:
			var h := node_at(mm.position)
			if h != hovered:
				hovered = h
				mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND if h != "" else Control.CURSOR_ARROW
				tooltip_text = ""
