extends "res://tools/capture_base.gd"
## The showcase film (video-production/): the real app, filmed by Godot's movie mode (tools/film.sh) with the
## English showcase Brain in a temporary home. One step per run (SBGD_FILM_STEP); each step is a film_* function
## below and leaves « mark <name> <frame> » lines (SBGD_MARKS) the cut is made from, so the cut follows the app
## when a screen moves. The sound is the app's own: its music and its effects, as a user hears them.
## Step « prepare » only installs and opens the Brain (the base home every step starts from).

var marks_path := ""


func mark(name: String) -> void:
	var line := "mark %s %d" % [name, Engine.get_frames_drawn()]
	print(line)
	if OS.get_environment("FILM_STILLS") == "1":  # a quick look at the framing: one picture per mark, no film
		root.get_texture().get_image().save_png(out_dir.path_join(name + ".png"))
	if marks_path == "":
		return
	var f := FileAccess.open(marks_path, FileAccess.READ_WRITE if FileAccess.file_exists(marks_path) else FileAccess.WRITE)
	if f != null:
		f.seek_end()
		f.store_line(line)
		f.close()


func _run() -> void:
	var step := OS.get_environment("SBGD_FILM_STEP")
	marks_path = OS.get_environment("SBGD_MARKS")
	# FILM_REAL=1: the real archivist (a model call each time it files); else the scripted one, no key, no cost
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "openai" if OS.get_environment("FILM_REAL") == "1" else "showcase")
	boot_env()
	# The film is 1920x1080 and is watched much smaller on the page: the interface is drawn 1.4 times larger (the
	# layout of a 1371x771 window, the narrowest that holds the whole top bar, with the sharpness of the full
	# frame). FILM_SCALE changes it.
	var scale := OS.get_environment("FILM_SCALE")
	root.content_scale_factor = float(scale) if scale != "" else 1.4
	if not await open_brain():
		quit(1)
		return
	mark("open")
	if step != "prepare":
		var fn := "film_" + step.replace("-", "_")
		if not has_method(fn):
			push_error("film: no step « %s »" % step)
			quit(1)
			return
		await call(fn)
		mark("end")
	await finish()


## Types in a line edit one letter at a time, as a hand would.
func type_in(edit: LineEdit, text: String, per_letter: float = 0.045) -> void:
	edit.grab_focus()
	for i in text.length():
		edit.text = text.substr(0, i + 1)
		edit.caret_column = i + 1
		await pause(per_letter)


## Scenes 1 and 2: the graph alive with a slow push in, then a thought typed and filed, with its receipt.
func film_open() -> void:
	await frame_brain(0.1, 0.8)   # the whole Brain, beside the Archivist's panel, from a little further
	mark("graph")
	await frame_brain(6.0)
	mark("typing")
	var ce: LineEdit = b.get("capture_edit")
	await type_in(ce, "Ask Marc if the induction cooktop needs its own 40 A circuit")
	await pause(0.6)
	ce.text_submitted.emit(ce.text)
	mark("sent")
	var end := Time.get_ticks_msec() + 30000
	while int(b.get("classified")) == 0 and Time.get_ticks_msec() < end:
		await pause(0.2)
	mark("receipt")
	await pause(1.6)
	mark("receipt-shown")
	await pause(2.4)


## The Captures view: everything that came in, how (typed, spoken, a page, a file) and where it went.
func film_captures() -> void:
	(b.get("toast") as Control).visible = false
	await b.call("set_view", "captures")
	await pause(1.5)
	stage()
	mark("captures")
	await pause(3.0)


# ---------------------------------------------------------------- what the scenes share

## The zoom and the centre that show the whole Brain in the free part of the graph: under the bars, above the
## capture bar (the graph's own rectangle already stops at a docked panel). `closer` > 1 comes nearer.
func brain_fit(closer: float = 1.0) -> Array:
	var lo := Vector2(INF, INF)
	var hi := Vector2(-INF, -INF)
	for id in g.nodes:
		var p: Vector2 = g.nodes[id]["pos"]
		lo = lo.min(p)
		hi = hi.max(p)
	var window := Vector2(root.size) / root.content_scale_factor
	var origin := g.global_position
	var top := maxf(0.0, 104.0 - origin.y)                                   # the header and the graph's own bar
	var bottom := maxf(0.0, origin.y + g.size.y - (window.y - 100.0))        # the capture bar
	var left := maxf(16.0, 56.0 - origin.x)                                  # the rail of shrunk panels
	var free := Rect2(left, top, g.size.x - left - 16.0, g.size.y - top - bottom)
	var world := hi - lo + Vector2(300.0, 260.0)  # the places' rings and their names reach beyond their items
	var z := minf(free.size.x / world.x, free.size.y / world.y) * closer
	print("film: fit graph at %s size %s free %s zoom %.3f" % [origin, g.size, free, z])
	return [z, (lo + hi) / 2.0 - (free.get_center() - g.size / 2.0) / z]


