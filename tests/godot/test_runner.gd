extends SceneTree
## Headless Godot tests: unit checks, then the real end-to-end flow through
## the UI (Welcome → Setup → System Console), a second launch, and shutdown.
##
##   SBGD_HOME=<temp dir> godot --headless --path . --script res://tests/godot/test_runner.gd
##
## SBGD_HOME must point to a throwaway folder: this test installs into it.

const E2E_TIMEOUT_S := 600.0

var passed := 0
var failed := 0


func _initialize() -> void:
	_run.call_deferred()


func check(cond: bool, label: String) -> void:
	if cond:
		passed += 1
		print("  ok   ", label)
	else:
		failed += 1
		printerr("  FAIL ", label)


func wait_until(cond: Callable, timeout_s: float) -> bool:
	var deadline := Time.get_ticks_msec() + int(timeout_s * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if cond.call():
			return true
		await create_timer(0.2).timeout
	return bool(cond.call())


func _run() -> void:
	# Private settings file: never touch the user's real preferences (theme, onboarding, volumes).
	OS.set_environment("SBGD_SETTINGS", OS.get_environment("SBGD_HOME").path_join("test-settings.cfg"))
	# The engine started by this test uses a fake transcription provider: no OpenAI call, no cost.
	OS.set_environment("SBGD_VOICE_PROVIDER", "fake")
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "fake")
	OS.set_environment("SBGD_KEYRING_SERVICE", "SecondBrainGD-test")  # never the user's real key
	OS.set_environment("SBGD_BILLING_PROVIDER", "fake")
	OS.set_environment("SBGD_SEED", "demo")  # the demo areas and notes the flow below relies on
	OS.set_environment("SBGD_TEST_NO_SHELL", "1")  # « ouvre l'original » records the path instead of launching an app  # real-costs panel reads canned OpenAI pages
	OS.unset_environment("OPENAI_ADMIN_KEY")
	# The agent room installs from a tiny local fixture (a fake app-server), never the 160 MB download.
	OS.set_environment("SBGD_AGENTS_MANIFEST", ProjectSettings.globalize_path("res://tests/fixtures/agents/manifest.json"))
	OS.set_environment("SBGD_AGENTS", "install")  # on demand since Loop 28: the test installs the fixture at setup
	SbSettings.set_value("assistant", "speaks", true)
	SbSettings.set_value("onboarding", "voice_done", false)
	if OS.get_environment("SBGD_HOME") == "":
		printerr("Set SBGD_HOME to a temporary folder before running these tests.")
		quit(2)
		return
	print("Unit checks")
	_unit()
	await _perf_check()
	await _drop_check()
	var apic: Node = load("res://scripts/monitoring/api_client.gd").new()
	check(apic.timeout_for("/sources/file", HTTPClient.METHOD_POST) >= 300.0, "reading a document may take minutes (OCR of many pages)")
	check(apic.timeout_for("/sources", HTTPClient.METHOD_GET) <= 5.0, "a plain request still fails fast")
	check(apic.timeout_for("/sources/abc/reread?job=1-2", HTTPClient.METHOD_POST) >= 300.0, "re-reading with AI may take minutes (its job id in the query)")
	check(AssistantPanel._linkify("renews on **December 1**.").contains("[b]December 1[/b]") and AssistantPanel.spoken("**$1,284**") == "$1,284",
		"a reply's **bold** shows as bold and is read without the stars")
	check(AssistantPanel.one_line("Improving\nEnergy  Performance\n in Canada") == "Improving Energy Performance in Canada",
		"a source title with line breaks shows on one line")
	var webp_img := Image.create(32, 24, false, Image.FORMAT_RGBA8)
	webp_img.fill(Color(0.2, 0.5, 0.8))
	var webp_tex := DocumentViewer.texture_from(webp_img.save_webp_to_buffer(), "text/html")
	check(webp_tex != null and webp_tex.get_width() == 32, "a page's WebP main image shows on its card (recognised by its bytes)")
	apic.free()
	var brain_script: GDScript = load("res://scenes/brain/brain.gd")
	check(brain_script.progress_text({"stage": "ocr", "done": 3, "total": 9}) == "page 3 / 9 read (local OCR)"
		and brain_script.progress_text({"stage": "summary"}) == "writing the summary"
		and brain_script.progress_text({"stage": "reading"}) == "", "reading progress reads « page 3 / 9 read (local OCR) »")
	print("End-to-end through the UI (data folder: %s)" % SbPaths.data_dir())
	await _e2e()
	print("\n%d passed, %d failed" % [passed, failed])
	quit(1 if failed > 0 else 0)


func _unit() -> void:
	check(SbPaths.data_dir() == OS.get_environment("SBGD_HOME"), "SBGD_HOME overrides the data folder")
	check(FileAccess.file_exists(SbPaths.bootstrap_script()), "bootstrap script found from res://")
	var runner := BootstrapRunner.new()
	var a := runner.feed_for_test('{"a":1}\n{"b"'.to_utf8_buffer())
	check(a.size() == 1 and a[0] == '{"a":1}', "runner returns complete lines only")
	var b := runner.feed_for_test(':2}\n\n'.to_utf8_buffer())
	check(b.size() == 1 and b[0] == '{"b":2}', "runner joins a line split across reads")
	runner.free()
	check(PythonLocator._parse_detect("noise\n{\"compatible\": true}\n").get("compatible") == true,
		"detect output is parsed from the last JSON line")
	check(PythonLocator.candidates().size() >= 3, "several Python candidates are tried")
	check(PythonLocator.which("definitely-not-a-real-command-sbgd") == "", "missing commands are skipped")
	check(PythonLocator.which(OS.get_executable_path()) != "", "absolute paths are accepted when they exist")
	check(SbFormat.bytes(null) == SbFormat.NA, "missing measurement shows Not available")
	check(SbFormat.local_time("2026-11-03T00:55:55.859Z") != SbFormat.NA, "ISO timestamps are formatted")
	check(SbFormat.number(42.0) == "42", "whole JSON numbers display without decimals")
	check(SbFormat.plain("**Recipe:** [Roast chicken](https://x.org/a), 4 servings [source](https://x.org/a).\n- [ ] carrots\nFor [[Dinner 1]]")
		== "Recipe: Roast chicken, 4 servings.\n☐ carrots\nFor Dinner 1", "an item's card in the graph shows Markdown as plain text")
	for name in SbTheme.THEMES:
		SbTheme.apply(name)
		check(SbTheme.current == name and SbTheme.build() != null, "theme %s applies" % name)
		check(SbAudio.tracks_for(name).size() >= 2, "theme %s has a music playlist" % name)
	check(SbTheme.resolve("auto") in SbTheme.THEMES, "auto theme resolves by time of day")
	# Voice encoder: 48 kHz stereo -> 24 kHz mono PCM16, continuous across calls
	var frames := PackedVector2Array()
	for i in 4800:
		var s := sin(TAU * 440.0 * float(i) / 48000.0) * 0.5
		frames.append(Vector2(s, s))
	var st := {}
	var pcm := VoiceCapture.encode(frames.slice(0, 2400), 48000.0, st)
	pcm.append_array(VoiceCapture.encode(frames.slice(2400), 48000.0, st))
	check(abs(pcm.size() / 2 - 2400) <= 2, "0.1 s at 48 kHz becomes 2400 samples at 24 kHz (%d)" % (pcm.size() / 2))
	var peak := 0
	for k in range(0, pcm.size(), 2):
		peak = maxi(peak, absi(pcm.decode_s16(k)))
	check(peak > 15000 and peak < 17000, "amplitude is preserved (peak %d ≈ 16384)" % peak)
	var st2 := {}
	check(VoiceCapture.encode(frames.slice(0, 441), 44100.0, st2).size() / 2 in [239, 240, 241], "44.1 kHz input resamples too")
	SbTheme.apply("morning")
	for sfx in ["click", "hover", "note_create", "setup_complete", "error"]:
		check(ResourceLoader.exists("res://assets/audio/sfx/%s.mp3" % sfx), "sound effect %s exists" % sfx)


