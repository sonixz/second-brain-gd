class_name CapturesView
extends PanelContainer
## "Captures": everything that came into the Brain, newest first, as the archivist
## understood it: what it is, where it was filed, its summary and themes, or the question
## it is waiting on. Click a card to open the item in the graph.

signal open_note(note_id: String)

var app: SbApp
var list: VBoxContainer
var title_label: Label
var context_label: Label
var items: Array = []


func setup(a: SbApp) -> CapturesView:
	app = a
	theme_type_variation = "Glass"
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)
	add_child(col)
	var head := HBoxContainer.new()
	col.add_child(head)
	var htext := VBoxContainer.new()
	htext.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(htext)
	var over := Label.new()
	over.text = "CAPTURES"
	over.theme_type_variation = "Overline"
	htext.add_child(over)
	title_label = Label.new()
	title_label.theme_type_variation = "Heading"
	title_label.text = "Everything you added"
	htext.add_child(title_label)
	context_label = Label.new()
	context_label.theme_type_variation = "Muted"
	context_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	head.add_child(context_label)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	col.add_child(scroll)
	list = VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.add_theme_constant_override("separation", 10)
	scroll.add_child(list)
	return self


func refresh() -> void:
	var res := await app.backend.api.call_api("/brain/feed?limit=80")
	var ctx := await app.backend.api.call_api("/brain/context")
	if not is_inside_tree():
		return
	if ctx["ok"]:
		var c: Variant = (ctx["data"] as Dictionary).get("context")
		context_label.text = ("Working on: %s" % str((c as Dictionary).get("name", ""))) if c is Dictionary else ""
	if not res["ok"]:
		return
	items = (res["data"] as Dictionary).get("items", [])
	for child in list.get_children():
		child.queue_free()
	title_label.text = "Everything you added (%d)" % items.size() if not items.is_empty() else "Nothing captured yet"
	if items.is_empty():
		var hint := Label.new()
		hint.theme_type_variation = "Muted"
		hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		hint.text = "Type, paste a link, drop a PDF, or hold F8 and speak: the archivist files it and it shows up here."
		list.add_child(hint)
		return
	for it in items:
		list.add_child(_card(it as Dictionary))


static func origin_label(it: Dictionary) -> String:
	match str(it.get("origin", "")):
		"url":
			return "Web page"
		"file":
			return "Document"
		"voice":
			return "Spoken"
		_:
			return "Typed"


func _card(it: Dictionary) -> Control:
	var card := PanelContainer.new()
	var filed := bool(it.get("filed", false))
	var edge := SbTheme.FOREST_LIGHT if filed else SbTheme.WARM
	card.add_theme_stylebox_override("panel", SbTheme.box(Color(SbTheme.PANEL_2, 0.85), 12, Color(edge, 0.45), 1, 12))
	card.mouse_filter = Control.MOUSE_FILTER_STOP
	card.mouse_default_cursor_shape = Control.CURSOR_POINTING_HAND
	var nid := str(it.get("id", ""))
	card.gui_input.connect(func(e: InputEvent) -> void:
		if e is InputEventMouseButton and (e as InputEventMouseButton).pressed \
				and (e as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
			open_note.emit(nid))
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 4)
	card.add_child(col)
	var top := HBoxContainer.new()
	col.add_child(top)
	var t := Label.new()
	t.text = str(it.get("title", ""))
	t.add_theme_font_size_override("font_size", 16)
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	t.clip_text = true
	top.add_child(t)
	var when := Label.new()
	when.theme_type_variation = "Muted"
	when.text = SbFormat.local_time(it.get("created_at", ""), true)
	top.add_child(when)
	var meta := Label.new()
	meta.theme_type_variation = "Muted"
	meta.text = "%s · %s · %s" % [str(it.get("place", "")), str(it.get("item_type", "note")).capitalize(), origin_label(it)]
	col.add_child(meta)
	var summary := str(it.get("summary", "")) if it.get("summary") != null else ""
	if summary != "":
		var s := Label.new()
		s.text = summary
		s.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		s.max_lines_visible = 3
		col.add_child(s)
	var themes: Array = it.get("themes", [])
	if not themes.is_empty():
		var row := HFlowContainer.new()
		row.add_theme_constant_override("h_separation", 6)
		col.add_child(row)
		for th in themes:
			var chip := Label.new()
			chip.text = "#" + str(th)
			chip.add_theme_color_override("font_color", SbTheme.MINT)
			row.add_child(chip)
	if not filed and it.get("question") != null:
		var q := Label.new()
		q.text = "Waiting: " + str(it.get("question"))
		q.add_theme_color_override("font_color", SbTheme.WARM)
		q.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		col.add_child(q)
	if it.get("origin_uri") != null and str(it.get("origin_uri")) != "":
		var u := Label.new()
		u.theme_type_variation = "Muted"
		u.text = str(it.get("origin_uri"))
		u.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		u.clip_text = true
		col.add_child(u)
	return card
