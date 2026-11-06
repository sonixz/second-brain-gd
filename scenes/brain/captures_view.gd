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
	over.text = I18n.t("CAPTURES")
	over.theme_type_variation = "Overline"
	htext.add_child(over)
	title_label = Label.new()
	title_label.theme_type_variation = "Heading"
	title_label.text = I18n.t("Everything you added")
	htext.add_child(title_label)
	context_label = Label.new()
	context_label.theme_type_variation = "Muted"
	context_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	head.add_child(context_label)
	var browser := Button.new()
	browser.text = I18n.t("Send from browser…")
	browser.tooltip_text = I18n.t("A bookmark that sends the page you are reading (or your selection) to the Brain")
	browser.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	browser.pressed.connect(show_bookmarklet)
	head.add_child(browser)
	# Packs moved to the engine room, Your data (Loop 30); a dropped .brain file and the voice still open them here.
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
		context_label.text = (I18n.t("Working on: %s") % str((c as Dictionary).get("name", ""))) if c is Dictionary else ""
	if not res["ok"]:
		return
	items = (res["data"] as Dictionary).get("items", [])
	for child in list.get_children():
		child.queue_free()
	title_label.text = I18n.t("Everything you added (%d)") % items.size() if not items.is_empty() else I18n.t("Nothing captured yet")
	if items.is_empty():
		var hint := Label.new()
		hint.theme_type_variation = "Muted"
		hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		hint.text = I18n.t("Type, paste a link, drop a PDF, or hold F8 and speak: the archivist files it and it shows up here.")
		list.add_child(hint)
		return
	for it in items:
		list.add_child(_card(it as Dictionary))


var bookmarklet := ""
var packs_dialog: PacksDialog
signal brain_changed


func open_packs() -> PacksDialog:
	packs_dialog = PacksDialog.new().setup(app)
	packs_dialog.changed.connect(func() -> void:
		brain_changed.emit()
		refresh())
	add_child(packs_dialog)
	packs_dialog.open()
	return packs_dialog


## The “Send to Brain” bookmark: copy it, then add it to the browser's bookmarks bar.
func show_bookmarklet() -> void:
	var res := await app.backend.api.call_api("/brain/capture-link")
	if not res["ok"] or not is_inside_tree():
		return
	bookmarklet = str((res["data"] as Dictionary).get("bookmarklet", ""))
	var dlg := AcceptDialog.new()
	dlg.title = I18n.t("Your browser and the Brain")
	dlg.theme = app.theme
	dlg.add_theme_stylebox_override("panel", SbTheme.box(SbTheme.PANEL, 0, SbTheme.BORDER, 1, 18))
	dlg.ok_button_text = I18n.t("Close")
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(620, 0)
	box.add_theme_constant_override("separation", 10)
	dlg.add_child(box)
	_extension_section(box)
	var sep := HSeparator.new()
	box.add_child(sep)
	var alt := Label.new()
	alt.text = I18n.t("WITHOUT THE EXTENSION: A BOOKMARK")
	alt.theme_type_variation = "Overline"
	box.add_child(alt)
	var how := Label.new()
	how.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	how.text = I18n.t("1. Copy the link below.\n2. In your browser, add a bookmark named “Send to Brain” and paste it as the address.\n3. On any page, click it: the page (or the text you selected) goes to the archivist, and a small window shows the receipt.\nThe Brain must be open. The link holds a capture key that can only add pages; you can renew it here.")
	box.add_child(how)
	var code := TextEdit.new()
	code.text = bookmarklet
	code.editable = false
	code.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	code.custom_minimum_size = Vector2(0, 90)
	box.add_child(code)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	box.add_child(row)
	var copy := Button.new()
	copy.text = I18n.t("Copy the link")
	copy.theme_type_variation = "PrimaryButton"
	copy.pressed.connect(func() -> void:
		DisplayServer.clipboard_set(bookmarklet)
		copy.text = I18n.t("Copied ✓"))
	row.add_child(copy)
	var renew := Button.new()
	renew.text = I18n.t("Renew the capture key")
	renew.theme_type_variation = "GhostButton"
	renew.pressed.connect(func() -> void:
		var r := await app.backend.api.call_api("/brain/capture-link/rotate", true, HTTPClient.METHOD_POST)
		if r["ok"]:
			bookmarklet = str((r["data"] as Dictionary).get("bookmarklet", ""))
			code.text = bookmarklet
			copy.text = I18n.t("Copy the link"))
	row.add_child(renew)
	add_child(dlg)
	dlg.popup_centered()
	dlg.confirmed.connect(dlg.queue_free)
	dlg.canceled.connect(dlg.queue_free)


