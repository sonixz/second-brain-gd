class_name GraphLayers3D
extends Control
## Layers in 3D (VIEW-F): the zones of the graph stacked in space, one plane per period, oldest at the bottom.
## An item sits on the plane of the moment it came in, above its place: a column of dots is a place growing
## through time. A showcase and a way to explore, not a place to work (owner, 2026-11-10): you turn, zoom and
## click; reading happens back in the 2D graph (double-click an item to land on it there).
##
## Input: drag = turn, wheel = zoom, click = select (item_selected), double-click = item_landed.
## Sober on purpose: unshaded colours, no lights, no effects — it runs in GL Compatibility on any machine.

signal item_selected(id: String)
signal item_landed(id: String)

const SCALE := 0.01            # graph world units -> 3D units
const GAP := 4.6               # height between two planes
const MAX_LAYERS := 5
const PICK_PX := 16.0
const SPIN := 0.12             # radians per second, until you touch it

var layers: Array = []         # [{t0, t1, label, y, count}], oldest first
var items: Array = []          # [{id, pos: Vector3, label, layer}]
var selected := ""
var hovered := ""
var yaw := 0.6
var pitch := 0.42
var distance := 30.0
var spinning := true
var screen_offset := Vector2.ZERO   # centre of the free area, as for the 2D graph (docked panels cover the sides)

var _viewport: SubViewport
var _camera: Camera3D
var _root: Node3D
var _dots: MultiMeshInstance3D
var _lines: MeshInstance3D
var _halo: MeshInstance3D
var _centre := Vector3.ZERO
var _press := Vector2.ZERO
var _moved := false
var _tip: Label


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_STOP
	var box := SubViewportContainer.new()
	box.stretch = true
	box.set_anchors_preset(Control.PRESET_FULL_RECT)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(box)
	_viewport = SubViewport.new()
	_viewport.own_world_3d = true
	_viewport.msaa_3d = Viewport.MSAA_4X
	box.add_child(_viewport)
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = SbTheme.BG
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color.WHITE
	var world_env := WorldEnvironment.new()
	world_env.environment = env
	_viewport.add_child(world_env)
	_camera = Camera3D.new()
	_camera.fov = 42.0
	_camera.far = 400.0
	_viewport.add_child(_camera)
	_root = Node3D.new()
	_viewport.add_child(_root)
	_tip = Label.new()
	_tip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_tip.add_theme_stylebox_override("normal", SbTheme.box(SbTheme.PANEL, 8, SbTheme.BORDER, 1, 8))
	_tip.visible = false
	add_child(_tip)
	_place_camera()


## Builds the scene from the 2D graph as it is now: its places, the items its filters and time cursor show,
## their links. Items keep the place they have in the Zones view.
func show_graph(graph: GraphView) -> void:
	for c in _root.get_children():
		_root.remove_child(c)
		c.queue_free()
	layers.clear()
	items.clear()
	var notes: Array = []
	for id in graph.nodes:
		var n: Dictionary = graph.nodes[id]
		if str(n["type"]) == "note" and graph.is_shown(str(id)):
			notes.append([str(id), GraphView._unix(str(n.get("created_at", "")))])
	var span := graph.time_span()  # the whole brain's life: the planes stay put while filters or the time cursor hide items
	if notes.is_empty() or span.is_empty():
		_place_camera()
		return
	var first: float = span[0]
	var last: float = span[1]
	# Planes: equal slices of the brain's life (one plane when everything came in the same day).
	var days := (last - first) / 86400.0
	var count := 1 if days < 1.0 else (3 if days < 5.0 else MAX_LAYERS)
	var slice := maxf((last - first) / count, 1.0)
	for i in count:
		var t0 := first + slice * i
		layers.append({"t0": t0, "t1": t0 + slice, "y": i * GAP, "count": 0,
			"label": _day(t0) if count == 1 or _day(t0) == _day(t0 + slice) else "%s – %s" % [_day(t0), _day(t0 + slice)]})
	var bounds := Rect2()
	var index: Dictionary = {}
	for pair in notes:
		var n: Dictionary = graph.nodes[pair[0]]
		var flat: Vector2 = (n["pos"] as Vector2) * SCALE
		var layer := clampi(int((float(pair[1]) - first) / slice), 0, count - 1)
		(layers[layer] as Dictionary)["count"] = int(layers[layer]["count"]) + 1
		index[pair[0]] = items.size()
		items.append({"id": pair[0], "label": str(n["label"]), "layer": layer, "col": graph._color(n),
			"pos": Vector3(flat.x, layer * GAP, flat.y)})
		bounds = Rect2(flat, Vector2.ZERO) if items.size() == 1 else bounds.expand(flat)
	var places: Array = []
	for id in graph.nodes:
		var n: Dictionary = graph.nodes[id]
		if str(n["type"]) == "space" and graph.is_shown(str(id)):
			var flat: Vector2 = (n["pos"] as Vector2) * SCALE
			places.append([str(n["label"]), flat, graph._color(n)])
			bounds = bounds.expand(flat)
	bounds = bounds.grow(2.5)
	_centre = Vector3(bounds.get_center().x, (count - 1) * GAP * 0.5, bounds.get_center().y)
	var free_w := maxf(400.0, size.x - absf(screen_offset.x) * 2.0 - 80.0)  # the scene fits the room the panels leave
	distance = clampf((maxf(bounds.size.x, bounds.size.y) * 0.95 + count * GAP) * clampf(size.x / free_w, 1.0, 2.2), 12.0, 260.0)
	_build_planes(bounds)
	_build_places(places, count)
	_build_dots()
	_build_links(graph, index)
	_halo = MeshInstance3D.new()
	var ring := TorusMesh.new()
	ring.inner_radius = 0.42
	ring.outer_radius = 0.52
	ring.rings = 24
	ring.ring_segments = 6
	_halo.mesh = ring
	_halo.material_override = _flat(SbTheme.MINT_SOFT)
	_halo.visible = false
	_root.add_child(_halo)
	select(selected)
	_place_camera()


