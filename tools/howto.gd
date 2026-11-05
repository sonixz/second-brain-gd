extends "res://tools/capture_base.gd"
## The How-to guides (tools/howto.sh): each guide is a short scenario played on the real app, a screenshot per
## step. SBGD_GUIDE picks the guide; the text of each step lives in tools/howto/guides.py (same step numbers).
## Clicks, typing and voice requests are simulated; the app, the engine and (for "real" guides) the model's
## answers are real: recorded once with the real model, replayed afterwards.

var files_dir := ""
var step_n := 0


func _run() -> void:
	files_dir = OS.get_environment("SBGD_HOWTO_FILES")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	var guide := OS.get_environment("SBGD_GUIDE")
	print("guide ", guide)
	var fn := "guide_" + guide.replace("-", "_")
	if not has_method(fn):
		push_error("howto: no guide called " + guide)
		quit(1)
		return
	await call(fn)
	await finish()


## One screenshot per step, numbered like the steps in guides.py.
func step(what: String, keep_toast: bool = false) -> void:
	step_n += 1
	if not keep_toast and b.get("toast") != null:
		(b.get("toast") as Control).visible = false
	await shot("%02d" % step_n)
	print("step %02d: %s" % [step_n, what])


## Waits until a condition holds (a reply arrived, an item was filed…), at most limit_s seconds.
func wait_until(cond: Callable, limit_s: float = 60.0) -> bool:
	var end := Time.get_ticks_msec() + int(limit_s * 1000.0)
	while Time.get_ticks_msec() < end:
		if cond.call():
			return true
		await pause(0.3)
	return false


## The graph node whose title contains every word (case-insensitive), "" if none.
func node_like(words: Array) -> String:
	for id in g.nodes:
		var label := str((g.nodes[id] as Dictionary).get("label", "")).to_lower()
		var ok := true
		for w in words:
			ok = ok and label.contains(str(w).to_lower())
		if ok and str((g.nodes[id] as Dictionary).get("type", "")) != "space":
			return str(id)
	return ""


## The item made from the file or page added last.
func newest_source_note() -> String:
	var r: Dictionary = await app.backend.api.call_api("/sources")
	if not r["ok"]:
		return ""
	var list: Array = (r["data"] as Dictionary).get("sources", [])
	return str((list[0] as Dictionary).get("note_id", "")) if not list.is_empty() else ""


func file(name: String) -> String:
	return files_dir.path_join(name)


func overview() -> void:
	g.zoom_to(0.5, Vector2(-60, 0), 0.3)
	await pause(2.0)
	calm()


# ---------------------------------------------------------------- 1. Your first five minutes (real answers)
func guide_first_minutes() -> void:
	await overview()
	var ce: LineEdit = b.get("capture_edit")
	ce.grab_focus()
	ce.text = "Ask Northwind if the heat pump quote includes the smart thermostat"
	ce.caret_column = ce.text.length()
	await pause(0.5)
	await step("a thought typed in the capture bar")
	var before := int(b.get("classified"))
	ce.text_submitted.emit(ce.text)
	await wait_until(func() -> bool: return int(b.get("classified")) > before, 90.0)
	await pause(1.5)
	await step("filed, with a receipt")
	before = int(b.get("classified"))
	b.call("add_source_file", file("heat-pump-quote.pdf"))
	await wait_until(func() -> bool: return int(b.get("classified")) > before, 120.0)
	await pause(2.0)
	await step("a PDF dropped on the window, read and filed")
	(b.get("toast") as Control).visible = false
	await b.call("set_view", "captures")
	await pause(1.5)
	await step("Captures: everything that came in")
	await b.call("set_view", "graph")
	await pause(1.0)
	await b.call("refresh_graph")
	await settle(10.0)
	var pdf := await newest_source_note()
	if pdf != "":
		g.zoom_level("read", pdf)
		await pause(3.0)
	await step("the PDF in the graph, with its first page")


# ---------------------------------------------------------------- 9. Arrange your panels (scripted)
func guide_panels() -> void:
	await overview()
	await step("the default layout: the Archivist on the left, the rail")
	var layer: SbPanelLayer = b.get("panel_layer")
	var sp: SbFloatingPanel = b.call("agent_panel", "sparring")
	sp.reveal()
	sp.dock = "free"
	sp.free_rect = Rect2(root.size.x * 0.45, 150, 420, 520)
	sp.layout_changed.emit()
	await pause(0.8)
	layer.show_drop(sp, "right")
	await step("drag a panel by its title bar: where it will land lights up")
	layer.show_drop(sp, "")
	sp.dock = "right"
	sp.dock_size = 420.0
	sp.layout_changed.emit()
	var places: SbFloatingPanel = b.get("places_panel")
	places.reveal()
	places.dock = "left"
	places.layout_changed.emit()
	await pause(1.0)
	await step("docked: Sparring on the right, Places stacked under the Archivist")
	var arch: SbFloatingPanel = b.get("archivist_panel")
	layer.move_split(arch, places, 160.0)
	await pause(0.6)
	await step("drag the line between two stacked panels to share the height")
	places.set_minimized(true)
	sp.set_minimized(true)
	await pause(1.0)
	await step("shrunk panels wait as letters on the rail")
	b.call("toggle_focus_mode")
	await pause(1.0)
	await step("Tab: the graph alone", true)
	b.call("toggle_focus_mode")
	await pause(0.6)
	places.reveal()
	await pause(1.0)
	var ps := places.body as ScrollContainer
	ps.scroll_vertical = int(ps.get_v_scroll_bar().max_value)
	await pause(0.5)
	await step("Reset the panel layout, at the bottom of Places")


