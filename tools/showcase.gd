extends SceneTree
## Website screenshots (tools/showcase.sh): the English showcase Brain (SBGD_SEED=showcase) through the real
## app, a scripted model (SBGD_ASSISTANT_PROVIDER=showcase) and fake voice: nothing calls OpenAI.
## One shot per idea of the product: intake and receipts, the graph and its zoom, originals, search, paths,
## filters, timeline, packs, voice.

var out_dir := ""
var app: SbApp
var b: Control
var g: GraphView


func _initialize() -> void:
	out_dir = OS.get_environment("SBGD_CAPTURE_DIR")
	DirAccess.make_dir_recursive_absolute(out_dir)
	_run.call_deferred()


func shot(name: String) -> void:
	await process_frame
	await process_frame
	root.get_texture().get_image().save_png(out_dir.path_join(name + ".png"))
	print("captured ", name)


func pause(s: float) -> void:
	await create_timer(s).timeout


## The showcase is taken "in the morning", like its theme.
func stage() -> void:
	(b.get("greeting") as Label).text = "Good morning"


func _install() -> bool:
	app = load("res://scenes/main.tscn").instantiate()
	root.add_child(app)
	await pause(1.0)
	(app.current().get("primary") as Button).pressed.emit()
	var setup: Control = app.current()
	var deadline := Time.get_ticks_msec() + 600000
	while app.current_screen == "setup" and Time.get_ticks_msec() < deadline:
		if (setup.get("continue_button") as Button).visible:
			(setup.get("continue_button") as Button).pressed.emit()
		await pause(0.3)
	while app.current_screen not in ["onboarding", "brain"] and Time.get_ticks_msec() < deadline:
		await pause(0.2)
	if app.current_screen == "onboarding":
		await pause(0.5)
		(app.current().get("panel") as VoiceKeyPanel).skipped.emit()
	while app.current_screen != "brain" and Time.get_ticks_msec() < deadline:
		await pause(0.2)
	return app.current_screen == "brain"


## No item focused or highlighted: the graph at rest.
func calm() -> void:
	g.selected = ""
	g.hovered = ""
	g.highlight = {}


func _space_id(name: String) -> String:
	for id in g.nodes:
		var nd: Dictionary = g.nodes[id]
		if str(nd["type"]) == "space" and str(nd["label"]) == name:
			return str(id).trim_prefix("space:")
	return ""


func _wait_meaning() -> void:
	var end := Time.get_ticks_msec() + 60000
	while Time.get_ticks_msec() < end:
		var ms: Dictionary = await app.backend.api.call_api("/brain/meaning/status")
		if ms["ok"] and int((ms["data"] as Dictionary).get("pending", 1)) == 0 and int((ms["data"] as Dictionary).get("embedded", 0)) > 0:
			return
		await pause(1.0)


## Waits until the layout has settled, so items sit still in their zones.
func settle(limit_s: float = 25.0) -> void:
	var end := Time.get_ticks_msec() + int(limit_s * 1000.0)
	while g.heat > 0.03 and Time.get_ticks_msec() < end:
		await pause(0.25)


func _run() -> void:
	var size := OS.get_environment("SBGD_SHOT_SIZE")
	root.size = Vector2i(1280, 800) if size == "" else Vector2i(int(size.get_slice("x", 0)), int(size.get_slice("x", 1)))
	OS.set_environment("SBGD_SETTINGS", OS.get_environment("SBGD_HOME").path_join("showcase-settings.cfg"))
	SbSettings.set_value("ui", "theme", "morning")
	SbSettings.set_value("ui", "modules", false)
	SbSettings.set_value("onboarding", "voice_done", true)
	SbSettings.set_value("voice", "speak_replies", false)
	OS.set_environment("SBGD_VOICE_PROVIDER", "fake")
	OS.set_environment("SBGD_BILLING_PROVIDER", "fake")
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	OS.set_environment("SBGD_SEED", "showcase")
	if not await _install():
		push_error("showcase: the brain screen never opened")
		quit(1)
		return
	b = app.current()
	stage()
	await _wait_meaning()
	await b.call("refresh_graph")
	g = b.get("graph")
	await pause(2.0)
	await settle()
	stage()

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
	(b.get("filters_bar") as GraphFilters).timeline_button.button_pressed = true
	await pause(3.0)
	await shot("12-timeline")
	(b.get("filters_bar") as GraphFilters).timeline_button.button_pressed = false
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

	# 16. An agent's settings (ⓘ): capabilities to tick, model, instructions.
	await b.call("show_agent_info", "sparring")
	await pause(1.0)
	await shot("16-agent-settings")
	b.call("close_agent_settings")

	SbSettings.set_value("ui", "theme", "auto")
	await app.backend.shutdown_engine(3.0)
	app.audio.stop_all()
	await process_frame
	quit()