func _day(t: float) -> String:
	var d := Time.get_datetime_dict_from_unix_time(int(t) + int(Time.get_time_zone_from_system().get("bias", 0)) * 60)
	return "%02d/%02d" % [d["day"], d["month"]]


func _flat(col: Color, per_item := false) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.albedo_color = col
	m.vertex_color_use_as_albedo = per_item
	if col.a < 1.0:
		m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		m.cull_mode = BaseMaterial3D.CULL_DISABLED
	return m


func _text(text: String, at: Vector3, col: Color, px: int) -> void:
	var l := Label3D.new()
	l.text = text
	l.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	l.no_depth_test = true
	l.fixed_size = true
	l.pixel_size = 0.00045
	l.font_size = px * 2
	l.outline_size = 10
	l.modulate = col
	l.outline_modulate = Color(SbTheme.BG, 0.9)
	l.position = at
	_root.add_child(l)


## One faint sheet per period, its edge drawn, its dates at a corner.
func _build_planes(bounds: Rect2) -> void:
	var edge := ImmediateMesh.new()
	edge.surface_begin(Mesh.PRIMITIVE_LINES)
	for layer in layers:
		var y: float = layer["y"]
		var sheet := MeshInstance3D.new()
		var quad := PlaneMesh.new()
		quad.size = bounds.size
		sheet.mesh = quad
		sheet.material_override = _flat(Color(SbTheme.FOREST_LIGHT, 0.07))
		sheet.position = Vector3(bounds.get_center().x, y - 0.02, bounds.get_center().y)
		_root.add_child(sheet)
		var corners := [Vector3(bounds.position.x, y, bounds.position.y), Vector3(bounds.end.x, y, bounds.position.y),
			Vector3(bounds.end.x, y, bounds.end.y), Vector3(bounds.position.x, y, bounds.end.y)]
		for i in 4:
			edge.surface_add_vertex(corners[i])
			edge.surface_add_vertex(corners[(i + 1) % 4])
		_text("%s · %d" % [layer["label"], layer["count"]], corners[3] + Vector3(-0.4, 0.0, 0.4), SbTheme.MUTED, 13)
	edge.surface_end()
	var outline := MeshInstance3D.new()
	outline.mesh = edge
	outline.material_override = _flat(Color(SbTheme.BORDER, 0.9))
	_root.add_child(outline)


## A place is a column through the planes, named at its top.
func _build_places(places: Array, count: int) -> void:
	if places.is_empty():
		return
	var top := (count - 1) * GAP
	var columns := ImmediateMesh.new()
	columns.surface_begin(Mesh.PRIMITIVE_LINES)
	for p in places:
		var flat: Vector2 = p[1]
		columns.surface_add_vertex(Vector3(flat.x, 0.0, flat.y))
		columns.surface_add_vertex(Vector3(flat.x, top + 0.9, flat.y))
		_text(str(p[0]), Vector3(flat.x, top + 1.4, flat.y), (p[2] as Color).lerp(SbTheme.TEXT, 0.35), 14)
	columns.surface_end()
	var mi := MeshInstance3D.new()
	mi.mesh = columns
	mi.material_override = _flat(Color(SbTheme.FOREST_LIGHT, 0.35))
	_root.add_child(mi)


