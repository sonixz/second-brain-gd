extends "res://tools/capture_base.gd"
## The screens the website showcase does not show (first run, other views, the engine room), for reviewing a
## language: SBGD_UI_LANG=fr SBGD_CAPTURE_SCRIPT=screens tools/showcase.sh screens-fr


func _run() -> void:
	boot_env()
	app = load("res://scenes/main.tscn").instantiate()
	root.add_child(app)
	await pause(1.5)
	await shot("01-welcome")
	(app.current().get("primary") as Button).pressed.emit()
	await pause(3.0)
	await shot("02-setup")
	var setup: Control = app.current()
	var deadline := Time.get_ticks_msec() + 600000
	while app.current_screen == "setup" and Time.get_ticks_msec() < deadline:
		if (setup.get("continue_button") as Button).visible:
			await shot("03-setup-done")
			(setup.get("continue_button") as Button).pressed.emit()
		await pause(0.3)
	while app.current_screen not in ["onboarding", "brain"] and Time.get_ticks_msec() < deadline:
		await pause(0.2)
	if app.current_screen == "onboarding":
		await pause(1.0)
		await shot("04-voice-key")
		(app.current().get("panel") as VoiceKeyPanel).skipped.emit()
	while app.current_screen != "brain" and Time.get_ticks_msec() < deadline:
		await pause(0.2)
	b = app.current()
	await pause(3.0)
	for v in ["today", "projects", "agents"]:
		await b.call("set_view", v)
		await pause(1.5)
		await shot("05-" + v)
	await b.call("set_view", "graph")
	app.show_console()
	await pause(6.0)
	await shot("06-engine-room")
	app.show_brain()
	await pause(2.0)
	await finish()
