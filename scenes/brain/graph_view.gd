class_name GraphView
extends Control
## The living knowledge graph: force-directed layout, pan/zoom camera, nodes
## that bloom when born, links that pulse, neighbours that light up on hover.
##
## Input: wheel = zoom, drag empty space = pan, drag a node = move it,
## click = select (signal node_selected), double-click empty = recentre.
##
## Semantic zoom (Loop 10): the closer you get, the more each item tells you.
##   far   (< 0.55)  places as named clusters, items as points
##   mid             circles with titles (the classic graph)
##   near  (>= 2.2)  items become cards: title, place, themes, summary
##   read  (>= 6)    the card shows the item's full text, at a readable size
## Card content comes from details_needed -> set_details (fetched by the brain screen).

signal node_selected(id: String, type: String)
signal background_clicked
signal details_needed(id: String)
signal page_needed(id: String, source_id: String, width: int)
signal node_activated(id: String)
signal item_dropped_on_place(id: String, space_id: String)  # an item dragged into another place's zone

const REPULSION := 5200.0
const SPRING := 0.035
const DAMPING := 0.86
const GRAVITY := 0.012
const HOME_PULL := 0.08            # an item's pull back into its own place's zone (Loop 13 zones)
const COLLIDE := 74.0              # two items closer than this push apart firmly (a card is 64 × 44)
const ZONE_FREE := 150.0           # inside this distance from its place, an item moves freely
const BIRTH_S := 1.1
const REST := {"space": 110.0, "link": 120.0, "tag": 85.0, "related": 150.0}
const ZOOM_MIN := 0.15
const ZOOM_MAX := 40.0
const FAR := 0.55
const NEAR := 2.2
const READ := 6.0
const CARD := Vector2(64.0, 44.0)   # a card's size in world units

var nodes: Dictionary = {}      # id -> Dictionary (see _make_node)
var edges: Array[Dictionary] = []
var selected := ""
var hovered := ""
var highlight: Dictionary = {}  # id -> true; empty = no filter
var cam := Vector2.ZERO          # world point at the centre of the view
var zoom := 1.0
var heat := 1.0
var _heat_goal := 0.0      # a gentle wake-up: heat rises to this over a moment instead of jumping (Loop 37)
var _sim_acc := 0.0        # time not yet simulated: the layout advances in fixed 1/60 s steps at any frame rate
var _t := 0.0
var _dragging_node := ""
var _panning := false
var _press_pos := Vector2.ZERO
var _moved := false
var _stars: Array[Vector3] = []
var _font: Font
var _neighbors: Dictionary = {}
var details: Dictionary = {}     # id -> {summary, place, themes, body, item_type}
var _asked: Dictionary = {}
var _zoom_tween: Tween
var show_minimap := true
var anchors: Dictionary = {}         # space node id -> its zone's centre (Loop 13)
var custom_anchors: Dictionary = {}  # zones the user moved by dragging a place
var zone_reach: Dictionary = {}      # space node id -> its zone's radius in world units, as last drawn
var show_legend := false
var legend_x := 388.0          # left edge of the free area (docked panels move it)
var right_inset := 0.0         # width taken by panels docked on the right: the minimap stays clear of them
var folded: Dictionary = {}          # space node id -> true when its items are folded in
var filter: Dictionary = {}
var filtered_out: Dictionary = {}          # node id -> true when filtered out or folded in
var _note_tags: Dictionary = {}
var path_ids: Array = []
const CELL := 100.0
const CROWD := 4                  # a neighbouring cell with more items than this pushes as one body
const CROWD_FROM := 600           # ... only in big graphs: below this, every push is exact, so nothing jolts
const SIM_DT := 1.0 / 60.0        # one layout step
const MAX_SPEED := 9.0            # world units per step: the graph glides, it never jumps
const REST_SPEED := 0.04          # below this, once cooled, an item stops instead of trembling
const NOTE_FIELDS := ["item_type", "origin", "created_at", "updated_at"]
const DENSE := 350                # beyond this many items on screen, draw lighter (no halos, fewer labels)
var _dense := false
var _mini_at := -1.0
var _mini_pts := PackedVector2Array()
var _mini_col := PackedColorArray()
var _mini_tr: Array = []
var _mini_tr_at := -1.0
var graph_layout := "zones"
var _tl_lanes: Dictionary = {}   # place id -> lane y
var _tl_t0 := 0.0
var _tl_t1 := 1.0
var _tl_width := 1400.0               # repulsion only reaches the 3×3 cells around an item
var _sim_ids: Array[String] = []
var _sim_index: Dictionary = {}
var _sim_space := PackedByteArray()
var _sim_spaces := PackedInt32Array()
var _sim_home := PackedInt32Array()      # item index -> its place index, -1 for places and tags
var _edge_a := PackedInt32Array()
var _edge_b := PackedInt32Array()
var _edge_rest := PackedFloat32Array()
var _edge_src := PackedInt32Array()     # index into `edges`
var _edge_kind := PackedByteArray()   # 0 structural (place, area, tag), 1 link, 2 related idea
var _sim_pos := PackedVector2Array()
var _sim_col := PackedColorArray()
var _sim_born := PackedFloat32Array()
var path_steps: Array = []
var page_tex: Dictionary = {}     # id -> {"w": int, "tex": Texture2D} (first page of a document)
var _page_asked: Dictionary = {}  # id -> width asked
var screen_offset := Vector2.ZERO  # centre of the free area (panels cover the left side)
var follow := ""           # the camera stays on this node (after « zoome sur X ») until you pan


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
	var before := nodes.size()
	var before_edges := _edge_signature()
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
			existing["layer"] = src.get("layer")
			for key in NOTE_FIELDS:
				if src.has(key):
					existing[key] = src[key]
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
	for id in nodes:
		(nodes[id] as Dictionary)["_col"] = _color(nodes[id])
	_layout_anchors()
	# On first load, places and items start in their zones rather than in a random ring.
	if first_load:
		for id in nodes:
			var n: Dictionary = nodes[id]
			if anchors.has(id):
				n["pos"] = anchors[id] as Vector2
		for id in nodes:
			var n: Dictionary = nodes[id]
			var hub := "space:" + str(n.get("space_id", ""))
			if str(n["type"]) == "note" and anchors.has(hub):
				n["pos"] = (anchors[hub] as Vector2) + Vector2.from_angle(randf() * TAU) * (60.0 + randf() * 80.0)
	_update_shown()
	if graph_layout == "timeline":
		_timeline_targets()
	# A periodic refresh with nothing new leaves the graph at rest; a change wakes it gently.
	if first_load:
		heat = 1.0
	elif not born.is_empty() or nodes.size() != before or _edge_signature() != before_edges:
		reheat(0.3)
	return born


## Wakes the layout softly (a filter, a fold, a new item): heat climbs to this over about half a second.
func reheat(h: float) -> void:
	_heat_goal = maxf(_heat_goal, h)


func _edge_signature() -> int:
	var parts := PackedStringArray()
	for e in edges:
		parts.append("%s>%s:%s" % [e["from"], e["to"], e["type"]])
	parts.sort()
	return hash(",".join(parts))


