extends PanelContainer
## The table view (Loop 37C): the same items as the graph, in rows and columns. Choose a type (a recipe's fields
## become columns) or every item; sort by a column, search, edit a cell in place, save the view. Tick recipes and
## « Grocery list » adds their ingredients up by aisle. Loaded by preload path (a new class can lag in Godot's
## class list on Windows).

signal open_note(note_id: String)
signal changed
signal failed(message: String)

var app: SbApp
var type_pick: OptionButton
var search: LineEdit
var views_pick: OptionButton
var tree: Tree
var count_label: Label
var grocery_button: Button
var data: Dictionary = {}
var type_id := ""
var sort_key := ""
var sort_desc := false
var picked: Dictionary = {}       # note id -> true (recipes ticked for the grocery list)
var _types: Array = []
var _cols: Array = []
var _filling := false
var grocery_dialog: AcceptDialog  # the open grocery list (tests)


func setup(a: SbApp) -> PanelContainer:
	app = a
	theme_type_variation = "Glass"
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	add_child(box)
	var bar := HBoxContainer.new()
	bar.add_theme_constant_override("separation", 8)
	box.add_child(bar)
	type_pick = OptionButton.new()
	type_pick.name = "TypePick"
	type_pick.custom_minimum_size = Vector2(150, 0)
	type_pick.clip_text = true
	type_pick.item_selected.connect(func(i: int) -> void:
		type_id = str(type_pick.get_item_metadata(i))
		sort_key = ""
		picked.clear()
		refresh())
	bar.add_child(type_pick)
	search = LineEdit.new()
	search.name = "TableSearch"
	search.placeholder_text = I18n.t("Search the rows (title, fields, ingredients)…")
	search.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	search.custom_minimum_size = Vector2(160, 0)
	search.text_changed.connect(func(_t: String) -> void: _debounce())
	bar.add_child(search)
	views_pick = OptionButton.new()
	views_pick.name = "ViewsPick"
	views_pick.custom_minimum_size = Vector2(120, 0)
	views_pick.fit_to_longest_item = false
	views_pick.clip_text = true
	views_pick.item_selected.connect(_on_view_picked)
	bar.add_child(views_pick)
	var save := Button.new()
	save.text = "+"
	save.custom_minimum_size = Vector2(40, 0)
	save.tooltip_text = I18n.t("Save the view") + " — " + I18n.t("Keep this type, search and sort under a name")
	save.pressed.connect(_ask_view_name)
	bar.add_child(save)
	var csv := Button.new()
	csv.text = "CSV"
	csv.tooltip_text = I18n.t("Save these rows as a CSV file (Excel)")
	csv.pressed.connect(_export_csv)
	bar.add_child(csv)
	tree = Tree.new()
	tree.name = "Rows"
	tree.size_flags_vertical = Control.SIZE_EXPAND_FILL
	tree.hide_root = true
	tree.column_titles_visible = true
	tree.select_mode = Tree.SELECT_ROW
	tree.column_title_clicked.connect(func(col: int, _button: int) -> void: sort_by(col))
	tree.item_edited.connect(_on_edited)
	tree.item_activated.connect(func() -> void:
		var it := tree.get_selected()
		if it != null:
			open_note.emit(str(it.get_metadata(0))))
	box.add_child(tree)
	var foot := HBoxContainer.new()
	foot.add_theme_constant_override("separation", 10)
	box.add_child(foot)
	count_label = Label.new()
	count_label.theme_type_variation = "Muted"
	count_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	foot.add_child(count_label)
	grocery_button = Button.new()
	grocery_button.name = "GroceryButton"
	grocery_button.theme_type_variation = "PrimaryButton"
	grocery_button.visible = false
	grocery_button.pressed.connect(open_grocery)
	foot.add_child(grocery_button)
	return self


var _debounce_at := 0


func _debounce() -> void:
	_debounce_at += 1
	var mine := _debounce_at
	await get_tree().create_timer(0.3).timeout
	if mine == _debounce_at and is_inside_tree():
		refresh()


func _label(def: Dictionary) -> String:
	return str(def.get("fr" if I18n.lang == "fr" else "en", def.get("key", "")))


## Rows from the engine, then the tree. The type list comes along so the picker shows counts.
func refresh() -> void:
	var tr := await app.backend.api.call_api("/brain/types")
	if tr["ok"]:
		_types = (tr["data"] as Dictionary).get("types", [])
	var q := "?type=%s&q=%s" % [type_id.uri_encode(), search.text.strip_edges().uri_encode()]
	var res := await app.backend.api.call_api("/brain/table" + q)
	if not is_inside_tree():
		return
	if not res["ok"]:
		failed.emit(str((res["data"] as Dictionary).get("detail", res["error"])))
		return
	data = res["data"]
	_fill_types()
	_fill_views()
	_fill_tree()


