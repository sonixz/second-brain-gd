extends "res://tools/capture_base.gd"
## @ mention screenshots (Loop 38): tools/showcase.sh with SBGD_CAPTURE_SCRIPT=mention_shots (SBGD_UI_LANG=fr for
## French). The showcase Brain and its scripted model: nothing calls OpenAI.


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
	await pause(1.0)
	# 1. Typing @ shows items by title.
	chat.input.grab_focus()
	chat.input.text = ("Qu'est-ce que je coupe pour respecter le budget? @Ren" if fr else "What can I cut to stay under budget? @Ren")
	chat.input.caret_column = chat.input.text.length()
	chat.input.text_changed.emit(chat.input.text)
	var end := Time.get_ticks_msec() + 10000
	while not chat.picker.visible and Time.get_ticks_msec() < end:
		await pause(0.2)
	calm()
	await pause(0.6)
	await shot("n1-picker")
	# 2. Two items pinned as chips.
	chat.input.text_submitted.emit(chat.input.text)
	chat.input.text = chat.input.text + "@Appl"
	chat.input.caret_column = chat.input.text.length()
	chat.input.text_changed.emit(chat.input.text)
	end = Time.get_ticks_msec() + 10000
	while (not chat.picker.visible or chat.picker_items.is_empty()) and Time.get_ticks_msec() < end:
		await pause(0.2)
	chat.input.text_submitted.emit(chat.input.text)
	await pause(0.6)
	await shot("n2-chips")
	# 3. The answer comes from them and cites them.
	await chat.send(chat.input.text)
	await pause(1.2)
	await shot("n3-answer")
	# 4. « Ask about this » on a graph item.
	var nid := g.find_node("Tile samples: the matte green wins")
	g.select(nid)
	b.call("open_note", nid)
	await pause(1.2)
	var ask: Button = b.find_child("AskAbout", true, false)
	if ask != null:
		ask.pressed.emit()
	await pause(0.8)
	await shot("n4-ask-about")
	quit(0)