func _make_node(src: Dictionary, i: int, total: int, first_load: bool) -> Dictionary:
	var type := str(src.get("type", "note"))
	var angle := TAU * float(i) / maxf(1.0, float(total)) + randf() * 0.3
	var radius := 120.0 if type == "space" else 260.0 + randf() * 120.0
	var n := {
		"id": str(src["id"]), "type": type, "label": str(src.get("label", "")), "kind": str(src.get("kind", "")),
		"space_id": str(src.get("space_id", "")), "weight": int(src.get("weight", 0)), "color": src.get("color"),
		"layer": src.get("layer"),
		"pos": Vector2.from_angle(angle) * radius, "vel": Vector2.ZERO,
		"born": (_t - BIRTH_S * randf() * 0.6) if first_load else _t, "pinned": false,
	}
	for key in NOTE_FIELDS:  # what the filters and the timeline read
		if src.has(key):
			n[key] = src[key]
	return n


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


func set_details(id: String, d: Dictionary) -> void:
	details[id] = d
	queue_redraw()


func set_page(id: String, width: int, tex: Texture2D) -> void:
	var cur: Dictionary = page_tex.get(id, {})
	if int(cur.get("w", 0)) < width:
		page_tex[id] = {"w": width, "tex": tex}
	queue_redraw()


## Zoom smoothly to a level, optionally centring on a world point.
func zoom_to(level: float, world_center: Variant = null, seconds: float = 0.45) -> void:
	var target := clampf(level, ZOOM_MIN, ZOOM_MAX)
	if _zoom_tween != null and _zoom_tween.is_valid():
		_zoom_tween.kill()
	_zoom_tween = create_tween().set_parallel().set_trans(Tween.TRANS_CUBIC).set_ease(Tween.EASE_OUT)
	_zoom_tween.tween_property(self, "zoom", target, seconds)
	if world_center is Vector2:
		_zoom_tween.tween_property(self, "cam", (world_center as Vector2) - screen_offset / target, seconds)


## Voice and buttons: "overview", "out", "closer", "read" (optionally on one node).
func zoom_level(level: String, id: String = "") -> void:
	var center: Variant = (nodes[id]["pos"] as Vector2) if id != "" and nodes.has(id) else null
	follow = id if id != "" and nodes.has(id) and level in ["closer", "read"] else ""
	match level:
		"overview":
			zoom_to(0.4, Vector2.ZERO if center == null else center)
		"out":
			zoom_to(zoom / 2.0, center)
		"closer":
			zoom_to(maxf(zoom * 2.0, NEAR + 0.2), center)
		"read":
			if id != "":
				selected = id
			zoom_to(READ + 3.0, center, 0.8)
		_:
			zoom_to(1.0, center)


## The node whose label matches best (exact, then starts with, then contains); tags rank last.
func find_node(text: String) -> String:
	var q := text.strip_edges().to_lower()
	if q == "":
		return ""
	var best := ""
	var best_score := 0
	for id in nodes:
		var n: Dictionary = nodes[id]
		var label := str(n["label"]).to_lower()
		var score := 0
		if label == q:
			score = 3
		elif label.begins_with(q):
			score = 2
		elif label.contains(q):
			score = 1
		if score > 0 and str(n["type"]) == "tag":
			score -= 1
		if score > best_score:
			best = str(id)
			best_score = score
	return best


func lod() -> String:
	if zoom < FAR:
		return "far"
	if zoom >= READ:
		return "read"
	if zoom >= NEAR:
		return "near"
	return "mid"


# ------------------------------------------------------------ organisation (Loop 13)
## Each place has a stable zone: the Inbox in the middle, the other places on rings around it,
## grouped by kind (projects, areas, resources, archive). Items gravitate to their place.
func _layout_anchors() -> void:
	anchors.clear()
	var order := {"project": 0, "area": 1, "resource": 2, "archive": 3}
	var places: Array = []
	for id in nodes:
		var n: Dictionary = nodes[id]
		if str(n["type"]) != "space":
			continue
		if str(n["kind"]) == "inbox":
			anchors[id] = Vector2.ZERO
		else:
			places.append(n)
	places.sort_custom(func(a: Dictionary, b: Dictionary) -> bool:
		var ka: int = order.get(str(a["kind"]), 9)
		var kb: int = order.get(str(b["kind"]), 9)
		if ka != kb:
			return ka < kb
		return str(a["label"]).naturalnocasecmp_to(str(b["label"])) < 0)
	var per_ring := 10
	for i in places.size():
		var ring := i / per_ring
		var in_ring := mini(per_ring, places.size() - ring * per_ring)
		var angle := TAU * float(i % per_ring) / float(in_ring) - PI / 2.0 + ring * 0.3
		var radius := maxf(420.0, float(in_ring) * 400.0 / TAU) + ring * 380.0
		var n: Dictionary = places[i]
		anchors[str(n["id"])] = custom_anchors.get(str(n["id"]), Vector2.from_angle(angle) * radius)


## Filters: {"types": [...], "origins": [...], "since_days": int, "text": String, "layers": "all|mine|packs"}.
func set_filter(f: Dictionary) -> void:
	filter = f
	_update_shown()
	reheat(0.5)
	queue_redraw()


func clear_filter() -> void:
	set_filter({})


func has_filter() -> bool:
	return not filter.is_empty()


func fold(space_id: String, on: bool) -> void:
	var key := space_id if space_id.begins_with("space:") else "space:" + space_id
	if on:
		folded[key] = true
	else:
		folded.erase(key)
	_update_shown()
	reheat(0.5)
	queue_redraw()


func is_shown(id: String) -> bool:
	return not filtered_out.has(id)


func _matches(n: Dictionary) -> bool:
	if filter.is_empty():
		return true
	var types: Array = filter.get("types", [])
	if not types.is_empty() and not types.has(str(n.get("item_type", n.get("kind", "")))):
		return false
	var origins: Array = filter.get("origins", [])
	if not origins.is_empty():
		var o := str(n.get("origin", ""))
		var o2 := "pack" if n.get("layer") != null and str(n.get("layer")) != "" else o
		if not (origins.has(o) or origins.has(o2)):
			return false
	var layers := str(filter.get("layers", "all"))
	var in_pack := n.get("layer") != null and str(n.get("layer")) != ""
	if (layers == "mine" and in_pack) or (layers == "packs" and not in_pack):
		return false
	var days := int(filter.get("since_days", 0))
	if days > 0:
		var created := str(n.get("created_at", "")).left(10)
		var limit := Time.get_date_string_from_unix_time(int(Time.get_unix_time_from_system()) - days * 86400)
		if created < limit:
			return false
	var text := str(filter.get("text", "")).strip_edges().to_lower()
	if text != "":
		var hay := str(n.get("label", "")).to_lower()
		for t in _note_tags.get(str(n["id"]), []):
			hay += " " + str(t)
		var any_word := false
		for w in text.split(" ", false):
			if hay.contains(w.trim_prefix("#")):
				any_word = true
		if not any_word:
			return false
	return true


func _update_shown() -> void:
	filtered_out.clear()
	_note_tags.clear()
	for e in edges:
		if str(e["type"]) == "tag":
			var a := str(e["from"])
			if not _note_tags.has(a):
				_note_tags[a] = []
			(_note_tags[a] as Array).append(str(e["to"]).trim_prefix("tag:").to_lower())
	var shown_tags: Dictionary = {}
	for id in nodes:
		var n: Dictionary = nodes[id]
		if str(n["type"]) != "note":
			continue
		if folded.has("space:" + str(n["space_id"])) or not _matches(n):
			filtered_out[id] = true
		else:
			for t in _note_tags.get(str(id), []):
				shown_tags["tag:" + str(t)] = true
	for id in nodes:
		if str((nodes[id] as Dictionary)["type"]) == "tag" and (not shown_tags.has(id) or graph_layout == "timeline"):
			filtered_out[id] = true
	_rebuild_sim()