func _fill_types() -> void:
	type_pick.clear()
	type_pick.add_item(I18n.t("Every item"))
	type_pick.set_item_metadata(0, "")
	for t in _types:
		var d: Dictionary = t
		type_pick.add_item("%s (%d)" % [_label({"fr": d.get("fr"), "en": d.get("en")}), int(d.get("count", 0))])
		type_pick.set_item_metadata(type_pick.item_count - 1, str(d["id"]))
		if str(d["id"]) == type_id:
			type_pick.select(type_pick.item_count - 1)
	if type_id == "":
		type_pick.select(0)


func _fill_views() -> void:
	views_pick.clear()
	views_pick.add_item(I18n.t("Saved views"))
	views_pick.set_item_metadata(0, {})
	for v in data.get("views", []):
		views_pick.add_item(str((v as Dictionary).get("name", "")))
		views_pick.set_item_metadata(views_pick.item_count - 1, v)
	views_pick.select(0)


func _on_view_picked(i: int) -> void:
	var v: Dictionary = views_pick.get_item_metadata(i)
	if v.is_empty():
		return
	type_id = str(v.get("type", ""))
	search.text = str(v.get("query", ""))
	sort_key = str(v.get("sort", ""))
	sort_desc = bool(v.get("desc", false))
	picked.clear()
	await refresh()


func show_view(name: String) -> bool:
	for v in data.get("views", []):
		if str((v as Dictionary).get("name", "")).to_lower() == name.to_lower():
			type_id = str(v.get("type", ""))
			search.text = str(v.get("query", ""))
			sort_key = str(v.get("sort", ""))
			sort_desc = bool(v.get("desc", false))
			await refresh()
			return true
	return false


func _recipes_mode() -> bool:
	var t: Variant = data.get("type")
	return t is Dictionary and str((t as Dictionary).get("id", "")) == "recipe"


## The tree: a tick column for recipes, then one column per field. Values are shown as people read them.
func _fill_tree() -> void:
	_filling = true
	tree.clear()
	_cols = data.get("columns", [])
	var tick := 1 if _recipes_mode() else 0
	tree.columns = _cols.size() + tick
	if tick == 1:
		tree.set_column_title(0, "☐")
		tree.set_column_expand(0, false)
		tree.set_column_custom_minimum_width(0, 40)
	for c in _cols.size():
		var def: Dictionary = _cols[c]
		var arrow := ("  ▼" if sort_desc else "  ▲") if str(def["key"]) == sort_key else ""
		tree.set_column_title(c + tick, _label(def) + arrow)
		tree.set_column_expand(c + tick, str(def["key"]) == "title")
		tree.set_column_custom_minimum_width(c + tick, 200 if str(def["key"]) == "title" else 84)
	var root := tree.create_item()
	var rows: Array = (data.get("rows", []) as Array).duplicate()
	if sort_key != "":
		rows.sort_custom(func(a: Variant, b: Variant) -> bool:
			var va: Variant = (a as Dictionary).get(sort_key)
			var vb: Variant = (b as Dictionary).get(sort_key)
			if va == null:
				return false
			if vb == null:
				return true
			var lt: bool = (str(va).to_lower() < str(vb).to_lower()) if (va is String or vb is String) else float(va) < float(vb)
			return (not lt) if sort_desc else lt)
	for r in rows:
		var row: Dictionary = r
		var it := tree.create_item(root)
		it.set_metadata(0, str(row["id"]))
		if tick == 1:
			it.set_cell_mode(0, TreeItem.CELL_MODE_CHECK)
			it.set_editable(0, int(row.get("_ingredients", 0)) > 0)
			it.set_checked(0, picked.has(str(row["id"])))
			it.set_tooltip_text(0, I18n.t("Tick for the grocery list") if int(row.get("_ingredients", 0)) > 0 else I18n.t("No ingredients on this recipe"))
		for c in _cols.size():
			var def: Dictionary = _cols[c]
			var col := c + tick
			var key := str(def["key"])
			var kind := str(def.get("kind", "text"))
			var v: Variant = row.get(key)
			if kind == "checkbox":
				it.set_cell_mode(col, TreeItem.CELL_MODE_CHECK)
				it.set_checked(col, bool(v) if v != null else false)
				it.set_editable(col, true)
				continue
			it.set_text(col, show_value(def, v))
			it.set_editable(col, data.get("type") is Dictionary and key not in ["title", "place", "created_at"] and kind in ["text", "number", "minutes", "rating", "choice", "date", "url"])
	count_label.text = I18n.t("%d rows") % rows.size()
	_filling = false
	_update_grocery_button()


