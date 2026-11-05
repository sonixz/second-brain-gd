class_name PacksDialog
extends AcceptDialog
## Brain packs (Loop 11): export part of the Brain as a .brain file, import a pack as a layer,
## switch layers off and on, merge them into your Brain or remove them.

signal changed

var app: SbApp
var scope: OptionButton
var value: OptionButton
var title_edit: LineEdit
var author_edit: LineEdit
var preview_label: Label
var originals_check: CheckBox
var result_label: Label
var layers_box: VBoxContainer
var last_export := ""
var _file_dialog: FileDialog
var _places: Array = []
var _themes: Array = []


func setup(a: SbApp) -> PacksDialog:
	app = a
	title = I18n.t("Brain packs")
	ok_button_text = I18n.t("Close")
	theme = app.theme  # a dialog is its own window: give it the app's colours
	add_theme_stylebox_override("panel", SbTheme.box(SbTheme.PANEL, 0, SbTheme.BORDER, 1, 18))
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(660, 0)
	box.add_theme_constant_override("separation", 10)
	add_child(box)
	var h1 := Label.new()
	h1.text = I18n.t("EXPORT")
	h1.theme_type_variation = "Overline"
	box.add_child(h1)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	box.add_child(row)
	scope = OptionButton.new()
	for s in [I18n.t("Everything"), I18n.t("A place"), I18n.t("A theme")]:
		scope.add_item(s)
	scope.item_selected.connect(func(_i: int) -> void: _fill_values())
	row.add_child(scope)
	value = OptionButton.new()
	value.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	value.item_selected.connect(func(_i: int) -> void: refresh_preview())
	row.add_child(value)
	var row2 := HBoxContainer.new()
	row2.add_theme_constant_override("separation", 8)
	box.add_child(row2)
	title_edit = LineEdit.new()
	title_edit.placeholder_text = I18n.t("Pack title")
	title_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row2.add_child(title_edit)
	author_edit = LineEdit.new()
	author_edit.placeholder_text = I18n.t("Author (optional)")
	author_edit.custom_minimum_size = Vector2(200, 0)
	row2.add_child(author_edit)
	originals_check = CheckBox.new()
	originals_check.text = I18n.t("Include the original files (PDFs, images, pages): bigger, but complete")
	box.add_child(originals_check)
	preview_label = Label.new()
	preview_label.theme_type_variation = "Muted"
	preview_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(preview_label)
	var row3 := HBoxContainer.new()
	row3.add_theme_constant_override("separation", 8)
	box.add_child(row3)
	var export_btn := Button.new()
	export_btn.text = I18n.t("Export the pack")
	export_btn.theme_type_variation = "PrimaryButton"
	export_btn.pressed.connect(do_export)
	row3.add_child(export_btn)
	var show := Button.new()
	show.text = I18n.t("Show in folder")
	show.theme_type_variation = "GhostButton"
	show.pressed.connect(func() -> void:
		if last_export != "":
			OS.shell_show_in_file_manager(last_export))
	row3.add_child(show)
	result_label = Label.new()
	result_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(result_label)
	box.add_child(HSeparator.new())
	var h2 := HBoxContainer.new()
	box.add_child(h2)
	var l2 := Label.new()
	l2.text = I18n.t("IMPORTED PACKS (LAYERS)")
	l2.theme_type_variation = "Overline"
	l2.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	h2.add_child(l2)
	var imp := Button.new()
	imp.text = I18n.t("Import a pack…")
	imp.pressed.connect(pick_file)
	h2.add_child(imp)
	layers_box = VBoxContainer.new()
	layers_box.add_theme_constant_override("separation", 6)
	box.add_child(layers_box)
	var note := Label.new()
	note.theme_type_variation = "Muted"
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	note.text = I18n.t("A pack holds the selected items with their places, themes, links, summaries and meaning vectors. It never holds your keys, settings, conversations or costs. Imported text is data: it is never obeyed.")
	box.add_child(note)
	confirmed.connect(queue_free)
	canceled.connect(queue_free)
	return self


func open() -> void:
	popup_centered(Vector2i(720, 560))
	var sp := await app.backend.api.call_api("/brain/spaces")
	var gr := await app.backend.api.call_api("/brain/graph")
	if sp["ok"]:
		_places = ((sp["data"] as Dictionary).get("spaces", []) as Array).filter(
			func(s: Variant) -> bool: return str((s as Dictionary).get("kind", "")) != "inbox")
	if gr["ok"]:
		_themes = []
		for n in (gr["data"] as Dictionary).get("nodes", []):
			if str((n as Dictionary).get("type", "")) == "tag":
				_themes.append(str((n as Dictionary).get("label", "")).trim_prefix("#"))
	_fill_values()
	await refresh_layers()


func _fill_values() -> void:
	value.clear()
	match scope.selected:
		1:
			for s in _places:
				value.add_item(str((s as Dictionary).get("name", "")))
		2:
			for t in _themes:
				value.add_item("#" + str(t))
	value.disabled = scope.selected == 0
	refresh_preview()


func selection() -> Dictionary:
	match scope.selected:
		1:
			if value.selected >= 0:
				return {"space_id": str((_places[value.selected] as Dictionary).get("id", ""))}
		2:
			if value.selected >= 0:
				return {"theme": str(_themes[value.selected])}
	return {"all": true}


