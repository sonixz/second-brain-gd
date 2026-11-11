class_name GraphLayers3D
extends Control
## Layers in 3D (VIEW-F): the zones of the graph stacked in space, one plane per period, oldest at the bottom.
## An item sits on the plane of the moment it came in, above its place: a column of dots is a place growing
## through time. A showcase and a way to explore, not a place to work (owner, 2026-11-10): you turn, zoom and
## click; reading happens back in the 2D graph (double-click an item to land on it there).
##
## Input: drag = turn, wheel = zoom, click = select (item_selected), double-click = item_landed.
## Light without weight (VIEW-I): every item wears a soft halo, links glow and carry small signals, the far side
## fades into a light fog, stars sit behind, and a click flies the camera to the item. All of it is flat colours
## and additive sprites — no lights, no post-processing — so it still runs in GL Compatibility on any machine.

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
var playing := false             # the time cursor plays: arrivals pop, the camera rises with the brain
const POP_S := 0.9               # an arriving ball grows in with a little bounce
var _clock := 0.0
var _born: Dictionary = {}       # id -> _clock when it appeared (while a scene was already up)
var _known: Dictionary = {}      # ids of the scene before this one
var _home := Vector3.ZERO        # where the camera looks at rest
var _rise := 0.0                 # the height the play looks at: the plane of the latest arrival
const MAX_SIGNALS := 240         # links that carry a travelling signal
var glow := 1.0                  # how strong the halos and signals are (follows the theme's graph_glow, never off)
var _aim := Vector3.ZERO         # where the camera is going to look: it glides, it never jumps
var _aim_dist := 30.0
var _home_dist := 30.0
var _flown := false              # the camera flew to an item (a click on nothing brings it home)
var _zoomed := false             # the wheel was used: a rebuild keeps that distance
var _built := false
var _halos: MultiMeshInstance3D
var _signals: MultiMeshInstance3D
var _signal_ab: Array = []       # [from, to, phase, speed] for each signal
var _glow_tex: GradientTexture2D
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
var _date: Label                 # the large date of the time cursor, as in the 2D graph
var legend_x := 388.0            # left edge of the free area


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
	env.fog_enabled = true           # the far side of the scene fades a little: depth without any light
	env.fog_light_color = SbTheme.BG
	env.fog_density = 0.007
	env.fog_sky_affect = 0.0
	_glow_tex = GradientTexture2D.new()
	_glow_tex.fill = GradientTexture2D.FILL_RADIAL
	_glow_tex.fill_from = Vector2(0.5, 0.5)
	_glow_tex.fill_to = Vector2(1.0, 0.5)
	_glow_tex.width = 64
	_glow_tex.height = 64
	var fade := Gradient.new()
	fade.set_color(0, Color(1, 1, 1, 1))
	fade.set_color(1, Color(1, 1, 1, 0))
	fade.add_point(0.35, Color(1, 1, 1, 0.32))
	_glow_tex.gradient = fade
	_build_stars()
	_root = Node3D.new()
	_viewport.add_child(_root)
	_tip = Label.new()
	_tip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_tip.add_theme_stylebox_override("normal", SbTheme.box(SbTheme.PANEL, 8, SbTheme.BORDER, 1, 8))
	_tip.visible = false
	add_child(_tip)
	_date = Label.new()
	_date.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_date.add_theme_font_size_override("font_size", SbTheme.fs(46))
	_date.position = Vector2(legend_x + 6.0, 196.0)
	add_child(_date)
	_place_camera()


## A soft round sprite that always faces the camera and adds its light to what is behind it.
func _sprite_material() -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	m.blend_mode = BaseMaterial3D.BLEND_MODE_ADD
	m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	m.billboard_mode = BaseMaterial3D.BILLBOARD_ENABLED
	m.billboard_keep_scale = true
	m.albedo_texture = _glow_tex
	m.vertex_color_use_as_albedo = true
	m.depth_draw_mode = BaseMaterial3D.DEPTH_DRAW_DISABLED
	m.disable_fog = true
	return m


func _sprites(count: int, quad_size: float) -> MultiMeshInstance3D:
	var quad := QuadMesh.new()
	quad.size = Vector2.ONE * quad_size
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.use_colors = true
	mm.mesh = quad
	mm.instance_count = count
	var mi := MultiMeshInstance3D.new()
	mi.multimesh = mm
	mi.material_override = _sprite_material()
	return mi


## Stars far behind the scene: they slide as it turns, which gives the depth. Always the same sky.
func _build_stars() -> void:
	var rng := RandomNumberGenerator.new()
	rng.seed = 2026
	var stars := _sprites(320, 1.0)
	for i in 320:
		var dir := Vector3(rng.randfn(), rng.randfn() * 0.7, rng.randfn()).normalized()
		var big := rng.randf() < 0.12
		stars.multimesh.set_instance_transform(i, Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * (2.6 if big else rng.randf_range(0.7, 1.5))), dir * rng.randf_range(170.0, 300.0)))
		stars.multimesh.set_instance_color(i, Color(SbTheme.MINT_SOFT, rng.randf_range(0.25, 0.9 if big else 0.6)))
	stars.extra_cull_margin = 1000.0
	_viewport.add_child(stars)