static func show_value(def: Dictionary, v: Variant) -> String:
	if v == null:
		return ""
	match str(def.get("kind", "text")):
		"minutes":
			var m := int(float(v))
			return ("%d h %02d" % [m / 60, m % 60]) if m >= 60 else "%d min" % m
		"rating":
			return "★ %s" % str(snappedf(float(v), 0.1)).replace(".", "," if I18n.lang == "fr" else ".")
		"number":
			var f := float(v)
			return str(int(f)) if f == int(f) else str(f)
		"date":
			return str(v).left(10)
		"list":
			return ", ".join(PackedStringArray(v as Array)) if v is Array else str(v)
	if str(def.get("key", "")) == "item_type":
		return {"recipe": I18n.t("Recipe"), "note": I18n.t("Note"), "idea": I18n.t("Idea"), "task": I18n.t("Task"),
			"reference": I18n.t("Reference"), "article": I18n.t("Article"), "document": I18n.t("Document")}.get(str(v), str(v))
	return str(v)


func sort_by(col: int) -> void:
	var tick := 1 if _recipes_mode() else 0
	if col < tick:
		return
	var key := str((_cols[col - tick] as Dictionary)["key"])
	sort_desc = (not sort_desc) if key == sort_key else false
	sort_key = key
	_fill_tree()


## A cell edited in place: a tick for the grocery list, or a field saved to the item (its text follows).
func _on_edited() -> void:
	if _filling:
		return
	var it := tree.get_edited()
	var col := tree.get_edited_column()
	var nid := str(it.get_metadata(0))
	var tick := 1 if _recipes_mode() else 0
	if tick == 1 and col == 0:
		if it.is_checked(0):
			picked[nid] = true
		else:
			picked.erase(nid)
		_update_grocery_button()
		return
	var def: Dictionary = _cols[col - tick]
	var value: Variant = it.is_checked(col) if str(def.get("kind", "")) == "checkbox" else it.get_text(col).replace("★", "").replace(" min", "").strip_edges()
	if str(def.get("kind", "")) == "minutes" and str(value).contains("h"):
		var parts := str(value).split("h")
		value = int(parts[0].strip_edges()) * 60 + int(parts[1].strip_edges() if parts.size() > 1 and parts[1].strip_edges() != "" else "0")
	var t: Dictionary = data["type"]
	var res := await app.backend.api.call_api("/brain/items/%s/props" % nid, true, HTTPClient.METHOD_POST,
		JSON.stringify({"type": str(t["id"]), "props": {str(def["key"]): value}}))
	if not res["ok"]:
		failed.emit(str((res["data"] as Dictionary).get("detail", res["error"])))
	changed.emit()
	await refresh()


func _update_grocery_button() -> void:
	grocery_button.visible = _recipes_mode()
	grocery_button.disabled = picked.is_empty()
	grocery_button.text = I18n.t("Grocery list (%d)") % picked.size() if not picked.is_empty() else I18n.t("Tick recipes for a grocery list")


func _ask_view_name() -> void:
	var dlg := ConfirmationDialog.new()
	dlg.title = I18n.t("Save the view")
	dlg.theme = app.theme
	var edit := LineEdit.new()
	edit.placeholder_text = I18n.t("Name, e.g. Quick recipes")
	edit.custom_minimum_size = Vector2(320, 0)
	dlg.add_child(edit)
	dlg.register_text_enter(edit)
	dlg.confirmed.connect(func() -> void:
		if edit.text.strip_edges() == "":
			return
		await app.backend.api.call_api("/brain/table/views", true, HTTPClient.METHOD_POST, JSON.stringify(
			{"name": edit.text.strip_edges(), "type": type_id, "query": search.text.strip_edges(), "sort": sort_key, "desc": sort_desc}))
		await refresh())
	add_child(dlg)
	dlg.popup_centered(Vector2i(380, 120))
	edit.grab_focus()


func csv_text() -> String:
	var lines := PackedStringArray()
	var head := PackedStringArray()
	for def in _cols:
		head.append(_quote(_label(def)))
	lines.append(",".join(head))
	for r in data.get("rows", []):
		var cells := PackedStringArray()
		for def in _cols:
			cells.append(_quote(show_value(def, (r as Dictionary).get(str((def as Dictionary)["key"])))))
		lines.append(",".join(cells))
	return "\n".join(lines) + "\n"


static func _quote(s: String) -> String:
	return "\"" + s.replace("\"", "\"\"") + "\""