## Every item as a small ball in its colour: one draw call, whatever their number.
func _build_dots() -> void:
	var ball := SphereMesh.new()
	ball.radius = 0.27
	ball.height = 0.54
	ball.radial_segments = 12
	ball.rings = 6
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = ball
	mm.instance_count = items.size()
	for i in items.size():
		mm.set_instance_transform(i, Transform3D(Basis.IDENTITY, items[i]["pos"]))
		mm.set_instance_color(i, items[i]["col"])
	_dots = MultiMeshInstance3D.new()
	_dots.multimesh = mm
	_dots.material_override = _flat(Color.WHITE, true)
	_root.add_child(_dots)


## Real links (clear) and related ideas (warm, fainter), across the planes: a line climbing is an idea coming back.
func _build_links(graph: GraphView, index: Dictionary) -> void:
	for kind in ["link", "related"]:
		var mesh := ImmediateMesh.new()
		var any := false
		for e in graph.edges:
			if str(e["type"]) == kind and index.has(e["from"]) and index.has(e["to"]):
				if not any:
					mesh.surface_begin(Mesh.PRIMITIVE_LINES)
					any = true
				mesh.surface_add_vertex(items[index[e["from"]]]["pos"])
				mesh.surface_add_vertex(items[index[e["to"]]]["pos"])
		if not any:
			continue
		mesh.surface_end()
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		mi.material_override = _flat(Color(SbTheme.MINT, 0.55) if kind == "link" else Color(SbTheme.WARM, 0.3))
		_root.add_child(mi)
		if kind == "link":
			_lines = mi


func _place_camera() -> void:
	pitch = clampf(pitch, 0.05, 1.45)
	var dir := Vector3(cos(pitch) * sin(yaw), sin(pitch), cos(pitch) * cos(yaw))
	_camera.position = _centre + dir * distance
	_camera.look_at(_centre, Vector3.UP)
	# The scene's centre sits in the middle of the free area, a little below the toolbars.
	var per_px := 2.0 * distance * tan(deg_to_rad(_camera.fov) * 0.5) / maxf(size.y, 1.0)
	_camera.h_offset = -screen_offset.x * per_px
	_camera.v_offset = 36.0 * per_px


func _process(delta: float) -> void:
	if not is_visible_in_tree():
		return
	if spinning:
		yaw += delta * SPIN
		_place_camera()


func select(id: String) -> void:
	selected = id
	if _halo == null:
		return
	_halo.visible = false
	for it in items:
		if str(it["id"]) == id:
			_halo.position = it["pos"]
			_halo.visible = true


## Where an item is on the screen (for picking, and for the tests).
func screen_of(id: String) -> Vector2:
	for it in items:
		if str(it["id"]) == id:
			return _camera.unproject_position(it["pos"]) * (size / Vector2(_viewport.size))
	return Vector2.INF


## The item under a screen point: the closest one within a few pixels, in front of the camera.
func item_at(screen_pos: Vector2) -> String:
	var best := ""
	var best_d := PICK_PX
	var to_screen := size / Vector2(_viewport.size)
	for it in items:
		if _camera.is_position_behind(it["pos"]):
			continue
		var d := (_camera.unproject_position(it["pos"]) * to_screen).distance_to(screen_pos)
		if d < best_d:
			best = str(it["id"])
			best_d = d
	return best


func _gui_input(event: InputEvent) -> void:
	if event is InputEventMouseButton:
		var mb: InputEventMouseButton = event
		if mb.pressed and mb.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN]:
			spinning = false
			distance = clampf(distance * (1.0 / 1.15 if mb.button_index == MOUSE_BUTTON_WHEEL_UP else 1.15), 6.0, 260.0)
			_place_camera()
		elif mb.button_index == MOUSE_BUTTON_LEFT:
			if mb.pressed:
				spinning = false
				_press = mb.position
				_moved = false
				if mb.double_click and item_at(mb.position) != "":
					item_landed.emit(item_at(mb.position))
			elif not _moved:
				var hit := item_at(mb.position)
				select(hit)
				if hit != "":
					item_selected.emit(hit)
		accept_event()
	elif event is InputEventMouseMotion:
		var mm: InputEventMouseMotion = event
		if mm.button_mask & MOUSE_BUTTON_MASK_LEFT:
			if mm.position.distance_to(_press) > 4.0:
				_moved = true
			yaw -= mm.relative.x * 0.006
			pitch += mm.relative.y * 0.006
			_place_camera()
		else:
			var h := item_at(mm.position)
			if h != hovered:
				hovered = h
				mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND if h != "" else Control.CURSOR_ARROW
				_tip.visible = h != ""
				for it in items:
					if str(it["id"]) == h:
						_tip.text = str(it["label"])
			_tip.position = mm.position + Vector2(14, 14)