## Builds the scene from the 2D graph as it is now: its places, the items its filters and time cursor show,
## their links. Items keep the place they have in the Zones view.
func show_graph(graph: GraphView) -> void:
	for c in _root.get_children():
		_root.remove_child(c)
		c.queue_free()
	layers.clear()
	items.clear()
	_date.position.x = legend_x + 6.0
	_date.text = ""
	if graph.time_cursor >= 0.0:
		var d := Time.get_datetime_dict_from_unix_time(int(graph.time_cursor) + int(Time.get_time_zone_from_system().get("bias", 0)) * 60)
		_date.text = "%02d · %02d · %04d" % [d["day"], d["month"], d["year"]]
	_date.modulate = Color(SbTheme.TEXT, 0.34 if playing else 0.2)
	var notes: Array = []
	for id in graph.nodes:
		var n: Dictionary = graph.nodes[id]
		if str(n["type"]) == "note" and graph.is_shown(str(id)):
			notes.append([str(id), GraphView._unix(str(n.get("created_at", "")))])
	var span := graph.time_span()  # the whole brain's life: the planes stay put while filters or the time cursor hide items
	if span.is_empty():
		_place_camera()
		return
	if _known.is_empty() and playing:
		_known = {"": true}  # the play starts from nothing: the very first items pop too
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
	var any_bound := false
	for id in graph.nodes:  # the frame holds every item and place, shown or not: it does not move while time plays
		var n: Dictionary = graph.nodes[id]
		if str(n["type"]) in ["note", "space"]:
			var at: Vector2 = (n["pos"] as Vector2) * SCALE
			bounds = bounds.expand(at) if any_bound else Rect2(at, Vector2.ZERO)
			any_bound = true
	var index: Dictionary = {}
	var seen: Dictionary = {}
	for pair in notes:
		var n: Dictionary = graph.nodes[pair[0]]
		var flat: Vector2 = (n["pos"] as Vector2) * SCALE
		var layer := clampi(int((float(pair[1]) - first) / slice), 0, count - 1)
		(layers[layer] as Dictionary)["count"] = int(layers[layer]["count"]) + 1
		index[pair[0]] = items.size()
		seen[pair[0]] = true
		if not _known.is_empty() and not _known.has(pair[0]):  # it just came in: it pops, and the play looks at its plane
			_born[pair[0]] = _clock
			_rise = layer * GAP
		items.append({"id": pair[0], "label": str(n["label"]), "layer": layer, "col": graph._color(n),
			"pos": Vector3(flat.x, layer * GAP, flat.y)})
	var places: Array = []
	for id in graph.nodes:
		var n: Dictionary = graph.nodes[id]
		if str(n["type"]) == "space" and graph.is_shown(str(id)):
			var flat: Vector2 = (n["pos"] as Vector2) * SCALE
			places.append([str(n["label"]), flat, graph._color(n)])
	bounds = bounds.grow(2.5)
	_known = seen
	glow = clampf(0.5 + 0.5 * graph._glow, 0.5, 1.6)
	_home = Vector3(bounds.get_center().x, (count - 1) * GAP * 0.5, bounds.get_center().y)
	var free_w := maxf(400.0, size.x - absf(screen_offset.x) * 2.0 - 80.0)  # the scene fits the room the panels leave
	_home_dist = clampf((maxf(bounds.size.x, bounds.size.y) * 0.95 + count * GAP) * clampf(size.x / free_w, 1.0, 2.2), 12.0, 260.0)
	if not _flown:
		_aim = Vector3(_home.x, _rise if playing else _home.y, _home.z)
		if not _zoomed:
			_aim_dist = _home_dist
	if not _built:  # the first scene is simply there; after that the camera glides
		_centre = _aim
		distance = _aim_dist
		_built = true
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
		var grown := 0.01 if _born.has(items[i]["id"]) else 1.0  # an arrival starts small; _process grows it
		mm.set_instance_transform(i, Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * grown), items[i]["pos"]))
		mm.set_instance_color(i, items[i]["col"])
	_dots = MultiMeshInstance3D.new()
	_dots.multimesh = mm
	_dots.material_override = _flat(Color.WHITE, true)
	_root.add_child(_dots)
	# A halo around each ball, in its colour.
	_halos = _sprites(items.size(), 2.6)
	for i in items.size():
		var grown := 0.01 if _born.has(items[i]["id"]) else 1.0
		_halos.multimesh.set_instance_transform(i, Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * grown), items[i]["pos"]))
		_halos.multimesh.set_instance_color(i, Color(items[i]["col"], 0.42 * glow))
	_root.add_child(_halos)


