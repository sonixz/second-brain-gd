extends AcceptDialog
## Import a folder (Loop 39): an Obsidian vault, linked notes or a Markdown folder comes in as a layer.
## The source is detected and said in the preview (« Obsidian vault detected »), never put forward elsewhere.
## Nothing enters before « Import »; afterwards the honest report: links resolved and the ones that point nowhere.
## Loaded by preload path (a new class can lag in Godot's class list on Windows).

signal imported(report: Dictionary)
signal add_documents(paths: Array)

var app: SbApp
var path := ""
var scan: Dictionary = {}
var report: Dictionary = {}
var detect_label: Label
var counts_label: Label
var notes_label: Label
var keep_check: CheckBox
var cost_label: Label
var result_label: RichTextLabel
var import_button: Button
var docs_button: Button
var _busy := false


func setup(a: SbApp, folder: String) -> AcceptDialog:
	app = a
	path = folder
	name = "FolderImportDialog"
	title = I18n.t("Import a folder")
	ok_button_text = I18n.t("Close")
	theme = app.theme  # a dialog is its own window: give it the app's colours
	add_theme_stylebox_override("panel", SbTheme.box(SbTheme.PANEL, 0, SbTheme.BORDER, 1, 18))
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(620, 0)
	box.add_theme_constant_override("separation", 10)
	add_child(box)
	var where := Label.new()
	where.theme_type_variation = "Muted"
	var home := OS.get_environment("USERPROFILE") if OS.get_environment("USERPROFILE") != "" else OS.get_environment("HOME")
	where.text = ("~" + folder.substr(home.length())) if home != "" and folder.begins_with(home) else folder
	where.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	where.clip_text = true
	box.add_child(where)
	detect_label = Label.new()
	detect_label.name = "Detected"
	detect_label.theme_type_variation = "Heading"
	detect_label.add_theme_font_size_override("font_size", 18)
	detect_label.text = I18n.t("Reading the folder…")
	box.add_child(detect_label)
	counts_label = Label.new()
	counts_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(counts_label)
	notes_label = Label.new()
	notes_label.theme_type_variation = "Muted"
	notes_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(notes_label)
	keep_check = CheckBox.new()
	keep_check.text = I18n.t("Keep your folders as places")
	keep_check.tooltip_text = I18n.t("Off: everything goes to the Inbox, for the archivist to file item by item")
	keep_check.button_pressed = true
	keep_check.toggled.connect(func(_on: bool) -> void: refresh())
	box.add_child(keep_check)
	cost_label = Label.new()
	cost_label.theme_type_variation = "Muted"
	cost_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(cost_label)
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_END
	row.add_theme_constant_override("separation", 8)
	box.add_child(row)
	docs_button = Button.new()
	docs_button.visible = false
	docs_button.pressed.connect(func() -> void:
		add_documents.emit(scan.get("document_paths", []))
		hide())
	row.add_child(docs_button)
	import_button = Button.new()
	import_button.name = "ImportButton"
	import_button.text = I18n.t("Import")
	import_button.theme_type_variation = "PrimaryButton"
	import_button.disabled = true
	import_button.pressed.connect(run_import)
	row.add_child(import_button)
	result_label = RichTextLabel.new()
	result_label.name = "ImportReport"
	result_label.bbcode_enabled = true
	result_label.fit_content = true
	result_label.custom_minimum_size = Vector2(600, 0)  # a known width, so the report wraps instead of growing tall
	result_label.selection_enabled = true
	result_label.visible = false
	box.add_child(result_label)
	return self


func open() -> void:
	popup_centered(Vector2i(680, 420))
	await refresh()


func _kind_line(kind: String, folder: String) -> String:
	match kind:
		"obsidian": return I18n.t("Obsidian vault detected: « %s »") % folder
		"logseq": return I18n.t("Logseq graph detected: « %s »") % folder
		"linked": return I18n.t("Linked notes: « %s »") % folder
		"markdown": return I18n.t("Markdown folder: « %s »") % folder
		"documents": return I18n.t("Folder of documents: « %s »") % folder
	return I18n.t("Nothing to import in « %s »") % folder