func _e2e() -> void:
	var app: SbApp = load("res://scenes/main.tscn").instantiate()
	root.add_child(app)
	await process_frame
	await process_frame
	check(app.current_screen == "welcome", "app opens on the Welcome screen")
	var welcome: Control = app.current()
	var primary: Button = welcome.get("primary")
	var was_installed := app.backend.is_installed()
	check(primary.text == ("Start" if was_installed else "Setup"), "primary button matches install state")

	# Press the real button.
	primary.pressed.emit()
	await process_frame
	check(app.current_screen == "setup", "Setup button opens the Setup screen")
	var setup: Control = app.current()
	var max_progress := 0.0
	var saw_running_dependency := false
	var agents_row_status := ""
	var deadline := Time.get_ticks_msec() + int(E2E_TIMEOUT_S * 1000.0)
	while app.current_screen in ["setup", "onboarding"] and Time.get_ticks_msec() < deadline:
		if app.current_screen == "onboarding":
			var ob: Control = app.current()
			check(ob.get("panel") != null, "first setup shows the voice onboarding step")
			await create_timer(0.5).timeout
			(ob.get("panel") as VoiceKeyPanel).skipped.emit()
			await process_frame
			continue
		if is_instance_valid(setup):
			var bar: ProgressBar = setup.get("progress")
			max_progress = maxf(max_progress, bar.value)
			var rows: Dictionary = setup.get("rows")
			var dep: StepRow = rows["dependencies"]
			if dep.status in ["started", "progress"]:
				saw_running_dependency = true
			agents_row_status = (rows["agents"] as StepRow).status
			var err_panel: PanelContainer = setup.get("error_panel")
			if err_panel.visible:
				var lbl: Label = setup.get("error_label")
				printerr("  setup error: ", lbl.text)
				break
		await create_timer(0.1).timeout
	check(app.current_screen == "brain", "setup completes and opens the Second Brain")
	if app.current_screen != "brain":
		return
	check(max_progress > 0.5, "progress bar moved (max %.2f)" % max_progress)
	check(agents_row_status in ["ok", "skipped"], "setup installs the agent room, fingerprint verified (%s)" % agents_row_status)
	if not was_installed:
		check(saw_running_dependency, "dependency step was shown running")

	var brain: Control = app.current()
	var graph: GraphView = brain.get("graph")
	var seeded := await wait_until(func() -> bool: return graph.node_count("note") >= 4, 20.0)
	check(seeded, "first visit shows the starter graph (%d notes)" % graph.node_count("note"))
	check(bool(brain.get("health_ok")), "brain header reports the engine healthy")
	# Assistant: briefing on open, a question with a cited note, auto-filing of a capture with undo.
	var ap: AssistantPanel = brain.get("assistant_panel")
	var briefed := await wait_until(func() -> bool: return ap.configured and ap.messages_shown >= 1 and not ap.busy, 20.0)
	check(briefed, "the assistant opens with today's briefing")
	ap.send("cherche constellations")
	var answered := await wait_until(func() -> bool: return ap.last_reply.contains("[["), 20.0)
	check(answered, "the assistant answers from the notes and cites them (%s)" % ap.last_reply.left(60))
	var gs_before := graph.node_count("note")
	var ce: LineEdit = brain.get("capture_edit")
	ce.text = "Getting started checklist for new users"
	ce.text_submitted.emit(ce.text)
	var filed := await wait_until(func() -> bool: return int(brain.get("classified")) == 1, 20.0)
	check(filed, "a capture is filed automatically by the assistant")
	var toast_label: Label = brain.get("toast_label")
	check(toast_label.text.contains("Ressources › Getting started"), "the archivist's receipt says where it went (%s)" % toast_label.text)
	check(ap.list.get_child_count() > 0 and str(brain.get("last_receipt")).contains("classé dans"), "the receipt also lands in the assistant panel")
	# Loop 9: on a place that does not exist yet, the archivist creates it (fresh Brains build their own structure).
	ce.text = "Photographie de nuit: pose longue et trépied"
	ce.text_submitted.emit(ce.text)
	var made := await wait_until(func() -> bool: return int(brain.get("classified")) == 2, 20.0)
	check(made and str(brain.get("last_receipt")).contains("Ressources › Photographie"), "an unknown subject gets a new place (%s)" % str(brain.get("last_receipt")))
	await brain.call("set_view", "captures")
	var cv: CapturesView = brain.get("captures_view")
	var fed := await wait_until(func() -> bool: return cv.items.size() >= 2 and cv.list.get_child_count() >= 2, 10.0)
	check(fed and str((cv.items[0] as Dictionary).get("title", "")).begins_with("Photographie"), "the Captures view lists what came in, newest first")
	brain.set("test_clipboard", "Le jeûne intermittent: fenêtre de 8 heures pour manger")
	var before_clip := int(brain.get("classified"))
	await brain.call("run_ui_actions", [{"action": "capture_clipboard"}])
	var clipped := await wait_until(func() -> bool: return int(brain.get("classified")) == before_clip + 1, 20.0)
	check(clipped, "« ajoute ça au Brain » / Ctrl+Shift+V files the clipboard (%s)" % str(brain.get("last_receipt")))
	await cv.show_bookmarklet()
	check(cv.bookmarklet.begins_with("javascript:") and cv.bookmarklet.contains("/capture?key="), "the browser bookmark is offered to copy")
	for d in cv.find_children("*", "AcceptDialog", true, false):
		d.queue_free()
	await ap.send("Je veux structurer le projet Lancement")
	check(str(brain.get("capture_hint").text).contains("Lancement"), "« je veux structurer le projet X » sets the working context")
	await ap.send("Je veux structurer")  # clears it again for the rest of the flow
	await brain.call("set_view", "graph")
	await brain.call("_undo_toast")
	check(toast_label.text.begins_with("Put back"), "the filing can be undone from the toast")
	check(graph.node_count("note") == gs_before + 3, "undo keeps the note, only its place changes")
	var spaces_res: Dictionary = await app.backend.api.call_api("/brain/spaces")
	var still_there := false
	for sp in (spaces_res["data"] as Dictionary).get("spaces", []):
		still_there = still_there or str((sp as Dictionary).get("name", "")) == "Jeûne"
	check(not still_there, "undoing removes the place the archivist had just created")
	# Brain packs (Loop 11): export by voice, import by drop (all duplicates here), layer removed by voice.
	await ap.send("Exporte Getting started", true)
	var pack_path := str(brain.get("last_pack_export"))
	check(pack_path.ends_with(".brain") and FileAccess.file_exists(pack_path), "« exporte Getting started » writes a .brain pack (%s)" % pack_path.get_file())
	var imported: bool = await brain.call("import_pack", pack_path)
	var pd: PacksDialog = cv.packs_dialog
	check(imported and pd != null and pd.result_label.text.contains("already in your Brain"), "dropping a .brain file imports it as a layer, skipping what is already there (%s)" % (pd.result_label.text if pd else ""))
	var layers_res: Dictionary = await app.backend.api.call_api("/packs/layers")
	check(((layers_res["data"] as Dictionary).get("layers", []) as Array).size() == 1, "the imported pack is listed as a layer")
	await ap.send("Retire le pack Getting started", true)
	layers_res = await app.backend.api.call_api("/packs/layers")
	check(((layers_res["data"] as Dictionary).get("layers", []) as Array).is_empty(), "« retire le pack » removes the layer")
	if pd != null:
		pd.queue_free()
	# Structure: Today view, checklists, Projects view, project card, next actions.
	await brain.call("set_view", "today")
	var tv: TodayView = brain.get("today_view")
	check(tv.visible and tv.data.has("checklists"), "Today view opens with real data")
	var lists: Array = tv.data.get("checklists", [])
	var groceries: Dictionary = {}
	for l in lists:
		if str((l as Dictionary)["name"]) == "Épicerie":
			groceries = l
	check(not groceries.is_empty(), "the Épicerie list exists from the start")
	await tv.add_items(str(groceries["id"]), "lait, pain")
	var items_now: Array = []
	for l in tv.data.get("checklists", []):
		if str((l as Dictionary)["name"]) == "Épicerie":
			items_now = (l as Dictionary)["items"]
	check(items_now.size() == 2, "items added to the grocery list from the Today view")
	await brain.call("set_view", "projects")
	var pv: ProjectsView = brain.get("projects_view")
	var areas: Array = pv.structure_data.get("areas", [])
	check(areas.size() == 4, "four starter areas (%d)" % areas.size())
	var famille := ""
	for a in areas:
		if str((a as Dictionary)["name"]) == "Famille":
			famille = str((a as Dictionary)["id"])
	var pid: String = await pv.create_project(famille, "Fête de Léa")
	check(pid != "" and pv.showing_card == pid, "a project is created in an area and its card opens")
	check(await pv.add_task(pid, "Réserver la salle @2030-01-15"), "a next action with a date is added from the card")
	var tasks: Array = pv.card_data.get("tasks", [])
	check(tasks.size() == 1 and str((tasks[0] as Dictionary)["due_date"]) == "2030-01-15", "the date was parsed from @YYYY-MM-DD")
	var instr_field: TextEdit = pv.get("_fields")["instructions"]
	instr_field.text = "Ton festif, budget serré."
	check(await pv.save_card(), "project card saves its assistant instructions")
	await pv.show_card(pid)
	check(str(pv.card_data.get("instructions", "")) == "Ton festif, budget serré.", "instructions are stored on the project")
	await brain.call("set_view", "today")
	var nexts: Array = tv.data.get("next_actions", [])
	var found_next := ""
	for n in nexts:
		if str((n as Dictionary)["title"]) == "Réserver la salle":
			found_next = str((n as Dictionary)["id"])
	check(found_next != "", "the project's next action shows in Today")
	await tv.set_done(found_next, true)
	await create_timer(1.0).timeout
	var still := false
	for n in tv.data.get("next_actions", []):
		if str((n as Dictionary)["id"]) == found_next:
			still = true
	check(not still, "ticking it in Today marks it done")
	var reviewed: bool = await ap.run_review()
	check(reviewed and ap.last_reply.begins_with("Revue"), "the weekly review runs from the assistant")
	await brain.call("set_view", "graph")
	# Sources: a file becomes a reference note in the graph; local links are refused.
	var doc := OS.get_environment("SBGD_HOME").path_join("atlas-plan.md")
	var fh := FileAccess.open(doc, FileAccess.WRITE)
	fh.store_string("Plan Atlas\n\nLa migration se fait en deux phases.\n\nPhase 1: inventaire. Phase 2: bascule un dimanche.")
	fh.close()
	var nodes_before_src := graph.node_count("note")
	var added: bool = await brain.call("add_source_file", doc)
	check(added and graph.node_count("note") == nodes_before_src + 1, "a dropped file becomes a note in the graph")
	var dup: bool = await brain.call("add_source_file", doc)
	check(dup and int(brain.get("sources_added")) == 1, "the same file is not added twice")
	var refused: bool = await brain.call("add_source_url", "http://127.0.0.1:1/private")
	check(not refused and str(brain.get("last_source_error")).contains("local"), "links to local networks are refused")
	var before := graph.node_count("note")
	var capture_edit: LineEdit = brain.get("capture_edit")
	capture_edit.text = "Test thought linking [[Engine room]] #e2e"
	capture_edit.text_submitted.emit(capture_edit.text)
	var grew := await wait_until(func() -> bool: return graph.node_count("note") == before + 1, 15.0)
	check(grew, "a captured thought becomes a new node in the graph")
	check(graph.nodes.has("tag:e2e"), "its #tag appears in the graph")
	var linked := false
	for e in graph.edges:
		if str(e["type"]) == "link" and str((graph.nodes[e["from"]] as Dictionary)["label"]).begins_with("Test thought"):
			linked = true
	check(linked, "its [[link]] appears as an edge")
	# Meaning memory: the engine's background worker embeds new notes (fake provider) within seconds.
	var meaning: Dictionary = {}
	for i in 40:
		var mres: Dictionary = await app.backend.api.call_api("/brain/meaning/status")
		meaning = mres["data"] if mres["ok"] else {}
		if int(meaning.get("embedded", 0)) > 0 and int(meaning.get("pending", 1)) == 0:
			break
		await create_timer(0.25).timeout
	check(int(meaning.get("embedded", 0)) > 0 and int(meaning.get("pending", 1)) == 0,
		"notes are indexed by meaning in the background (%s)" % str(meaning))
	var rel_id := str(brain.get("current_note").get("id", "")) if not (brain.get("current_note") as Dictionary).is_empty() else ""
	for id in graph.nodes:
		if rel_id == "" and str((graph.nodes[id] as Dictionary)["type"]) == "note":
			rel_id = str(id)
	var rres: Dictionary = await app.backend.api.call_api("/brain/notes/" + rel_id.uri_encode() + "/related")
	check(rres["ok"] and (rres["data"] as Dictionary).has("related"), "a note's related ideas are served")
	var small := brain.size
	brain.size = Vector2(1600, 1000)  # headless windows are tiny: room for the panels
	await process_frame
	await brain.call("open_note", rel_id, false)
	await create_timer(0.6).timeout
	var tile: SbFloatingPanel = brain.get("inspector")
	var arch_panel: SbFloatingPanel = brain.get("archivist_panel")
	check(tile.visible and tile.position.x > arch_panel.position.x + arch_panel.size.x,
		"the item tile opens on the right, not over the Archivist (x %.0f)" % tile.position.x)
	brain.call("_close_inspector")
	brain.size = small
	# Agent room: a folder, a session against the fake app-server, an approval, the change applied.
	brain.call("set_view", "agents")
	var av: AgentsView = brain.get("agents_view")
	await av.refresh()
	check(bool(av.info.get("installed", false)), "the agent room is installed and ready")
	var work := ProjectSettings.globalize_path("user://agent-e2e-%d" % Time.get_ticks_msec())
	DirAccess.make_dir_recursive_absolute(work)
	var data_refused: bool = await av.add_folder(OS.get_environment("SBGD_HOME"))
	check(not data_refused, "the app's own data folder cannot be given to agents")
	check(await av.add_folder(work), "a project folder is added to the agent room")
	check(await av.start_session(work), "an agent session starts in that folder")
	var ready_agent := await wait_until(func() -> bool: return av.session_status == "idle", 10.0)
	check(ready_agent, "the agent is ready (%s)" % av.session_status)
	await av.send_message("please write a notes file")
	var asked := await wait_until(func() -> bool: return not av.pending.is_empty(), 10.0)
	check(asked and not FileAccess.file_exists(work.path_join("notes.md")), "a file change waits for approval, nothing written yet")
	check(av.approvals_box.get_child_count() == 1, "an approval card is shown")
	await av.decide(int((av.pending[0] as Dictionary)["request_id"]), "accept")
	var applied := await wait_until(func() -> bool: return av.session_status == "idle" and FileAccess.file_exists(work.path_join("notes.md")), 10.0)
	check(applied, "after approval the change is applied and the turn completes")
	check(av.transcript.get_parsed_text().contains("Fait."), "the agent's reply streams into the transcript")
	brain.call("set_view", "graph")
	# Voice: a real session through the engine (fake provider), audio pushed through the real encoder.
	var voice_before := graph.node_count("note")
	var started: bool = await brain.call("start_voice", false)
	check(started, "voice session opens through the local WebSocket")
	var vc: VoiceCapture = brain.get("voice_capture")
	var tone := PackedVector2Array()
	for i in 48000 * 3 / 2:
		var s := sin(TAU * 220.0 * float(i) / 48000.0) * 0.3
		tone.append(Vector2(s, s))
	for c in range(0, tone.size(), 4800):
		vc.feed_frames(tone.slice(c, c + 4800), 48000.0)
		await process_frame
	await brain.call("stop_voice")
	var voiced := await wait_until(func() -> bool: return graph.node_count("note") == voice_before + 1, 15.0)
	check(voiced, "a spoken thought becomes a note")
	var heard := false
	for id in graph.nodes:
		var n: Dictionary = graph.nodes[id]
		if str(n.get("source", "")) == "voice" or str(n["label"]).begins_with("[fake transcript of 1.5"):
			heard = true
	check(heard, "the transcript of 1.5 s of audio arrived intact")
	check(int(brain.get("voice_notes")) == 1, "the note is recorded as a voice capture")
	# Hands-free (Loop 7a): the assistant drives the interface, and F8 push-to-talk reaches her.
	await ap.send("Ouvre mes projets")
	var opened := await wait_until(func() -> bool: return str(brain.get("view")) == "projects", 10.0)
	check(opened, "« ouvre mes projets » opens the Projects view (%s)" % str(ap.last_ui_actions))
	await brain.call("run_ui_actions", [{"action": "open_view", "view": "graph"}, {"action": "set_volume", "change": "down"}])
	check(str(brain.get("view")) == "graph", "ui actions switch views back to the graph")
	var replies_before := ap.messages_shown
	brain.call("push_to_talk", true, false)
	var ptt_open := await wait_until(func() -> bool: return str(brain.get("voice_state")) == "listening", 10.0)
	check(ptt_open and (brain.get("listening_overlay") as Control).visible, "holding F8 opens the mic with a visible listening indicator")
	var vc2: VoiceCapture = brain.get("voice_capture")
	for c in range(0, tone.size(), 4800):
		vc2.feed_frames(tone.slice(c, c + 4800), 48000.0)
		await process_frame
	await brain.call("push_to_talk", false, false)
	var talked := await wait_until(func() -> bool: return ap.messages_shown >= replies_before + 2 and ap.last_reply.contains("fake transcript"), 20.0)
	check(talked, "releasing F8 sends the speech to the assistant (%s)" % ap.last_reply.left(60))
	check(not (brain.get("listening_overlay") as Control).visible, "the listening indicator hides after sending")
	# Voice fixes (Loop 8b): replay by voice, speed by voice and setting, replay buttons.
	var said_before := ap.last_reply
	await ap.send("Relis-moi ça", true)
	check(ap.replayed == said_before and ap.replayed != "", "« relis-moi ça » reads the previous answer again (%s)" % ap.replayed.left(40))
	var speed_before := app.audio.voice_speed
	await ap.send("Parle plus vite", true)
	await process_frame
	check(app.audio.voice_speed > speed_before, "« parle plus vite » speeds the voice up (%.2f → %.2f)" % [speed_before, app.audio.voice_speed])
	app.audio.set_voice_speed(SbAudio.VOICE_SPEED_DEFAULT)
	var replay_buttons := 0
	for b2 in ap.list.find_children("*", "Button", true, false):
		if (b2 as Button).text == "▶ Replay":
			replay_buttons += 1
	check(replay_buttons >= 3, "every answer has a replay button (%d)" % replay_buttons)
	# Originals and the document viewer (Loop 12).
	var pdf := ProjectSettings.globalize_path("res://tests/fixtures/docs/sample.pdf")
	var pdf_added: bool = await brain.call("add_source_file", pdf)
	check(pdf_added, "a PDF is added (its original is kept)")
	await ap.send("Ouvre le document sample", true)
	var shown := await wait_until(func() -> bool:
		var v: DocumentViewer = brain.get("viewer")
		return v != null and v.visible and v.current_texture() != null, 15.0)
	var dv: DocumentViewer = brain.get("viewer")
	check(shown and dv.pages() == 2, "« ouvre le document » shows the PDF's real page full screen (%d pages)" % (dv.pages() if dv else 0))
	await ap.send("Page suivante", true)
	check(dv.page == 2, "« page suivante » turns the page")
	var page2_ok := await wait_until(func() -> bool: return dv.current_texture() != null, 10.0)
	check(page2_ok, "page 2 is rendered by the engine")
	dv.size = Vector2(1280, 800)  # headless runs have a tiny window; give the viewer a real screen
	dv.set_zoom(4.0)
	var sharper := await wait_until(func() -> bool:
		for key in dv.textures:
			if str(key).begins_with("2:") and int(str(key).split(":")[1]) >= 1600:
				return true
		return false, 10.0)
	check(sharper, "zooming in fetches a sharper page")
	await ap.send("Ouvre l'original", true)
	await wait_until(func() -> bool: return dv.last_opened_original != "", 10.0)
	check(dv.last_opened_original.ends_with(".pdf") and dv.last_opened_original.contains("originals"), "« ouvre l'original » opens the kept file (%s)" % dv.last_opened_original.get_file())
	dv.hide_viewer()
	var doc_id := str(dv.doc.get("note_id", ""))
	await refresh_and_wait(brain)
	graph.zoom_level("read", doc_id)
	var paged := await wait_until(func() -> bool: return graph.page_tex.has(doc_id), 10.0)
	check(paged, "up close in the graph, the document's card shows its first page")
	graph.zoom_to(1.0, Vector2.ZERO, 0.01)
	await create_timer(0.1).timeout
	# An HTML page opens in the reading view, its original in the browser.
	var html_path := OS.get_temp_dir().path_join("sbgd-test-cv-%d.html" % Time.get_ticks_usec())
	var hf := FileAccess.open(html_path, FileAccess.WRITE)
	hf.store_string("<html><head><title>CV test</title><style>p{color:red}</style></head><body><header><h1>Alex Tremblay</h1></header>"
		+ "<section><h2>Expérience</h2><p>" + "Architecte infonuagique, automatisation des déploiements. ".repeat(12) + "</p></section></body></html>")
	hf.close()
	check(await brain.call("add_source_file", html_path), "an HTML file is added")
	var srcs: Dictionary = (await app.backend.api.call_api("/sources"))["data"]
	var html_note := ""
	for s0 in srcs.get("sources", []):
		if str((s0 as Dictionary).get("mime", "")) == "text/html" and str((s0 as Dictionary).get("uri", "")).ends_with(html_path.get_file()):
			html_note = str((s0 as Dictionary).get("note_id", ""))
	var html_open: bool = await brain.call("open_document_for", html_note)
	check(html_open and dv.is_text() and dv.reader.visible, "an HTML document opens in the reading view")
	check(dv.reader_text.text.contains("Alex Tremblay") and dv.reader_text.text.contains("Architecte infonuagique")
		and not dv.reader_text.text.contains("color:red"), "the reading view shows the full text without its markup")
	dv.open_original()
	check(dv.last_opened_original.ends_with(".html") and dv.last_opened_original.contains("originals"), "« Open original » opens the kept HTML file")
	dv.hide_viewer()
	DirAccess.remove_absolute(html_path)
	# A place can be removed from the list (✕): its items go back to the Inbox, Undo restores it.
	var made_place := await app.backend.api.call_api("/brain/spaces", true, HTTPClient.METHOD_POST, JSON.stringify({"name": "Temporary place"}))
	var tmp_sid := str((made_place["data"] as Dictionary).get("id", ""))
	await brain.call("refresh_spaces")
	var removed: bool = await brain.call("remove_place", tmp_sid)
	var left: Dictionary = (await app.backend.api.call_api("/brain/spaces"))["data"]
	check(removed and not (left.get("spaces", []) as Array).any(func(x: Variant) -> bool: return str((x as Dictionary)["id"]) == tmp_sid),
		"a place can be removed")
	var inbox_kept: Dictionary = await app.backend.api.call_api("/brain/spaces/inbox", true, HTTPClient.METHOD_DELETE)
	check(not inbox_kept["ok"], "the Inbox cannot be removed")
	# Internet: a web search answers with its sources as links under the reply; a link opens in the browser.
	await ap.send("Cherche sur le web des offres DevSecOps à Montréal")
	check(ap.last_reply.begins_with("Sur le web") and ap.last_sources.size() == 2, "a web search answers with its sources (%d)" % ap.last_sources.size())
	ap._on_link("https://example.com/emplois/devsecops")
	check(ap.last_opened_url == "https://example.com/emplois/devsecops", "a source opens in the browser")
	var web_linked: String = ap._linkify("Voir https://example.org/guide et [[Atlas risks]]")
	check(web_linked.contains("[url=https://example.org/guide]") and web_linked.contains("[url=Atlas risks]"), "web addresses and item titles both become links")
	# Floating panels (2026-11-04): move, dock by dropping near an edge (the landing place lights up), splitter,
	# shrink into the rail, Ctrl+number, Tab for the graph alone, remember, reset.
	brain.size = Vector2(1600, 1000)  # headless windows are tiny
	var layer: SbPanelLayer = brain.get("panel_layer")
	layer.animate = false
	layer.size = brain.size
	var arch: SbFloatingPanel = brain.get("archivist_panel")
	var places: SbFloatingPanel = brain.get("places_panel")
	var spar: SbFloatingPanel = brain.get("sparring_panel")
	layer.reset_all()
	layer.relayout()
	check(arch.dock == "left" and arch.visible and places.minimized and spar.minimized and arch.size.y > 600.0,
		"the archivist has the left edge; the others wait on the rail (%.0f px tall)" % arch.size.y)
	check(layer.rail_buttons().size() == 3, "the rail shows the shrunk panels: Sparring, Places, the Agent Builder (%d)" % layer.rail_buttons().size())
	check(is_equal_approx(float((brain.get("filters_bar") as Control).offset_left), layer.margin_side + SbPanelLayer.RAIL_W + layer.left_extent),
		"the graph's toolbar moves aside for the rail and the docked panels")
	var drag := func(panel: SbFloatingPanel, to: Vector2, release: bool = true) -> void:
		var down := InputEventMouseButton.new()
		down.button_index = MOUSE_BUTTON_LEFT
		down.pressed = true
		down.global_position = panel.global_position + Vector2(60, 12)
		panel._on_header_input(down)
		var mv := InputEventMouseMotion.new()
		mv.global_position = to
		panel._on_header_input(mv)
		if release:
			var up := InputEventMouseButton.new()
			up.button_index = MOUSE_BUTTON_LEFT
			up.pressed = false
			up.global_position = to
			panel._on_header_input(up)
			layer.relayout()
	drag.call(arch, Vector2(1560, 300), false)
	check(layer.drop_preview().position.x > 1000.0, "while dragging near the right edge, the landing place lights up")
	var up0 := InputEventMouseButton.new()
	up0.button_index = MOUSE_BUTTON_LEFT
	up0.pressed = false
	up0.global_position = Vector2(1560, 300)
	arch._on_header_input(up0)
	layer.relayout()
	check(arch.dock == "right" and layer.drop_preview().size == Vector2.ZERO, "dropped there, it docks on the right and the light goes off")
	drag.call(arch, Vector2(700, 300))
	check(arch.dock == "free" and arch.position.x > 500.0, "dragged to the middle, it floats there")
	var saved: Dictionary = SbSettings.get_value("panels", "archivist", {})
	check(str(saved.get("dock", "")) == "free", "its place is remembered")
	layer.reset_all()
	spar.reveal()
	layer.relayout()
	var h_arch := arch.size.y
	layer.move_split(arch, spar, 150.0)
	check(arch.size.y > h_arch + 100.0 and spar.size.y < h_arch - 100.0, "the splitter shares the edge (%.0f / %.0f px)" % [arch.size.y, spar.size.y])
	brain.call("toggle_panel", 1)  # Ctrl+2 while Sparring is open: it shrinks
	layer.relayout()
	check(spar.minimized and not spar.visible, "Ctrl+2 shrinks Sparring into the rail")
	brain.call("toggle_panel", 1)
	layer.relayout()
	check(spar.visible and str(brain.get("active_agent")) == "sparring", "Ctrl+2 again opens it and makes it the agent you talk to")
	brain.call("toggle_focus_mode")
	layer.relayout()
	check(not arch.visible and not spar.visible, "Tab: the graph alone")
	brain.call("toggle_focus_mode")
	layer.relayout()
	check(arch.visible and spar.visible, "Tab again brings back the same panels")
	brain.call("set_agent", "archivist")
	layer.reset_all()
	layer.relayout()
	check(arch.dock == "left" and places.minimized and arch.weight == 1.0, "« Reset the panel layout » puts everything back")
	# Sparring (2026-11-04): its own panel and conversation; F8 follows the agent you use; a synthesis is saved on approval.
	var sp: AssistantPanel = brain.get("sparring_chat")
	sp.input.focus_entered.emit()
	check(str(brain.get("active_agent")) == "sparring", "using Sparring's panel makes it the agent F8 and F9 talk to")
	await sp.send("Résume-moi tout ça")
	var drafted := await wait_until(func() -> bool: return sp.last_draft != "", 10.0)
	check(drafted and sp.last_draft == "Synthèse de test", "Sparring shows its synthesis in full, not saved yet")
	var before_notes := int(((await app.backend.api.call_api("/brain/graph"))["data"] as Dictionary)["nodes"].size())
	await sp.send("Oui, sauvegarde cette synthèse dans le Brain.")
	var saved_ok := await wait_until(func() -> bool: return sp.last_reply.contains("C'est dans ton Brain"), 10.0)
	check(saved_ok, "on approval the synthesis is saved (%s)" % sp.last_reply.left(60))
	var hist_a: Dictionary = (await app.backend.api.call_api("/assistant/history?agent=archivist"))["data"]
	check(not str(hist_a.get("messages", [])).contains("Synthèse de test"), "Sparring's conversation stays separate from the archivist's")
	brain.call("set_agent", "archivist")
	# Agents as data (Loop 2): a custom agent gets its panel on the rail; ⓘ shows its instructions and capabilities.
	await app.backend.api.call_api("/assistant/agents/sparring/reset", true, HTTPClient.METHOD_POST)
	var made_agent := await _create_test_agent(app)
	await brain.call("refresh_agents")
	var panels_now: Dictionary = brain.get("agent_panels")
	check(made_agent and panels_now.has("coach-test") and (panels_now["coach-test"] as SbFloatingPanel).minimized,
		"a new agent gets its own panel, waiting on the rail")
	await brain.call("show_agent_info", "sparring")
	var sett: SbAgentSettings = brain.get("agent_settings")
	check(str(brain.get("last_agent_info")) == "sparring" and sett != null and sett.instructions.text.contains("Sparring"),
		"ⓘ opens the agent's settings with its instructions")
	check(brain.get("agent_settings_panel") is SbFloatingPanel, "the settings open in a floating tile you can move")
	(sett.checks["internet"] as CheckButton).button_pressed = false  # switch Internet off: saved at once
	var unticked := await wait_until(func() -> bool:
		return not ("internet" in (sett.prof.get("capabilities", []) as Array)), 5.0)
	check(unticked, "switching a capability off saves it at once (Internet removed from Sparring)")
	sett.model_option.select(2)
	sett.model_option.item_selected.emit(2)
	var remodel := await wait_until(func() -> bool: return str(sett.prof.get("model", "")) == "gpt-4o", 5.0)
	check(remodel, "the model can be changed (%s)" % str(sett.prof.get("model", "")))
	check(not sett.missions_box.visible, "no mission ceiling shown while the agent may not run missions")
	(sett.checks["missions"] as CheckButton).button_pressed = true
	check(sett.missions_box.visible, "the Missions capability shows the agent's mission ceiling")
	sett.m_cost.value = 0.5
	var ceiled := await wait_until(func() -> bool:
		return is_equal_approx(float((sett.prof.get("missions", {}) as Dictionary).get("max_cost", 0.0)), 0.5), 5.0)
	var lim := await app.backend.api.call_api("/missions/limits?agent=sparring", true)
	check(ceiled and lim["ok"] and is_equal_approx(float((lim["data"] as Dictionary).get("max_cost", 0.0)), 0.5),
		"the agent's mission ceiling is saved and used by its next mission (0.50 $)")
	sett.instructions.text = str(sett.instructions.text) + "\n- Termine toujours par une question."
	sett.instructions.text_changed.emit()
	await sett._patch({"instructions": sett.instructions.text})
	check(str(sett.prof.get("instructions", "")).ends_with("Termine toujours par une question."), "the instructions can be edited and saved")
	await app.backend.api.call_api("/assistant/agents/sparring/reset", true, HTTPClient.METHOD_POST)
	brain.call("close_agent_settings")
	await app.backend.api.call_api("/assistant/agents/coach-test", true, HTTPClient.METHOD_DELETE)
	await brain.call("refresh_agents")
	check(not (brain.get("agent_panels") as Dictionary).has("coach-test"), "a deleted agent's panel goes away")
	# The Agent Builder (Loop 3): « + » on the rail opens it; it drafts, shows the draft, creates the agent on yes.
	(brain.get("panel_layer") as SbPanelLayer).create_requested.emit()
	var bld: AssistantPanel = (brain.get("agent_chats") as Dictionary).get("builder")
	var builder_open := await wait_until(func() -> bool: return str(brain.get("active_agent")) == "builder" \
		and not bld.busy and bld.last_reply.begins_with("Avec plaisir"), 10.0)
	check(builder_open, "« + » on the rail opens the Agent Builder and it asks the first question")
	await bld.send("Un coach pour préparer mes entrevues, direct mais bienveillant.")
	var shown_draft := await wait_until(func() -> bool: return bld.last_agent_draft == "Coach entrevue", 10.0)
	check(shown_draft, "the new agent's instructions show in full before anything is created")
	await bld.send("Oui, crée-le.")
	var created := await wait_until(func() -> bool: return (brain.get("agent_panels") as Dictionary).has("coach-entrevue"), 10.0)
	check(created, "on yes the agent exists, with its own panel")
	await app.backend.api.call_api("/assistant/agents/coach-entrevue", true, HTTPClient.METHOD_DELETE)
	await brain.call("refresh_agents")
	brain.call("set_agent", "archivist")
	# The legend and the lines' tooltips; the navigation is Graph, Captures, Projects.
	var gv: GraphView = brain.get("graph")
	var some_note := ""
	for id in gv.nodes:
		if str((gv.nodes[id] as Dictionary)["type"]) == "note":
			some_note = str(id)
			break
	check(gv.edge_text({"from": some_note, "to": "space:inbox", "type": "space"}).contains("belongs to"), "a line explains itself on hover")
	var nav: Dictionary = brain.get("view_buttons")
	check(nav.keys() == ["graph", "captures", "projects"], "the tabs are Graph, Captures, Projects (%s)" % [nav.keys()])
	# Graph first, semantic zoom (Loop 10).
	await brain.call("set_view", "graph")
	var vb: Dictionary = brain.get("view_buttons")
	check(not vb.has("today") and not vb.has("agents") and (vb["projects"] as Button).visible, "Today and Agents are set aside; Graph, Captures and Projects stay")
	graph.zoom = 0.3
	check(graph.lod() == "far", "zoomed out, places become named clusters")
	var target_id := graph.find_node("Links make constellations")
	check(target_id != "", "items can be found in the graph by title")
	await ap.send("Zoome sur Links make constellations", true)
	var zoomed := await wait_until(func() -> bool: return graph.lod() == "read" and graph.selected == target_id, 5.0)
	check(zoomed, "« zoome sur Links make constellations » flies into that item (%s, zoom %.1f)" % [graph.lod(), graph.zoom])
	var carded := await wait_until(func() -> bool: return graph.details.has(target_id), 10.0)
	check(carded and str((graph.details[target_id] as Dictionary).get("body", "")).contains("double brackets"),
		"up close, the card holds the item's full text")
	# An organised graph (Loop 13): stable zones, folding, filters, by voice.
	var inbox_anchor: Vector2 = graph.anchors.get("space:inbox", Vector2(999, 999))
	var zone_ok := inbox_anchor == Vector2.ZERO and graph.anchors.size() >= 3
	for k1 in graph.anchors:
		for k2 in graph.anchors:
			if k1 != k2 and (graph.anchors[k1] as Vector2).distance_to(graph.anchors[k2] as Vector2) < 250.0:
				zone_ok = false
	check(zone_ok, "each place has its own zone, the Inbox in the middle (%d zones)" % graph.anchors.size())
	await ap.send("Replie Getting started", true)
	var gs_id := ""
	for nid in graph.nodes:
		if str((graph.nodes[nid] as Dictionary)["label"]) == "Getting started" and str((graph.nodes[nid] as Dictionary)["type"]) == "space":
			gs_id = str(nid)
	var folded_ok := await wait_until(func() -> bool: return graph.folded.has(gs_id), 5.0)
	var gs_note := graph.find_node("Links make constellations")
	check(folded_ok and not graph.is_shown(gs_note) and graph.place_count(gs_id) > 0, "« replie Getting started » gathers its items into the place")
	check(str(brain.get("stats_label").text).contains("of"), "the stats say how many items are shown (%s)" % brain.get("stats_label").text)
	await ap.send("Déplie Getting started", true)
	await wait_until(func() -> bool: return not graph.folded.has(gs_id), 5.0)
	check(graph.is_shown(gs_note), "« déplie » brings them back")
	await ap.send("Montre seulement les notes sur constellations", true)
	var filtered := await wait_until(func() -> bool: return graph.has_filter(), 5.0)
	var fb: GraphFilters = brain.get("filters_bar")
	check(filtered and graph.is_shown(gs_note) and graph.shown_note_count() < graph.node_count("note") and fb.summary.text.contains("constellations"),
		"« montre seulement… sur constellations » filters the graph (%d shown, %s)" % [graph.shown_note_count(), fb.summary.text])
	await ap.send("Enlève les filtres", true)
	await wait_until(func() -> bool: return not graph.has_filter(), 5.0)
	check(graph.shown_note_count() == graph.node_count("note") and not fb.clear_button.visible, "« enlève les filtres » shows everything again")
	# Search and connect in the graph (Loop 14).
	await ap.send("Cherche à l'écran constellations", true)
	var l14_listed := await wait_until(func() -> bool: return (brain.get("last_hits") as Array).size() > 0, 10.0)
	var l14_rb: VBoxContainer = brain.get("results_box")
	check(l14_listed and l14_rb != null and l14_rb.get_child_count() >= 2 and graph.highlight.has(gs_note),
		"« cherche… » lights up the hits and lists them with why they matched")
	check(str((l14_rb.get_child(1) as Button).text).contains("by "), "each hit says how it matched (%s)" % (l14_rb.get_child(1) as Button).text)
	brain.get("search_edit").text = ""
	await brain.call("_on_search_changed", "")
	# Loop 38: @ mentions pin Brain items to one question.
	check(AssistantPanel.mention_query("prix @poul", 10) == "@poul" and AssistantPanel.mention_query("mail a@b", 8) == ""
		and AssistantPanel.mention_query("sans", 4) == "", "« @word » before the caret opens the picker; an e-mail address does not")
	ap.input.text = "Résume @Links"
	ap.input.caret_column = ap.input.text.length()
	ap.input.text_changed.emit(ap.input.text)
	var m_picked := await wait_until(func() -> bool: return ap.picker.visible and not ap.picker_items.is_empty(), 10.0)
	check(m_picked and str((ap.picker_items[0] as Dictionary).get("title", "")) == "Links make constellations",
		"typing @ shows Brain items by title (%d)" % ap.picker_items.size())
	ap.input.text_submitted.emit(ap.input.text)  # Enter picks the item instead of sending
	check(ap.mentions.size() == 1 and ap.input.text == "Résume " and ap.chips_box.visible and not ap.picker.visible,
		"Enter picks the item: a chip appears and the @word goes away (« %s »)" % ap.input.text)
	await ap.send("Résume cet élément")
	check(ap.last_mentions.size() == 1 and str((ap.last_mentions[0] as Dictionary).get("title", "")) == "Links make constellations"
		and ap.mentions.is_empty() and not ap.chips_box.visible, "the question goes with the item pinned, then the chips clear")
	var asked_cp: AssistantPanel = brain.call("chat_panel")
	brain.call("ask_about", graph.find_node("Links make constellations"), "Links make constellations")
	check(asked_cp.mentions.size() == 1 and asked_cp.chips_box.visible, "« Ask about this » pins a graph item to the active agent's next question")
	asked_cp.clear_mentions()
	# Loop 39: import a folder of notes (an Obsidian vault) as a layer.
	var fv_root := OS.get_environment("SBGD_HOME").path_join("Test vault")
	for fv_rel in [".obsidian/app.json", "Projects/Garden/Garden plan.md", "Areas/Soil.md", "Start here.md", "Templates/Daily.md"]:
		DirAccess.make_dir_recursive_absolute(fv_root.path_join(str(fv_rel)).get_base_dir())
		var fv_f := FileAccess.open(fv_root.path_join(str(fv_rel)), FileAccess.WRITE)
		fv_f.store_string({"Projects/Garden/Garden plan.md": "---\ntags: [garden]\n---\nCompost from [[Soil]]. Also [[Not written yet]].",
			"Areas/Soil.md": "Loam and compost. #soil", "Start here.md": "See [[Garden plan]].",
			"Templates/Daily.md": "{{date}}"}.get(str(fv_rel), "{}"))
		fv_f.close()
	var fv_dlg: AcceptDialog = brain.call("import_folder", fv_root)
	var fv_scanned := await wait_until(func() -> bool: return not (fv_dlg.get("scan") as Dictionary).is_empty(), 15.0)
	var fv_scan: Dictionary = fv_dlg.get("scan")
	check(fv_scanned and str(fv_scan.get("kind", "")) == "obsidian" and int(fv_scan.get("notes", 0)) == 3
		and int(fv_scan.get("unresolved", 0)) == 1 and int(fv_scan.get("templates", 0)) == 1,
		"a dropped folder opens the preview: Obsidian vault detected, 3 notes, 1 link to a missing note, templates left out (%s)" % (fv_dlg.get("detect_label") as Label).text)
	check(graph.find_node("Garden plan") == "", "nothing is imported before « Import »")
	await fv_dlg.call("run_import")
	var fv_report: Dictionary = fv_dlg.get("report")
	var fv_in := await wait_until(func() -> bool: return graph.find_node("Garden plan") != "", 15.0)
	check(fv_in and int(fv_report.get("created", 0)) == 3 and int(fv_report.get("resolved", 0)) == 2
		and (fv_dlg.get("result_label") as RichTextLabel).text.contains("Not written yet"),
		"Import brings the notes in as a layer, with the author's links, and lists the link that points nowhere")
	check(graph.find_node("Garden") != "" or graph.anchors.has("space:" + str(graph.nodes.get(graph.find_node("Garden plan"), {}).get("space_id", ""))),
		"the vault's folders become places (Projects/Garden is the project Garden)")
	await app.backend.api.call_api("/packs/layers/" + str(fv_report.get("layer_id", "")), true, HTTPClient.METHOD_DELETE)
	fv_dlg.hide()
	await brain.call("refresh_graph")
	check(graph.find_node("Garden plan") == "", "the imported layer is removed in one go")
	await ap.send("Comment Welcome to your Second Brain est relié à Capture a thought ?", true)
	var l14_welcome := graph.find_node("Welcome to your Second Brain")
	var l14_pathed := await wait_until(func() -> bool: return graph.path_ids.size() >= 2, 10.0)
	check(l14_pathed and str(graph.path_ids[0]) == l14_welcome and ap.last_reply.contains("étape"),
		"« comment X est relié à Y » draws the path and says it (%s)" % ap.last_reply.left(80))
	graph.clear_path()
	var l14_engine_room := graph.find_node("Engine room")
	await brain.call("answer_related", l14_welcome, l14_engine_room, "keep")
	var l14_wn: Dictionary = await app.backend.api.call_api("/brain/notes/" + l14_welcome)
	var l14_linked := false
	for lk in (l14_wn["data"] as Dictionary).get("links_out", []):
		l14_linked = l14_linked or str((lk as Dictionary).get("id", "")) == l14_engine_room
	check(l14_linked, "keeping a related idea turns it into a real link")
	await brain.call("edit_in_card", l14_engine_room)
	var l14_ed: PanelContainer = brain.get("card_editor")
	check(l14_ed != null and l14_ed.visible, "double-clicking an item opens an editor right on its card")
	var l14_te: TextEdit = l14_ed.find_children("*", "TextEdit", true, false)[0]
	l14_te.text = l14_te.text + "\nEdited in the graph."
	(l14_ed.find_children("*", "Button", true, false).filter(func(x: Variant) -> bool: return (x as Button).text.begins_with("Save"))[0] as Button).pressed.emit()
	var l14_saved := await wait_until(func() -> bool: return brain.get("card_editor") == null, 10.0)
	var l14_en: Dictionary = await app.backend.api.call_api("/brain/notes/" + l14_engine_room)
	check(l14_saved and str((l14_en["data"] as Dictionary).get("body", "")).contains("Edited in the graph."), "the card's edit is l14_saved")
	# Timeline (Loop 15): items on a time axis, one lane per place, and back.
	await ap.send("Montre la chronologie", true)
	var tl_on := await wait_until(func() -> bool: return graph.graph_layout == "timeline", 5.0)
	await create_timer(1.2).timeout
	var ordered := true
	var by_time: Array = []
	for nid in graph.nodes:
		var nd: Dictionary = graph.nodes[nid]
		if str(nd["type"]) == "note" and graph.is_shown(str(nid)):
			by_time.append([str(nd.get("created_at", "")), (nd["pos"] as Vector2).x])
	by_time.sort_custom(func(x: Array, y: Array) -> bool: return str(x[0]) < str(y[0]))
	for i in range(1, by_time.size()):
		if str(by_time[i][0]).left(16) > str(by_time[i - 1][0]).left(16) and float(by_time[i][1]) + 30.0 < float(by_time[i - 1][1]):
			ordered = false
	var fbar: GraphFilters = brain.get("filters_bar")
	check(tl_on and ordered and fbar.timeline_button.button_pressed, "« montre la chronologie » lays items out in time order (%d items)" % by_time.size())
	await ap.send("Retour aux zones", true)
	var back := await wait_until(func() -> bool: return graph.graph_layout == "zones", 5.0)
	check(back and not fbar.timeline_button.button_pressed, "« retour aux zones » brings the organised graph back")
	await ap.send("Vue d'ensemble", true)
	var overview := await wait_until(func() -> bool: return graph.lod() == "far", 5.0)
	check(overview, "« vue d'ensemble » zooms back out to the places")
	graph.zoom_to(1.0, Vector2.ZERO, 0.01)
	await create_timer(0.1).timeout
	# Live conversation (Loop 7b): speech to speech through the engine (fake Realtime upstream).
	SbSettings.set_value("voice", "headphones", true)  # the dummy audio driver never drains playback
	await brain.call("set_view", "graph")
	var lc: LiveConversation = app.live
	var live_on: bool = await lc.start(false)
	check(live_on and lc.active and lc.state == "listening", "F9 opens a live conversation (%s)" % lc.last_error)
	var second := PackedVector2Array()
	for i in 48000:
		var s2 := sin(TAU * 200.0 * float(i) / 48000.0) * 0.3
		second.append(Vector2(s2, s2))
	var bubbles_before := ap.messages_shown
	for c in range(0, second.size(), 4800):
		lc.capture.feed_frames(second.slice(c, c + 4800), 48000.0)
		await process_frame
	var turned := await wait_until(func() -> bool: return str(brain.get("view")) == "projects" \
		and ap.last_reply.begins_with("C'est ouvert"), 15.0)
	check(turned, "a spoken request opens Projects and the answer joins the conversation (%s)" % ap.last_reply.left(40))
	check(ap.messages_shown >= bubbles_before + 2, "what you said and what she answered both appear")
	check(lc.player._pushed > 0 or lc.player.buffered_frames() > 0, "her voice streams into the player")
	check(lc.cost_usd != null and float(lc.cost_usd) > 0.0 and lc._meter.text.contains("$"),
		"the live pill shows this conversation's running cost (%s)" % lc._meter.text)
	app.set_theme_choice("focus")  # rebuilds the brain screen: the conversation must survive
	for _i in 10:
		await process_frame
	brain = app.current()
	graph = brain.get("graph")
	ap = brain.get("assistant_panel")
	check(lc.active and lc._pill.visible, "the conversation survives a theme change")
	for _t in 2:
		for c in range(0, second.size(), 4800):
			lc.capture.feed_frames(second.slice(c, c + 4800), 48000.0)
			await process_frame
		await create_timer(0.3).timeout
	var said_bye := await wait_until(func() -> bool: return not lc.active, 15.0)
	check(said_bye and lc.last_end == "goodbye", "« merci, c'est tout » ends the conversation (%s)" % lc.last_end)
	SbSettings.set_value("voice", "headphones", false)
	var notes_before_restart := graph.node_count("note")  # before leaving the brain screen (it is freed)
	app.set_theme_choice("evening")
	await process_frame
	check(SbTheme.current == "evening" and app.current_screen == "brain", "theme switch keeps you in the brain")
	check(app.audio.playlist.size() >= 2 and app.audio.theme_name == "evening", "music follows the theme")
	app.set_theme_choice("auto")
	# Missions (Loop 33): « Mission… » starts one; its card shows the plan, the question with choices, the draft;
	# approving saves the items (scripted mission of the fake model).
	var mchat: AssistantPanel = app.current().call("chat_panel", "archivist")
	var mcard: Control = mchat.mission_card
	mchat.mission_row.visible = true
	mchat.mission_edit.text = "This week's menu from the grocery specials"
	await mchat.start_mission(mchat.mission_edit.text)
	var m_asked := await wait_until(func() -> bool:
		return str((mcard.get("mission") as Dictionary).get("status", "")) == "waiting", 30.0)
	check(m_asked and mcard.visible and (mcard.get("choice_boxes") as Array).size() == 4 and not mchat.mission_row.visible,
		"a mission plans, keeps the specials and asks which ones (its card shows the choices)")
	if m_asked:
		((mcard.get("choice_boxes") as Array)[0] as BaseButton).button_pressed = true
		await mcard.call("answer")
	var m_drafted := await wait_until(func() -> bool:
		return str((mcard.get("mission") as Dictionary).get("status", "")) == "draft", 30.0)
	check(m_drafted and ((mcard.get("mission") as Dictionary).get("plan", []) as Array).all(func(st: Dictionary) -> bool: return st["status"] == "done"),
		"after the answer the mission shows its draft, every step ticked")
	if m_drafted:
		await mcard.call("approve")
	var msaved := await wait_until(func() -> bool:
		return str((mcard.get("mission") as Dictionary).get("status", "")) == "saved", 15.0)
	var mres: Dictionary = (mcard.get("mission") as Dictionary).get("result", {})
	check(msaved and (mres.get("note_ids", []) as Array).size() == 3, "approving saves the draft's items in the Brain")
	mcard.visible = false
	notes_before_restart += (mres.get("note_ids", []) as Array).size()  # the mission's items are kept too
	# FR / EN (Loop 26): English by default; the switch rebuilds the screen in French and tells the engine.
	check(I18n.lang == "en", "English is the app's language by default")
	check(app.current().find_child("LangFR", true, false) is Button, "the FR / EN switch is in the top bar")
	await app.set_language("fr")
	for _i in 6:
		await process_frame
	var fr_nav: Dictionary = app.current().get("view_buttons")
	check(I18n.lang == "fr" and (fr_nav["graph"] as Button).text == "Graphe" and (fr_nav["projects"] as Button).text == "Projets",
		"FR rebuilds the interface in French (%s)" % (fr_nav["graph"] as Button).text)
	var lang_st := await app.backend.api.call_api("/assistant/status")
	check(lang_st["ok"] and str((lang_st["data"] as Dictionary).get("ui_language", "")) == "fr",
		"the engine follows the app's language (agents, Live, its own words)")
	await app.set_language("en")
	for _i in 6:
		await process_frame
	var en_nav: Dictionary = app.current().get("view_buttons")
	check((en_nav["graph"] as Button).text == "Graph" and str(SbSettings.get_value("ui", "language", "")) == "en",
		"EN brings the English back, and the choice is remembered")
	app.show_console()
	await process_frame
	check(app.current_screen == "console", "engine room opens from the brain")
	var console: Control = app.current()
	var ready := await wait_until(func() -> bool:
		return bool(console.get("health_ok")) and not (console.get("last_status") as Dictionary).is_empty() \
			and not (console.get("last_storage") as Dictionary).is_empty() \
			and not (console.get("last_events") as Array).is_empty(), 20.0)
	check(ready, "console received health, status, storage and events from the API")
	var status: Dictionary = console.get("last_status")
	var py: Dictionary = status.get("python", {})
	var db: Dictionary = status.get("database", {})
	var proc: Dictionary = status.get("process", {})
	check(bool(py.get("in_venv", false)), "API runs inside the virtual environment")
	check(int(db.get("schema_version", 0)) >= 1, "database schema is migrated")
	check(int(proc.get("pid", 0)) == app.backend.server_pid(), "status pid matches runtime/server.json")
	check(proc.get("rss_bytes") != null, "API memory is measured")
	# Your data (Loop 30): back up now, the list, a typed word guards restoring, a restore, the folder removal.
	var home_dir := OS.get_environment("SBGD_HOME")
	check(InfoCard.is_local_path(home_dir) and not InfoCard.is_local_path("http://127.0.0.1:8765")
		and not InfoCard.is_local_path("/no/such/folder/sbgd") and not InfoCard.is_local_path("ok · 12 ms"),
		"engine-room values that are folders or files on this computer are recognised (and only those)")
	var openable := 0
	for l in console.find_children("*", "Label", true, false):
		if (l as Label).mouse_default_cursor_shape == Control.CURSOR_POINTING_HAND and InfoCard.is_local_path((l as Label).text):
			openable += 1
	check(openable >= 2, "the database file and the data folder open with a click (%d paths)" % openable)
	var mp: Control = console.find_child("MissionsPanel", true, false)
	check(mp != null, "the engine room has a Missions card")
	if mp != null:
		await mp.call("refresh")
		var mlist: Array = mp.get("missions")
		var m_shown := mlist.size() > 0 and mp.find_child("Mission_" + str((mlist[0] as Dictionary).get("id", "")), true, false) != null
		check(m_shown and str(mp.get("summary_label").text).contains("1"),
			"the Missions card lists the missions and this month's cost (%s)" % str(mp.get("summary_label").text))
		if m_shown:
			var first: Dictionary = mlist[0]
			mp.set("open_id", str(first.get("id", "")))
			mp.call("_rebuild")
			var detail: RichTextLabel = mp.find_child("MissionDetail", true, false)
			check(detail != null and detail.text.contains("[url=") and detail.text.contains("Maxi"),
				"a mission opens on its plan, findings with source links and the answer given")
			await mp.call("_again", str(first.get("id", "")))
			var again_id := str(mp.get("open_id"))
			check(again_id != "" and again_id != str(first.get("id", "")), "« Run again » starts the same goal as a new mission")
			if again_id != "":
				await app.backend.api.call_api("/missions/%s/stop" % again_id, true, HTTPClient.METHOD_POST, "{}")
	var dp: DataPanel = console.find_child("DataPanel", true, false)
	check(dp != null, "the engine room has a Your data card")
	if dp != null:
		var backed := await dp.back_up_now()
		check(backed and str(dp.last.get("last", {}).get("kind", "")) == "manual" and dp.state_label.text.contains("✓"),
			"Back up now: a checked backup, shown in the card (%s)" % dp.state_label.text)
		check(dp.open_backups_folder() != "" and dp.where_label.text == str(dp.last.get("destination", "")) and not dp.where_label.editable,
			"the backups folder can be opened, and its path selected and copied")
		var rows := (dp.last.get("backups", []) as Array)
		check(not rows.is_empty() and dp.list_box.get_child_count() >= 2, "the backups are listed with Restore")
		var cw := dp.confirm_word("Restore", "test", "RESTORE")
		check(cw.get_ok_button().disabled, "restoring waits for the typed word")
		var cedit: LineEdit = cw.find_children("*", "LineEdit", true, false)[0]
		cedit.text = "restore"
		cedit.text_changed.emit(cedit.text)
		check(not cw.get_ok_button().disabled, "typing the word unlocks it")
		cw.queue_free()
		var restored := await dp.restore(str((rows[0] as Dictionary).get("id", "")))
		check(restored and dp.result_label.text.contains("safety copy"), "a restore keeps a safety copy (%s)" % dp.result_label.text.left(60))
	var tree_dir := OS.get_environment("SBGD_HOME").path_join("remove-tree-test")
	DirAccess.make_dir_recursive_absolute(tree_dir.path_join("backups/brain-x"))
	DirAccess.make_dir_recursive_absolute(tree_dir.path_join("data/notes"))
	FileAccess.open(tree_dir.path_join("data/notes/a.txt"), FileAccess.WRITE).store_string("x")
	FileAccess.open(tree_dir.path_join("backups/brain-x/keep.txt"), FileAccess.WRITE).store_string("x")
	var resisted := DataPanel.remove_tree(tree_dir, tree_dir.path_join("backups"))
	check(resisted == 0 and not DirAccess.dir_exists_absolute(tree_dir.path_join("data"))
		and FileAccess.file_exists(tree_dir.path_join("backups/brain-x/keep.txt")),
		"uninstalling removes the folder but keeps the backups when asked")
	DataPanel.remove_tree(tree_dir)
	# The console shows the latest 40 operations; the setup may be older than that by now, so ask for more.
	var all_events: Dictionary = await app.backend.api.call_api("/system/events?limit=500")
	var events: Array = (all_events["data"] as Dictionary).get("events", []) if all_events["ok"] else []
	var has_ready := false
	for e in events:
		var ev: Dictionary = e
		if str(ev.get("component")) == "bootstrap" and str(ev.get("status")) == "ok":
			has_ready = true
	check(has_ready, "recent operations include the verified setup")
	var bp: BillingPanel = console.get("billing_panel")
	var billed := await wait_until(func() -> bool: return not bp.last.is_empty(), 20.0)
	check(billed and bool(bp.last.get("configured", false)) and bp.data_box.visible,
		"real-costs panel shows OpenAI's billed figures")
	check(bp.chart.days.size() == 30 and not bp.chart.groups.is_empty() and bp.legend.get_child_count() > 0,
		"cost chart has 30 daily bars with a legend (%d bars)" % bp.chart.days.size())
	check(bp.month_value.text.begins_with("$") and bp.models_grid.get_child_count() > 5,
		"month total and the per-model table are filled (%s)" % bp.month_value.text)
	check(bp.chart._get_tooltip(Vector2(bp.chart.size.x - 8, 40)).contains("—"),
		"hovering a bar explains that day's cost")
	var installed_at := str(db.get("installed_at", ""))

	# Second launch of the app: install is recognised and the fast path works.
	var res := await app.backend.shutdown_engine(3.0)
	check(bool(res.get("stopped", false)) and bool(res.get("graceful", false)), "engine stops gracefully on request")
	check(not await app.backend.engine_alive(), "API no longer answers after shutdown")
	app.audio.stop_all()
	await process_frame
	app.queue_free()
	await process_frame
	var app2: SbApp = load("res://scenes/main.tscn").instantiate()
	root.add_child(app2)
	await process_frame
	await process_frame
	var w2: Control = app2.current()
	var p2: Button = w2.get("primary")
	check(p2.text == "Start", "reopened app recognises the installation")
	var started_ms := Time.get_ticks_msec()
	p2.pressed.emit()
	var reopened := await wait_until(func() -> bool: return app2.current_screen == "brain", 120.0)
	check(reopened, "Start reaches the brain again")
	var fast_s := (Time.get_ticks_msec() - started_ms) / 1000.0
	check(fast_s < 30.0, "second start does not reinstall (%.1f s)" % fast_s)
	var b2: Control = app2.current()
	var g2: GraphView = b2.get("graph")
	var kept := await wait_until(func() -> bool: return g2.node_count("note") == notes_before_restart, 20.0)
	check(kept, "captured notes are still there after a restart")
	app2.show_console()
	await process_frame
	var c2: Control = app2.current()
	var ok2 := await wait_until(func() -> bool:
		return bool(c2.get("health_ok")) and not (c2.get("last_status") as Dictionary).is_empty(), 20.0)
	check(ok2, "console healthy after restart")
	var st2: Dictionary = c2.get("last_status")
	var db2: Dictionary = st2.get("database", {})
	check(str(db2.get("installed_at", "")) == installed_at and installed_at != "", "data kept across re-setup")
	await app2.backend.shutdown_engine(3.0)
	check(not await app2.backend.engine_alive(), "engine stopped at the end of the test")
	app2.audio.stop_all()
	await process_frame
	app2.queue_free()
	await process_frame


