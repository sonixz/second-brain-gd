class_name ProjectsView
extends PanelContainer
## Areas with their projects (PARA), and a project card to edit the goal,
## status, due date and next actions.

signal open_note(note_id: String)
signal ask_assistant(space_id: String, prompt: String)
signal changed
signal failed(message: String)

var app: SbApp
var stack: VBoxContainer
var structure_data: Dictionary = {}
var card_data: Dictionary = {}
var showing_card := ""
var _fields: Dictionary = {}


func setup(a: SbApp) -> ProjectsView:
	app = a
	theme_type_variation = "Glass"
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	stack = VBoxContainer.new()
	stack.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	stack.add_theme_constant_override("separation", 12)
	scroll.add_child(stack)
	return self


## A project status (an id from the engine) in the interface language.
static func status_label(s: String) -> String:
	return {"active": I18n.t("Active"), "waiting": I18n.t("Waiting"), "someday": I18n.t("Someday"),
		"done": I18n.t("Done")}.get(s, s.capitalize())


## A space kind (project, area, resource) as an overline.
static func kind_label(k: String) -> String:
	return {"project": I18n.t("PROJECT"), "area": I18n.t("AREA"), "resource": I18n.t("RESOURCE"),
		"archive": I18n.t("ARCHIVE")}.get(k, k.to_upper())


func _clear() -> void:
	for c in stack.get_children():
		c.queue_free()


func refresh() -> void:
	if showing_card != "":
		await show_card(showing_card)
		return
	var res := await app.backend.api.call_api("/brain/structure")
	if not res["ok"] or not is_inside_tree():
		return
	structure_data = res["data"]
	_clear()
	var head := HBoxContainer.new()
	stack.add_child(head)
	var t := Label.new()
	t.text = I18n.t("Areas & projects")
	t.theme_type_variation = "Heading"
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(t)
	var hint := Label.new()
	hint.theme_type_variation = "Muted"
	hint.text = I18n.t("Areas last forever · projects end with an outcome")
	head.add_child(hint)
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 14)
	grid.add_theme_constant_override("v_separation", 14)
	stack.add_child(grid)
	var areas: Array = structure_data.get("areas", [])
	for item in areas:
		grid.add_child(_area_card(item))
	var loose: Array = structure_data.get("loose_projects", [])
	if not loose.is_empty():
		grid.add_child(_area_card({"id": "", "name": I18n.t("Projects without an area"), "projects": loose, "color": null}))
	var res_list: Array = structure_data.get("resources", [])
	if not res_list.is_empty():
		var l := Label.new()
		l.theme_type_variation = "Muted"
		l.text = I18n.t("Resources: %s") % ", ".join(res_list.map(func(r: Variant) -> String: return str((r as Dictionary)["name"])))
		stack.add_child(l)


func _area_card(area: Dictionary) -> PanelContainer:
	var card := PanelContainer.new()
	card.theme_type_variation = "Inset"
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	card.add_child(col)
	var head := HBoxContainer.new()
	col.add_child(head)
	var dot := Label.new()
	dot.text = "●"
	dot.add_theme_color_override("font_color", Color(str(area["color"])) if area.get("color") != null else SbTheme.FOREST_LIGHT)
	head.add_child(dot)
	var name := Button.new()
	name.text = str(area["name"])
	name.theme_type_variation = "GhostButton"
	name.add_theme_font_override("font", SbTheme.font(650))
	name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	name.alignment = HORIZONTAL_ALIGNMENT_LEFT
	var aid := str(area["id"])
	if aid != "":
		name.pressed.connect(func() -> void: show_card(aid))
	head.add_child(name)
	var projects: Array = area.get("projects", [])
	for item in projects:
		var p: Dictionary = item
		var b := Button.new()
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		var bits: PackedStringArray = [str(p["name"])]
		if str(p.get("status", "active")) != "active":
			bits.append("(%s)" % status_label(str(p["status"])))
		if p.get("due_date") != null:
			bits.append("· " + str(p["due_date"]))
		bits.append("· " + I18n.t("%d open") % int(p.get("open_tasks", 0)))
		b.text = "  ".join(bits)
		b.clip_text = true
		var pid := str(p["id"])
		b.pressed.connect(func() -> void: show_card(pid))
		col.add_child(b)
	if aid != "":
		var add := LineEdit.new()
		add.placeholder_text = I18n.t("+ New project in %s…") % area["name"]
		add.text_submitted.connect(func(text: String) -> void: create_project(aid, text))
		col.add_child(add)
	return card


