extends SceneTree
## Walks the real flow and saves screenshots (needs a display, see tools/capture.sh).
## Uses SBGD_HOME (fresh folder ⇒ a full install is captured).

var out_dir := ""


func _initialize() -> void:
	out_dir = OS.get_environment("SBGD_CAPTURE_DIR")
	DirAccess.make_dir_recursive_absolute(out_dir)
	_run.call_deferred()


func shot(name: String) -> void:
	await process_frame
	await process_frame
	var img := root.get_texture().get_image()
	img.save_png(out_dir.path_join(name + ".png"))
	print("captured ", name)


func pause(s: float) -> void:
	await create_timer(s).timeout


func _run() -> void:
	root.size = Vector2i(1280, 800)
	var app: SbApp = load("res://scenes/main.tscn").instantiate()
	root.add_child(app)
	await pause(1.0)
	await shot("01-welcome")
	var welcome: Control = app.current()
	(welcome.get("diag_button") as Button).pressed.emit()
	await pause(2.5)
	await shot("02-prerequisites")
	(welcome.get("primary") as Button).pressed.emit()
	var setup: Control = app.current()
	var got_mid := false
	var deadline := Time.get_ticks_msec() + 600000
	while app.current_screen == "setup" and Time.get_ticks_msec() < deadline:
		var rows: Dictionary = setup.get("rows")
		var dep: StepRow = rows["dependencies"]
		if not got_mid and dep.status == "progress" and (setup.get("progress") as ProgressBar).value > 0.35:
			await shot("03-setup-installing")
			got_mid = true
		var done: Button = setup.get("continue_button")
		if done.visible:
			await pause(0.3)
			await shot("04-setup-ready")
			break
		await process_frame
	while app.current_screen != "console" and Time.get_ticks_msec() < deadline:
		await pause(0.2)
	await pause(6.5)
	await shot("05-system-console")
	await app.backend.shutdown_engine(3.0)
	await pause(4.0)
	await shot("06-console-engine-stopped")
	quit()