func _export_csv() -> void:
	var fd := FileDialog.new()
	fd.file_mode = FileDialog.FILE_MODE_SAVE_FILE
	fd.access = FileDialog.ACCESS_FILESYSTEM
	fd.use_native_dialog = true
	fd.filters = PackedStringArray(["*.csv ; CSV"])
	fd.current_file = ("table" if type_id == "" else type_id) + ".csv"
	fd.file_selected.connect(func(path: String) -> void:
		var f := FileAccess.open(path, FileAccess.WRITE)
		if f == null:
			failed.emit(I18n.t("Could not write %s") % path)
			return
		f.store_buffer(PackedByteArray([0xEF, 0xBB, 0xBF]))  # Excel reads the accents right with a BOM
		f.store_string(csv_text())
		f.close()
		failed.emit(I18n.t("Saved: %s") % path.get_file()))
	add_child(fd)
	fd.popup_centered_ratio(0.6)


## The grocery list: the ticked recipes, their servings (changeable), the ingredients added up by aisle.
func open_grocery() -> AcceptDialog:
	if grocery_dialog != null and is_instance_valid(grocery_dialog):
		grocery_dialog.queue_free()
	var dlg := AcceptDialog.new()
	grocery_dialog = dlg
	dlg.name = "GroceryDialog"
	dlg.title = I18n.t("Grocery list")
	dlg.theme = app.theme
	dlg.add_theme_stylebox_override("panel", SbTheme.box(SbTheme.PANEL, 0, SbTheme.BORDER, 1, 18))
	dlg.ok_button_text = I18n.t("Close")
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(600, 0)
	box.add_theme_constant_override("separation", 8)
	dlg.add_child(box)
	var servings_box := VBoxContainer.new()
	box.add_child(servings_box)
	var list := RichTextLabel.new()
	list.name = "GroceryList"
	list.bbcode_enabled = true
	list.fit_content = true
	list.custom_minimum_size = Vector2(580, 0)
	list.selection_enabled = true
	box.add_child(list)
	var save := Button.new()
	save.name = "SaveGrocery"
	save.text = I18n.t("Save the list")
	save.tooltip_text = I18n.t("A note linked to the recipes, and the lines added to your « Épicerie » checklist")
	save.theme_type_variation = "PrimaryButton"
	box.add_child(save)
	var servings: Dictionary = {}
	for r in data.get("rows", []):
		var row: Dictionary = r
		if not picked.has(str(row["id"])):
			continue
		var line := HBoxContainer.new()
		var name_l := Label.new()
		name_l.text = str(row["title"])
		name_l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		line.add_child(name_l)
		var spin := SpinBox.new()
		spin.min_value = 1
		spin.max_value = 40
		spin.value = float(row.get("servings", 4)) if row.get("servings") != null else 4.0
		spin.suffix = I18n.t("servings")
		spin.custom_minimum_size = Vector2(150, 0)
		servings[str(row["id"])] = spin
		line.add_child(spin)
		servings_box.add_child(line)
	var picks := func() -> Array:
		var out: Array = []
		for id in servings:
			out.append({"id": id, "servings": (servings[id] as SpinBox).value})
		return out
	var redo := func() -> void:
		var res := await app.backend.api.call_api("/brain/grocery", true, HTTPClient.METHOD_POST, JSON.stringify({"picks": picks.call()}))
		if res["ok"] and is_instance_valid(list):
			list.text = grocery_text(res["data"])
	for id in servings:
		(servings[id] as SpinBox).value_changed.connect(func(_v: float) -> void: redo.call())
	save.pressed.connect(func() -> void:
		save.disabled = true
		var res := await app.backend.api.call_api("/brain/grocery", true, HTTPClient.METHOD_POST,
			JSON.stringify({"picks": picks.call(), "save": true}))
		if res["ok"]:
			var d: Dictionary = res["data"]
			save.text = I18n.t("Saved: « %s »") % str(d.get("title", "")) + ((" · " + I18n.t("added to %s") % str(d["checklist"])) if d.get("checklist") != null else "")
			changed.emit()
		else:
			save.disabled = false
			failed.emit(str((res["data"] as Dictionary).get("detail", res["error"]))))
	add_child(dlg)
	dlg.popup_centered_clamped(Vector2i(660, 520))
	redo.call()
	return dlg


static func grocery_text(g: Dictionary) -> String:
	var b := PackedStringArray()
	for grp in g.get("groups", []):
		var d: Dictionary = grp
		b.append("[b]%s[/b]" % str(d.get("name", "")))
		for i in d.get("items", []):
			var it: Dictionary = i
			var from := ", ".join(PackedStringArray(it.get("recipes", [])))
			b.append("  ☐ %s — %s  [color=#%s]%s[/color]" % [str(it.get("name", "")).replace("[", "[lb]"), str(it.get("display", "")),
				SbTheme.MUTED.to_html(false), from.replace("[", "[lb]")])
	return "\n".join(b)
