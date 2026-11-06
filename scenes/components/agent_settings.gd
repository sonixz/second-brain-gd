class_name SbAgentSettings
extends ScrollContainer
## An agent's settings (ⓘ in its title bar), shown in a floating tile: name, model, capabilities (each an on/off
## switch, its tools listed),
## first words, instructions. Every change is saved at once (capabilities, model) or with Save (text) and applies
## from the next message, in a live conversation too (from the next thing said). Built-in agents can go back to the original;
## custom agents can be deleted. « Ask the Builder » hands the change over to the Agent Builder, by voice.

signal changed
signal ask_builder(agent_name: String)
signal close_requested

var app: SbApp
var agent_id := ""
var prof: Dictionary = {}
var caps_info: Dictionary = {}
var models: Array = []
var status: Label
var name_edit: LineEdit
var model_option: OptionButton
var intro_edit: LineEdit
var instructions: TextEdit
var save_button: Button
var checks: Dictionary = {}   # capability -> CheckButton (on/off switch)
var missions_box: VBoxContainer  # the agent's own mission ceiling (Loop 35), shown with the Missions capability
var m_cost: SpinBox
var m_minutes: SpinBox
var m_model: OptionButton
var _patching := false


func setup(a: SbApp, id: String, profile: Dictionary, capabilities: Dictionary, model_list: Array) -> SbAgentSettings:
	app = a
	agent_id = id
	prof = profile
	caps_info = capabilities
	models = model_list
	horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 10)
	add_child(box)

	# Identity and model
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 10)
	box.add_child(top)
	var badge := Label.new()
	badge.text = str(prof.get("letter", "?"))
	badge.add_theme_font_size_override("font_size", 26)
	badge.custom_minimum_size = Vector2(40, 40)
	badge.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	badge.add_theme_color_override("font_color", Color("#" + str(prof.get("color", "a9d4ff"))))
	top.add_child(badge)
	name_edit = LineEdit.new()
	name_edit.text = str(prof.get("name", id))
	name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name_edit.tooltip_text = I18n.t("The agent's name (Enter to save)")
	name_edit.text_submitted.connect(func(t: String) -> void: _patch({"name": t}))
	top.add_child(name_edit)
	model_option = OptionButton.new()
	model_option.tooltip_text = I18n.t("The model this agent thinks with")
	var current := str(prof.get("model", "gpt-6-sol"))
	var found := false
	for m in models:
		model_option.add_item(str((m as Dictionary).get("label", (m as Dictionary).get("id", ""))))
		model_option.set_item_metadata(model_option.item_count - 1, str((m as Dictionary).get("id", "")))
		if str((m as Dictionary).get("id", "")) == current:
			model_option.select(model_option.item_count - 1)
			found = true
	if not found:
		model_option.add_item(current)
		model_option.set_item_metadata(model_option.item_count - 1, current)
		model_option.select(model_option.item_count - 1)
	model_option.item_selected.connect(func(i: int) -> void: _patch({"model": str(model_option.get_item_metadata(i))}))
	top.add_child(model_option)
	status = Label.new()
	status.theme_type_variation = "Muted"
	status.text = I18n.t("Adjusted (not the original)") if bool(prof.get("modified", false)) else \
		(I18n.t("Built-in agent") if bool(prof.get("builtin", false)) else I18n.t("Your agent"))
	box.add_child(status)

	# Capabilities
	box.add_child(_overline(I18n.t("CAPABILITIES · WHAT IT MAY DO")))
	var have: Array = prof.get("capabilities", [])
	for key in caps_info:
		var c: Dictionary = caps_info[key]
		var row := VBoxContainer.new()
		row.add_theme_constant_override("separation", 0)
		box.add_child(row)
		var cb := CheckButton.new()  # an on/off switch
		cb.text = "%s · %s" % [str(c.get("label", key)), str(c.get("description", ""))]
		cb.alignment = HORIZONTAL_ALIGNMENT_LEFT
		cb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		cb.button_pressed = key in have
		cb.tooltip_text = I18n.t("Tools: %s") % ", ".join((c.get("tools", []) as Array).map(func(t: Variant) -> String: return str(t)))
		if key == "agents" and agent_id == "builder":
			cb.disabled = true  # the Builder without it would be no builder
			cb.tooltip_text += "\n" + I18n.t("(The Agent Builder always keeps this one.)")
		if key == "organise" and not (key in have):
			cb.tooltip_text += "\n" + I18n.t("Lets this agent change your graph (with Undo).")
		var k := str(key)
		cb.toggled.connect(func(_on: bool) -> void: _save_capabilities())
		row.add_child(cb)
		checks[k] = cb
		var tools := Label.new()
		tools.theme_type_variation = "Muted"
		tools.add_theme_font_size_override("font_size", 12)
		tools.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		tools.text = "      " + ", ".join((c.get("tools", []) as Array).map(func(t: Variant) -> String: return str(t)))
		row.add_child(tools)

	# Missions: the agent's own ceiling and model (shown when it may run missions)
	_missions_block(box)

	# First words (custom agents)
	if not bool(prof.get("builtin", false)):
		box.add_child(_overline(I18n.t("FIRST WORDS")))
		intro_edit = LineEdit.new()
		intro_edit.text = str(prof.get("intro", ""))
		intro_edit.placeholder_text = I18n.t("What it says when you open it")
		intro_edit.text_submitted.connect(func(t: String) -> void: _patch({"intro": t}))
		box.add_child(intro_edit)

	# Instructions
	var ihead := HBoxContainer.new()
	box.add_child(ihead)
	var ilab := _overline(I18n.t("INSTRUCTIONS"))
	ilab.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	ihead.add_child(ilab)
	var builder := Button.new()
	builder.text = I18n.t("Ask the Builder to change it…")
	builder.theme_type_variation = "GhostButton"
	builder.tooltip_text = I18n.t("Describe the change out loud; the Agent Builder rewrites the instructions and shows you the result")
	builder.visible = agent_id != "builder"
	builder.pressed.connect(func() -> void:
		ask_builder.emit(str(prof.get("name", agent_id)))
		close_requested.emit())
	ihead.add_child(builder)
	instructions = TextEdit.new()
	instructions.text = str(prof.get("instructions", ""))
	instructions.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	instructions.custom_minimum_size = Vector2(0, 300)
	instructions.text_changed.connect(func() -> void: save_button.disabled = false)
	box.add_child(instructions)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	box.add_child(actions)
	save_button = Button.new()
	save_button.text = I18n.t("Save the instructions")
	save_button.theme_type_variation = "PrimaryButton"
	save_button.disabled = true
	save_button.pressed.connect(func() -> void:
		if await _patch({"instructions": instructions.text}):
			save_button.disabled = true)
	actions.add_child(save_button)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	actions.add_child(spacer)
	if bool(prof.get("builtin", false)):
		var reset := Button.new()
		reset.text = I18n.t("Back to the original")
		reset.theme_type_variation = "GhostButton"
		reset.disabled = not bool(prof.get("modified", false))
		reset.pressed.connect(func() -> void:
			var r := await app.backend.api.call_api("/assistant/agents/%s/reset" % agent_id, true, HTTPClient.METHOD_POST)
			if r["ok"]:
				_reload(r["data"])
				status.text = I18n.t("Back to the original ✓")
				changed.emit())
		actions.add_child(reset)
	else:
		var del := Button.new()
		del.text = I18n.t("Delete this agent")
		del.theme_type_variation = "GhostButton"
		del.pressed.connect(func() -> void:
			await app.backend.api.call_api("/assistant/agents/" + agent_id, true, HTTPClient.METHOD_DELETE)
			changed.emit()
			close_requested.emit())
		actions.add_child(del)
	return self


