class_name MissionCard
extends PanelContainer
## An agent's mission (Loop 33), at the top of its panel: the goal, the plan ticked as it goes, what the agent is
## doing, the cost so far, Stop; its question with choices when it waits for you; the draft with Approve / Change /
## Discard; then what was saved. Follows the engine (GET /missions?agent=…) while a mission is active.

signal saved(count: int)

const POLL_S := 1.5

var app: SbApp
var agent := "archivist"
var mission: Dictionary = {}
var dismissed := ""                 # a finished mission the user closed
var body: VBoxContainer
var scroll: ScrollContainer
var actions: VBoxContainer          # the answer / approve buttons: always in view, under what scrolls
var timer: Timer
var busy := false
var last_status := ""
var choice_boxes: Array[BaseButton] = []
var other_edit: LineEdit
var change_edit: LineEdit
var draft_open := {}                # item index -> shown in full


func setup(a: SbApp, who: String) -> MissionCard:
	app = a
	agent = who
	visible = false
	add_theme_stylebox_override("panel", SbTheme.box(Color(SbTheme.WARM, 0.12), 14, Color(SbTheme.WARM, 0.45), 1, 12))
	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 8)
	add_child(outer)
	scroll = ScrollContainer.new()  # a long draft scrolls inside the card: the chat below stays in view
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	outer.add_child(scroll)
	actions = VBoxContainer.new()
	actions.add_theme_constant_override("separation", 6)
	outer.add_child(actions)
	body = VBoxContainer.new()
	body.add_theme_constant_override("separation", 6)
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(body)
	timer = Timer.new()
	timer.wait_time = POLL_S
	timer.timeout.connect(refresh)
	add_child(timer)
	return self


func active() -> bool:
	return str(mission.get("status", "")) in ["running", "waiting", "draft"]


## Asks the engine for this agent's latest mission and redraws when it changed.
func refresh() -> void:
	if busy or app == null or not is_inside_tree():
		return
	busy = true
	var res := await app.backend.api.call_api("/missions?agent=" + agent.uri_encode())
	busy = false
	if not res["ok"] or not is_inside_tree():
		return
	var list: Array = (res["data"] as Dictionary).get("missions", [])
	var m: Dictionary = list[0] if not list.is_empty() else {}
	if m.is_empty() or str(m.get("id", "")) == dismissed:
		mission = {}
		visible = false
		timer.stop()
		return
	var before := JSON.stringify(mission)
	mission = m
	if str(m.get("status", "")) != last_status and str(m.get("status", "")) == "waiting" and last_status != "":
		app.audio.play("notification")
	last_status = str(m.get("status", ""))
	if JSON.stringify(mission) != before:
		_rebuild()
	visible = true
	if active():
		if timer.is_stopped():
			timer.start()
	else:
		timer.stop()


## A mission was just started (or answered): follow it closely again.
func follow() -> void:
	dismissed = ""
	await refresh()
	if timer.is_stopped():
		timer.start()


func _status_text(st: String) -> String:
	return {"running": I18n.t("WORKING"), "waiting": I18n.t("WAITING FOR YOU"), "draft": I18n.t("DRAFT READY · NOT SAVED YET"),
		"saved": I18n.t("SAVED"), "stopped": I18n.t("STOPPED"), "failed": I18n.t("COULD NOT FINISH")}.get(st, st.to_upper())


func _feed_text(e: Dictionary) -> String:
	var d := str(e.get("detail", ""))
	match str(e.get("kind", "")):
		"start": return I18n.t("Started")
		"plan": return I18n.t("Wrote the plan")
		"step": return I18n.t("Done: %s") % d
		"search": return I18n.t("Searching the web: %s") % d
		"read": return I18n.t("Reading %s") % d
		"browser": return I18n.t("Reading in your browser: %s") % d
		"brain": return I18n.t("Looking in your Brain: %s") % d
		"found": return I18n.t("Kept: %s") % d.replace("_", " ")
		"question": return I18n.t("Asked you a question")
		"answer": return I18n.t("You answered: %s") % d
		"revise": return I18n.t("You asked for changes: %s") % d
		"draft": return I18n.t("Draft ready: %s") % d
		"saved": return I18n.t("Saved in the Brain")
		"stopped": return I18n.t("Stopped: %s") % d
		"failed": return I18n.t("Could not finish: %s") % d
	return d