## The browser extension (Edge, Chrome): status, pairing code, unpairing. The extension itself lives in
## browser-extension/ and is loaded once in the browser (Developer mode → Load unpacked).
var pair_code := ""


func _extension_section(box: VBoxContainer) -> void:
	var title := Label.new()
	title.text = I18n.t("BROWSER EXTENSION · EDGE, CHROME (RECOMMENDED)")
	title.theme_type_variation = "Overline"
	box.add_child(title)
	var state := Label.new()
	state.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(state)
	var steps := Label.new()
	steps.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	steps.theme_type_variation = "Muted"
	steps.text = I18n.t("Install it once: in the browser open edge://extensions (or chrome://extensions), turn on Developer mode, click “Load unpacked” and choose the folder browser-extension in the project. Then pair it: click below, and type the code in the extension (its icon in the toolbar). It talks only to this computer.")
	box.add_child(steps)
	var code_label := Label.new()
	code_label.add_theme_font_size_override("font_size", 30)
	code_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	code_label.visible = false
	box.add_child(code_label)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	box.add_child(row)
	var pair := Button.new()
	pair.text = I18n.t("Pair a browser")
	pair.theme_type_variation = "PrimaryButton"
	row.add_child(pair)
	var unpair := Button.new()
	unpair.text = I18n.t("Unpair all browsers")
	unpair.theme_type_variation = "GhostButton"
	row.add_child(unpair)
	var refresh_state := func() -> void:
		var r := await app.backend.api.call_api("/browser/status")
		if not r["ok"] or not is_instance_valid(state):
			return
		var d: Dictionary = r["data"]
		var paired: Array = d.get("paired", [])
		state.set_meta("connected", bool(d.get("connected", false)))
		if bool(d.get("connected", false)):
			state.text = (I18n.t("● Connected: %s (extension %s)") % [str(d.get("browser", "")), str(d.get("extension_version", ""))]
				+ ("" if bool(d.get("can_read_tabs", false)) else I18n.t(". Voice commands such as “add it” need “Also let the Brain read the pages it opens” in the extension.")))
		elif not paired.is_empty():
			state.text = I18n.t("○ Paired (%s), not connected right now. The extension reconnects by itself while the app is open.") % \
				", ".join(paired.map(func(x: Variant) -> String: return str((x as Dictionary).get("browser", I18n.t("browser")))))
		else:
			state.text = I18n.t("○ No browser paired yet.")
		unpair.visible = not paired.is_empty()
	refresh_state.call()
	pair.pressed.connect(func() -> void:
		var r := await app.backend.api.call_api("/browser/pair/start", true, HTTPClient.METHOD_POST)
		if not r["ok"]:
			code_label.text = I18n.t("Could not start pairing")
			code_label.visible = true
			return
		var d: Dictionary = r["data"]
		pair_code = str(d.get("code", ""))
		code_label.text = I18n.t("%s     port %d") % [pair_code, int(d.get("port", 8765))]
		code_label.visible = true
		pair.text = I18n.t("New code")
		steps.text = I18n.t("Type this code in the extension within 10 minutes (it works once). Then this window shows “Connected”.")
		for i in 60:  # watch for the extension for two minutes
			await get_tree().create_timer(2.0).timeout
			if not is_instance_valid(state):
				return
			await refresh_state.call()
			if bool(state.get_meta("connected", false)) and code_label.visible:  # keeps watching: the permission can come a moment later
				code_label.visible = false
				steps.text = I18n.t("Paired. On any page: the extension's icon → Send this page (or Alt+Shift+B). The Archivist can now open, add and close pages when you ask."))
	unpair.pressed.connect(func() -> void:
		await app.backend.api.call_api("/browser/pair", true, HTTPClient.METHOD_DELETE)
		refresh_state.call())


static func origin_label(it: Dictionary) -> String:
	match str(it.get("origin", "")):
		"url":
			return I18n.t("Web page")
		"file":
			return I18n.t("File")
		"voice":
			return I18n.t("Spoken")
		_:
			return I18n.t("Typed")


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
		q.text = I18n.t("Waiting: %s") % str(it.get("question"))
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
