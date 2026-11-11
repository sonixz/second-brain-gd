extends "res://tools/capture_base.gd"
## Website screenshots (tools/showcase.sh): the English showcase Brain (SBGD_SEED=showcase) through the real
## app, a scripted model (SBGD_ASSISTANT_PROVIDER=showcase) and fake voice: nothing calls OpenAI.
## One shot per idea of the product: intake and receipts, the graph and its zoom, originals, search, paths,
## filters, timeline, packs, voice, agents, the web, panels.


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return

	# 1. The whole Brain: a zone per place, the Inbox in the middle.
	g.zoom_to(0.5, Vector2(-60, 0), 0.3)
	await pause(3.0)
	await shot("01-graph-overview")

	# 2. Intake: a thought typed in the capture bar, filed by the archivist with a receipt.
	var ce: LineEdit = b.get("capture_edit")
	ce.text = "Ask Marc if the induction cooktop for the kitchen needs its own 40 A circuit"
	ce.text_submitted.emit(ce.text)
	var end := Time.get_ticks_msec() + 30000
	while int(b.get("classified")) == 0 and Time.get_ticks_msec() < end:
		await pause(0.3)
	await pause(1.2)
	await shot("02-capture-receipt")

	# 3. Captures: everything that came in, where it went, typed/spoken/web/file.
	(b.get("toast") as Control).visible = false  # the receipt was shown in shot 2
	await b.call("set_view", "captures")
	await pause(1.5)
	stage()
	await shot("03-captures")
	await b.call("set_view", "graph")
	await pause(1.0)

	# 4–5. Semantic zoom: cards, then the full text inside one item.
	await settle()
	var kitchen := "space:" + str(_space_id("Kitchen renovation"))
	g.zoom_to(2.3, (g.nodes[kitchen]["pos"] as Vector2) + Vector2(0, 90), 0.4)
	await pause(2.5)
	await shot("04-graph-cards")
	var art := g.find_node("Local-first software: you own your data")
	g.zoom_level("read", art)
	await pause(2.5)
	await shot("05-graph-read")

	# 6–7. Originals: the PDF quote inside the graph, then full screen.
	var quote := g.find_node("Contractor quote — Brightline Renovations")
	g.zoom_level("read", quote)
	await pause(3.0)
	await shot("06-document-card")
	await b.call("open_document_for", quote)
	await pause(2.0)
	await shot("07-document-viewer")
	var dv: DocumentViewer = b.get("viewer")
	dv.hide_viewer()
	var sketch := g.find_node("Kitchen layout sketch")
	g.zoom_level("read", sketch)
	await pause(3.0)
	await shot("08-image-card")

	# 9. Search lights up the graph, with the reason for each hit.
	g.zoom_to(0.6, Vector2.ZERO, 0.3)
	await pause(1.5)
	await b.call("show_search", "countertops")
	await pause(2.0)
	await shot("09-search")
	b.get("search_edit").text = ""
	await b.call("_on_search_changed", "")

	# 10. « How is X connected to Y? »: the path, drawn.
	var pres: Dictionary = await app.backend.api.call_api("/brain/path?from=" + "Opening story for the talk".uri_encode() + "&to=" + "Automerge".uri_encode())
	if pres["ok"] and bool((pres["data"] as Dictionary).get("found", false)):
		g.set_path((pres["data"] as Dictionary)["ids"], (pres["data"] as Dictionary)["steps"])
		await pause(2.5)
		await shot("10-path")
		g.clear_path()
	else:
		push_error("showcase: no path " + str(pres))

	# 11. Folded places and a filter: only the articles.
	g.zoom_to(0.85, Vector2(-250, -80), 0.3)
	await b.call("fold_place", "Cooking", true)
	await b.call("fold_place", "Apartment move 2025", true)
	(b.get("filters_bar") as GraphFilters).apply({"types": ["article"]})
	await pause(1.0)
	await settle(10.0)
	calm()
	await shot("11-filtered")
	(b.get("filters_bar") as GraphFilters).apply({})
	await b.call("fold_place", "Cooking", false)
	await b.call("fold_place", "Apartment move 2025", false)
	await pause(0.5)

	# 12. Timeline: three weeks, one lane per place.
	(b.get("filters_bar") as GraphFilters).set_view("timeline")
	await pause(3.0)
	await shot("12-timeline")
	(b.get("filters_bar") as GraphFilters).set_view("zones")
	await pause(1.5)

	# 13. Brain packs: one place exported as a file someone else can import as a layer.
	await b.call("set_view", "captures")
	await pause(0.8)
	var cv: CapturesView = b.get("captures_view")
	var pd := cv.open_packs()
	await pause(1.2)
	pd.scope.select(1)
	pd._fill_values()
	for i in pd.value.item_count:
		if pd.value.get_item_text(i) == "Local-first software":
			pd.value.select(i)
	pd.title_edit.text = "Local-first software, reading notes"
	pd.refresh_preview()
	await pause(1.5)
	pd.size = Vector2i(760, 600)
	pd.position = (root.size - pd.size) / 2
	await pause(0.5)
	await shot("13-packs")
	pd.queue_free()
	await b.call("set_view", "graph")
	await pause(1.0)

	# 14. Live conversation (F9): the archivist answers aloud and drives the graph.
	SbSettings.set_value("voice", "headphones", true)
	var lc: LiveConversation = app.live
	await lc.start(false)
	await pause(1.0)
	var ap: AssistantPanel = b.get("assistant_panel")
	await ap.add_live("user", "How is the opening story for my talk connected to Automerge?")
	await ap.add_live("assistant", "Through your talk outline: it points to CRDTs in plain words, which cites Automerge.")
	var pres2: Dictionary = await app.backend.api.call_api("/brain/path?from=" + "Opening story for the talk".uri_encode() + "&to=" + "Automerge".uri_encode())
	if pres2["ok"] and bool((pres2["data"] as Dictionary).get("found", false)):
		g.set_path((pres2["data"] as Dictionary)["ids"], (pres2["data"] as Dictionary)["steps"])
	calm()
	lc._set_state("listening")
	await pause(2.0)
	await shot("14-live-voice")
	lc.stop("user")
	g.clear_path()
	SbSettings.set_value("voice", "headphones", false)
	await pause(1.0)

	# 17. Internet: the archivist searches the web and answers with its sources as links.
	b.call("_update_capture_hint")
	g.zoom_to(0.62, Vector2(-40, 0), 0.3)
	await pause(1.5)
	calm()
	await ask(ap, "Search the web for the circuit an induction cooktop needs")
	await pause(1.0)
	await shot("17-web-search")

	# 18. Sparring, docked on the right: it challenges the idea, then drafts a synthesis to approve.
	var sp: SbFloatingPanel = b.call("agent_panel", "sparring")
	await b.call("open_agent", "sparring")
	sp.dock = "right"
	sp.dock_size = 470.0
	sp.layout_changed.emit()
	var spc: AssistantPanel = b.call("chat_panel", "sparring")
	await ask(spc, "I want to open my local-first talk with a story and no slides. Challenge me.")
	await ask(spc, "Instead of the diagram: a shared recipe card that everyone edits at once.")
	await ask(spc, "Good. Sum it up.")
	await pause(1.5)
	calm()
	await shot("18-sparring")

	# 19. The Agent Builder interviews, then shows the new agent in full before creating it.
	sp.set_minimized(true)
	var bp: SbFloatingPanel = null
	await b.call("open_agent", "builder")
	bp = b.call("agent_panel", "builder")
	bp.dock = "right"
	bp.dock_size = 470.0
	bp.layout_changed.emit()
	var bc: AssistantPanel = b.call("chat_panel", "builder")
	await ask(bc, "I'd like a coach to rehearse my talk.")
	await ask(bc, "Tough but kind, short answers. It should know my talk.")
	await pause(1.5)
	await shot("19-agent-builder")
	bp.set_minimized(true)

	# 20. Panels: dragging one shows where it will land; shrunk panels wait on the rail.
	sp.set_minimized(false)
	await pause(0.6)
	sp.dock = "free"
	sp.free_rect = Rect2(root.size.x * 0.52, 150, 420, 520)
	sp.layout_changed.emit()
	await pause(0.8)
	var layer: SbPanelLayer = b.get("panel_layer")
	layer.show_drop(sp, "right")
	await shot("20-panels")
	layer.show_drop(sp, "")
	sp.reset()
	await pause(0.5)

	# 21. The browser: the extension's pairing code (and the bookmark, without the extension).
	await b.call("set_view", "captures")
	await pause(0.8)
	await cv.show_bookmarklet()
	await pause(0.8)
	var dlg: AcceptDialog = null
	for c in cv.get_children():
		if c is AcceptDialog:
			dlg = c
	if dlg != null:
		for btn in dlg.find_children("*", "Button", true, false):
			if (btn as Button).text == "Pair a browser":
				(btn as Button).pressed.emit()
		await pause(1.5)
		for l in dlg.find_children("*", "Label", true, false):  # the showcase engine runs on a test port; show the default
			if (l as Label).text.contains("port "):
				(l as Label).text = (l as Label).text.get_slice("port ", 0) + "port 8765"
		await shot("21-browser")
		dlg.queue_free()
	await b.call("set_view", "graph")
	await pause(1.0)

	# 15. The same Brain in the evening theme.
	app.set_theme_choice("evening")
	await pause(6.0)
	b = app.current()
	stage()
	(b.get("greeting") as Label).text = "Good evening"
	g = b.get("graph")
	g.zoom_to(0.5, Vector2(-60, 0), 0.3)
	await pause(3.0)
	await shot("15-evening")

	# 16. An agent's settings (ⓘ), in a tile: on/off capabilities, model, instructions.
	await b.call("show_agent_info", "sparring")
	await pause(1.0)
	await shot("16-agent-settings")
	b.call("close_agent_settings")

	await finish()
