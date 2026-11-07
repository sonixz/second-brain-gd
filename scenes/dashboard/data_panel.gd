class_name DataPanel
extends PanelContainer
## Your data (Loop 30), in the engine room: backups (status, back up now, where, how often, restore), one file to
## move to another computer, packs, repair the installation, start fresh, uninstall.
## Erasing or replacing anything asks the user to type a word, and the engine takes a verified backup first
## (engine/backups.py). Nothing here can be done by voice except backing up.

var app: SbApp
var state_label: Label
var warn_label: Label
var where_label: LineEdit
var freq: OptionButton
var list_box: VBoxContainer
var result_label: Label
var backup_button: Button
var last: Dictionary = {}
var _busy := false
var _dir_dialog: FileDialog
var _file_dialog: FileDialog

const FREQUENCIES := [0, 6, 12, 24, 72, 168]  # hours; 0 = off


func setup(a: SbApp) -> DataPanel:
	app = a
	return self


func _ready() -> void:
	theme_type_variation = "Card"
	name = "DataPanel"
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	add_child(col)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 10)
	col.add_child(head)
	var t := VBoxContainer.new()
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t.add_theme_constant_override("separation", 0)
	head.add_child(t)
	var title := Label.new()
	title.text = I18n.t("Your data")
	title.theme_type_variation = "Heading"
	title.add_theme_font_size_override("font_size", 16)
	t.add_child(title)
	state_label = Label.new()
	state_label.theme_type_variation = "Muted"
	state_label.text = I18n.t("Loading…")
	t.add_child(state_label)
	backup_button = Button.new()
	backup_button.text = I18n.t("Back up now")
	backup_button.theme_type_variation = "PrimaryButton"
	backup_button.pressed.connect(back_up_now)
	head.add_child(backup_button)

	warn_label = Label.new()
	warn_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	warn_label.add_theme_color_override("font_color", SbTheme.WARM)
	warn_label.visible = false
	col.add_child(warn_label)

	var where_row := HBoxContainer.new()
	where_row.add_theme_constant_override("separation", 10)
	col.add_child(where_row)
	var wl := Label.new()
	wl.text = I18n.t("Backups go to")
	wl.theme_type_variation = "Muted"
	where_row.add_child(wl)
	where_label = LineEdit.new()  # read-only, but the path can be selected and copied
	where_label.editable = false
	where_label.selecting_enabled = true
	where_label.add_theme_color_override("font_uneditable_color", SbTheme.TEXT)
	where_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	where_row.add_child(where_label)
	var open_dir := Button.new()
	open_dir.text = I18n.t("Open folder")
	open_dir.tooltip_text = I18n.t("Show the backups folder in your file manager")
	open_dir.pressed.connect(open_backups_folder)
	where_row.add_child(open_dir)
	var choose := Button.new()
	choose.text = I18n.t("Choose…")
	choose.tooltip_text = I18n.t("Another disk, a USB key or a synced folder (OneDrive): they survive a disk failure")
	choose.pressed.connect(_choose_destination)
	where_row.add_child(choose)
	var fl := Label.new()
	fl.text = I18n.t("Automatic")
	fl.theme_type_variation = "Muted"
	where_row.add_child(fl)
	freq = OptionButton.new()
	for h in FREQUENCIES:
		freq.add_item(frequency_label(h))
	freq.item_selected.connect(_frequency_chosen)
	where_row.add_child(freq)

	list_box = VBoxContainer.new()
	list_box.add_theme_constant_override("separation", 4)
	col.add_child(list_box)

	var actions := HFlowContainer.new()
	actions.add_theme_constant_override("h_separation", 8)
	actions.add_theme_constant_override("v_separation", 8)
	col.add_child(actions)
	for spec in [
			[I18n.t("Export everything…"), I18n.t("One file with your whole Brain, to move it to another computer"), _export],
			[I18n.t("Import a backup file…"), I18n.t("A file exported on another computer: it is checked, then you choose to restore it"), _pick_import],
			[I18n.t("Packs…"), I18n.t("Share a project as a .brain file, or bring in someone's pack as a layer"), _open_packs],
			[I18n.t("Repair the installation…"), I18n.t("Reinstalls the engine's Python environment; your data is not touched"), _repair]]:
		var b := Button.new()
		b.text = spec[0]
		b.tooltip_text = spec[1]
		b.theme_type_variation = "GhostButton"
		b.pressed.connect(spec[2])
		actions.add_child(b)
	# Sensitive actions apart (Loop UX-C): each asks for a typed word, and starting fresh takes a verified backup first.
	var danger := PanelContainer.new()
	danger.name = "SensitiveActions"
	danger.add_theme_stylebox_override("panel", SbTheme.box(Color(SbTheme.ERROR, 0.06), 10, Color(SbTheme.ERROR, 0.35), 1, 14))
	col.add_child(danger)
	var dbox := VBoxContainer.new()
	dbox.add_theme_constant_override("separation", 6)
	danger.add_child(dbox)
	var dhead := Label.new()
	dhead.theme_type_variation = "Overline"
	dhead.add_theme_color_override("font_color", SbTheme.ERROR)
	dhead.text = I18n.t("SENSITIVE ACTIONS")
	dbox.add_child(dhead)
	var dhint := Label.new()
	dhint.theme_type_variation = "Muted"
	dhint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	dhint.text = I18n.t("Each asks you to type a word to confirm. Starting fresh takes a verified backup first; uninstalling keeps your backups unless you untick it.")
	dbox.add_child(dhint)
	var drow := HBoxContainer.new()
	drow.add_theme_constant_override("separation", 8)
	dbox.add_child(drow)
	for spec in [
			[I18n.t("Start fresh…"), I18n.t("An empty Brain, after a verified backup of this one"), _start_fresh],
			[I18n.t("Uninstall…"), I18n.t("Remove Second Brain GD's data, keys and preferences from this computer"), _uninstall]]:
		var b := Button.new()
		b.text = spec[0]
		b.tooltip_text = spec[1]
		b.add_theme_color_override("font_color", SbTheme.ERROR)
		b.pressed.connect(spec[2])
		drow.add_child(b)

	result_label = Label.new()
	result_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	result_label.visible = false
	col.add_child(result_label)
	refresh()