## Items of a place, shown or not (for the "+N" badge of a folded place).
func place_count(space_node: String) -> int:
	var sid := space_node.trim_prefix("space:")
	var c := 0
	for id in nodes:
		var n: Dictionary = nodes[id]
		if str(n["type"]) == "note" and str(n["space_id"]) == sid:
			c += 1
	return c


func shown_note_count() -> int:
	var c := 0
	for id in nodes:
		if str((nodes[id] as Dictionary)["type"]) == "note" and not filtered_out.has(id):
			c += 1
	return c


## The chain between two items (Loop 14), drawn bright with travelling dots.
func set_path(ids: Array, steps: Array) -> void:
	path_ids = ids.map(func(i: Variant) -> String: return str(i))
	path_steps = steps
	set_highlight(path_ids)
	if path_ids.is_empty():
		return
	var lo := Vector2(1e9, 1e9)
	var hi := Vector2(-1e9, -1e9)
	for id in path_ids:
		if nodes.has(id):
			var p: Vector2 = nodes[id]["pos"]
			lo = Vector2(minf(lo.x, p.x), minf(lo.y, p.y))
			hi = Vector2(maxf(hi.x, p.x), maxf(hi.y, p.y))
	var span := (hi - lo).max(Vector2(200, 200))
	var free := size - Vector2(screen_offset.x * 2.0 + 120.0, 260.0)
	follow = ""
	zoom_to(clampf(minf(free.x / span.x, free.y / span.y), ZOOM_MIN, 2.0), (lo + hi) * 0.5)


func clear_path() -> void:
	path_ids = []
	path_steps = []
	set_highlight([])


func _draw_path() -> void:
	for i in range(path_ids.size() - 1):
		var a := str(path_ids[i])
		var b := str(path_ids[i + 1])
		if not nodes.has(a) or not nodes.has(b):
			continue
		var pa := world_to_screen(nodes[a]["pos"] as Vector2)
		var pb := world_to_screen(nodes[b]["pos"] as Vector2)
		draw_line(pa, pb, Color(SbTheme.WARM, 0.25), 9.0, true)
		draw_line(pa, pb, Color(SbTheme.WARM, 0.95), 3.0, true)
		for k in 3:
			var t := fmod(_t * 0.6 + float(k) / 3.0, 1.0)
			draw_circle(pa.lerp(pb, t), 3.5, SbTheme.MINT_SOFT)


# ------------------------------------------------------------ timeline (Loop 15)
## "zones" (the organised graph) or "timeline": items slide onto a time axis, one lane per place.
func set_layout(mode: String) -> void:
	if mode == graph_layout or not mode in ["zones", "timeline"]:
		return
	if mode == "timeline":
		for id in nodes:
			(nodes[id] as Dictionary)["zone_pos"] = (nodes[id] as Dictionary)["pos"]
	graph_layout = mode
	_update_shown()
	if mode == "timeline":
		_timeline_targets()
		follow = ""
		var free_w := maxf(400.0, size.x - screen_offset.x * 2.0 - 80.0)
		zoom_to(clampf(free_w / (_tl_width + 420.0), ZOOM_MIN, 1.2), Vector2(-110.0, 0))
	else:
		for id in nodes:
			var n: Dictionary = nodes[id]
			if n.has("zone_pos"):
				n["pos"] = n["zone_pos"]
		_rebuild_sim()
		reheat(0.4)
		zoom_to(0.6, Vector2.ZERO)
	queue_redraw()


static func _unix(iso: String) -> float:
	if iso.length() < 10:
		return 0.0
	return float(Time.get_unix_time_from_datetime_string(iso.left(19)))  # "YYYY-MM-DDTHH:MM:SS", UTC


func _timeline_targets() -> void:
	_tl_lanes.clear()
	var times: Array = []
	for id in _sim_ids:
		var n: Dictionary = nodes[id]
		if str(n["type"]) == "note":
			times.append(_unix(str(n.get("created_at", ""))))
	if times.is_empty():
		return
	_tl_t0 = times.min()
	_tl_t1 = maxf(times.max(), _tl_t0 + 600.0)  # at least ten minutes, so recent items still spread out
	var pad := (_tl_t1 - _tl_t0) * 0.04
	_tl_t0 -= pad
	_tl_t1 += pad
	_tl_width = clampf(times.size() * 22.0, 1400.0, 9000.0)
	var lanes: Array = []
	for id in _sim_ids:
		if str((nodes[id] as Dictionary)["type"]) == "space":
			lanes.append(id)
	lanes.sort_custom(func(a: Variant, b: Variant) -> bool:
		return str((nodes[a] as Dictionary)["label"]).naturalnocasecmp_to(str((nodes[b] as Dictionary)["label"])) < 0)
	var lane_h := 110.0
	var top := -lane_h * lanes.size() * 0.5
	for i in lanes.size():
		_tl_lanes[str(lanes[i]).trim_prefix("space:")] = top + i * lane_h
		(nodes[lanes[i]] as Dictionary)["tl"] = Vector2(-_tl_width * 0.5 - 170.0, top + i * lane_h)
	var jitter: Dictionary = {}
	for id in _sim_ids:
		var n: Dictionary = nodes[id]
		if str(n["type"]) != "note":
			continue
		var x := -_tl_width * 0.5 + (_unix(str(n.get("created_at", ""))) - _tl_t0) / (_tl_t1 - _tl_t0) * _tl_width
		var y: float = _tl_lanes.get(str(n["space_id"]), 0.0)
		var slot := "%d:%d" % [int(x / 18.0), int(y)]
		var k: int = jitter.get(slot, 0)  # items added at the same moment stack in their lane
		jitter[slot] = k + 1
		n["tl"] = Vector2(x, y + (k % 3 - 1) * 26.0 + (k / 3) * 8.0)


func _timeline_step(delta: float) -> void:
	var w := minf(1.0, delta * 6.0)
	for i in _sim_ids.size():
		var n: Dictionary = nodes[_sim_ids[i]]
		if n.has("tl"):
			n["pos"] = (n["pos"] as Vector2).lerp(n["tl"] as Vector2, w)
			_sim_pos[i] = n["pos"]