## Maximum cost and minutes per mission, and the model missions think with ("Same as the agent" by default).
## A change is saved at once and applies to the next mission started.
func _missions_block(box: VBoxContainer) -> void:
	missions_box = VBoxContainer.new()
	missions_box.name = "MissionsBlock"
	missions_box.add_theme_constant_override("separation", 6)
	missions_box.visible = "missions" in (prof.get("capabilities", []) as Array)
	box.add_child(missions_box)
	missions_box.add_child(_overline(I18n.t("MISSIONS · CEILING PER MISSION")))
	var own: Dictionary = prof.get("missions", {}) if prof.get("missions") is Dictionary else {}
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	missions_box.add_child(row)
	m_cost = _spin(0.05, 20.0, 0.05, float(own.get("max_cost", 1.0)), " $")
	m_cost.name = "MissionCost"
	m_cost.tooltip_text = I18n.t("A mission stops cleanly at this cost, with what it found so far")
	row.add_child(_labelled(I18n.t("At most"), m_cost))
	m_minutes = _spin(1.0, 240.0, 1.0, float(own.get("max_minutes", 15.0)), " min")
	m_minutes.name = "MissionMinutes"
	m_minutes.tooltip_text = I18n.t("Working time only: the time it waits for your answer does not count")
	row.add_child(_labelled(I18n.t("and"), m_minutes))
	m_model = OptionButton.new()
	m_model.name = "MissionModel"
	m_model.tooltip_text = I18n.t("The model missions think with: a strong one does the long jobs better")
	m_model.add_item(I18n.t("Same model as the agent"))
	m_model.set_item_metadata(0, "")
	for m in models:
		m_model.add_item(str((m as Dictionary).get("label", (m as Dictionary).get("id", ""))))
		m_model.set_item_metadata(m_model.item_count - 1, str((m as Dictionary).get("id", "")))
		if str((m as Dictionary).get("id", "")) == str(own.get("model", "")):
			m_model.select(m_model.item_count - 1)
	m_model.item_selected.connect(func(_i: int) -> void: _save_missions())
	missions_box.add_child(m_model)
	m_cost.value_changed.connect(func(_v: float) -> void: _save_missions())
	m_minutes.value_changed.connect(func(_v: float) -> void: _save_missions())
	var hint := Label.new()
	hint.theme_type_variation = "Muted"
	hint.add_theme_font_size_override("font_size", 12)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.text = I18n.t("Applies to the next mission. What missions cost is in the engine room.")
	missions_box.add_child(hint)