static func frequency_label(hours: int) -> String:
	match hours:
		0:
			return I18n.t("Off")
		24:
			return I18n.t("Every day")
		72:
			return I18n.t("Every 3 days")
		168:
			return I18n.t("Every week")
	return I18n.t("Every %d hours") % hours


## "2 h ago", "3 days ago"… from a number of hours.
static func age_text(hours: Variant) -> String:
	if hours == null:
		return I18n.t("never")
	var h := float(hours)
	if h < 1.0:
		return I18n.t("less than an hour ago")
	if h < 48.0:
		return I18n.t("%d h ago") % int(h)
	return I18n.t("%d days ago") % int(h / 24.0)


func refresh() -> void:
	var r := await app.backend.api.call_api("/data/backups")
	if not is_inside_tree():
		return
	if not r["ok"]:
		state_label.text = I18n.t("Backups: not available (%s)") % str(r["error"])
		return
	last = r["data"]
	_render()


func _render() -> void:
	var s: Dictionary = last.get("settings", {})
	var lb: Variant = last.get("last")
	if lb is Dictionary:
		state_label.text = (I18n.t("Last backup: %s ✓") % age_text(last.get("age_hours"))) + ("" if not bool(last.get("overdue", false))
			else "  " + I18n.t("(overdue)"))
	else:
		state_label.text = I18n.t("No backup yet")
	where_label.text = str(last.get("destination", ""))
	where_label.tooltip_text = where_label.text
	var hours := int(s.get("every_hours", 24)) if bool(s.get("enabled", true)) else 0
	var idx := FREQUENCIES.find(hours)
	freq.select(idx if idx >= 0 else 3)
	warn_label.visible = bool(last.get("same_disk", false))
	warn_label.text = I18n.t("These backups are on the same disk as your Brain: they protect you from mistakes, not from a disk failure. Choose another disk, a USB key or a synced folder (OneDrive).")
	for c in list_box.get_children():
		c.queue_free()
	var items: Array = last.get("backups", [])
	if items.is_empty():
		return
	var head := Label.new()
	head.text = I18n.t("BACKUPS")
	head.theme_type_variation = "Overline"
	list_box.add_child(head)
	for i in mini(8, items.size()):
		var b: Dictionary = items[i]
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 10)
		list_box.add_child(row)
		var l := Label.new()
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var counts: Dictionary = b.get("counts", {})
		l.text = "%s · %s · %s · %s" % [SbFormat.datetime_text(str(b.get("created_at", ""))), kind_label(str(b.get("kind", ""))),
			(I18n.t("%d item") if int(counts.get("notes", 0)) == 1 else I18n.t("%d items")) % int(counts.get("notes", 0)),
			SbFormat.bytes(int(b.get("db_bytes", 0)) + int(b.get("originals_bytes", 0)))]
		row.add_child(l)
		var restore := Button.new()
		restore.text = I18n.t("Restore…")
		restore.theme_type_variation = "GhostButton"
		var bid := str(b.get("id", ""))
		var when := l.text.get_slice(" · ", 0)
		restore.pressed.connect(func() -> void: _restore(bid, when))
		row.add_child(restore)


