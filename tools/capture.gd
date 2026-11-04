extends SceneTree
## Walks the real flow and saves screenshots (needs a display, see tools/capture.sh).
## Uses SBGD_HOME (fresh folder ⇒ a full install is captured), then fills a demo
## brain through the real API and captures each theme.

var out_dir := ""
var app: SbApp
var _filled := false

const DEMO_SPACES := [["Client Atlas", "ffd2a1"], ["Second Brain GD", "a6dcff"], ["Health & energy", "c8b6ff"]]
const DEMO_NOTES := [
	[0, "Atlas kickoff notes", "idea", "Goals for Q1, stakeholders, first risks. See [[Atlas risks]] #client #meeting"],
	[0, "Atlas risks", "note", "Data migration, tight timeline, two vendors. Follow up in [[Weekly review]] #client"],
	[0, "Proposal draft v2", "task", "Pricing section and timeline. Based on [[Atlas kickoff notes]] #client"],
	[1, "Voice capture with Whisper", "idea", "Local faster-whisper in the engine, mic in Godot. Links [[Engine room]] #roadmap"],
	[1, "Daily router agent", "idea", "Every morning: read the inbox, route each thought to its project. [[Weekly review]] #roadmap #agents"],
	[1, "Graph physics tuning", "note", "Springs, repulsion, birth bloom. #roadmap"],
	[2, "Morning routine", "journal", "Walk, coffee, 20 minutes of reading before screens. #habits"],
	[2, "Sleep notes", "note", "Less screen after 22h. Related to [[Morning routine]] #habits"],
	[-1, "Weekly review", "task", "Sunday: inbox to zero, look at every project, plan the week. #habits #review"],
	[-1, "Book: Building a Second Brain", "reference", "CODE: capture, organize, distill, express. [[Welcome to your Second Brain]] #reading"],
	[-1, "Idea: soundscapes per project", "idea", "Each space could have its own ambience. #roadmap"],
]


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


func api(path: String, payload: Dictionary) -> Dictionary:
	return await app.backend.api.call_api(path, true, HTTPClient.METHOD_POST, JSON.stringify(payload))


func _day(offset: int) -> String:
	return Time.get_date_string_from_unix_time(int(Time.get_unix_time_from_system()) + offset * 86400)


## A realistic demo brain through the real API: projects under areas, tasks
## with near due dates, notes, groceries.
func fill_demo() -> void:
	var st := await app.backend.api.call_api("/brain/structure")
	var area: Dictionary = {}
	for a in (st["data"] as Dictionary).get("areas", []):
		area[str((a as Dictionary)["name"])] = str((a as Dictionary)["id"])
	var proj: Dictionary = {}
	for spec in [["Client Atlas", "Vision au travail", "Signer le mandat Q1", 10, "ffd2a1"],
			["Second Brain GD", "Vision au travail", "Assistant quotidien utile", 45, "a6dcff"],
			["Fête de Léa", "Famille", "Une fête simple et joyeuse", 20, "ffa9c6"]]:
		var res := await api("/brain/projects", {"name": spec[0], "area_id": area.get(spec[1], ""), "goal": spec[2],
			"due_date": _day(int(spec[3])), "color": "#" + str(spec[4])})
		proj[spec[0]] = str((res["data"] as Dictionary).get("id", ""))
	for n in DEMO_NOTES:
		var payload := {"title": n[1], "kind": n[2], "body": n[3]}
		var target: String = str(["Client Atlas", "Second Brain GD", "Santé"][int(n[0])]) if int(n[0]) >= 0 else ""
		if target != "":
			payload["space_id"] = proj.get(target, area.get(target, ""))
		await api("/brain/notes", payload)
	for task in [["Envoyer la proposition Atlas", "Client Atlas", -1], ["Appeler le fournisseur de données", "Client Atlas", 0],
			["Réserver la salle", "Fête de Léa", 3], ["Inviter la famille", "Fête de Léa", 6],
			["Prendre rendez-vous chez le dentiste", "Santé", 2]]:
		await api("/brain/tasks", {"title": task[0], "space_id": proj.get(task[1], area.get(task[1], "")), "due_date": _day(int(task[2]))})
	var lists := await app.backend.api.call_api("/brain/checklists")
	for cl in (lists["data"] as Dictionary).get("checklists", []):
		if str((cl as Dictionary)["name"]) == "Épicerie":
			await api("/brain/checklists/%s/items" % (cl as Dictionary)["id"], {"items": ["Lait", "Œufs", "Café", "Bananes", "Pain de seigle"]})