## Real links (clear) and related ideas (warm, fainter), across the planes: a line climbing is an idea coming back.
func _build_links(graph: GraphView, index: Dictionary) -> void:
	_signal_ab.clear()
	var signal_cols: Array = []
	for kind in ["link", "related"]:
		var mesh := ImmediateMesh.new()
		var any := false
		for e in graph.edges:
			if str(e["type"]) == kind and index.has(e["from"]) and index.has(e["to"]):
				if not any:
					mesh.surface_begin(Mesh.PRIMITIVE_LINES)
					any = true
				var a: Vector3 = items[index[e["from"]]]["pos"]
				var b: Vector3 = items[index[e["to"]]]["pos"]
				mesh.surface_add_vertex(a)
				mesh.surface_add_vertex(b)
				if _signal_ab.size() < MAX_SIGNALS:  # a small light travels along the link, each at its own pace
					var n := _signal_ab.size()
					_signal_ab.append([a, b, fmod(n * 0.37, 1.0), 0.16 + 0.07 * fmod(n * 0.61, 1.0)])
					signal_cols.append(Color(SbTheme.MINT_SOFT if kind == "link" else SbTheme.WARM, (0.85 if kind == "link" else 0.6) * glow))
		if not any:
			continue
		mesh.surface_end()
		var mi := MeshInstance3D.new()
		mi.mesh = mesh
		var line := _flat(Color(SbTheme.MINT, 0.6) if kind == "link" else Color(SbTheme.WARM, 0.34))
		line.blend_mode = BaseMaterial3D.BLEND_MODE_ADD  # crossing links add up: the busy places shine
		mi.material_override = line
		_root.add_child(mi)
		if kind == "link":
			_lines = mi
	_signals = _sprites(_signal_ab.size(), 0.55)
	for i in _signal_ab.size():
		_signals.multimesh.set_instance_color(i, signal_cols[i])
	_root.add_child(_signals)
	_move_signals()


func _move_signals() -> void:
	if _signals == null:
		return
	for i in _signal_ab.size():
		var s: Array = _signal_ab[i]
		var k := fmod(_clock * float(s[3]) + float(s[2]), 1.0)
		_signals.multimesh.set_instance_transform(i, Transform3D(Basis.IDENTITY, (s[0] as Vector3).lerp(s[1], smoothstep(0.0, 1.0, k))))


## The camera glides to an item and comes closer; fly_home() brings it back.
func fly_to(id: String) -> void:
	for it in items:
		if str(it["id"]) == id:
			_flown = true
			spinning = false
			_aim = it["pos"]
			_aim_dist = clampf(_home_dist * 0.42, 9.0, 60.0)


func fly_home() -> void:
	_flown = false
	_zoomed = false
	_aim = _home
	_aim_dist = _home_dist


func _place_camera() -> void:
	pitch = clampf(pitch, 0.05, 1.45)
	var dir := Vector3(cos(pitch) * sin(yaw), sin(pitch), cos(pitch) * cos(yaw))
	_camera.position = _centre + dir * distance
	_camera.look_at(_centre, Vector3.UP)
	# The scene's centre sits in the middle of the free area, a little below the toolbars.
	var per_px := 2.0 * distance * tan(deg_to_rad(_camera.fov) * 0.5) / maxf(size.y, 1.0)
	_camera.h_offset = -screen_offset.x * per_px
	_camera.v_offset = 36.0 * per_px


## The play starts or stops: while it plays the scene turns and the camera rises with the latest arrivals.
func set_playing(on: bool) -> void:
	playing = on
	_flown = false
	if on:
		spinning = true
		_rise = 0.0
	else:
		_aim = _home


func _process(delta: float) -> void:
	if not is_visible_in_tree():
		return
	_clock += delta
	if playing and not _flown:
		_aim.y = _rise
	var moving := _centre.distance_to(_aim) > 0.01 or absf(distance - _aim_dist) > 0.01
	if moving:
		var k := minf(1.0, delta * (1.6 if playing else 3.2))
		_centre = _centre.lerp(_aim, k)
		distance = lerpf(distance, _aim_dist, k)
	if spinning:
		yaw += delta * SPIN
	if spinning or moving:
		_place_camera()
	_move_signals()
	if _halo != null and _halo.visible:  # the selected item's ring breathes
		_halo.scale = Vector3.ONE * (1.0 + 0.12 * sin(_clock * 3.0))
	if not _born.is_empty() and _dots != null:  # arrivals grow in
		for i in items.size():
			var id: String = items[i]["id"]
			if _born.has(id):
				var k := clampf((_clock - float(_born[id])) / POP_S, 0.0, 1.0)
				_dots.multimesh.set_instance_transform(i, Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * GraphView._ease_out_back(k) * (1.0 + 0.9 * (1.0 - k))), items[i]["pos"]))
				# its halo flashes wide, then settles
				_halos.multimesh.set_instance_transform(i, Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * (1.0 + 2.6 * (1.0 - k)) * minf(1.0, k * 6.0)), items[i]["pos"]))
				if k >= 1.0:
					_born.erase(id)


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
			_zoomed = true
			_aim_dist = clampf(_aim_dist * (1.0 / 1.15 if mb.button_index == MOUSE_BUTTON_WHEEL_UP else 1.15), 6.0, 260.0)
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
					fly_to(hit)  # the camera glides to it; a click on nothing flies home
					item_selected.emit(hit)
				else:
					fly_home()
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