static func kind_label(kind: String) -> String:
	match kind:
		"auto":
			return I18n.t("Automatic")
		"manual":
			return I18n.t("Manual")
		"before-restore":
			return I18n.t("Safety copy (before a restore)")
		"before-fresh":
			return I18n.t("Safety copy (before starting fresh)")
	return kind


func _say(text: String, warn: bool = false) -> void:
	result_label.text = text
	result_label.add_theme_color_override("font_color", SbTheme.WARM if warn else SbTheme.TEXT)
	result_label.visible = text != ""


func _error_text(r: Dictionary) -> String:
	var d: Variant = r.get("data")
	return str((d as Dictionary).get("detail", r["error"])) if d is Dictionary and (d as Dictionary).has("detail") else str(r["error"])


func back_up_now() -> bool:
	if _busy:
		return false
	_busy = true
	backup_button.disabled = true
	backup_button.text = I18n.t("Backing up…")
	var r := await app.backend.api.call_api("/data/backups", true, HTTPClient.METHOD_POST, "{}")
	_busy = false
	if not is_inside_tree():
		return false
	backup_button.disabled = false
	backup_button.text = I18n.t("Back up now")
	if r["ok"]:
		var d: Dictionary = r["data"]
		_say(I18n.t("Backed up: %d items and %d files in %s s, checked.") % [int((d.get("counts", {}) as Dictionary).get("notes", 0)),
			int(d.get("originals", 0)), str(d.get("seconds", "?"))])
	else:
		_say(I18n.t("The backup failed: %s") % _error_text(r), true)
	await refresh()
	return r["ok"]


## Opens the backups folder in the system's file manager (created first if no backup went there yet).
func open_backups_folder() -> String:
	var dir := str(last.get("destination", ""))
	if dir == "":
		return ""
	DirAccess.make_dir_recursive_absolute(dir)
	if OS.get_environment("SBGD_TEST_NO_SHELL") != "1":
		OS.shell_open(dir)
	return dir


func _choose_destination() -> void:
	if _dir_dialog == null:
		_dir_dialog = FileDialog.new()
		_dir_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
		_dir_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_dir_dialog.use_native_dialog = true
		_dir_dialog.title = I18n.t("Where should backups go?")
		_dir_dialog.dir_selected.connect(func(d: String) -> void: set_destination(d))
		add_child(_dir_dialog)
	_dir_dialog.popup_centered_ratio(0.6)


func set_destination(dir: String) -> bool:
	var r := await app.backend.api.call_api("/data/backups/settings", true, HTTPClient.METHOD_PUT, JSON.stringify({"destination": dir}))
	if not is_inside_tree():
		return false
	if r["ok"]:
		_say(I18n.t("Backups now go to %s. The next one starts there.") % dir)
	else:
		_say(I18n.t("Cannot use that folder: %s") % _error_text(r), true)
	await refresh()
	return r["ok"]


func _frequency_chosen(i: int) -> void:
	var hours: int = FREQUENCIES[i]
	var body := {"enabled": hours > 0}
	if hours > 0:
		body["every_hours"] = hours
	await app.backend.api.call_api("/data/backups/settings", true, HTTPClient.METHOD_PUT, JSON.stringify(body))
	await refresh()