## Loop 15: a big synthetic brain stays workable (generous limits: headless CPU timing).
func _perf_check() -> void:
	var g := GraphView.new()
	g.size = Vector2(1280, 800)
	root.add_child(g)
	await process_frame
	var nodes: Array = []
	var edges: Array = []
	for p in 13:
		nodes.append({"id": "space:p%d" % p, "type": "space", "label": "Place %d" % p, "kind": "resource", "weight": 150})
	for i in 2000:
		nodes.append({"id": "n%d" % i, "type": "note", "label": "Item %d" % i, "kind": "note", "space_id": "p%d" % (i % 13)})
		edges.append({"from": "n%d" % i, "to": "space:p%d" % (i % 13), "type": "space"})
		if i % 3 == 0 and i > 0:
			edges.append({"from": "n%d" % i, "to": "n%d" % (i - 1), "type": "link"})
	g.set_graph({"nodes": nodes, "edges": edges})
	var t := Time.get_ticks_usec()
	g._simulate(1.0)
	var sim_ms := (Time.get_ticks_usec() - t) / 1000.0
	g.heat = 0.0
	g.queue_redraw()
	await process_frame
	g.queue_redraw()
	await process_frame
	check(sim_ms < 60.0, "2,000 items: one layout step takes %.1f ms" % sim_ms)
	check(g.draw_ms < 120.0, "2,000 items: one frame draws in %.1f ms" % g.draw_ms)
	g.queue_free()