func _draw_timeline_axis() -> void:
	if _tl_lanes.is_empty():
		return
	var span := _tl_t1 - _tl_t0
	var step := 86400.0
	var fmt := "day"
	if span > 86400.0 * 60:
		step = 86400.0 * 30
		fmt = "month"
	elif span > 86400.0 * 14:
		step = 86400.0 * 7
		fmt = "week"
	elif span < 3600.0 * 3:
		step = 600.0 if span > 3600.0 else 120.0
		fmt = "time"
	elif span < 86400.0 * 2:
		step = 3600.0 * (1 if span < 86400.0 * 0.5 else 3)
		fmt = "time"
	var tops: Array = _tl_lanes.values()
	var y0: float = tops.min() - 70.0
	var y1: float = tops.max() + 70.0
	var t := ceilf(_tl_t0 / step) * step
	var font := _font
	while t <= _tl_t1 + 1.0:
		var x := -_tl_width * 0.5 + (t - _tl_t0) / span * _tl_width
		var a := world_to_screen(Vector2(x, y0))
		var b := world_to_screen(Vector2(x, y1))
		draw_line(a, b, Color(SbTheme.BORDER, 0.55), 1.0)
		var d := Time.get_datetime_dict_from_unix_time(int(t) + int(Time.get_time_zone_from_system().get("bias", 0)) * 60)
		var label := "%04d-%02d" % [d["year"], d["month"]] if fmt == "month" else (
			"%02d:%02d" % [d["hour"], d["minute"]] if fmt == "time" else "%02d/%02d" % [d["day"], d["month"]])
		draw_string(font, b + Vector2(-18, 18), label, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, SbTheme.MUTED)
		t += step
	for sid in _tl_lanes:
		var y: float = _tl_lanes[sid]
		draw_line(world_to_screen(Vector2(-_tl_width * 0.5 - 60.0, y)), world_to_screen(Vector2(_tl_width * 0.5 + 40.0, y)),
			Color(SbTheme.BORDER, 0.35), 1.0)


# --------------------------------------------------------------- simulation
func _process(delta: float) -> void:
	_t += delta
	if follow != "" and nodes.has(follow) and not (_zoom_tween != null and _zoom_tween.is_running()):
		cam = cam.lerp((nodes[follow]["pos"] as Vector2) - screen_offset / zoom, minf(1.0, delta * 8.0))
	if graph_layout == "timeline":
		_timeline_step(delta)
	else:
		if _heat_goal > 0.0:  # wake up softly, then cool down as before
			if heat < _heat_goal:
				heat = move_toward(heat, _heat_goal, delta * 1.2)
			if heat >= _heat_goal:
				_heat_goal = 0.0
		if heat > 0.02:
			# Fixed steps whatever the frame rate: a slow frame runs two or three small steps, never one big
			# one (a big step overshoots, and items start to shake). A big graph keeps to one step per frame.
			_sim_acc = minf(_sim_acc + delta, SIM_DT * 3.0)
			var steps := 0
			var most := 3 if _sim_ids.size() < CROWD_FROM else 1
			while _sim_acc >= SIM_DT and steps < most:
				_simulate(1.0)
				if _heat_goal <= 0.0:
					heat *= 0.995 if _sim_ids.size() < 600 else (0.985 if _sim_ids.size() < 2000 else 0.97)
				_sim_acc -= SIM_DT
				steps += 1
			if steps == most:
				_sim_acc = 0.0
		else:
			_sim_acc = 0.0
	queue_redraw()


## Packed arrays for the layout (Loop 15): rebuilt when the graph, the filters or the folds change.
func _rebuild_sim() -> void:
	_sim_ids = []
	for id in nodes:
		if not filtered_out.has(id):
			_sim_ids.append(str(id))
	_sim_index.clear()
	var n := _sim_ids.size()
	_sim_space = PackedByteArray()
	_sim_space.resize(n)
	_sim_spaces = PackedInt32Array()
	_sim_pos = PackedVector2Array()
	_sim_pos.resize(n)
	_sim_col = PackedColorArray()
	_sim_col.resize(n)
	_sim_born = PackedFloat32Array()
	_sim_born.resize(n)
	for i in n:
		var nd: Dictionary = nodes[_sim_ids[i]]
		_sim_pos[i] = nd["pos"]
		_sim_col[i] = nd.get("_col", Color.WHITE)
		_sim_born[i] = float(nd["born"])
		_sim_index[_sim_ids[i]] = i
		var is_space := str((nodes[_sim_ids[i]] as Dictionary)["type"]) == "space"
		_sim_space[i] = 1 if is_space else 0
		if is_space:
			_sim_spaces.append(i)
	# Each item's place (its index in the packed arrays, -1 for tags): items gravitate to their zone, not to the centre.
	_sim_home = PackedInt32Array()
	_sim_home.resize(n)
	for i in n:
		var home := "space:" + str((nodes[_sim_ids[i]] as Dictionary).get("space_id", ""))
		_sim_home[i] = int(_sim_index.get(home, -1)) if _sim_space[i] == 0 else -1
	_edge_a = PackedInt32Array()
	_edge_b = PackedInt32Array()
	_edge_rest = PackedFloat32Array()
	_edge_kind = PackedByteArray()
	_edge_src = PackedInt32Array()
	for ei in edges.size():
		var e: Dictionary = edges[ei]
		if _sim_index.has(e["from"]) and _sim_index.has(e["to"]):
			_edge_src.append(ei)
			_edge_a.append(int(_sim_index[e["from"]]))
			_edge_b.append(int(_sim_index[e["to"]]))
			_edge_rest.append(float(REST.get(str(e["type"]), 120.0)))
			_edge_kind.append(1 if str(e["type"]) == "link" else (2 if str(e["type"]) == "related" else 0))


func _simulate(step: float) -> void:
	var n := _sim_ids.size()
	if n == 0:
		return
	var pos := PackedVector2Array()
	pos.resize(n)
	for i in n:
		pos[i] = (nodes[_sim_ids[i]] as Dictionary)["pos"]
	var force := PackedVector2Array()
	force.resize(n)
	# Repulsion between neighbours only: a grid of CELL-sized cells. Items of the same cell push each other
	# exactly; a neighbouring cell pushes as one body at its centre when it is crowded (a dense, unsettled
	# graph stays cheap), item by item otherwise. Each side applies its own half, so forces stay balanced.
	var grid: Dictionary = {}
	for i in n:
		var key := Vector2i(floori(pos[i].x / CELL), floori(pos[i].y / CELL))
		# Packed arrays are values in GDScript: append to the cell's array, then store it back.
		var cell: PackedInt32Array = grid.get(key, PackedInt32Array())
		cell.append(i)
		grid[key] = cell
	var centre: Dictionary = {}
	for key in grid:
		var members: PackedInt32Array = grid[key]
		if members.size() > CROWD and n >= CROWD_FROM:
			var c := Vector2.ZERO
			for m in members:
				c += pos[m]
			centre[key] = c / float(members.size())
	for key in grid:
		var here: PackedInt32Array = grid[key]
		for a in here.size():
			var i := here[a]
			var pi := pos[i]
			var si := _sim_space[i]
			for b in range(a + 1, here.size()):
				var j := here[b]
				if si == 1 and _sim_space[j] == 1:
					continue
				var f := _push(pi - pos[j], si, _sim_space[j], i, j)
				force[i] += f
				force[j] -= f
			for dx in range(-1, 2):
				for dy in range(-1, 2):
					if dx == 0 and dy == 0:
						continue
					var other_key := Vector2i(key.x + dx, key.y + dy)
					if not grid.has(other_key):
						continue
					if centre.has(other_key):
						var crowd: PackedInt32Array = grid[other_key]
						force[i] += _push(pi - (centre[other_key] as Vector2), si, 0, i, -1) * float(crowd.size())
						continue
					for j in (grid[other_key] as PackedInt32Array):
						if si == 1 and _sim_space[j] == 1:
							continue
						force[i] += _push(pi - pos[j], si, _sim_space[j], i, j)
	# Places push each other apart at any distance (there are few of them).
	for a in _sim_spaces.size():
		var i := _sim_spaces[a]
		for b in range(a + 1, _sim_spaces.size()):
			var j := _sim_spaces[b]
			var d := pos[i] - pos[j]
			var dist2 := maxf(d.length_squared(), 100.0)
			var f := d * (REPULSION * 9.0 / (dist2 * sqrt(dist2)))
			force[i] += f
			force[j] -= f
	for k in _edge_a.size():
		var i := _edge_a[k]
		var j := _edge_b[k]
		var d := pos[j] - pos[i]
		var len := d.length()
		if len < 0.001:
			continue
		var f := d * ((len - _edge_rest[k]) * SPRING / len)
		force[i] += f
		force[j] -= f
	for i in n:
		var id: String = _sim_ids[i]
		var node: Dictionary = nodes[id]
		if bool(node["pinned"]) or id == _dragging_node:
			node["vel"] = Vector2.ZERO
			continue
		var p := pos[i]
		var f: Vector2
		if _sim_space[i] == 1 and anchors.has(id):  # a place stays in its zone
			f = force[i] * 0.25 + ((anchors[id] as Vector2) - p) * 0.06
		elif _sim_home[i] >= 0:  # free inside its zone, pulled back beyond it
			var out := p - pos[_sim_home[i]]
			var dist := out.length()
			f = force[i] - (out * ((dist - ZONE_FREE) / dist) * HOME_PULL if dist > ZONE_FREE else Vector2.ZERO)
		elif _sim_space[i] == 0:  # a theme sits among its items, barely pulled to the centre
			f = force[i] - p * GRAVITY * 0.02
		else:
			f = force[i] - p * GRAVITY * 0.35
		var v: Vector2 = ((node["vel"] as Vector2) + f * step * heat) * DAMPING
		v = v.limit_length(MAX_SPEED)
		if heat < 0.15 and v.length() < REST_SPEED:
			v = Vector2.ZERO
		node["vel"] = v
		node["pos"] = p + v * step
		_sim_pos[i] = node["pos"]