## A dialog that asks the user to type a word before doing something that replaces or erases.
func confirm_word(title: String, text: String, word: String, extra: Control = null) -> ConfirmationDialog:
	var dlg := ConfirmationDialog.new()
	dlg.title = title
	dlg.theme = app.theme
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(560, 0)
	box.add_theme_constant_override("separation", 10)
	dlg.add_child(box)
	var l := Label.new()
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size = Vector2(560, 0)  # a fixed width: a wrapping label would otherwise stretch the dialog
	l.text = text
	box.add_child(l)
	if extra != null:
		box.add_child(extra)
	var hint := Label.new()
	hint.theme_type_variation = "Muted"
	hint.text = I18n.t("Type %s to confirm:") % word
	box.add_child(hint)
	var edit := LineEdit.new()
	edit.placeholder_text = word
	box.add_child(edit)
	dlg.ok_button_text = title
	dlg.cancel_button_text = I18n.t("Cancel")
	dlg.get_ok_button().disabled = true
	edit.text_changed.connect(func(t: String) -> void: dlg.get_ok_button().disabled = t.strip_edges().to_upper() != word.to_upper())
	dlg.canceled.connect(dlg.queue_free)
	add_child(dlg)
	dlg.reset_size()
	dlg.popup_centered(Vector2i(600, 0))
	edit.grab_focus()
	return dlg


func _restore(snap_id: String, when: String) -> void:
	var dlg := confirm_word(I18n.t("Restore"), I18n.t("Your Brain goes back to the backup of %s. What you added since then is replaced; a verified safety copy of the current state is taken first, so you can come back.") % when, I18n.t("RESTORE"))
	dlg.confirmed.connect(func() -> void:
		dlg.queue_free()
		restore(snap_id))


func restore(snap_id: String) -> bool:
	_say(I18n.t("Restoring… (safety copy first)"))
	var r := await app.backend.api.call_api("/data/backups/%s/restore" % snap_id, true, HTTPClient.METHOD_POST, JSON.stringify({"confirm": "RESTORE"}))
	if not is_inside_tree():
		return false
	if r["ok"]:
		_say(I18n.t("Restored the backup of %s. The state just before is kept in the list as a safety copy.") % SbFormat.datetime_text(str((r["data"] as Dictionary).get("created_at", ""))))
	else:
		_say(I18n.t("Nothing was changed: %s") % _error_text(r), true)
	await refresh()
	return r["ok"]


func _start_fresh() -> void:
	var dlg := confirm_word(I18n.t("Start fresh"), I18n.t("Your Brain is emptied and starts again with its starter notes. A verified backup is taken first: you can restore it any time. Your API key, preferences and browser pairing stay."), I18n.t("START FRESH"))
	dlg.confirmed.connect(func() -> void:
		dlg.queue_free()
		start_fresh())


func start_fresh() -> bool:
	_say(I18n.t("Starting fresh… (backup first)"))
	var r := await app.backend.api.call_api("/data/fresh", true, HTTPClient.METHOD_POST, JSON.stringify({"confirm": "START FRESH"}))
	if not is_inside_tree():
		return false
	if r["ok"]:
		_say(I18n.t("A fresh Brain. The previous one is in the backups (safety copy): Restore brings it back."))
	else:
		_say(I18n.t("Nothing was changed: %s") % _error_text(r), true)
	await refresh()
	return r["ok"]


func _export() -> void:
	_say(I18n.t("Exporting everything… (a backup first)"))
	var r := await app.backend.api.call_api("/data/export", true, HTTPClient.METHOD_POST, "{}")
	if not is_inside_tree():
		return
	if r["ok"]:
		var path := str((r["data"] as Dictionary).get("path", ""))
		_say(I18n.t("Saved: %s (%s). Copy it to the other computer, then Import a backup file there.") % [path, SbFormat.bytes(int((r["data"] as Dictionary).get("bytes", 0)))])
		if OS.get_environment("SBGD_TEST_NO_SHELL") != "1":
			OS.shell_show_in_file_manager(path)
	else:
		_say(I18n.t("The export failed: %s") % _error_text(r), true)
	await refresh()


func _pick_import() -> void:
	if _file_dialog == null:
		_file_dialog = FileDialog.new()
		_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILE
		_file_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_file_dialog.use_native_dialog = true
		_file_dialog.filters = PackedStringArray(["*.zip ; " + I18n.t("Second Brain GD backup")])
		_file_dialog.file_selected.connect(func(p: String) -> void: import_file(p))
		add_child(_file_dialog)
	_file_dialog.popup_centered_ratio(0.6)


func import_file(path: String) -> bool:
	_say(I18n.t("Reading the backup file…"))
	var r := await app.backend.api.call_api("/data/import", true, HTTPClient.METHOD_POST, JSON.stringify({"path": path}))
	if not is_inside_tree():
		return false
	if not r["ok"]:
		_say(I18n.t("This file cannot be used: %s") % _error_text(r), true)
		return false
	var d: Dictionary = r["data"]
	await refresh()
	_say(I18n.t("The backup of %s is checked and listed. Restore it to make it your Brain.") % SbFormat.datetime_text(str(d.get("created_at", ""))))
	_restore(str(d.get("id", "")), SbFormat.datetime_text(str(d.get("created_at", ""))))
	return true