## The whole Brain in view (beside the Archivist's panel when it is open).
func frame_brain(seconds: float = 0.3, closer: float = 1.0) -> void:
	var fit := brain_fit(closer)
	g.zoom_to(fit[0], fit[1], seconds)
	await pause(seconds + 0.6)


## The Archivist's panel shrunk into the rail: the graph alone.
func fold_panel() -> void:
	var p: SbFloatingPanel = b.call("agent_panel")
	if p != null:
		p.set_minimized(true)
	await pause(0.8)


## Waits until the Archivist has filed one more item than `before` (or `limit_s` of real time).
func wait_filed(before: int, limit_s: float = 60.0) -> bool:
	var end := Time.get_ticks_msec() + int(limit_s * 1000.0)
	while int(b.get("classified")) <= before and Time.get_ticks_msec() < end:
		await pause(0.2)
	return int(b.get("classified")) > before


## A call to the Brain's MCP endpoint, as an AI tool makes it (its own token).
func mcp_call(token: String, tool: String, args: Dictionary) -> void:
	var req := HTTPRequest.new()
	root.add_child(req)
	req.request("http://127.0.0.1:%d/mcp" % app.backend.api.port, PackedStringArray(["Content-Type: application/json", "Authorization: Bearer " + token]),
		HTTPClient.METHOD_POST, JSON.stringify({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}))
	await req.request_completed
	req.queue_free()


# ---------------------------------------------------------------- the scenes

## Scenes 2 and 3: a thought typed, a PDF dropped on the window; the Archivist files each and says where.
func film_capture() -> void:
	await frame_brain()
	mark("start")
	var ce: LineEdit = b.get("capture_edit")
	await type_in(ce, "Ask Marc if the induction cooktop needs its own 40 A circuit")
	await pause(0.5)
	var before := int(b.get("classified"))
	ce.text_submitted.emit(ce.text)
	mark("sent")
	if not await wait_filed(before):
		push_error("film: the thought was not filed")
	mark("receipt")
	await pause(3.5)
	(b.get("toast") as Control).visible = false
	await frame_brain(1.2)
	before = int(b.get("classified"))
	b.call("add_source_file", ProjectSettings.globalize_path("res://tools/howto/files/heat-pump-quote.pdf"))
	mark("dropped")
	if not await wait_filed(before, 120.0):
		push_error("film: the PDF was not filed")
	mark("receipt-pdf")
	await pause(4.5)


## Scene 4: from the places down to a page of a PDF, one zoom.
func film_zoom() -> void:
	await fold_panel()
	await frame_brain()
	await pause(0.8)
	mark("far")
	var kitchen := "space:" + _space_id("Kitchen renovation")
	g.zoom_to(2.3, (g.nodes[kitchen]["pos"] as Vector2) + Vector2(0, 90), 3.2)
	await pause(4.4)
	mark("cards")
	var quote := g.find_node("Contractor quote — Brightline Renovations")
	g.zoom_level("read", quote)
	await pause(4.0)
	mark("read")
	await b.call("open_document_for", quote)
	await pause(3.5)
	mark("document")
	(b.get("viewer") as DocumentViewer).hide_viewer()
	await pause(0.6)


## Scene 5: the same Brain on a timeline, around one item, placed by meaning, growing through time, and in 3D.
func film_views() -> void:
	await fold_panel()
	var fb: GraphFilters = b.get("filters_bar")
	await frame_brain()
	await pause(0.8)
	mark("zones")
	fb.set_view("timeline")
	fb.set_lanes("type")   # a lane per type of item: eleven lanes, one per place, do not fit this window
	await pause(3.4)
	mark("timeline")
	fb.set_lanes("place")
	fb.set_view("zones")
	await pause(0.8)
	calm()
	fb.set_view("focus")
	await pause(3.0)
	mark("focus")
	for id in g.nodes:
		if int(g._focus_hops.get(id, -1)) == 1:
			g.set_focus(str(id))
			break
	await pause(3.0)
	mark("focus-walk")
	fb.set_view("meaning")
	await pause(2.2)
	g.zoom_to(g.zoom * 1.7, null, 1.6)   # the map sits small in the middle: come closer
	await pause(2.4)
	mark("meaning")
	fb.set_view("zones")
	await frame_brain()
	fb.time_button.button_pressed = true
	fb.speed_button.pressed.emit()   # faster: the whole growth fits the shot
	fb.speed_button.pressed.emit()
	fb.set_playing(true)
	mark("play")
	await pause(7.0)
	fb.time_button.button_pressed = false
	fb.speed_button.pressed.emit()   # back to the usual speed
	fb.set_view("layers")
	await pause(2.2)
	mark("layers")
	await pause(4.0)
	var layers: GraphLayers3D = b.get("layers_view")
	if layers != null and layers.items.size() > 0:
		var mid := str((layers.items[layers.items.size() / 2] as Dictionary)["id"])
		layers.fly_to(mid)
		layers.select(mid)
	mark("layers-fly")
	await pause(3.5)
	fb.set_view("zones")
	await pause(0.6)