func _run() -> void:
	root.size = Vector2i(1280, 800)
	OS.set_environment("SBGD_SETTINGS", OS.get_environment("SBGD_HOME").path_join("capture-settings.cfg"))
	SbSettings.set_value("ui", "theme", "morning")
	SbSettings.set_value("onboarding", "voice_done", false)
	OS.set_environment("SBGD_VOICE_PROVIDER", "fake")  # screenshots never call OpenAI
	OS.set_environment("SBGD_BILLING_PROVIDER", "fake")
	OS.set_environment("SBGD_SEED", "demo")  # canned billing pages in OpenAI's shapes
	app = load("res://scenes/main.tscn").instantiate()
	root.add_child(app)
	await pause(1.2)
	await shot("01-welcome")
	(app.current().get("primary") as Button).pressed.emit()
	var setup: Control = app.current()
	var got_mid := false
	var deadline := Time.get_ticks_msec() + 600000
	while app.current_screen == "setup" and Time.get_ticks_msec() < deadline:
		var rows: Dictionary = setup.get("rows")
		var dep: StepRow = rows["dependencies"]
		if not got_mid and dep.status == "progress" and (setup.get("progress") as ProgressBar).value > 0.35:
			await shot("02-setup-installing")
			got_mid = true
		if (setup.get("continue_button") as Button).visible and not _filled:
			_filled = true
			await shot("03-setup-ready")
			app.backend.load_runtime()
			await fill_demo()
			break
		await process_frame
	while app.current_screen not in ["onboarding", "brain"] and Time.get_ticks_msec() < deadline:
		await pause(0.2)
	if app.current_screen == "onboarding":
		await pause(1.5)
		await shot("03b-voice-onboarding")
		(app.current().get("panel") as VoiceKeyPanel).skipped.emit()
	while app.current_screen != "brain" and Time.get_ticks_msec() < deadline:
		await pause(0.2)
	var b0: Control = app.current()
	var ap: AssistantPanel = b0.get("assistant_panel")
	var waited := Time.get_ticks_msec() + 60000
	while (ap.busy or ap.messages_shown == 0) and Time.get_ticks_msec() < waited:
		await pause(0.3)
	await pause(5.0)
	await shot("04-brain-briefing")
	ap.send("C'est quoi les risques sur Atlas, et qu'est-ce qui est dû cette semaine?")
	await pause(0.5)
	while ap.busy and Time.get_ticks_msec() < waited + 60000:
		await pause(0.3)
	await pause(1.0)
	await shot("04b-assistant-answer")
	var ce: LineEdit = b0.get("capture_edit")
	ce.text = "faut que je rappelle le monsieur d'Atlas pour le problème de migration"
	ce.text_submitted.emit(ce.text)
	while int(b0.get("classified")) == 0 and Time.get_ticks_msec() < waited + 90000:
		await pause(0.3)
	await pause(2.5)
	await shot("04c-auto-filed")
	await b0.call("set_view", "today")
	await pause(1.5)
	await shot("04d-today")
	await b0.call("set_view", "projects")
	await pause(1.2)
	await shot("04e-projects")
	var pv: ProjectsView = b0.get("projects_view")
	for a in pv.structure_data.get("areas", []):
		for pj in (a as Dictionary).get("projects", []):
			if str((pj as Dictionary)["name"]) == "Client Atlas":
				await pv.show_card(str((pj as Dictionary)["id"]))
	await pause(1.0)
	await shot("04f-project-card")
	await b0.call("set_view", "captures")
	await pause(1.5)
	await shot("04g-captures")
	var cvz: CapturesView = b0.get("captures_view")
	var pdz := cvz.open_packs()
	await pause(1.5)
	pdz.scope.select(1)
	pdz._fill_values()
	for i in pdz.value.item_count:
		if pdz.value.get_item_text(i) == "Client Atlas":
			pdz.value.select(i)
	pdz.title_edit.text = ""
	pdz.refresh_preview()
	await pause(1.5)
	await pdz.do_export()
	await pause(0.8)
	await shot("04h-packs")
	pdz.queue_free()
	await pause(0.3)
	await b0.call("set_view", "graph")
	app.show_brain()
	await pause(7.0)
	(app.current().get("tab_spaces") as Button).pressed.emit()
	(app.current().get("tab_spaces") as Button).button_pressed = true
	await pause(0.5)
	await shot("05-brain-morning")
	var brain: Control = app.current()
	var graph: GraphView = brain.get("graph")
	var target := ""
	for id in graph.nodes:
		if str((graph.nodes[id] as Dictionary)["label"]) == "Daily router agent":
			target = str(id)
	# Related ideas need the background meaning index (real embeddings when run through dotenvx).
	var mdeadline := Time.get_ticks_msec() + 40000
	while Time.get_ticks_msec() < mdeadline:
		var ms: Dictionary = await app.backend.api.call_api("/brain/meaning/status")
		if ms["ok"] and int((ms["data"] as Dictionary).get("pending", 1)) == 0 and int((ms["data"] as Dictionary).get("embedded", 0)) > 0:
			break
		await pause(1.0)
	await brain.call("refresh_graph")
	await pause(3.0)
	brain.call("open_note", target, true)
	await pause(2.5)
	await shot("06-brain-note-open")
	brain.call("_close_inspector")
	var capture_edit: LineEdit = brain.get("capture_edit")
	capture_edit.text = "Try a soft blue for the evening palette #design"
	capture_edit.text_submitted.emit(capture_edit.text)
	await pause(0.45)
	await shot("07-brain-note-born")
	# Listening state: real session (fake provider), synthetic audio through the real encoder.
	brain = app.current()
	await brain.call("start_voice", false)
	var vc: VoiceCapture = brain.get("voice_capture")
	for k in 12:
		var frames := PackedVector2Array()
		for i in 4800:
			var s := sin(TAU * 180.0 * float(i) / 48000.0) * (0.25 + 0.2 * sin(float(k)))
			frames.append(Vector2(s, s))
		vc.feed_frames(frames, 48000.0)
		await pause(0.1)
	(brain.get("capture_edit") as LineEdit).text = "Remind me to send the Atlas proposal on Friday…"
	await shot("07b-voice-listening")
	await brain.call("stop_voice")
	await pause(1.0)
	# Hands-free: holding F8 shows the listening indicator (fake voice provider, no mic).
	brain.call("push_to_talk", true, false)
	await pause(1.5)
	await shot("07c-push-to-talk")
	await brain.call("push_to_talk", false, false)
	await pause(4.0)
	# Live conversation (Loop 7b), fake Realtime upstream: one spoken turn, then the pill mid-answer.
	SbSettings.set_value("voice", "headphones", true)
	var lc: LiveConversation = app.live
	await lc.start(false)
	var sec := PackedVector2Array()
	for i in 48000:
		var v := sin(TAU * 200.0 * float(i) / 48000.0) * 0.3
		sec.append(Vector2(v, v))
	for c in range(0, sec.size(), 4800):
		lc.capture.feed_frames(sec.slice(c, c + 4800), 48000.0)
		await process_frame
	await pause(2.5)
	lc._set_state("listening")
	await shot("07d-live-conversation")
	lc.stop("user")
	SbSettings.set_value("voice", "headphones", false)
	await pause(1.0)
	for theme in ["focus", "evening", "forest"]:
		app.set_theme_choice(theme)
		await pause(6.0)
		await shot("08-brain-" + theme)
	app.set_theme_choice("morning")
	await pause(1.0)
	# Semantic zoom (Loop 10): far clusters, cards, then the full text inside an item.
	var bz: Control = app.current()
	await bz.call("set_view", "graph")
	var gz: GraphView = bz.get("graph")
	gz.zoom_to(0.32, Vector2.ZERO, 0.3)
	await pause(1.2)
	await shot("11-graph-overview")
	var kick := gz.find_node("Atlas kickoff notes")
	gz.zoom_level("closer", kick)
	gz.zoom_to(3.0, gz.nodes[kick]["pos"] if kick != "" else Vector2.ZERO, 0.4)
	await pause(2.5)
	await shot("12-graph-cards")
	gz.zoom_level("read", kick)
	await pause(2.5)
	await shot("13-graph-read")
	# An organised graph (Loop 13): zones per place, a folded place, a filter.
	gz.zoom_to(0.62, Vector2(-120, 0), 0.3)
	await pause(4.0)
	await shot("17-graph-zones")
	await bz.call("fold_place", "Fête de Léa", true)
	await bz.call("fold_place", "Santé", true)
	(bz.get("filters_bar") as GraphFilters).apply({"text": "atlas"})
	await pause(2.5)
	await shot("18-graph-filtered")
	(bz.get("filters_bar") as GraphFilters).apply({})
	await bz.call("fold_place", "Fête de Léa", false)
	await bz.call("fold_place", "Santé", false)
	await pause(0.5)
	# Search and connect (Loop 14): hits with reasons, then the path between two items.
	await bz.call("show_search", "atlas")
	await pause(2.0)
	await shot("19-graph-search")
	bz.get("search_edit").text = ""
	await bz.call("_on_search_changed", "")
	var pres: Dictionary = await app.backend.api.call_api("/brain/path?from=" + "Morning routine".uri_encode() + "&to=" + "Atlas risks".uri_encode())
	if pres["ok"] and bool((pres["data"] as Dictionary).get("found", false)):
		gz.set_path((pres["data"] as Dictionary)["ids"], (pres["data"] as Dictionary)["steps"])
		await pause(2.5)
		await shot("20-graph-path")
		gz.clear_path()
	await pause(0.5)
	# Timeline (Loop 15): items on a time axis, one lane per place.
	(bz.get("filters_bar") as GraphFilters).timeline_button.button_pressed = true
	await pause(3.0)
	await shot("21-graph-timeline")
	(bz.get("filters_bar") as GraphFilters).timeline_button.button_pressed = false
	await pause(1.5)
	# Originals and the document viewer (Loop 12): a PDF in its card, then full screen.
	await bz.call("add_source_file", ProjectSettings.globalize_path("res://tests/fixtures/docs/sample.pdf"))
	await pause(2.0)
	var doc_node := gz.find_node("sample")
	gz.zoom_level("read", doc_node)
	await pause(3.0)
	await shot("14-graph-document")
	await bz.call("open_document_for", doc_node)
	await pause(2.0)
	await shot("15-document-viewer")
	var dvz: DocumentViewer = bz.get("viewer")
	dvz.set_zoom(2.6, dvz.size * Vector2(0.45, 0.3))
	await pause(2.5)
	await shot("16-document-zoomed")
	dvz.hide_viewer()
	gz.zoom_to(1.0, Vector2.ZERO, 0.2)
	await pause(0.5)
	app.show_console()
	await pause(6.5)
	await shot("09-engine-room")
	var console: Control = app.current()
	var bp: BillingPanel = console.get("billing_panel")
	var sc := bp.get_parent().get_parent() as ScrollContainer
	if sc != null:
		sc.ensure_control_visible(bp)
		await pause(0.6)
		sc.scroll_vertical = int(bp.position.y) - 8
	await pause(0.8)
	await shot("09b-real-costs")
	(app.get("_widget") as AudioWidget).call("_open")
	await pause(0.6)
	await shot("10-ambiance-panel")
	SbSettings.set_value("ui", "theme", "auto")
	await app.backend.shutdown_engine(3.0)
	app.audio.stop_all()
	await process_frame
	quit()