## An item let go in another place's zone asks to move there; let go elsewhere, it stays put.
func _drop_check() -> void:
	var g := GraphView.new()
	g.size = Vector2(1280, 800)
	root.add_child(g)
	await process_frame
	g.set_graph({"nodes": [
		{"id": "space:a", "type": "space", "label": "A", "kind": "project"},
		{"id": "space:b", "type": "space", "label": "B", "kind": "project"},
		{"id": "n1", "type": "note", "label": "Item", "kind": "note", "space_id": "a"}],
		"edges": [{"from": "n1", "to": "space:a", "type": "space"}]})
	g.queue_redraw()
	await process_frame
	var moved: Array = []
	g.item_dropped_on_place.connect(func(id: String, sid: String) -> void: moved.append([id, sid]))
	var b_pos: Vector2 = (g.nodes["space:b"] as Dictionary)["pos"]
	g.zone_reach["space:b"] = 120.0
	g.drop_item("n1", b_pos + Vector2(20, 0))
	check(moved == [["n1", "b"]], "an item dropped in another place's zone asks to move there")
	g.drop_item("n1", Vector2(5000, 5000))
	check(moved.size() == 1 and not bool((g.nodes["n1"] as Dictionary)["pinned"]), "an item dropped outside any zone floats back (nothing is pinned)")
	g.queue_free()


## Agents are created by the Agent Builder (Loop 3); here straight through the engine for the test.
func _create_test_agent(app: SbApp) -> bool:
	var res := await app.backend.api.call_api("/assistant/agents", true, HTTPClient.METHOD_POST,
		JSON.stringify({"name": "Coach test", "instructions": "Tu prépares mes entrevues, avec des questions précises et du feedback franc.",
			"capabilities": ["read_brain", "internet"]}))
	return res["ok"]


func refresh_and_wait(brain: Control) -> void:
	await brain.call("refresh_graph")
	await process_frame