## The push of one item on another: inverse-square repulsion (stronger around places), plus a firm
## collision push between items closer than COLLIDE so cards keep their own room.
func _push(d: Vector2, sa: int, sb: int, i: int, j: int) -> Vector2:
	if d.length_squared() < 0.25:  # two items on the same spot: part them in a stable direction
		d = Vector2.from_angle(float(i * 7 + j * 13)) * 0.5
	var dist2 := maxf(d.length_squared(), 100.0)
	var dl := sqrt(dist2)
	var f := d * (REPULSION * (2.2 if sa == 1 or sb == 1 else 1.0) / (dist2 * dl))
	if dl < COLLIDE and sa == 0 and sb == 0:
		f += d * ((COLLIDE - dl) * 0.25 / dl)
	return f


## Dense or far views (Loop 15): everything ordinary comes from the packed layout arrays,
## in a handful of batched draw calls. Returns the items that still need the full rendering.
func _draw_fast_layer(level: String) -> Array:
	var half := size * 0.5
	var view := Rect2(Vector2(-40, -40), size + Vector2(80, 80))
	var links := PackedVector2Array()
	var link_col := PackedColorArray()
	var ideas := PackedVector2Array()
	var idea_col := PackedColorArray()
	var focus := not highlight.is_empty() or hovered != "" or selected != ""
	for k in _edge_a.size():
		var kind := _edge_kind[k]
		if kind == 0:
			continue
		var pa := (_sim_pos[_edge_a[k]] - cam) * zoom + half
		var pb := (_sim_pos[_edge_b[k]] - cam) * zoom + half
		if not view.has_point(pa) and not view.has_point(pb):
			continue
		var dim := focus and (_is_dim(_sim_ids[_edge_a[k]]) or _is_dim(_sim_ids[_edge_b[k]]))
		if kind == 1:
			links.append(pa)
			links.append(pb)
			link_col.append(Color(SbTheme.MINT, 0.12 if dim else 0.45))
		else:
			ideas.append(pa)
			ideas.append(pb)
			idea_col.append(Color(SbTheme.WARM, 0.1 if dim else 0.35))
	if links.size() > 0:
		draw_multiline_colors(links, link_col, 1.2)
	if ideas.size() > 0:
		draw_multiline_colors(ideas, idea_col, 1.0)
	var dot := clampf(7.0 * zoom, 1.6, 5.0)
	var dots := PackedVector2Array()
	var dot_col := PackedColorArray()
	var special: Array = []
	var fresh := _t - BIRTH_S
	for i in _sim_ids.size():
		var id: String = _sim_ids[i]
		if _sim_space[i] == 1 or id == selected or id == hovered or _sim_born[i] > fresh or (focus and highlight.has(id)):
			special.append(id)
			continue
		var p := (_sim_pos[i] - cam) * zoom + half
		if not view.has_point(p):
			continue
		dots.append(p - Vector2(dot, 0))
		dots.append(p + Vector2(dot, 0))
		dot_col.append(Color(_sim_col[i], 0.25 if focus and _is_dim(id) else 0.9))
	if dots.size() > 0:
		draw_multiline_colors(dots, dot_col, dot * 2.0)
	return special


## Classic views draw only what is on screen (plus the special items), chosen from the packed arrays.
func _on_screen_ids(level: String) -> Array:
	var out: Array = []
	var margin := 80.0 if level == "mid" or level == "far" else CARD.x * zoom
	var half := size * 0.5
	var r := Rect2(Vector2(-margin, -margin), size + Vector2(margin, margin) * 2.0)
	for i in _sim_ids.size():
		if r.has_point((_sim_pos[i] - cam) * zoom + half) or _sim_space[i] == 1:
			out.append(_sim_ids[i])
	return out


func _on_screen_edges(ids: Array) -> Array:
	var shown := PackedByteArray()
	shown.resize(_sim_ids.size())
	for id in ids:
		if _sim_index.has(id):
			shown[int(_sim_index[id])] = 1
	var out: Array = []
	for k in _edge_a.size():
		if shown[_edge_a[k]] == 1 or shown[_edge_b[k]] == 1:
			out.append(edges[_edge_src[k]])
	return out


func _count_on_screen() -> int:
	var c := 0
	var lo := screen_to_world(Vector2.ZERO)
	var r := Rect2(lo, screen_to_world(size) - lo)
	for i in _sim_pos.size():
		if r.has_point(_sim_pos[i]):
			c += 1
	return c


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


var draw_ms := 0.0   # last _draw duration (perf checks)


func _draw() -> void:
	var t0 := Time.get_ticks_usec()
	_draw_all()
	draw_ms = (Time.get_ticks_usec() - t0) / 1000.0


