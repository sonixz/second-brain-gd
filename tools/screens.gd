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
	var scrolls := app.current().find_children("*", "ScrollContainer", true, false)
	if not scrolls.is_empty():  # down to the real costs (OpenAI billing)
		var sc: ScrollContainer = scrolls[0]
		var top := sc.get_v_scroll_bar().max_value
		for n in app.current().find_children("*", "", true, false):  # the billing card's top, like the website image
			var sn: Script = n.get_script()
			if sn != null and sn.resource_path.ends_with("billing_panel.gd") and n is Control:
				top = (n as Control).global_position.y - (sc.get_child(0) as Control).global_position.y - 4.0
				break
		sc.scroll_vertical = int(top)
		await pause(1.5)
		await shot("07-costs")
	app.show_brain()
	await pause(2.0)
	await finish()
