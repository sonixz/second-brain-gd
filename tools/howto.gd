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
	if not keep_toast and is_instance_valid(b) and b.get("toast") != null:  # b is freed while the engine room shows
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
## The engine room's Your data card (Loop 30), scrolled into view.
func open_your_data() -> DataPanel:
	app.show_console()
	await pause(3.0)
	var dp: DataPanel = app.current().find_child("DataPanel", true, false)
	var sc: ScrollContainer = app.current().find_children("*", "ScrollContainer", true, false)[0]
	await pause(0.5)
	sc.scroll_vertical = int(dp.global_position.y - (sc.get_child(0) as Control).global_position.y - 4.0)
	await pause(0.6)
	return dp


func back_to_brain() -> void:
	app.show_brain()
	await pause(3.0)
	b = app.current()
	g = b.get("graph")
	stage()


func guide_packs() -> void:
	var dp := await open_your_data()
	dp._open_packs()
	await pause(1.2)
	var pd: PacksDialog = null
	for c in dp.get_children():
		if c is PacksDialog:
			pd = c
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
	await step("engine room → Your data → Packs…: choose what leaves, see it before")
	await pd.do_export()
	await pause(1.0)
	await step("export: one .brain file")
	await pd.import_path(file("sourdough-starter.brain"))
	await pause(1.5)
	await step("import a pack someone shared: it becomes a layer")
	pd.queue_free()
	await back_to_brain()
	await b.call("refresh_graph")
	await settle(30.0)
	g.zoom_to(0.45, Vector2(-60, 0), 0.3)
	await pause(2.0)
	calm()
	await step("its items join the graph, in their own place")


# ---------------------------------------------------------------- Bring your Obsidian vault (no model call)
func guide_vault() -> void:
	await overview()
	var dlg: AcceptDialog = b.call("import_folder", file("My vault"))
	await wait_until(func() -> bool: return not (dlg.get("scan") as Dictionary).is_empty(), 15.0)
	await pause(1.0)
	await step("drop the vault: the preview says what it found")
	await dlg.call("run_import")
	await pause(1.0)
	await step("Import: the report, links found and the ones pointing nowhere")
	dlg.hide()
	await b.call("refresh_graph")
	await settle(30.0)
	g.zoom_to(0.42, Vector2(-60, 0), 0.3)
	await pause(2.0)
	calm()
	await step("folders became places, links are the author's")
	var beds := node_like(["raised", "beds"])
	if beds != "":
		g.zoom_level("read", beds)
		g.select(beds)
	await pause(3.0)
	calm()
	await step("the note's picture is kept with it")
	var dp := await open_your_data()
	dp._open_packs()
	await pause(1.5)
	var pd: PacksDialog = null
	for c in dp.get_children():
		if c is PacksDialog:
			pd = c
	if pd != null:
		pd.size = Vector2i(760, 760)
		pd.position = (root.size - pd.size) / 2
	await pause(1.5)
	await step("the vault is a layer: off, merge or remove")
	if pd != null:
		pd.queue_free()
	await back_to_brain()