func _draw_all() -> void:
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

	var level := lod()
	if graph_layout == "timeline":
		_draw_timeline_axis()
		if level == "far":
			level = "mid"  # no place clusters on a time axis
	_dense = _count_on_screen() > DENSE
	var fast := level == "far" or (_dense and level == "mid")
	if level == "far" and graph_layout == "zones":
		_draw_clusters()
	var special: Array = _draw_fast_layer(level) if fast else _on_screen_ids(level)
	# Edges (classic view): faint structural ones in one batch, links and ideas one by one.
	var faint := PackedVector2Array()
	var faint_col := PackedColorArray()
	var view := Rect2(Vector2(-40, -40), size + Vector2(80, 80))
	for e in (_on_screen_edges(special) if not fast else []):
		var type: String = e["type"]
		if filtered_out.has(e["from"]) or filtered_out.has(e["to"]):
			continue
		var a0: Dictionary = nodes[e["from"]]
		var b0: Dictionary = nodes[e["to"]]
		var sa := world_to_screen(a0["pos"] as Vector2)
		var sb := world_to_screen(b0["pos"] as Vector2)
		if not view.has_point(sa) and not view.has_point(sb) and not view.intersects(Rect2(sa, Vector2.ZERO).expand(sb)):
			continue
		var pa := sa
		var pb := sb
		var grow := minf(_birth(a0), _birth(b0))
		var dim := _is_dim(str(e["from"])) or _is_dim(str(e["to"]))
		if type in ["space", "area", "tag"] and minf(_birth(a0), _birth(b0)) >= 1.0:
			var fc := Color(SbTheme.FOREST_LIGHT if type != "tag" else SbTheme.MUTED, (0.22 if type != "tag" else 0.16) * (0.25 if dim else 1.0))
			faint.append(sa)
			faint.append(sb)
			faint_col.append(fc)
			continue
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
		elif type == "related":
			# Related ideas found by meaning: warm, dashed, so they read as suggestions rather than links
			col = SbTheme.WARM
			alpha = 0.42
			width = 1.4
		if dim:
			alpha *= 0.25
		elif hovered != "" and (str(e["from"]) == hovered or str(e["to"]) == hovered):
			alpha = minf(1.0, alpha * 2.2)
		var end := pa.lerp(pb, grow)
		if type == "related":
			draw_dashed_line(pa, end, Color(col, alpha * grow), width * clampf(zoom, 0.6, 1.4), 6.0 * clampf(zoom, 0.6, 1.4))
		else:
			draw_line(pa, end, Color(col, alpha * grow), width * clampf(zoom, 0.6, 1.4), true)
		if type == "link" and not dim and grow >= 1.0:
			var k := fmod(_t * 0.35 + float(hash(str(e["from"])) % 97) / 97.0, 1.0)
			draw_circle(pa.lerp(pb, k), 2.2, Color(SbTheme.MINT_SOFT, 0.75))

	if faint.size() > 0:
		draw_multiline_colors(faint, faint_col, 1.0)
	if path_ids.size() > 1:
		_draw_path()
	# Nodes: in fast views only the special ones (places, selection, hover, hits, newborns) are drawn here.
	var margin := 80.0 if level == "mid" or level == "far" else CARD.x * zoom
	for id in special:
		if filtered_out.has(id):
			continue
		var n: Dictionary = nodes[id]
		var p := world_to_screen(n["pos"] as Vector2)
		if p.x < -margin or p.y < -margin or p.x > size.x + margin or p.y > size.y + margin:
			continue
		var ntype: String = n["type"]
		if (level == "near" or level == "read") and ntype == "note":
			_draw_card(n, p, level == "read")
			continue
		if level == "far" and ntype != "space":
			draw_circle(p, maxf(1.5, _radius(n) * zoom), Color(_color(n), 0.25 if _is_dim(str(id)) else 0.85))
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
		if not _dense:
			draw_circle(p, r * 2.2, Color(col, (0.05 + 0.06 * breathe) * a))
		match str(n["type"]):
			"space":
				draw_circle(p, r, Color(SbTheme.PANEL_2, 0.92 * a))
				draw_arc(p, r, 0, TAU, 64, Color(col, 0.95 * a), 2.5, true)
				draw_arc(p, r + 6.0 * zoom, _t * 0.4, _t * 0.4 + PI * 0.6, 32, Color(col, 0.45 * a), 1.5, true)
				if folded.has(id):
					var badge := "+%d" % place_count(str(id))
					var bw := _font.get_string_size(badge, HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x + 12.0
					var bp := p + Vector2(r * 0.7, -r * 0.9)
					draw_rect(Rect2(bp, Vector2(bw, 20)), Color(col, 0.9 * a))
					draw_string(_font, bp + Vector2(6, 15), badge, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, SbTheme.ON_ACCENT)
			"tag":
				draw_arc(p, r, 0, TAU, 24, Color(col, 0.8 * a), 1.5, true)
			_:
				draw_circle(p, r, Color(col, 0.95 * a))
				if not _dense:
					draw_circle(p + Vector2(-r * 0.3, -r * 0.3), r * 0.35, Color(1, 1, 1, 0.25 * a))
		if n.get("layer") != null and str(n.get("layer")) != "":
			# from an imported pack: a dotted ring, so a layer reads apart from your own items
			for k in 12:
				var a0 := TAU * float(k) / 12.0 + _t * 0.15
				draw_arc(p, r + 4.0, a0, a0 + TAU / 24.0, 4, Color(SbTheme.INFO, 0.8 * a), 1.6, true)
		if str(id) == selected:
			draw_arc(p, r + 7.0, 0, TAU, 48, SbTheme.MINT_SOFT, 2.0, true)
			draw_arc(p, r + 12.0 + 2.0 * breathe, 0, TAU, 48, Color(SbTheme.MINT_SOFT, 0.35), 1.5, true)
		_draw_label(n, p, r, dim)
	if show_minimap and nodes.size() > 1:
		_draw_minimap()
	if show_legend:
		_draw_legend()


func _draw_clusters() -> void:
	var members: Dictionary = {}
	for id in nodes:
		var n: Dictionary = nodes[id]
		if str(n["type"]) == "note" and not filtered_out.has(id):
			var hub := "space:" + str(n["space_id"])
			if not members.has(hub):
				members[hub] = []
			(members[hub] as Array).append(n["pos"])
	for hub in members:
		if not nodes.has(hub):
			continue
		var h: Dictionary = nodes[hub]
		var center: Vector2 = h["pos"]
		# The zone holds most of its items: one item pulled away by a link elsewhere does not inflate it.
		var dists: Array[float] = []
		for q in members[hub]:
			dists.append(center.distance_to(q as Vector2))
		dists.sort()
		var reach := maxf(60.0, dists[mini(dists.size() - 1, int(dists.size() * 0.6))] + 40.0)
		zone_reach[hub] = reach
		var col := _color(h)
		var sp := world_to_screen(center)
		draw_circle(sp, reach * zoom, Color(col, 0.07))
		draw_arc(sp, reach * zoom, 0, TAU, 64, Color(col, 0.35), 1.5, true)
		var text := "%s  ·  %d" % [str(h["label"]), (members[hub] as Array).size()]
		var w := _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, 16).x
		draw_string(_font, sp + Vector2(-w * 0.5, -reach * zoom - 8.0), text, HORIZONTAL_ALIGNMENT_LEFT, -1, 16, Color(SbTheme.TEXT, 0.9))


