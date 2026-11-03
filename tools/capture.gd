extends SceneTree
## Walks the real flow and saves screenshots (needs a display, see tools/capture.sh).
## Uses SBGD_HOME (fresh folder ⇒ a full install is captured), then fills a demo
## brain through the real API and captures each theme.

var out_dir := ""
var app: SbApp

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


func _run() -> void:
	root.size = Vector2i(1280, 800)
	SbSettings.set_value("ui", "theme", "morning")
	SbSettings.set_value("onboarding", "voice_done", false)
	OS.set_environment("SBGD_VOICE_PROVIDER", "fake")  # screenshots never call OpenAI
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
		if (setup.get("continue_button") as Button).visible:
			await pause(0.3)
			await shot("03-setup-ready")
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
	await pause(4.0)
	await shot("04-brain-first-visit")
	# Fill a demo brain through the real API.
	var space_ids: Array[String] = []
	for s in DEMO_SPACES:
		var res := await api("/brain/spaces", {"name": s[0], "color": "#" + str(s[1])})
		space_ids.append(str((res["data"] as Dictionary).get("id", "")))
	for n in DEMO_NOTES:
		var payload := {"title": n[1], "kind": n[2], "body": n[3]}
		if int(n[0]) >= 0:
			payload["space_id"] = space_ids[int(n[0])]
		await api("/brain/notes", payload)
	app.show_brain()
	await pause(7.0)
	await shot("05-brain-morning")
	var brain: Control = app.current()
	var graph: GraphView = brain.get("graph")
	var target := ""
	for id in graph.nodes:
		if str((graph.nodes[id] as Dictionary)["label"]) == "Daily router agent":
			target = str(id)
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
	for theme in ["focus", "evening", "forest"]:
		app.set_theme_choice(theme)
		await pause(6.0)
		await shot("08-brain-" + theme)
	app.set_theme_choice("morning")
	await pause(1.0)
	app.show_console()
	await pause(6.5)
	await shot("09-engine-room")
	(app.get("_widget") as AudioWidget).call("_open")
	await pause(0.6)
	await shot("10-ambiance-panel")
	SbSettings.set_value("ui", "theme", "auto")
	await app.backend.shutdown_engine(3.0)
	app.audio.stop_all()
	await process_frame
	quit()