func _dict(v: Variant) -> Dictionary:
	return v if v is Dictionary else {}


func _label(text: String, variation: String = "", wrap := true) -> Label:
	var l := Label.new()
	l.text = text
	if variation != "":
		l.theme_type_variation = variation
	if wrap:
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	return l


func _button(text: String, variation: String, cb: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.theme_type_variation = variation
	b.pressed.connect(cb)
	return b


func _rebuild() -> void:
	_fit()  # measured on the next frame, once the new content is laid out
	for c in body.get_children() + actions.get_children():
		c.queue_free()
	choice_boxes.clear()
	var st := str(mission.get("status", ""))
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	body.add_child(head)
	var over := _label(I18n.t("MISSION") + " · " + _status_text(st), "Overline", false)
	over.add_theme_color_override("font_color", SbTheme.WARM)
	head.add_child(over)
	var cost: float = float(mission.get("cost", 0.0))
	head.add_child(_label("%.2f $ · %d min" % [cost, int(round(float(mission.get("minutes", 0.0))))], "Muted", false))
	if active():
		head.add_child(_button(I18n.t("Stop"), "GhostButton", func() -> void: _post("/stop")))
	else:
		head.add_child(_button(I18n.t("Close"), "GhostButton", func() -> void:
			dismissed = str(mission.get("id", ""))
			visible = false))
	body.add_child(_label(str(mission.get("goal", ""))))
	var plan: Array = mission.get("plan", [])
	if not plan.is_empty() and st in ["waiting", "draft"]:  # one line: the question or the draft needs the room
		var done := plan.filter(func(x: Dictionary) -> bool: return x.get("status", "") != "todo").size()
		body.add_child(_label(I18n.t("Plan: %d of %d steps done") % [done, plan.size()], "Muted"))
	elif not plan.is_empty():
		var pl := VBoxContainer.new()
		pl.add_theme_constant_override("separation", 1)
		body.add_child(pl)
		var current_set := false
		for s in plan:
			var sst := str((s as Dictionary).get("status", "todo"))
			var mark := "✓ " if sst == "done" else ("– " if sst == "skipped" else ("▸ " if not current_set and st == "running" else "○ "))
			if sst == "todo":
				current_set = true
			var l := _label(mark + str((s as Dictionary).get("title", "")), "" if sst == "todo" else "Muted")
			pl.add_child(l)
	if st == "running":
		var feed: Array = mission.get("feed", [])
		var n := feed.size()
		for i in range(maxi(0, n - 2), n):
			body.add_child(_label("… " + _feed_text(feed[i]), "Muted"))
	elif st == "waiting":
		_draw_question(_dict(mission.get("question")))
	elif st == "draft":
		_draw_draft(_dict(mission.get("draft")))
	elif st == "saved":
		var ids: Array = _dict(mission.get("result")).get("note_ids", [])
		body.add_child(_label(I18n.t("%d items saved in the Brain. “Undo” in the archivist's panel removes them all.") % ids.size()))
	elif st in ["stopped", "failed"]:
		body.add_child(_label(str(mission.get("reason", "")), "Muted"))


func _fit() -> void:
	await get_tree().process_frame
	if not is_inside_tree():
		return
	var room := 420.0
	var host := get_parent() as Control
	if host != null and host.size.y > 0:
		room = maxf(160.0, host.size.y * 0.72 - actions.get_combined_minimum_size().y)
	scroll.custom_minimum_size.y = minf(body.get_combined_minimum_size().y, room)


func _draw_question(q: Dictionary) -> void:
	body.add_child(_label(str(q.get("question", "")), "Heading"))
	var multiple := bool(q.get("multiple", false))
	var group := ButtonGroup.new()
	for c in q.get("choices", []):
		var cb := CheckBox.new()
		cb.text = str(c)
		cb.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		cb.tooltip_text = str(c)
		for state in ["normal", "hover", "pressed", "focus", "hover_pressed", "disabled"]:  # compact rows
			var sb := StyleBoxEmpty.new()
			sb.content_margin_top = 3
			sb.content_margin_bottom = 3
			cb.add_theme_stylebox_override(state, sb)
		cb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		if not multiple:
			cb.button_group = group
		body.add_child(cb)
		choice_boxes.append(cb)
	other_edit = LineEdit.new()
	other_edit.placeholder_text = I18n.t("Or write your answer…")
	other_edit.text_submitted.connect(func(_t: String) -> void: answer())
	actions.add_child(other_edit)
	var row := HBoxContainer.new()
	actions.add_child(row)
	row.add_child(_button(I18n.t("Answer"), "PrimaryButton", answer))


## Sends the ticked choices (and the written answer) to the mission, which resumes.
func answer() -> void:
	var picked: Array = []
	for b in choice_boxes:
		if b.button_pressed:
			picked.append(b.text)
	if other_edit != null and other_edit.text.strip_edges() != "":
		picked.append(other_edit.text.strip_edges())
	if picked.is_empty():
		return
	await _post("/answer", {"answer": picked})


func _draw_draft(d: Dictionary) -> void:
	body.add_child(_label(str(d.get("title", "")), "Heading"))
	body.add_child(_label(str(d.get("summary", ""))))
	if str(d.get("place", "")) != "":
		body.add_child(_label(I18n.t("Goes into: %s") % str(d.get("place", "")), "Muted"))
	var items: Array = d.get("items", [])
	for i in items.size():
		var it: Dictionary = items[i]
		var row := VBoxContainer.new()
		body.add_child(row)
		var title := Button.new()
		title.flat = true
		title.alignment = HORIZONTAL_ALIGNMENT_LEFT
		title.text = ("▾ " if draft_open.get(i, false) else "▸ ") + str(it.get("title", ""))
		title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		title.pressed.connect(func() -> void:
			draft_open[i] = not draft_open.get(i, false)
			_rebuild())
		row.add_child(title)
		if draft_open.get(i, false):
			var rt := RichTextLabel.new()
			rt.bbcode_enabled = false
			rt.fit_content = true
			rt.selection_enabled = true
			rt.text = str(it.get("body", "")) + ("\n\n" + str(it.get("url", "")) if str(it.get("url", "")) != "" else "")
			rt.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			row.add_child(rt)
	var buttons := HBoxContainer.new()
	buttons.add_theme_constant_override("separation", 8)
	actions.add_child(buttons)
	buttons.add_child(_button(I18n.t("Approve and save"), "PrimaryButton", approve))
	buttons.add_child(_button(I18n.t("Discard"), "GhostButton", func() -> void: _post("/stop")))
	var change_row := HBoxContainer.new()
	actions.add_child(change_row)
	change_edit = LineEdit.new()
	change_edit.placeholder_text = I18n.t("Or say what to change…")
	change_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	change_edit.text_submitted.connect(func(_t: String) -> void: change())
	change_row.add_child(change_edit)
	change_row.add_child(_button(I18n.t("Change"), "GhostButton", change))


func approve() -> void:
	var res := await _post("/approve")
	if res.get("ok", false):
		saved.emit((_dict(mission.get("result")).get("note_ids", []) as Array).size())


func change() -> void:
	if change_edit == null or change_edit.text.strip_edges() == "":
		return
	await _post("/revise", {"changes": change_edit.text.strip_edges()})


func _post(what: String, payload: Dictionary = {}) -> Dictionary:
	if mission.is_empty():
		return {}
	var res := await app.backend.api.call_api("/missions/" + str(mission.get("id", "")) + what, true, HTTPClient.METHOD_POST,
		JSON.stringify(payload))
	if not res["ok"]:
		push_warning("mission " + what + ": " + str(res.get("error", "")))
	await follow()
	return res


## Starts a mission for this agent (the panel's Mission button, or the tests).
func start_mission(goal: String) -> Dictionary:
	var res := await app.backend.api.call_api("/missions", true, HTTPClient.METHOD_POST,
		JSON.stringify({"agent": agent, "goal": goal}))
	if res["ok"]:
		await follow()
	return res