## Near: a card with title, place, themes and summary. Read: the full text, readable.
func _draw_card(n: Dictionary, p: Vector2, reading: bool) -> void:
	var id := str(n["id"])
	if not details.has(id) and not _asked.has(id):
		_asked[id] = true
		details_needed.emit(id)
	var d: Dictionary = details.get(id, {})
	var sz := CARD * zoom
	var rect := Rect2(p - sz * 0.5, sz)
	var dim := _is_dim(id)
	var col := _color(n)
	var a := 0.35 if dim else 1.0
	var box := StyleBoxFlat.new()
	box.bg_color = Color(SbTheme.PANEL_2, 0.94 * a)
	box.border_color = Color(col, (0.95 if id == selected else 0.55) * a)
	box.set_border_width_all(3 if id == selected else 1)
	box.set_corner_radius_all(int(clampf(zoom * 2.0, 6.0, 18.0)))
	draw_style_box(box, rect)
	var stripe := clampf(zoom * 0.9, 3.0, 8.0)
	draw_rect(Rect2(rect.position, Vector2(stripe, sz.y)), Color(col, 0.9 * a))
	# Text grows with the card until it is comfortable, then the card simply holds more of it.
	var fs_title := int(clampf(zoom * 2.6, 9.0, 24.0))
	var fs := int(clampf(zoom * 1.9, 8.0, 17.0))
	var pad := clampf(zoom * 2.2, 5.0, 22.0)
	var x := rect.position.x + pad + stripe
	var width := sz.x - pad * 2.0 - stripe
	# A document or an image: its first page sits on the right, sharper as you zoom in (a web page: its main image).
	var src: Variant = d.get("source")
	if src is Dictionary and (int((src as Dictionary).get("pages", 0) if (src as Dictionary).get("pages") != null else 0) > 0
			or int((src as Dictionary).get("images", 0)) > 0):
		var ph := sz.y - pad * 2.0
		var pt: Dictionary = page_tex.get(id, {})
		var tex: Texture2D = pt.get("tex")
		var aspect := (tex.get_size().x / maxf(1.0, tex.get_size().y)) if tex != null else 0.72
		var pw := minf(ph * aspect, sz.x * 0.48)
		ph = pw / aspect
		var prect := Rect2(Vector2(rect.end.x - pad - pw, rect.position.y + pad), Vector2(pw, ph))
		if tex != null:
			draw_rect(prect.grow(1.0), Color(0, 0, 0, 0.3 * a))
			draw_texture_rect(tex, prect, false, Color(1, 1, 1, a))
		else:
			draw_rect(prect, Color(1, 1, 1, 0.12 * a))
		var want := int(pw)
		if int(pt.get("w", 0)) < want * 0.8 and int(_page_asked.get(id, 0)) < want * 0.8:
			_page_asked[id] = want
			page_needed.emit(id, str((src as Dictionary).get("id", "")), want)
		width -= pw + pad
	var y := rect.position.y + pad + fs_title
	draw_string(_font, Vector2(x, y), str(n["label"]), HORIZONTAL_ALIGNMENT_LEFT, width, fs_title, Color(SbTheme.TEXT, a))
	y += fs * 1.5
	var meta := str(d.get("place", ""))
	var themes: Array = d.get("themes", [])
	if not themes.is_empty():
		meta += ("   " if meta != "" else "") + " ".join(themes.map(func(t: Variant) -> String: return "#" + str(t)))
	if meta != "":
		draw_string(_font, Vector2(x, y), meta, HORIZONTAL_ALIGNMENT_LEFT, width, maxi(8, fs - 1), Color(SbTheme.MINT, 0.9 * a))
		y += fs * 1.6
	var summary := str(d.get("summary", "")) if d.get("summary") != null else ""
	var body := str(d.get("body", "")) if d.get("body") != null else ""
	var text := body if reading else summary
	if text == "":
		text = summary if reading else body.left(240)
	text = SbFormat.plain(text)  # drawn as plain text: no Markdown marks
	var lines_room := int(maxf(0.0, (rect.end.y - pad - y) / (fs * 1.35)))
	if lines_room > 0 and text != "":
		draw_multiline_string(_font, Vector2(x, y), text, HORIZONTAL_ALIGNMENT_LEFT, width, fs, lines_room,
			Color(SbTheme.TEXT, 0.82 * a))


## A small map of the whole graph with the visible area, bottom right. Click it to jump.
func minimap_rect() -> Rect2:
	return Rect2(size - Vector2(178 + right_inset, 196), Vector2(162, 112))  # above the music button, left of docked panels


func _minimap_transform() -> Array:
	if _t - _mini_tr_at < 0.4 and not _mini_tr.is_empty():
		return _mini_tr
	_mini_tr_at = _t
	_mini_tr = _minimap_transform_now()
	return _mini_tr


func _minimap_transform_now() -> Array:
	var box := minimap_rect()
	var lo := Vector2(1e9, 1e9)
	var hi := Vector2(-1e9, -1e9)
	for id in nodes:
		var q: Vector2 = nodes[id]["pos"]
		lo = Vector2(minf(lo.x, q.x), minf(lo.y, q.y))
		hi = Vector2(maxf(hi.x, q.x), maxf(hi.y, q.y))
	var span := (hi - lo).max(Vector2(200, 200))
	var k := minf((box.size.x - 16.0) / span.x, (box.size.y - 16.0) / span.y)
	return [box.position + box.size * 0.5 - (lo + span * 0.5) * k, k]


func _draw_minimap() -> void:
	var box := minimap_rect()
	var tr := _minimap_transform()
	var origin: Vector2 = tr[0]
	var k: float = tr[1]
	draw_rect(box, Color(SbTheme.PANEL, 0.72))
	draw_rect(box, Color(SbTheme.BORDER, 0.9), false, 1.0)
	if _t - _mini_at > 0.4 or _mini_pts.is_empty():
		_mini_at = _t
		_mini_pts = PackedVector2Array()
		_mini_col = PackedColorArray()
		for id in nodes:
			if filtered_out.has(id):
				continue
			var n: Dictionary = nodes[id]
			var q := origin + (n["pos"] as Vector2) * k
			var w := 2.4 if str(n["type"]) == "space" else 1.3
			_mini_pts.append(q - Vector2(w * 0.5, 0))
			_mini_pts.append(q + Vector2(w * 0.5, 0))
			_mini_col.append(Color(_color(n), 0.9))
	if _mini_pts.size() > 0:
		draw_multiline_colors(_mini_pts, _mini_col, 2.0)
	var lo := origin + screen_to_world(Vector2.ZERO) * k
	var hi := origin + screen_to_world(size) * k
	draw_rect(Rect2(lo, hi - lo).intersection(box), Color(SbTheme.MINT_SOFT, 0.85), false, 1.2)


func _jump_minimap(pos: Vector2) -> void:
	var tr := _minimap_transform()
	create_tween().tween_property(self, "cam", (pos - (tr[0] as Vector2)) / float(tr[1]), 0.35).set_trans(Tween.TRANS_CUBIC)