# ---------------------------------------------------------------- 4. Find how two ideas connect (real answers)
func guide_connect() -> void:
	await overview()
	await b.call("show_search", "countertops")
	await pause(2.0)
	await step("search: hits light up, each with why it matched")
	b.get("search_edit").text = ""
	await b.call("_on_search_changed", "")
	await pause(0.8)
	var ap: AssistantPanel = b.get("assistant_panel")
	await ask(ap, "How is the opening story for my talk connected to Automerge?")
	await pause(2.0)
	calm()
	await step("ask how two ideas connect: the path is drawn", true)
	g.clear_path()
	# A note written straight into a place (no filing, so nothing links it yet): close in meaning to the CRDT notes.
	var made: Dictionary = await app.backend.api.call_api("/brain/notes", true, HTTPClient.METHOD_POST, JSON.stringify({
		"title": "Merging edits without a server", "space_id": _space_id("Local-first software"),
		"body": "Two people edit the same document offline. When they reconnect, the edits merge to the same result and "
			+ "no server decides who wins. Automerge does this with CRDTs, plain words for the talk."}))
	var pick := str((made["data"] as Dictionary).get("id", "")) if made["ok"] else ""
	await _wait_meaning()
	await b.call("refresh_graph")
	await settle(8.0)
	await b.call("open_note", pick, true)
	await pause(2.5)
	await step("open an item: related ideas are suggested")
	var related: Control = b.get("related_box")
	var kept := false
	for btn in related.find_children("*", "Button", true, false):
		if not kept and (btn as Button).text.contains("✓"):
			(btn as Button).pressed.emit()
			kept = true
	await pause(1.5)
	await step("✓ keeps a suggestion as a real link", true)


# ---------------------------------------------------------------- 5. Search the web and keep a page (real answers)
func guide_web() -> void:
	await overview()
	var ap: AssistantPanel = b.get("assistant_panel")
	await ask(ap, "Search the web: what size of circuit does an induction cooktop need?")
	await pause(1.0)
	await step("a question about the world: an answer with its sources")
	var before := int(b.get("classified"))
	await ask(ap, "Add the first source to Kitchen renovation.")
	await wait_until(func() -> bool: return int(b.get("classified")) > before or not ap.busy, 60.0)
	await pause(2.0)
	await step("add it: the page is kept, summarised and filed", true)
	await b.call("refresh_graph")
	await settle(10.0)
	var page := await newest_source_note()
	if page != "":
		g.zoom_level("read", page)
		await pause(3.0)
	await step("the page in the graph, kept for good")


# ---------------------------------------------------------------- 11. Organise by voice (real answers)
func guide_organise() -> void:
	await overview()
	var ap: AssistantPanel = b.get("assistant_panel")
	await ask(ap, "What is still waiting in the Inbox?")
	await step("ask what is waiting")
	await ask(ap, "Put the heat pump rebate note in Finances.")
	await pause(1.5)
	await step("move an item by its name", true)
	await ask(ap, "Link the heat pump rebate to the renovation budget.")
	await pause(1.5)
	await step("link two items", true)
	await ask(ap, "Undo that.")
	await pause(1.5)
	await step("undo the last change", true)


# ---------------------------------------------------------------- 7. Think an idea through with Sparring (real answers)
func guide_sparring() -> void:
	await overview()
	var sp: SbFloatingPanel = b.call("agent_panel", "sparring")
	await b.call("open_agent", "sparring")
	sp.dock = "right"
	sp.dock_size = 470.0
	sp.layout_changed.emit()
	await pause(1.2)
	await step("open Sparring: it waits for your idea")
	var spc: AssistantPanel = b.call("chat_panel", "sparring")
	await ask(spc, "I want to open my local-first talk with a story and no slides for the first three minutes. Challenge me honestly.")
	calm()
	await step("say the idea: it reacts, and asks one question")
	await ask(spc, "Instead of a diagram for CRDTs, I'd use a shared recipe card that everyone edits at once.")
	calm()
	await step("answer: it pushes further, using what your Brain holds")
	await ask(spc, "Good. Sum it up.")
	await wait_until(func() -> bool: return spc.last_draft != "", 30.0)
	await pause(1.5)
	calm()
	await step("“sum it up”: the synthesis, shown in full, not saved yet")
	var before := int(b.get("classified"))
	await ask(spc, "Yes, save it.")
	await wait_until(func() -> bool: return int(b.get("classified")) > before, 30.0)
	await pause(1.5)
	calm()
	await step("“yes, save it”: the Archivist files it", true)


