extends AcceptDialog
## The timeline of changes (Loop MCP-B2): who changed what and when (the assistant, the archivist, an MCP client…),
## restore points, and « go back to this moment »: every change after it undone, for everyone or one author. An
## item edited since is left as it is and listed. Loaded by preload path (a new class can lag in Godot's class list).

signal changed

var app: SbApp
var author := ""
var entries: Array = []
var author_pick: OptionButton
var rows: VBoxContainer
var result_label: Label
var _authors: Array = []


func setup(a: SbApp) -> AcceptDialog:
	app = a
	name = "TimelineDialog"
	title = I18n.t("Timeline of changes")
	ok_button_text = I18n.t("Close")
	theme = app.theme
	add_theme_stylebox_override("panel", SbTheme.box(SbTheme.PANEL, 0, SbTheme.BORDER, 1, 18))
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(680, 460)
	box.add_theme_constant_override("separation", 8)
	add_child(box)
	var bar := HBoxContainer.new()
	bar.add_theme_constant_override("separation", 8)
	box.add_child(bar)
	author_pick = OptionButton.new()
	author_pick.name = "AuthorPick"
	author_pick.custom_minimum_size = Vector2(220, 0)
	author_pick.item_selected.connect(func(i: int) -> void:
		author = str(author_pick.get_item_metadata(i))
		refresh())
	bar.add_child(author_pick)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bar.add_child(spacer)
	var point := Button.new()
	point.name = "NewPoint"
	point.text = I18n.t("Make a restore point")
	point.tooltip_text = I18n.t("A moment to come back to, e.g. before a big clean-up")
	point.pressed.connect(func() -> void:
		await app.backend.api.call_api("/brain/timeline/points", true, HTTPClient.METHOD_POST,
			JSON.stringify({"name": I18n.t("Restore point")}))
		refresh())
	bar.add_child(point)
	result_label = Label.new()
	result_label.name = "Result"
	result_label.theme_type_variation = "Muted"
	result_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	result_label.visible = false
	box.add_child(result_label)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	box.add_child(scroll)
	rows = VBoxContainer.new()
	rows.name = "Rows"
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 4)
	scroll.add_child(rows)
	return self


func open() -> void:
	popup_centered_clamped(Vector2i(740, 600))
	await refresh()


static func who(a: String) -> String:
	if a == "assistant" or a == "":
		return I18n.t("You and the archivist")
	return a.trim_prefix("mcp:")


static func what(kind: String) -> String:
	return {"create_note": I18n.t("added"), "add_task": I18n.t("added a task"), "update_note": I18n.t("changed"),
		"classify": I18n.t("filed"), "link": I18n.t("linked"), "unlink": I18n.t("unlinked"), "set_fields": I18n.t("changed fields"),
		"remove_place": I18n.t("removed a place"), "to_checklist": I18n.t("added to a checklist"),
		"mission_saved": I18n.t("saved a mission"), "create_project": I18n.t("created a project"),
		"complete_task": I18n.t("completed a task"), "web_page": I18n.t("added a page")}.get(kind, kind)


func refresh() -> void:
	var res := await app.backend.api.call_api("/brain/timeline?author=" + author.uri_encode())
	if not res["ok"] or not is_inside_tree():
		return
	entries = (res["data"] as Dictionary).get("entries", [])
	_authors = (res["data"] as Dictionary).get("authors", [])
	author_pick.clear()
	author_pick.add_item(I18n.t("Everyone"))
	author_pick.set_item_metadata(0, "")
	for a in _authors:
		author_pick.add_item(who(str(a)))
		author_pick.set_item_metadata(author_pick.item_count - 1, str(a))
		if str(a) == author:
			author_pick.select(author_pick.item_count - 1)
	if author == "":
		author_pick.select(0)
	for c in rows.get_children():
		c.queue_free()
	for e in entries:
		var d: Dictionary = e
		var line := HBoxContainer.new()
		line.add_theme_constant_override("separation", 8)
		var l := Label.new()
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		l.clip_text = true
		l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		var at := str(d.get("at", "")).substr(5, 11).replace("T", " ")
		var b := Button.new()
		if str(d.get("type", "")) == "point":
			l.text = "◆ %s  %s" % [at, str(d.get("name", ""))]
			l.add_theme_color_override("font_color", SbTheme.WARM)
			b.text = I18n.t("Go back here")
			b.tooltip_text = I18n.t("Undo every change made after this point") + ("" if author == "" else " (" + who(author) + ")")
			var pid := str(d["id"])
			b.pressed.connect(func() -> void: _confirm({"point_id": pid, "author": author}, str(d.get("name", ""))))
		else:
			l.text = "%s  %s · %s « %s »%s" % [at, who(str(d.get("author", ""))), what(str(d.get("kind", ""))), str(d.get("title", "")),
				("  (" + I18n.t("undone") + ")") if bool(d.get("undone", false)) else ""]
			if bool(d.get("undone", false)):
				l.modulate = Color(1, 1, 1, 0.45)
			b.text = I18n.t("Undo from here")
			b.tooltip_text = I18n.t("Undo this change and every change after it") + ("" if author == "" else " (" + who(author) + ")")
			b.disabled = bool(d.get("undone", false))
			var aid := int(d["id"])
			b.pressed.connect(func() -> void: _confirm({"action_id": aid - 1, "author": author}, str(d.get("title", ""))))
		line.add_child(l)
		line.add_child(b)
		rows.add_child(line)


func _confirm(body: Dictionary, label: String) -> void:
	var dlg := ConfirmationDialog.new()
	dlg.theme = app.theme
	dlg.title = I18n.t("Go back to this moment?")
	dlg.dialog_text = I18n.t("Every change after « %s » is undone%s. Items created since go to the trash; an item you changed by hand since stays as it is.") % [
		label, "" if str(body.get("author", "")) == "" else " (" + who(str(body["author"])) + ")"]
	dlg.dialog_autowrap = true
	dlg.ok_button_text = I18n.t("Go back")
	dlg.confirmed.connect(func() -> void: await rewind(body))
	add_child(dlg)
	dlg.popup_centered(Vector2i(460, 180))


func rewind(body: Dictionary) -> Dictionary:
	var res := await app.backend.api.call_api("/brain/timeline/rewind", true, HTTPClient.METHOD_POST, JSON.stringify(body))
	if not res["ok"]:
		result_label.text = str((res["data"] as Dictionary).get("detail", res["error"]))
		result_label.visible = true
		return {}
	var d: Dictionary = res["data"]
	var conflicts: Array = d.get("conflicts", [])
	result_label.text = I18n.t("%d changes undone.") % int(d.get("undone", 0)) + ("" if conflicts.is_empty() else
		" " + I18n.t("%d left as they are (changed since): %s") % [conflicts.size(), str((conflicts[0] as Dictionary).get("why", ""))])
	result_label.visible = true
	changed.emit()
	await refresh()
	return d