## Scene 6: a question, its answer with its sources, then the path between two ideas, drawn.
func film_ask() -> void:
	await frame_brain()
	var ap: AssistantPanel = b.get("assistant_panel")
	mark("start")
	await type_in(ap.input, "What did the contractor quote for the kitchen?")
	await pause(0.4)
	ap.input.text = ""
	await ap.send("What did the contractor quote for the kitchen?")
	var end := Time.get_ticks_msec() + 90000
	while ap.busy and Time.get_ticks_msec() < end:
		await pause(0.2)
	mark("answer")
	await pause(5.0)
	var pres: Dictionary = await app.backend.api.call_api("/brain/path?from=" + "Opening story for the talk".uri_encode() + "&to=" + "Automerge".uri_encode())
	if pres["ok"] and bool((pres["data"] as Dictionary).get("found", false)):
		await fold_panel()
		g.zoom_to(0.6, Vector2.ZERO, 0.4)
		await pause(1.0)
		g.set_path((pres["data"] as Dictionary)["ids"], (pres["data"] as Dictionary)["steps"])
		mark("path")
		await pause(4.5)
		g.clear_path()
	else:
		push_error("film: no path " + str(pres))


## Scene 7: the same door, for an AI tool. It proposes over MCP; the proposal waits; Approve; the Archivist files it.
## The tool's calls are made here, through the Brain's real MCP endpoint with a key of its own, in a tool's name.
func film_tool() -> void:
	await frame_brain()
	var lights: Button = b.get("mcp_lights")
	var c: Dictionary = await app.backend.api.call_api("/mcp/clients", true, HTTPClient.METHOD_POST, JSON.stringify({"name": "Claude Code", "level": "propose_items"}))
	var token := str((c["data"] as Dictionary)["token"])
	mark("start")
	await mcp_call(token, "overview", {})
	await lights.call("poll")
	await pause(1.2)
	await mcp_call(token, "search", {"query": "sync example for the talk"})
	await lights.call("poll")
	await pause(1.0)
	await mcp_call(token, "propose_item", {"title": "Talk demo: Automerge for the sync example",
		"content": "Decision taken while building the demo for the local-first talk: the sync example uses Automerge rather than Yjs, because its document history is easier to show on stage. The demo lives in talk-demo/sync.",
		"reason": "A decision taken during a coding session; it belongs with the talk's notes.",
		"suggested_place": "Talk: local-first software"})
	await lights.call("poll")
	mark("proposed")
	await pause(1.5)
	var dlg: AcceptDialog = lights.call("open_dialog")
	await pause(3.0)
	var approve: Button = null
	for bt in dlg.find_children("*", "Button", true, false):
		if (bt as Button).text == I18n.t("Approve") and approve == null:
			approve = bt
	if approve == null:
		push_error("film: no Approve button")
		return
	var sc: Node = approve.get_parent()
	while sc != null and not (sc is ScrollContainer):
		sc = sc.get_parent()
	if sc != null:
		(sc as ScrollContainer).ensure_control_visible(approve)
	await pause(2.5)
	mark("waiting")
	await pause(1.5)
	approve.pressed.emit()
	mark("approved")
	var note_id := ""
	var state := ""
	var end := Time.get_ticks_msec() + 180000
	while state == "" and Time.get_ticks_msec() < end:
		var r: Dictionary = await app.backend.api.call_api("/mcp/proposals?status=all", true)
		for p in (r.get("data", {}) as Dictionary).get("proposals", []) if r.get("ok", false) else []:
			if str((p as Dictionary).get("client_name", "")) == "Claude Code" and str(p.get("status", "")) in ["applied", "failed", "rejected"]:
				state = str(p.get("status", ""))
				note_id = str(p.get("note_id", ""))
		await pause(0.4)
	print("film: proposal ", state)
	await pause(3.0)
	mark("filed")
	dlg.hide()
	await b.call("refresh_graph")
	await pause(1.5)
	await settle()
	var node := ""
	for k in g.nodes:
		if note_id != "" and str(k).ends_with(note_id):
			node = str(k)
	if node != "":
		await fold_panel()
		g.zoom_level("read", node)
	await pause(1.5)
	mark("item")
	await pause(4.5)


## Scene 8: the seven themes, one after the other (the cut takes a beat of each, on its mark).
func film_themes() -> void:
	await fold_panel()
	for theme in ["morning", "focus", "evening", "forest", "terminal", "paper", "neon"]:
		if theme != "morning":
			app.set_theme_choice(theme)  # a theme switch rebuilds the brain screen
			await pause(5.5)
			b = app.current()
			g = b.get("graph")
			await fold_panel()
		await frame_brain()
		await pause(1.0)
		calm()
		mark(theme)
		await pause(2.6)