# ---------------------------------------------------------------- 8. Create your own agent (real answers)
func guide_own_agent() -> void:
	await overview()
	var layer: SbPanelLayer = b.get("panel_layer")
	layer.create_requested.emit()  # the rail's « + »
	await wait_until(func() -> bool:
		var c: AssistantPanel = b.call("chat_panel", "builder")
		return c != null and c.messages_shown >= 3 and not c.busy, 60.0)
	var bc: AssistantPanel = b.call("chat_panel", "builder")
	var bp: SbFloatingPanel = b.call("agent_panel", "builder")
	bp.dock = "right"
	bp.dock_size = 470.0
	bp.layout_changed.emit()
	await pause(1.2)
	await step("+ on the rail: the Agent Builder asks what the agent is for")
	await ask(bc, "A coach to rehearse my local-first talk out loud before the meetup. It should know my talk.")
	await step("answer in a sentence or two: it asks the next question")
	var answers := ["Demanding but kind, short spoken answers, no lists. It times each part against the 20 minutes.",
		"It only reads my Brain, it never changes anything. That's all, write it."]
	for a in answers:
		if bc.last_agent_draft != "":
			break
		await ask(bc, a)
	var tries := 0
	while bc.last_agent_draft == "" and tries < 2:
		await ask(bc, "That's everything I need. Please write the draft now.")
		tries += 1
	await pause(1.5)
	await step("the draft, in full: role, tone, how it works, what to avoid")
	await ask(bc, "Yes, create it.")
	await b.call("refresh_agents")
	await pause(2.0)
	await step("“yes, create it”: its letter joins the rail", true)
	var made := ""
	for id in (b.get("agent_chats") as Dictionary).keys():
		if not str(id) in ["archivist", "sparring", "builder"]:
			made = str(id)
	if made != "":
		bp.set_minimized(true)
		await b.call("open_agent", made)
		var mp: SbFloatingPanel = b.call("agent_panel", made)
		mp.dock = "right"
		mp.dock_size = 470.0
		mp.layout_changed.emit()
		var mc: AssistantPanel = b.call("chat_panel", made)
		await ask(mc, "Let's start with the opening. Here it goes: last year, on a plane, I lost a whole afternoon of notes because my app needed the cloud.")
		await step("talk to it in its own panel")
		await b.call("show_agent_info", made)
		await pause(1.2)
		await step("ⓘ its settings: switches, model, instructions")


