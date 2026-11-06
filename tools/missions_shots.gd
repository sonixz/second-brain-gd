extends "res://tools/capture_base.gd"
## Mission screenshots (Loop 33): tools/showcase.sh with SBGD_CAPTURE_SCRIPT=missions_shots (SBGD_UI_LANG=fr for
## French). The showcase Brain and the scripted mission of the fake model: nothing calls OpenAI.


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	g.zoom_to(0.5, Vector2(-60, 0), 0.3)
	var fr := I18n.lang == "fr"
	var panel: SbFloatingPanel = b.call("agent_panel", "archivist")
	panel.reveal()
	panel.dock = "right"
	panel.dock_size = 520.0
	panel.layout_changed.emit()
	var chat: AssistantPanel = b.call("chat_panel", "archivist")
	var card: Control = chat.mission_card
	await pause(1.0)
	chat.mission_row.visible = true
	chat.mission_edit.text = "Le menu de la semaine avec les rabais d’IGA, Maxi et Provigo" if fr else "This week's menu from the IGA, Maxi and Provigo specials"
	await pause(0.5)
	await shot("m0-start")
	await chat.start_mission(chat.mission_edit.text)
	var end := Time.get_ticks_msec() + 30000
	while str((card.get("mission") as Dictionary).get("status", "")) != "waiting" and Time.get_ticks_msec() < end:
		await pause(0.3)
	var boxes: Array = card.get("choice_boxes")
	if boxes.size() >= 4:
		(boxes[0] as BaseButton).button_pressed = true
		(boxes[3] as BaseButton).button_pressed = true
	calm()
	await pause(0.8)
	await shot("m1-question")
	await card.call("answer")
	end = Time.get_ticks_msec() + 30000
	while str((card.get("mission") as Dictionary).get("status", "")) != "draft" and Time.get_ticks_msec() < end:
		await pause(0.3)
	(card.get("draft_open") as Dictionary)[0] = true
	card.call("_rebuild")
	await pause(0.8)
	(card.get("scroll") as ScrollContainer).scroll_vertical = 150  # the items of the draft
	await shot("m2-draft")
	await card.call("approve")
	await pause(2.5)
	await shot("m3-saved")
	# Loop 35: the agent's own mission ceiling, then the missions in the engine room.
	await app.backend.api.call_api("/assistant/agents/archivist", true, HTTPClient.METHOD_PATCH,
		JSON.stringify({"missions": {"max_cost": 0.75, "max_minutes": 10, "model": ""}}))
	await b.call("show_agent_info", "archivist")
	await pause(1.0)
	var sett: SbAgentSettings = b.get("agent_settings")
	if sett != null and sett.missions_box != null:
		sett.missions_box.visible = true
		await pause(0.3)
		sett.ensure_control_visible(sett.missions_box)
		sett.scroll_vertical = int(sett.missions_box.position.y) - 40
	await pause(0.8)
	await shot("m4-agent-ceiling")
	b.call("close_agent_settings")
	app.show_console()
	await pause(4.0)
	var console: Control = app.current()
	var mp: Control = console.find_child("MissionsPanel", true, false)
	if mp != null:
		await mp.call("refresh")
		var ms: Array = mp.get("missions")
		if not ms.is_empty():
			mp.set("open_id", str((ms[0] as Dictionary).get("id", "")))
			mp.call("_rebuild")
		await pause(0.5)
		var sc := mp.get_parent().get_parent() as ScrollContainer
		if sc != null:
			sc.scroll_vertical = int(mp.position.y) - 8
	await pause(0.8)
	await shot("m5-engine-room")
	await finish()