func _open_packs() -> void:
	var pd := PacksDialog.new().setup(app)
	add_child(pd)
	pd.open()


func _repair() -> void:
	var dlg := ConfirmationDialog.new()
	dlg.title = I18n.t("Repair the installation")
	dlg.theme = app.theme
	dlg.dialog_text = I18n.t("The engine stops, its Python environment is rebuilt and its packages reinstalled (a minute or two, internet needed when not using the app's own Python). Your data is not touched.")
	dlg.dialog_autowrap = true
	dlg.min_size = Vector2i(560, 0)
	dlg.ok_button_text = I18n.t("Repair")
	dlg.cancel_button_text = I18n.t("Cancel")
	dlg.confirmed.connect(func() -> void:
		dlg.queue_free()
		app.repair_installation())
	dlg.canceled.connect(dlg.queue_free)
	add_child(dlg)
	dlg.popup_centered()


func _uninstall() -> void:
	var data_dir := SbPaths.data_dir()
	var dest := str(last.get("destination", ""))
	var inside := dest.begins_with(data_dir)
	var keep := CheckBox.new()
	keep.text = I18n.t("Keep my backups (%s)") % dest
	keep.button_pressed = true
	keep.visible = inside
	var dlg := confirm_word(I18n.t("Uninstall"), I18n.t("Removes from this computer: your Brain (%s), your API keys in the credential store, the app's preferences. The app folder itself is yours to delete afterwards. Back up first if you may want your Brain again.") % data_dir, I18n.t("UNINSTALL"), keep)
	dlg.confirmed.connect(func() -> void:
		dlg.queue_free()
		uninstall(keep.button_pressed or not inside))


## Removes the data folder (keeping the backups in it unless asked), the keys and the preferences, then quits.
func uninstall(keep_backups: bool) -> bool:
	var data_dir := SbPaths.data_dir()
	if not FileAccess.file_exists(data_dir.path_join("install_state.json")) or data_dir.length() < 8:
		_say(I18n.t("Not removed: %s does not look like Second Brain GD's data folder.") % data_dir, true)
		return false
	_say(I18n.t("Removing…"))
	await app.backend.api.call_api("/voice/key", true, HTTPClient.METHOD_DELETE)
	await app.backend.api.call_api("/billing/key", true, HTTPClient.METHOD_DELETE)
	await app.backend.shutdown_engine(5.0)
	var keep := data_dir.path_join("backups") if keep_backups else ""
	var left := remove_tree(data_dir, keep)
	DirAccess.remove_absolute(ProjectSettings.globalize_path(SbSettings.path()) if SbSettings.path().begins_with("user://") else SbSettings.path())
	var done := AcceptDialog.new()
	done.title = I18n.t("Uninstalled")
	done.theme = app.theme
	done.dialog_autowrap = true
	done.min_size = Vector2i(520, 0)
	done.dialog_text = (I18n.t("Second Brain GD's data, keys and preferences are removed from this computer.") + "\n"
		+ (I18n.t("Your backups are kept in %s.") % keep + "\n" if keep != "" else "")
		+ (I18n.t("%d files could not be removed (in use?): delete %s by hand.") % [left, data_dir] + "\n" if left > 0 else "")
		+ I18n.t("You can now delete the app's folder."))
	done.ok_button_text = I18n.t("Quit")
	done.confirmed.connect(func() -> void: app.quit_app())
	done.canceled.connect(func() -> void: app.quit_app())
	add_child(done)
	done.popup_centered()
	return left == 0


## Deletes a folder's content recursively, except `keep` (a sub-folder). Returns how many files resisted.
static func remove_tree(dir: String, keep: String = "") -> int:
	var failed := 0
	var d := DirAccess.open(dir)
	if d == null:
		return 0
	d.include_hidden = true
	for f in d.get_files():
		if DirAccess.remove_absolute(dir.path_join(f)) != OK:
			failed += 1
	for sub in d.get_directories():
		var p := dir.path_join(sub)
		if keep != "" and p.simplify_path() == keep.simplify_path():
			continue
		failed += remove_tree(p, keep)
		DirAccess.remove_absolute(p)
	if keep == "" or not keep.begins_with(dir):
		DirAccess.remove_absolute(dir)
	return failed