# ---------------------------------------------------------------- Plan the week's meals with a mission (real answers)
## Loop 36: the Archivist gets the Missions capability, then a real mission on the real web (recorded once): the
## week's specials, a question, real recipes, a draft approved into the Brain, and its cost in the engine room.
func guide_mission() -> void:
	await overview()
	await app.backend.api.call_api("/assistant/agents/archivist", true, HTTPClient.METHOD_PATCH,
		JSON.stringify({"missions": {"max_cost": 1.0, "max_minutes": 12}}))
	var panel: SbFloatingPanel = b.call("agent_panel", "archivist")
	panel.reveal()
	panel.dock = "right"
	panel.dock_size = 540.0
	panel.layout_changed.emit()
	await b.call("show_agent_info", "archivist")
	await pause(1.0)
	var sett: SbAgentSettings = b.get("agent_settings")
	(sett.checks["missions"] as CheckButton).button_pressed = true
	await wait_until(func() -> bool: return "missions" in (sett.prof.get("capabilities", []) as Array), 10.0)
	await pause(0.6)
	var sw := (sett.checks["missions"] as Control).get_parent() as Control  # the Missions switch, its block below
	sett.scroll_vertical = maxi(0, int(sw.position.y) - 12)
	await pause(0.8)
	await step("ⓘ: switch Missions on, its ceiling below")
	b.call("close_agent_settings")
	var chat: AssistantPanel = b.call("chat_panel", "archivist")
	var card: Control = chat.mission_card
	chat.mission_row.visible = true
	chat.mission_edit.text = "This week's dinners from the Maxi flyer: 3 suppers with real recipes, and the grocery list"
	await pause(0.8)
	await step("Mission…: say what the job is")
	await chat.start_mission(chat.mission_edit.text)
	await wait_until(func() -> bool:
		var plan: Array = (card.get("mission") as Dictionary).get("plan", [])
		return plan.any(func(st: Dictionary) -> bool: return st.get("status", "") == "done") \
			or str((card.get("mission") as Dictionary).get("status", "")) != "running", 240.0)
	await pause(1.0)
	await step("it works in the background: the plan, ticked step by step")
	await wait_until(func() -> bool: return str((card.get("mission") as Dictionary).get("status", "")) != "running", 420.0)
	if str((card.get("mission") as Dictionary).get("status", "")) == "waiting":  # the recorded run did not ask
		var boxes: Array = card.get("choice_boxes")
		for i in mini(3, boxes.size()):
			(boxes[i] as BaseButton).button_pressed = true
		await card.call("answer")
	await wait_until(func() -> bool:
		return str((card.get("mission") as Dictionary).get("status", "")) in ["draft", "stopped", "failed"], 420.0)
	(card.get("draft_open") as Dictionary)[0] = true
	card.call("_rebuild")
	await pause(1.0)
	await step("the draft: real recipes with their links, the plan, the list")
	await card.call("approve")
	await wait_until(func() -> bool: return str((card.get("mission") as Dictionary).get("status", "")) == "saved", 60.0)
	await pause(1.5)
	await step("approve: everything is saved at once, one Undo removes it")
	await b.call("refresh_graph")
	await settle(10.0)
	var res: Dictionary = (card.get("mission") as Dictionary).get("result", {}) if (card.get("mission") as Dictionary).get("result") is Dictionary else {}
	var ids: Array = res.get("note_ids", [])
	if not ids.is_empty():
		g.zoom_level("read", str(ids[0]))
		await pause(3.0)
	calm()
	await step("the recipes in your Brain, linked to the week's plan")
	app.show_console()
	await pause(4.0)
	var console: Control = app.current()
	var mp: Control = console.find_child("MissionsPanel", true, false)
	if mp != null:
		await mp.call("refresh")
		var ms: Array = mp.get("missions")
		if not ms.is_empty():
			mp.set("open_id", str((ms[0] as Dictionary).get("id", "")))
			mp.call("_rebuild")
		await pause(0.6)
		var sc := mp.get_parent().get_parent() as ScrollContainer
		if sc != null:
			sc.scroll_vertical = int(mp.position.y) - 8
	await pause(0.8)
	await step("the engine room: what it did, its sources, what it cost")


# ---------------------------------------------------------------- 6. Connect your browser (real Edge, real answers)
## A real Microsoft Edge on the Windows desktop, driven by tools/howto/edge.ps1: a throwaway profile (no sign-in),
## the extension loaded from browser-extension/. Its screenshots are the Edge window itself, toolbar and all.
## Only with tools/howto.sh --edge (it needs Windows and a few minutes of the screen).
var edge_ps1 := ""
var edge_out := ""