func _draw_label(n: Dictionary, p: Vector2, r: float, dim: bool) -> void:
	var id := str(n["id"])
	var type := str(n["type"])
	if type == "space" and zoom < FAR and graph_layout == "zones":
		return  # the cluster already carries the place's name
	var important := type == "space" or id == hovered or id == selected or highlight.has(id)
	var neighbor := hovered != "" and (_neighbors.get(hovered, {}) as Dictionary).has(id)
	if not (important or neighbor or (zoom >= 0.85 and type == "note" and not _dense)):
		return
	var text := str(n["label"])
	if text.length() > 34:
		text = text.left(32) + "…"
	var fs := 15 if type == "space" else 13
	var w := _font.get_string_size(text, HORIZONTAL_ALIGNMENT_LEFT, -1, fs).x
	var pos := p + Vector2(-w * 0.5, r + 16.0)
	var a := 0.35 if dim else (1.0 if important else 0.8)
	if not _dense:
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
## What a line means, for its tooltip and the legend.
func edge_at(screen_pos: Vector2) -> Dictionary:
	var best: Dictionary = {}
	var best_d := 6.0
	for e in edges:
		if filtered_out.has(e["from"]) or filtered_out.has(e["to"]):
			continue
		var a := world_to_screen((nodes[e["from"]] as Dictionary)["pos"] as Vector2)
		var b := world_to_screen((nodes[e["to"]] as Dictionary)["pos"] as Vector2)
		var d := Geometry2D.get_closest_point_to_segment(screen_pos, a, b).distance_to(screen_pos)
		if d < best_d:
			best_d = d
			best = e
	return best


func edge_text(e: Dictionary) -> String:
	if e.is_empty():
		return ""
	var a := str((nodes[e["from"]] as Dictionary)["label"])
	var b := str((nodes[e["to"]] as Dictionary)["label"])
	match str(e["type"]):
		"space":
			return I18n.t("“%s” belongs to the place “%s”") % [a, b]
		"area":
			return I18n.t("“%s” is part of “%s”") % [a, b]
		"tag":
			return I18n.t("“%s” carries %s") % [a, b]
		"related":
			return I18n.t("Suggested by meaning (dashed): “%s” ≈ “%s”\nOpen the item to keep (✓) or dismiss (✕) it") % [a, b]
	return I18n.t("Link: “%s” — “%s”") % [a, b]


## [line type, explanation]; the explanations follow the interface language.
static func legend() -> Array:
	return [["link", I18n.t("Link: you wrote [[…]], the archivist linked, or you kept a suggestion")],
		["related", I18n.t("Suggested by meaning, not confirmed yet")],
		["space", I18n.t("Belongs to this place")], ["tag", I18n.t("Carries this #theme")],
		["path", I18n.t("Answer to “how is X connected to Y?”")]]


func _draw_legend() -> void:
	var font := get_theme_default_font()
	var rows := legend()
	var widest := 0.0
	for row in rows:
		widest = maxf(widest, font.get_string_size(str(row[1]), HORIZONTAL_ALIGNMENT_LEFT, -1, 13).x)
	var box := Rect2(Vector2(legend_x, 148), Vector2(maxf(470.0, widest + 90.0), 30 + rows.size() * 26))
	draw_rect(box, Color(SbTheme.BG, 0.92))
	draw_rect(box, Color(SbTheme.FOREST_LIGHT, 0.35), false, 1.0)
	draw_string(font, box.position + Vector2(14, 22), I18n.t("LINES IN THE GRAPH"), HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color(SbTheme.TEXT, 0.7))
	for i in rows.size():
		var y := box.position.y + 44.0 + i * 26.0
		var a := Vector2(box.position.x + 14, y)
		var b := a + Vector2(46, 0)
		match str(rows[i][0]):
			"link":
				draw_line(a, b, Color(SbTheme.MINT, 0.85), 2.2, true)
				draw_circle(a.lerp(b, 0.6), 2.4, Color(SbTheme.MINT_SOFT, 0.9))
			"related":
				draw_dashed_line(a, b, Color(SbTheme.WARM, 0.8), 1.8, 6.0)
			"space":
				draw_line(a, b, Color(SbTheme.FOREST_LIGHT, 0.6), 1.2, true)
			"tag":
				draw_line(a, b, Color(SbTheme.MUTED, 0.5), 1.0, true)
			"path":
				draw_line(a, b, Color(SbTheme.WARM, 1.0), 3.5, true)
		draw_string(font, Vector2(b.x + 14, y + 5), str(rows[i][1]), HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(SbTheme.TEXT, 0.9))


## The place whose zone contains a world point ("" when none). Closest centre wins where zones overlap.
func zone_at(world: Vector2) -> String:
	var best := ""
	var best_d := 1e9
	for hub in zone_reach:
		if not nodes.has(hub):
			continue
		var d := ((nodes[hub] as Dictionary)["pos"] as Vector2).distance_to(world)
		if d <= float(zone_reach[hub]) and d < best_d:
			best = str(hub)
			best_d = d
	return best


## End of a drag: an item let go inside another place's zone asks to be refiled there;
## anywhere else the layout simply takes it back.
func drop_item(id: String, world: Vector2) -> void:
	if not nodes.has(id):
		return
	var n: Dictionary = nodes[id]
	if str(n["type"]) != "note":
		return
	var hub := zone_at(world)
	n["pinned"] = false  # as before: the layout takes it back; nothing stays pinned
	if hub != "" and hub != "space:" + str(n["space_id"]) and not folded.has(hub):
		item_dropped_on_place.emit(id, hub.trim_prefix("space:"))


func node_at(screen_pos: Vector2) -> String:
	var best := ""
	var best_d := 1e9
	var cards := zoom >= NEAR
	for id in nodes:
		if filtered_out.has(id):
			continue
		var n: Dictionary = nodes[id]
		if cards and str(n["type"]) == "note":
			var c := world_to_screen(n["pos"] as Vector2)
			if Rect2(c - CARD * zoom * 0.5, CARD * zoom).has_point(screen_pos) and c.distance_to(screen_pos) < best_d:
				best = str(id)
				best_d = c.distance_to(screen_pos)
			continue
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
				var f := 1.18 if mb.button_index == MOUSE_BUTTON_WHEEL_UP else 1.0 / 1.18
				zoom = clampf(zoom * f, ZOOM_MIN, ZOOM_MAX)
				cam += before - screen_to_world(mb.position)  # the point under the cursor stays put
			accept_event()
		elif mb.button_index == MOUSE_BUTTON_LEFT:
			if mb.pressed and show_minimap and minimap_rect().has_point(mb.position):
				_jump_minimap(mb.position)
				accept_event()
				return
			if mb.pressed:
				_press_pos = mb.position
				_moved = false
				_dragging_node = node_at(mb.position)
				_panning = _dragging_node == ""
				if mb.double_click and _dragging_node == "":
					create_tween().tween_property(self, "cam", Vector2.ZERO, 0.6).set_trans(Tween.TRANS_CUBIC)
				elif mb.double_click and _dragging_node.begins_with("space:"):
					fold(_dragging_node, not folded.has(_dragging_node))
				elif mb.double_click:
					node_activated.emit(_dragging_node)
			else:
				if _moved and _dragging_node != "":
					drop_item(_dragging_node, screen_to_world(mb.position))
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
				if _sim_index.has(_dragging_node):
					_sim_pos[int(_sim_index[_dragging_node])] = n["pos"]
				if anchors.has(_dragging_node):  # moving a place moves its zone
					anchors[_dragging_node] = n["pos"]
					custom_anchors[_dragging_node] = n["pos"]
				heat = maxf(heat, 0.6)
			elif _panning:
				follow = ""
				cam -= mm.relative / zoom
		else:
			var h := node_at(mm.position)
			if h != hovered:
				hovered = h
				mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND if h != "" else Control.CURSOR_ARROW
				tooltip_text = ""
			if h == "" and zoom >= 0.25:
				tooltip_text = edge_text(edge_at(mm.position))
