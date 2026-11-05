extends SceneTree
## Shared by the website screenshots (tools/showcase.gd) and the How-to guides (tools/howto.gd): installs the app
## in a temp home on a private virtual display, opens the English showcase Brain, takes screenshots.

var out_dir := ""
var app: SbApp
var b: Control
var g: GraphView


func _initialize() -> void:
	out_dir = OS.get_environment("SBGD_CAPTURE_DIR")
	DirAccess.make_dir_recursive_absolute(out_dir)
	call_deferred("_run")


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


## Sends a message in an agent's panel and waits for its answer (and any draft card).
func ask(panel: AssistantPanel, text: String) -> void:
	await panel.send(text)
	var end := Time.get_ticks_msec() + 20000
	while panel.busy and Time.get_ticks_msec() < end:
		await pause(0.2)
	await pause(1.2)


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




## The environment both share; a provider already chosen by the caller (record, replay) is kept.
func boot_env() -> void:
	var size := OS.get_environment("SBGD_SHOT_SIZE")
	root.size = Vector2i(1280, 800) if size == "" else Vector2i(int(size.get_slice("x", 0)), int(size.get_slice("x", 1)))
	OS.set_environment("SBGD_SETTINGS", OS.get_environment("SBGD_HOME").path_join("showcase-settings.cfg"))
	SbSettings.set_value("ui", "theme", "morning")
	SbSettings.set_value("ui", "modules", false)
	SbSettings.set_value("onboarding", "voice_done", true)
	SbSettings.set_value("voice", "speak_replies", false)
	# the app's language: English (the site's screenshots), or SBGD_UI_LANG=fr to review the French interface
	SbSettings.set_value("ui", "language", "fr" if OS.get_environment("SBGD_UI_LANG") == "fr" else "en")
	OS.set_environment("SBGD_VOICE_PROVIDER", "fake")
	OS.set_environment("SBGD_BILLING_PROVIDER", "fake")
	if OS.get_environment("SBGD_ASSISTANT_PROVIDER") == "":
		OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	OS.set_environment("SBGD_SEED", "showcase")


## Installs, opens the Brain and waits until it is indexed and still.
func open_brain() -> bool:
	if not await _install():
		push_error("capture: the brain screen never opened")
		return false
	b = app.current()
	stage()
	await _wait_meaning()
	await b.call("refresh_graph")
	g = b.get("graph")
	await pause(2.0)
	await settle()
	stage()
	return true


func finish() -> void:
	SbSettings.set_value("ui", "theme", "auto")
	await app.backend.shutdown_engine(3.0)
	app.audio.stop_all()
	await process_frame
	quit()


func _run() -> void:  # each capture script defines its own
	pass
