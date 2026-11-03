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
	OS.set_environment("SBGD_BILLING_PROVIDER", "fake")  # real-costs panel reads canned OpenAI pages
	OS.unset_environment("OPENAI_ADMIN_KEY")
	# The agent room installs from a tiny local fixture (a fake app-server), never the 160 MB download.
	OS.set_environment("SBGD_AGENTS_MANIFEST", ProjectSettings.globalize_path("res://tests/fixtures/agents/manifest.json"))
	SbSettings.set_value("assistant", "speaks", true)
	SbSettings.set_value("onboarding", "voice_done", false)
	if OS.get_environment("SBGD_HOME") == "":
		printerr("Set SBGD_HOME to a temporary folder before running these tests.")
		quit(2)
		return
	print("Unit checks")
	_unit()
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
	check(toast_label.text.begins_with("Filed in Getting started"), "a toast says where it went (%s)" % toast_label.text)
	await brain.call("_undo_toast")
	check(toast_label.text.begins_with("Put back"), "the filing can be undone from the toast")
	check(graph.node_count("note") == gs_before + 1, "undo keeps the note, only its place changes")
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
	await ap.send("Ouvre ma journée d'aujourd'hui")
	var opened := await wait_until(func() -> bool: return str(brain.get("view")) == "today", 10.0)
	check(opened, "« ouvre ma journée » opens the Today view (%s)" % str(ap.last_ui_actions))
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
	var turned := await wait_until(func() -> bool: return str(brain.get("view")) == "today" \
		and ap.last_reply.begins_with("C'est ouvert"), 15.0)
	check(turned, "a spoken request opens Today and the answer joins the conversation (%s)" % ap.last_reply.left(40))
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
	var events: Array = console.get("last_events")
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