# ---------------------------------------------------------------- 2. Read a scanned PDF (real answers, recorded OCR)
func guide_scanned_pdf() -> void:
	await overview()
	var before := int(b.get("classified"))
	b.call("add_source_file", file("insurance-renewal-scan.pdf"))  # not awaited: the progress shows meanwhile
	var toast_label: Label = b.get("toast_label")
	await wait_until(func() -> bool: return toast_label != null and toast_label.text.contains("read (local OCR)"), 30.0)
	await pause(0.3)
	await step("the scan is read page by page, on this computer", true)
	await wait_until(func() -> bool: return int(b.get("classified")) > before, 120.0)
	await pause(1.5)
	await step("filed, with what the pages say", true)
	var note := await newest_source_note()
	await b.call("open_document_for", note)
	await pause(2.5)
	await step("the original pages, read by Windows OCR")
	var dv: DocumentViewer = b.get("viewer")
	dv.hide_viewer()
	await pause(0.5)
	var ap: AssistantPanel = b.get("assistant_panel")
	await ask(ap, "When does my home insurance renew, and what is the new premium?")
	await step("ask about it: the answer comes from the scanned pages")
	await b.call("open_document_for", note)
	await pause(1.5)
	await dv.reread_with_ai()
	await pause(1.0)
	await step("Re-read with AI, only if the reading needs it")


# ---------------------------------------------------------------- 3. Find your way in the graph (scripted)
func guide_graph() -> void:
	g.zoom_to(0.42, Vector2(-60, 0), 0.3)
	await pause(2.5)
	calm()
	await step("from afar: one zone per place, the Inbox in the middle")
	var kitchen := "space:" + str(_space_id("Kitchen renovation"))
	g.zoom_to(2.3, (g.nodes[kitchen]["pos"] as Vector2) + Vector2(0, 90), 0.4)
	await pause(2.5)
	await step("closer: items become cards")
	var art := g.find_node("Local-first software: you own your data")
	g.zoom_level("read", art)
	await pause(2.5)
	await step("closer still: the full text, inside the graph")
	g.zoom_to(0.62, Vector2(-40, 0), 0.3)
	await b.call("fold_place", "Cooking", true)
	await b.call("fold_place", "Apartment move 2025", true)
	await pause(1.5)
	await settle(8.0)
	calm()
	await step("fold the places you are not using")
	var fb: GraphFilters = b.get("filters_bar")
	fb.apply({"types": ["article"]})
	fb.call("_open")
	await pause(1.5)
	await settle(8.0)
	calm()
	await step("filter: only the articles")
	fb.apply({})
	fb.popup.hide()
	await b.call("fold_place", "Cooking", false)
	await b.call("fold_place", "Apartment move 2025", false)
	await pause(1.0)
	fb.legend_button.button_pressed = true
	await pause(1.0)
	await step("? : what the lines mean")
	fb.legend_button.button_pressed = false
	fb.timeline_button.button_pressed = true
	await pause(3.0)
	await step("Timeline: the same items along time")
	fb.timeline_button.button_pressed = false


# ---------------------------------------------------------------- 10. Share a project as a pack (scripted)
func guide_packs() -> void:
	await b.call("set_view", "captures")
	await pause(0.8)
	var cv: CapturesView = b.get("captures_view")
	var pd := cv.open_packs()
	await pause(1.2)
	pd.scope.select(1)
	pd._fill_values()
	for i in pd.value.item_count:
		if pd.value.get_item_text(i) == "Kitchen renovation":
			pd.value.select(i)
	pd.title_edit.text = "Kitchen renovation"
	pd.author_edit.text = "Sam"
	pd.refresh_preview()
	pd.size = Vector2i(760, 640)
	pd.position = (root.size - pd.size) / 2
	await pause(1.5)
	await step("Captures → Packs…: choose what leaves, see it before")
	await pd.do_export()
	await pause(1.0)
	await step("export: one .brain file")
	await pd.import_path(file("sourdough-starter.brain"))
	await pause(1.5)
	await step("import a pack someone shared: it becomes a layer")
	pd.queue_free()
	await b.call("set_view", "graph")
	await pause(1.0)
	await b.call("refresh_graph")
	await settle(10.0)
	g.zoom_to(0.45, Vector2(-60, 0), 0.3)
	await pause(2.0)
	calm()
	await step("its items join the graph, in their own place")
