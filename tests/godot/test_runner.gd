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
	# The engine started by this test uses a fake transcription provider: no OpenAI call, no cost.
	OS.set_environment("SBGD_VOICE_PROVIDER", "fake")
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
	if not was_installed:
		check(saw_running_dependency, "dependency step was shown running")

	var brain: Control = app.current()
	var graph: GraphView = brain.get("graph")
	var seeded := await wait_until(func() -> bool: return graph.node_count("note") >= 4, 20.0)
	check(seeded, "first visit shows the starter graph (%d notes)" % graph.node_count("note"))
	check(bool(brain.get("health_ok")), "brain header reports the engine healthy")
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