## The preview: detection, counts, what is left out, the cost. Nothing is imported here.
func refresh() -> void:
	if _busy:
		return
	_busy = true
	var res := await app.backend.api.call_api("/brain/import/scan", true, HTTPClient.METHOD_POST,
		JSON.stringify({"path": path, "keep_folders": keep_check.button_pressed}))
	_busy = false
	if not is_inside_tree():
		return
	if not res["ok"]:
		detect_label.text = I18n.t("This folder cannot be read: %s") % str(res.get("error", ""))
		import_button.disabled = true
		return
	scan = res["data"]
	var kind := str(scan.get("kind", ""))
	detect_label.text = _kind_line(kind, str(scan.get("name", "")))
	var n := int(scan.get("notes", 0))
	counts_label.text = I18n.t("%d notes · %d links · %d attachments · %d places · %d themes") % [n,
		int(scan.get("links", 0)), int(scan.get("attachments", 0)), int(scan.get("folders", 0)), int(scan.get("tags", 0))]
	var lines := PackedStringArray()
	if int(scan.get("unresolved", 0)) > 0:
		var names := PackedStringArray()
		for u in (scan.get("unresolved_list", []) as Array).slice(0, 5):
			names.append(str((u as Dictionary).get("target", "")))
		lines.append(I18n.t("%d links point to notes that do not exist yet (%s…): they stay as written.") % [int(scan["unresolved"]), ", ".join(names)])
	if int(scan.get("templates", 0)) > 0:
		lines.append(I18n.t("%d template notes are left out.") % int(scan["templates"]))
	if int(scan.get("embeds", 0)) > 0:
		lines.append(I18n.t("Pictures and files inside notes are not brought in yet (%d).") % int(scan["embeds"]))
	if bool(scan.get("inner", false)):
		lines.append(I18n.t("The vault is in a subfolder: that one is imported."))
	var again: Dictionary = scan["again"] if scan.get("again") is Dictionary else {}
	if not again.is_empty():
		lines.append(I18n.t("Already imported: %d new, %d changed, %d unchanged.") % [int(again.get("new", 0)), int(again.get("changed", 0)), int(again.get("same", 0))])
	notes_label.text = "\n".join(lines)
	notes_label.visible = not lines.is_empty()
	cost_label.text = I18n.t("Estimated cost: %s for the meaning of the notes; no AI call for the structure.") % _money(float(scan.get("cost_usd", 0)))
	var docs := int(scan.get("documents", 0))
	docs_button.visible = kind == "documents" and docs > 0
	docs_button.text = I18n.t("Add the %d documents") % docs
	keep_check.visible = n > 0
	cost_label.visible = n > 0
	import_button.disabled = n == 0
	import_button.text = I18n.t("Import again") if not again.is_empty() else I18n.t("Import")


static func _money(v: float) -> String:
	return "< 0.01 $" if v < 0.01 else "%.2f $" % v


## Imports, then shows the report and refreshes the Brain.
func run_import() -> void:
	if _busy or scan.is_empty():
		return
	_busy = true
	import_button.disabled = true
	import_button.text = I18n.t("Importing…")
	var res := await app.backend.api.call_api("/brain/import/run", true, HTTPClient.METHOD_POST,
		JSON.stringify({"path": path, "keep_folders": keep_check.button_pressed}))
	_busy = false
	if not is_inside_tree():
		return
	result_label.visible = true
	if not res["ok"]:
		result_label.text = I18n.t("The import failed: %s") % str(res.get("error", ""))
		import_button.disabled = false
		import_button.text = I18n.t("Import")
		return
	report = res["data"]
	var b := PackedStringArray()
	b.append("[b]" + I18n.t("Imported: %d new, %d updated, %d unchanged.") % [int(report.get("created", 0)), int(report.get("updated", 0)), int(report.get("unchanged", 0))] + "[/b]")
	b.append(I18n.t("%d of %d links found their note.") % [int(report.get("resolved", 0)), int(report.get("links", 0))])
	var un: Array = report.get("unresolved_list", [])
	if not un.is_empty():
		var names := PackedStringArray()
		for u in un.slice(0, 12):
			names.append(str((u as Dictionary).get("target", "")).replace("[", "[lb]"))
		b.append(I18n.t("Pointing nowhere: %s") % ", ".join(names) + ("…" if un.size() > 12 else ""))
	b.append(I18n.t("It is a layer: switch it off, merge it or remove it in Brain packs."))
	result_label.text = "\n".join(b)
	import_button.text = I18n.t("Done")
	await get_tree().process_frame
	reset_size()  # the report made it taller: fit it, centred again
	popup_centered()
	imported.emit(report)