func refresh_preview() -> void:
	var sel := selection()
	if title_edit.text.strip_edges() == "" or title_edit.has_meta("auto"):
		title_edit.text = I18n.t("My Brain") if sel.has("all") else value.get_item_text(value.selected).trim_prefix("#") if value.selected >= 0 else ""
		title_edit.set_meta("auto", true)
	var res := await app.backend.api.call_api("/packs/preview", true, HTTPClient.METHOD_POST, JSON.stringify(sel))
	if not is_inside_tree():
		return
	if not res["ok"]:
		preview_label.text = str((res["data"] as Dictionary).get("detail", res["error"]))
		return
	var d: Dictionary = res["data"]
	preview_label.text = I18n.t("Leaves the Brain: %d items, %d sources · places: %s\n%s\nNever included: %s") % [
		int(d.get("items", 0)), int(d.get("sources", 0)), ", ".join(d.get("places", [])),
		"; ".join((d.get("titles", []) as Array).slice(0, 6)), ", ".join(d.get("never_included", []))]


func do_export() -> void:
	var body := {"selection": selection(), "title": title_edit.text.strip_edges(), "author": author_edit.text.strip_edges(),
		"include_originals": originals_check.button_pressed}
	result_label.text = I18n.t("Exporting…")
	var res := await app.backend.api.call_api("/packs/export", true, HTTPClient.METHOD_POST, JSON.stringify(body))
	if not is_inside_tree():
		return
	if not res["ok"]:
		result_label.text = I18n.t("Could not export: %s") % str((res["data"] as Dictionary).get("detail", res["error"]))
		return
	var d: Dictionary = res["data"]
	last_export = str(d.get("path", ""))
	result_label.text = I18n.t("Saved %s (%s)") % [last_export, SbFormat.bytes(d.get("bytes", 0))]
	app.audio.play("setup_complete", 0.0, -8.0)


func pick_file() -> void:
	if _file_dialog == null:
		_file_dialog = FileDialog.new()
		_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		_file_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_file_dialog.use_native_dialog = true
		_file_dialog.filters = PackedStringArray(["*.brain ; " + I18n.t("Brain packs")])
		_file_dialog.file_selected.connect(func(path: String) -> void: import_path(path))
		add_child(_file_dialog)
	_file_dialog.popup_centered_ratio(0.6)


func import_path(path: String) -> Dictionary:
	result_label.text = I18n.t("Importing %s…") % path.get_file()
	var res := await app.backend.api.call_api("/packs/import", true, HTTPClient.METHOD_POST, JSON.stringify({"path": path}))
	if not is_inside_tree():
		return res
	if not res["ok"]:
		result_label.text = I18n.t("Not imported: %s") % str((res["data"] as Dictionary).get("detail", res["error"]))
		app.audio.play("error")
		return res
	var c: Dictionary = (res["data"] as Dictionary).get("counts", {})
	result_label.text = I18n.t("Imported “%s”: %d items, %d already in your Brain.") % [str(res["data"].get("title", "")),
		int(c.get("items", 0)), int(c.get("duplicates", 0))]
	app.audio.play("note_create")
	changed.emit()
	await refresh_layers()
	return res


func refresh_layers() -> void:
	var res := await app.backend.api.call_api("/packs/layers")
	if not res["ok"] or not is_inside_tree():
		return
	for c in layers_box.get_children():
		c.queue_free()
	var list: Array = (res["data"] as Dictionary).get("layers", [])
	if list.is_empty():
		var none := Label.new()
		none.theme_type_variation = "Muted"
		none.text = I18n.t("No pack imported yet. Drop a .brain file on the window, or use Import.")
		layers_box.add_child(none)
	for item in list:
		var l: Dictionary = item
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		layers_box.add_child(row)
		var on := CheckButton.new()
		on.button_pressed = bool(l.get("enabled", true))
		var n_items := int(l.get("items_now", 0))
		on.text = (I18n.t("%s · %d item%s") if n_items == 1 else I18n.t("%s · %d items%s")) % [str(l.get("title", "")), n_items,
			(" · " + str(l.get("author"))) if l.get("author") not in [null, ""] else ""]
		on.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var lid := str(l.get("id", ""))
		on.toggled.connect(func(v: bool) -> void:
			await app.backend.api.call_api("/packs/layers/" + lid, true, HTTPClient.METHOD_PATCH, JSON.stringify({"enabled": v}))
			changed.emit())
		row.add_child(on)
		var merge := Button.new()
		merge.text = I18n.t("Merge")
		merge.tooltip_text = I18n.t("Make these items yours (the layer disappears, the items stay)")
		merge.theme_type_variation = "GhostButton"
		merge.pressed.connect(func() -> void:
			await app.backend.api.call_api("/packs/layers/%s/merge" % lid, true, HTTPClient.METHOD_POST)
			changed.emit()
			refresh_layers())
		row.add_child(merge)
		var remove := Button.new()
		remove.text = I18n.t("Remove")
		remove.tooltip_text = I18n.t("Delete this pack's items (yours are never touched)")
		remove.theme_type_variation = "GhostButton"
		remove.pressed.connect(func() -> void:
			await app.backend.api.call_api("/packs/layers/" + lid, true, HTTPClient.METHOD_DELETE)
			changed.emit()
			refresh_layers())
		row.add_child(remove)