func create_project(area_id: String, name: String) -> String:
	if name.strip_edges() == "":
		return ""
	var payload := {"name": name.strip_edges()}
	if area_id != "":
		payload["area_id"] = area_id
	var res := await app.backend.api.call_api("/brain/projects", true, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if not res["ok"]:
		app.audio.play("error")
		return ""
	app.audio.play("note_create")
	changed.emit()
	var pid := str((res["data"] as Dictionary)["id"])
	await show_card(pid)
	return pid


# -------------------------------------------------------------- the card
func show_card(space_id: String) -> void:
	var res := await app.backend.api.call_api("/brain/spaces/%s/card" % space_id)
	if not res["ok"] or not is_inside_tree():
		return
	showing_card = space_id
	card_data = res["data"]
	_clear()
	_fields.clear()
	var c := card_data
	var is_project := str(c["kind"]) == "project"
	var top := HBoxContainer.new()
	top.add_theme_constant_override("separation", 8)
	stack.add_child(top)
	var back := Button.new()
	back.text = I18n.t("← All areas")
	back.theme_type_variation = "GhostButton"
	back.pressed.connect(func() -> void:
		showing_card = ""
		refresh())
	top.add_child(back)
	var kind := Label.new()
	kind.text = kind_label(str(c["kind"]))
	kind.theme_type_variation = "Overline"
	kind.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(kind)
	var ask := Button.new()
	ask.text = I18n.t("Ask the assistant")
	ask.theme_type_variation = "PrimaryButton"
	ask.pressed.connect(func() -> void:
		ask_assistant.emit(space_id, I18n.t("How is “%s” going? What would be the most useful next step?") % c["name"]))
	top.add_child(ask)
	var name := LineEdit.new()
	name.text = str(c["name"])
	name.add_theme_font_override("font", SbTheme.font(650))
	name.add_theme_font_size_override("font_size", SbTheme.fs(22))
	stack.add_child(name)
	_fields["name"] = name
	var grid := GridContainer.new()
	grid.columns = 2
	grid.add_theme_constant_override("h_separation", 12)
	grid.add_theme_constant_override("v_separation", 8)
	stack.add_child(grid)
	_field(grid, "goal", I18n.t("Goal"), I18n.t("What does done look like?"), c.get("goal"))
	_field(grid, "why", I18n.t("Why"), I18n.t("Why it matters"), c.get("why"))
	if is_project:
		_field(grid, "due_date", I18n.t("Due"), I18n.t("YYYY-MM-DD"), c.get("due_date"))
		var status := OptionButton.new()
		for s in ["active", "waiting", "someday", "done"]:
			status.add_item(status_label(s))
			status.set_item_metadata(status.item_count - 1, s)
			if s == str(c.get("status", "active")):
				status.select(status.item_count - 1)
		_labelled(grid, I18n.t("Status"), status)
		_fields["status"] = status
		var area := OptionButton.new()
		area.add_item(I18n.t("— no area —"))
		area.set_item_metadata(0, "")
		var areas: Array = structure_data.get("areas", [])
		for item in areas:
			var a: Dictionary = item
			area.add_item(str(a["name"]))
			area.set_item_metadata(area.item_count - 1, str(a["id"]))
			if str(a["id"]) == str(c.get("area_id", "")):
				area.select(area.item_count - 1)
		_labelled(grid, I18n.t("Area"), area)
		_fields["area_id"] = area
	var instr := TextEdit.new()
	instr.placeholder_text = I18n.t("Instructions for the assistant in this project (tone, language, people, constraints…)")
	instr.text = "" if c.get("instructions") == null else str(c["instructions"])
	instr.custom_minimum_size = Vector2(0, 70)
	instr.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	_labelled(grid, I18n.t("Assistant"), instr)
	_fields["instructions"] = instr
	var save := Button.new()
	save.text = I18n.t("Save")
	save.pressed.connect(func() -> void: save_card())
	stack.add_child(save)
	# Next actions
	var tl := Label.new()
	tl.text = I18n.t("NEXT ACTIONS")
	tl.theme_type_variation = "Overline"
	stack.add_child(tl)
	var tasks: Array = c.get("tasks", [])
	for item in tasks:
		var t: Dictionary = item
		var cb := CheckBox.new()
		cb.text = str(t["title"]) + ("   · " + str(t["due_date"]) if t.get("due_date") != null else "")
		cb.button_pressed = str(t["status"]) == "done"
		cb.modulate.a = 0.5 if cb.button_pressed else 1.0
		cb.set_meta("sfx", "none")
		var tid := str(t["id"])
		cb.toggled.connect(func(on: bool) -> void:
			cb.modulate.a = 0.5 if on else 1.0
			app.audio.play("step_done" if on else "click", 0.05)
			await app.backend.api.call_api("/brain/tasks/" + tid, true, HTTPClient.METHOD_PATCH, JSON.stringify({"done": on}))
			changed.emit())
		stack.add_child(cb)
	var add := LineEdit.new()
	add.placeholder_text = I18n.t("+ Next action…  (add a date with “@2026-11-20”)")
	add.text_submitted.connect(func(text: String) -> void: add_task(space_id, text))
	stack.add_child(add)
	var projects: Array = c.get("projects", [])
	if not projects.is_empty():
		var pl := Label.new()
		pl.text = I18n.t("PROJECTS")
		pl.theme_type_variation = "Overline"
		stack.add_child(pl)
		for item in projects:
			var p: Dictionary = item
			var b := Button.new()
			b.theme_type_variation = "GhostButton"
			b.alignment = HORIZONTAL_ALIGNMENT_LEFT
			b.text = "%s  (%s)" % [p["name"], status_label(str(p["status"]))]
			var pid := str(p["id"])
			b.pressed.connect(func() -> void: show_card(pid))
			stack.add_child(b)
	var notes: Array = c.get("notes", [])
	if not notes.is_empty():
		var nl := Label.new()
		nl.text = I18n.t("NOTES")
		nl.theme_type_variation = "Overline"
		stack.add_child(nl)
		for item in notes.slice(0, 12):
			var n: Dictionary = item
			var b := Button.new()
			b.theme_type_variation = "GhostButton"
			b.alignment = HORIZONTAL_ALIGNMENT_LEFT
			b.text = "· " + str(n["title"])
			var nid := str(n["id"])
			b.pressed.connect(func() -> void: open_note.emit(nid))
			stack.add_child(b)


func _field(grid: GridContainer, key: String, label: String, placeholder: String, value: Variant) -> void:
	var e := LineEdit.new()
	e.placeholder_text = placeholder
	e.text = "" if value == null else str(value)
	_labelled(grid, label, e)
	_fields[key] = e


func _labelled(grid: GridContainer, label: String, control: Control) -> void:
	var l := Label.new()
	l.text = label
	l.theme_type_variation = "Muted"
	grid.add_child(l)
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	grid.add_child(control)


func save_card() -> bool:
	var payload := {}
	for key in _fields:
		var f: Variant = _fields[key]
		if f is LineEdit:
			payload[key] = (f as LineEdit).text.strip_edges()
		elif f is TextEdit:
			payload[key] = (f as TextEdit).text.strip_edges()
		elif f is OptionButton:
			var o := f as OptionButton
			payload[key] = str(o.get_item_metadata(o.selected))
	if str(payload.get("area_id", "x")) == "":
		payload.erase("area_id")
	if payload.has("due_date") and str(payload["due_date"]) == "":
		payload.erase("due_date")
	var res := await app.backend.api.call_api("/brain/spaces/" + showing_card, true, HTTPClient.METHOD_PATCH,
		JSON.stringify(payload))
	if not res["ok"]:
		app.audio.play("error")
		var d: Dictionary = res["data"]
		failed.emit(str(d.get("detail", res["error"])))
		return false
	app.audio.play("confirm")
	changed.emit()
	return true


## "Call the plumber @2026-11-20" -> task with a due date
func add_task(space_id: String, text: String) -> bool:
	var t := text.strip_edges()
	if t == "":
		return false
	var payload := {"title": t, "space_id": space_id}
	var m := RegEx.create_from_string("@(\\d{4}-\\d{2}-\\d{2})").search(t)
	if m != null:
		payload["due_date"] = m.get_string(1)
		payload["title"] = t.replace(m.get_string(0), "").strip_edges()
	var res := await app.backend.api.call_api("/brain/tasks", true, HTTPClient.METHOD_POST, JSON.stringify(payload))
	if not res["ok"]:
		app.audio.play("error")
		return false
	app.audio.play("note_create", 0.04)
	changed.emit()
	await show_card(space_id)
	return true