func _spin(lo: float, hi: float, step: float, v: float, suffix: String) -> SpinBox:
	var sp := SpinBox.new()
	sp.min_value = lo
	sp.max_value = hi
	sp.step = step
	sp.value = v
	sp.suffix = suffix
	sp.custom_minimum_size = Vector2(110, 0)
	return sp


func _labelled(text: String, c: Control) -> HBoxContainer:
	var h := HBoxContainer.new()
	h.add_theme_constant_override("separation", 6)
	var l := Label.new()
	l.text = text
	h.add_child(l)
	h.add_child(c)
	return h


func _save_missions() -> void:
	await _patch({"missions": {"max_cost": m_cost.value, "max_minutes": m_minutes.value,
		"model": str(m_model.get_item_metadata(m_model.selected))}})


func _overline(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.theme_type_variation = "Overline"
	return l


func _save_capabilities() -> void:
	var caps: Array = []
	for k in checks:
		if (checks[k] as CheckButton).button_pressed:
			caps.append(k)
	if missions_box != null:
		missions_box.visible = "missions" in caps
	await _patch({"capabilities": caps})


## Saves fields at once; the next message (or live session) uses them. One save at a time: two at once
## (a capability switched, then the ceiling changed) would each write the whole profile and the last one would win.
func _patch(fields: Dictionary) -> bool:
	while _patching and is_inside_tree():
		await get_tree().process_frame
	_patching = true
	var r := await app.backend.api.call_api("/assistant/agents/" + agent_id, true, HTTPClient.METHOD_PATCH, JSON.stringify(fields))
	_patching = false
	if not is_inside_tree():
		return r["ok"]
	if r["ok"]:
		prof = r["data"]
		status.text = I18n.t("Saved ✓ · applies from the next message, live conversations included")
		changed.emit()
	else:
		status.text = I18n.t("Could not save: %s") % str(r.get("error", ""))
	return r["ok"]


func _reload(p: Dictionary) -> void:
	prof = p
	name_edit.text = str(p.get("name", agent_id))
	instructions.text = str(p.get("instructions", ""))
	save_button.disabled = true
	var have: Array = p.get("capabilities", [])
	for k in checks:
		(checks[k] as CheckButton).set_pressed_no_signal(k in have)


func selected_capabilities() -> Array:
	return checks.keys().filter(func(k: Variant) -> bool: return (checks[k] as CheckButton).button_pressed)