func edge(args: Array) -> String:
	var out := []
	var code := OS.execute("powershell.exe", ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", edge_ps1] + args, out, true)
	var text := "".join(out).strip_edges()
	print("edge %s: %s" % [args[0], text.left(300)])
	if code != 0:
		push_error("edge %s failed: %s" % [args[0], text.left(400)])
	return text


## A step whose screenshot is the Edge window (focus first unless an extension popup must stay open).
func edge_step(what: String, focus: bool = true) -> void:
	step_n += 1
	if focus:
		edge(["focus"])
	edge(["shot", edge_out + "\\%02d.png" % step_n])
	print("step %02d: %s (Edge)" % [step_n, what])


func popup(js: String) -> String:
	return edge(["eval", "/popup.html", js, "gesture"])


func open_popup() -> void:
	edge(["focus"])
	edge(["eval", "/background.js", "chrome.action.openPopup().then(() => 'open')", "gesture"])
	await pause(1.2)


func guide_browser() -> void:
	edge_ps1 = OS.get_environment("SBGD_EDGE_PS1")
	edge_out = OS.get_environment("SBGD_EDGE_OUT")
	await overview()
	# 1. The app: Captures → Send from browser… → Pair a browser.
	var cv: CapturesView = b.get("captures_view")
	await b.call("set_view", "captures")
	await pause(0.8)
	await cv.show_bookmarklet()
	await pause(0.8)
	var dlg: AcceptDialog = null
	for c in cv.get_children():
		if c is AcceptDialog:
			dlg = c
	for btn in dlg.find_children("*", "Button", true, false):
		if (btn as Button).text == "Pair a browser":
			(btn as Button).pressed.emit()
	await pause(1.5)
	await step("the app shows a one-time pairing code and its port")
	var code := cv.pair_code
	var port := str(app.backend.api.port)
	# 2. Edge: the extension's popup, code and port typed in.
	edge(["launch", OS.get_environment("SBGD_EDGE_EXT"), "https://en.wikipedia.org/wiki/Heat_pump"])
	await pause(4.0)
	edge(["dismiss", "Not now"])
	await open_popup()
	popup("document.getElementById('code').value = '%s'; document.getElementById('port').value = '%s'; 'typed'" % [code, port])
	await pause(0.5)
	await edge_step("Edge: the extension's popup, code and port typed in", false)
	# 3. Pair: Edge asks for the permission to read the pages the Brain opens.
	popup("document.getElementById('pairBtn').click(); 'clicked'")
	await pause(2.0)
	await edge_step("Edge asks: let the extension read the pages", false)
	for i in 3:  # Edge's own prompt: Allow (checked from the extension itself, the click is retried if needed)
		edge(["click", "Allow"])
		await pause(1.0)
		if edge(["eval", "/background.js", "chrome.permissions.contains({origins: ['<all_urls>']})"]) == "true":
			break
	# 4. The app: connected, with the browser's name.
	var state_ok := func() -> bool:
		for l in dlg.find_children("*", "Label", true, false):
			if (l as Label).text.begins_with("● Connected") and not (l as Label).text.contains(" need "):
				return true
		return false
	if not await wait_until(state_ok, 40.0):
		push_error("browser: the extension did not connect")
		edge(["close"])
		return
	await pause(0.8)
	await step("the app: ● Connected: Edge")
	dlg.queue_free()
	# 5. Edge: Send this page.
	var before := int(b.get("classified"))
	await open_popup()
	popup("document.getElementById('send').click(); 'sent'")
	var sent := false
	for i in 90:  # the engine reads and files the page (the model summarises it)
		await pause(1.0)
		if popup("document.getElementById('result').hidden ? '' : 'shown'").contains("shown") \
				or popup("document.getElementById('error').hidden ? '' : 'error'").contains("error"):
			sent = true
			break
	await pause(0.5)
	await edge_step("Edge: Send this page, the receipt in the popup", false)
	# 6. The app: the page is in, filed, marked as coming from the browser.
	await wait_until(func() -> bool: return int(b.get("classified")) > before, 30.0)
	await b.call("set_view", "captures")
	await pause(1.5)
	await step("the app: the page, as Edge showed it, read and filed")
	await b.call("set_view", "graph")
	await pause(0.8)
	# 7. A web search in the app, then "open the first one": Edge opens it.
	var ap: AssistantPanel = b.get("assistant_panel")
	await ask(ap, "Search the web: do cold-climate heat pumps still work at -25 °C?")
	await wait_until(func() -> bool: return not ap.busy, 90.0)
	await pause(1.0)
	await step("a web search: the answer and its sources")
	await ask(ap, "Open the first one.")
	await wait_until(func() -> bool: return not ap.busy, 60.0)
	await pause(4.0)
	await edge_step("Edge opens the page, in a new tab")
	# 8. "Add it": the page as Edge shows it.
	before = int(b.get("classified"))
	await ask(ap, "Add it.")
	await wait_until(func() -> bool: return int(b.get("classified")) > before or not ap.busy, 90.0)
	await wait_until(func() -> bool: return not ap.busy, 60.0)
	await pause(2.0)
	await step("“add it”: the open page is kept and filed", true)
	# 9. "Close it": only the tab the Brain opened.
	await ask(ap, "Close it.")
	await wait_until(func() -> bool: return not ap.busy, 60.0)
	await pause(2.0)
	await edge_step("Edge: the Brain's tab is closed, yours stays")
	edge(["close"])
	if not sent:
		push_error("browser: the page was not sent")


## Pairs the throwaway Edge without screenshots (the browser guide shows the pairing itself).
func edge_connect(url: String) -> bool:
	edge_ps1 = OS.get_environment("SBGD_EDGE_PS1")
	edge_out = OS.get_environment("SBGD_EDGE_OUT")
	var r: Dictionary = await app.backend.api.call_api("/browser/pair/start", true, HTTPClient.METHOD_POST)
	if not r["ok"]:
		return false
	var code := str((r["data"] as Dictionary).get("code", ""))
	edge(["launch", OS.get_environment("SBGD_EDGE_EXT"), url])
	await pause(4.0)
	edge(["dismiss", "Not now"])
	await open_popup()
	popup("document.getElementById('code').value = '%s'; document.getElementById('port').value = '%d'; document.getElementById('pairBtn').click(); 'paired'" % [code, app.backend.api.port])
	await pause(2.0)
	for i in 3:
		edge(["click", "Allow"])
		await pause(1.0)
		if edge(["eval", "/background.js", "chrome.permissions.contains({origins: ['<all_urls>']})"]) == "true":
			break
	var end := Time.get_ticks_msec() + 30000
	while Time.get_ticks_msec() < end:
		var st: Dictionary = await app.backend.api.call_api("/browser/status")
		if st["ok"] and bool((st["data"] as Dictionary).get("connected", false)) and bool((st["data"] as Dictionary).get("can_read_tabs", false)):
			return true
		await pause(1.0)
	return false


## A real right-click in Edge (DevTools mouse events): Edge opens its own context menu at that point.
func edge_right_click(js_point: String) -> void:
	var at := edge(["eval", "wikipedia.org", js_point]).replace("\"", "")
	await pause(1.0)
	var x := at.get_slice(",", 0)
	var y := at.get_slice(",", 1)
	for kind in ["mouseMoved", "mousePressed", "mouseReleased"]:
		var extra := "" if kind == "mouseMoved" else ";button=right;clickCount=1"
		edge(["cdp", "wikipedia.org", "Input.dispatchMouseEvent", "type=%s;x=%s;y=%s%s" % [kind, x, y, extra]])
	await pause(1.5)


# ---------------------------------------------------------------- 6b. Keep the pictures that matter (real Edge, real answers)
func guide_images() -> void:
	await overview()
	if not await edge_connect("https://en.wikipedia.org/wiki/Heat_pump"):
		push_error("images: the extension did not connect")
		edge(["close"])
		return
	# a fundraising banner may cover the article: close it the way a reader would (it can appear a moment later)
	await pause(3.0)
	edge(["eval", "wikipedia.org", "(() => { const m = [...document.querySelectorAll('a, button')].find((e) => /maybe later|close/i.test(e.textContent || e.getAttribute('aria-label') || '')); if (m) m.click(); return m ? 'closed' : 'none'; })()"])
	await pause(1.0)
	# 1. Send a page with pictures: its main image and its figures come with it.
	var before := int(b.get("classified"))
	await open_popup()
	popup("document.getElementById('send').click(); 'sent'")
	for i in 120:
		await pause(1.0)
		if popup("document.getElementById('result').hidden && document.getElementById('error').hidden ? '' : 'done'").contains("done"):
			break
	await pause(0.5)
	await edge_step("Edge: Send this page; the receipt counts the pictures kept", false)
	# 2. The page's card in the graph shows its main image.
	await wait_until(func() -> bool: return int(b.get("classified")) > before, 30.0)
	(b.get("toast") as Control).visible = false
	await b.call("refresh_graph")
	await settle(10.0)
	var page := await newest_source_note()
	if page != "":
		g.zoom_level("read", page)
		await pause(4.0)
	await step("the page's card shows its main image")
	# 3. The reading view: the kept pictures, with their captions, then the text.
	await b.call("open_document_for", page)
	await pause(3.0)
	await step("the reading view: the pictures first, with their captions")
	var viewer: Variant = b.get("viewer")
	if viewer != null:
		viewer.call("hide_viewer")
	await pause(0.5)
	# 4. Right-click a diagram in Edge: Send this image to the Brain.
	edge(["focus"])
	await edge_right_click("(() => { const f = [...document.querySelectorAll('figure')].find((x) => /indoor compartment/.test(x.innerText)); "
		+ "const i = f.querySelector('img'); window.scrollBy(0, i.getBoundingClientRect().top - 120); "
		+ "const r = i.getBoundingClientRect(); return Math.round(r.x + r.width / 2) + ',' + Math.round(r.y + 50); })()")
	await edge_step("Edge: right-click a diagram → Send this image to the Brain", false)
	before = int(b.get("classified"))
	edge(["click", "Send this image to the Brain", "menu"])
	# 5. The picture is an item of its own: described, filed, linked to its page.
	await wait_until(func() -> bool: return int(b.get("classified")) > before, 90.0)
	await pause(1.0)
	(b.get("toast") as Control).visible = false
	await b.call("refresh_graph")
	await settle(10.0)
	var pic := await newest_source_note()
	if pic != "" and pic != page:
		g.zoom_level("read", pic)
		await pause(4.0)
	await step("the diagram, an item of its own: described and filed")
	# 6. Ask about it: the Archivist answers from what the picture shows.
	var ap: AssistantPanel = b.get("assistant_panel")
	await ask(ap, "What does the heat pump diagram I just kept show?")
	await wait_until(func() -> bool: return not ap.busy, 90.0)
	await pause(1.5)
	await step("ask about it: the answer comes from the picture")
	edge(["close"])


# ---------------------------------------------------------------- Back up and restore (scripted)
func guide_backups() -> void:
	var dp := await open_your_data()
	await pause(0.8)
	await step("the engine room, Your data: where backups go, how often")
	await dp.back_up_now()
	await pause(0.8)
	await step("Back up now: a full backup, read back and checked")
	var rows: Array = dp.last.get("backups", [])
	var first: Dictionary = rows[0]
	dp._restore(str(first.get("id", "")), SbFormat.datetime_text(str(first.get("created_at", ""))))
	await pause(0.6)
	var dlg: ConfirmationDialog = null
	for c in dp.get_children():
		if c is ConfirmationDialog:
			dlg = c
	var edit: LineEdit = dlg.find_children("*", "LineEdit", true, false)[0]
	edit.text = I18n.t("RESTORE")
	edit.text_changed.emit(edit.text)
	await pause(0.5)
	await step("Restore…: type the word; a safety copy comes first")
	dlg.queue_free()
	await dp.restore(str(first.get("id", "")))
	await pause(0.8)
	await step("restored, and the state before it kept as a safety copy")
	dp._export()
	for i in 40:
		await pause(0.5)
		if dp.result_label.text.begins_with(I18n.t("Saved: %s (%s). Copy it to the other computer, then Import a backup file there.").get_slice("%s", 0)):
			break
	await pause(0.5)
	await step("Export everything: one file to move your Brain to another computer")
