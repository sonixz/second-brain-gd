extends Control
## Welcome: identity, install status read from disk, Setup/Start, and the
## prerequisite diagnostic.

var app: SbApp
var status_dot: StatusDot
var status_label: Label
var primary: Button
var secondary: Button
var diag_button: Button
var diag_panel: PanelContainer
var diag_text: RichTextLabel
var custom_edit: LineEdit
var locator: PythonLocator


func bind(a: SbApp) -> void:
	app = a


func _ready() -> void:
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(center)
	var col := VBoxContainer.new()
	col.custom_minimum_size = Vector2(560, 0)
	col.alignment = BoxContainer.ALIGNMENT_CENTER
	col.add_theme_constant_override("separation", 14)
	center.add_child(col)

	var logo := BrainLogo.new()
	logo.custom_minimum_size = Vector2(170, 170)
	logo.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	col.add_child(logo)

	var over := Label.new()
	over.text = "LOCAL-FIRST KNOWLEDGE SYSTEM"
	over.theme_type_variation = "Overline"
	over.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(over)
	var title := Label.new()
	title.text = "SECOND BRAIN GD"
	title.theme_type_variation = "Title"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(title)
	var tagline := Label.new()
	tagline.text = "Your knowledge. Your system. Your control."
	tagline.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	tagline.add_theme_color_override("font_color", SbTheme.MINT_SOFT)
	col.add_child(tagline)

	var pill := PanelContainer.new()
	pill.theme_type_variation = "Inset"
	pill.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	col.add_child(pill)
	var pill_row := HBoxContainer.new()
	pill_row.add_theme_constant_override("separation", 10)
	pill.add_child(pill_row)
	status_dot = StatusDot.new()
	status_dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	pill_row.add_child(status_dot)
	status_label = Label.new()
	pill_row.add_child(status_label)

	var buttons := HBoxContainer.new()
	buttons.alignment = BoxContainer.ALIGNMENT_CENTER
	buttons.add_theme_constant_override("separation", 12)
	col.add_child(buttons)
	primary = Button.new()
	primary.theme_type_variation = "PrimaryButton"
	primary.custom_minimum_size = Vector2(200, 50)
	primary.set_meta("sfx", "confirm")
	primary.pressed.connect(func() -> void: app.start_setup())
	buttons.add_child(primary)
	secondary = Button.new()
	secondary.text = "Re-run full setup"
	secondary.tooltip_text = "Checks every component again. Your data is kept."
	secondary.custom_minimum_size = Vector2(0, 50)
	secondary.pressed.connect(func() -> void: app.start_setup())
	buttons.add_child(secondary)

	diag_button = Button.new()
	diag_button.text = "Check prerequisites"
	diag_button.theme_type_variation = "GhostButton"
	diag_button.size_flags_horizontal = Control.SIZE_SHRINK_CENTER
	diag_button.pressed.connect(_run_diagnostic)
	col.add_child(diag_button)

	diag_panel = PanelContainer.new()
	diag_panel.theme_type_variation = "Card"
	diag_panel.visible = false
	col.add_child(diag_panel)
	var dcol := VBoxContainer.new()
	dcol.add_theme_constant_override("separation", 10)
	diag_panel.add_child(dcol)
	diag_text = RichTextLabel.new()
	diag_text.bbcode_enabled = true
	diag_text.fit_content = true
	diag_text.selection_enabled = true
	diag_text.meta_clicked.connect(func(meta: Variant) -> void: OS.shell_open(str(meta)))
	dcol.add_child(diag_text)
	var crow := HBoxContainer.new()
	crow.add_theme_constant_override("separation", 8)
	dcol.add_child(crow)
	custom_edit = LineEdit.new()
	custom_edit.placeholder_text = "Optional: full path to python.exe"
	custom_edit.text = PythonLocator.custom_python()
	custom_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	crow.add_child(custom_edit)
	var apply := Button.new()
	apply.text = "Use & re-check"
	apply.pressed.connect(func() -> void:
		PythonLocator.save_custom_python(custom_edit.text)
		_run_diagnostic())
	crow.add_child(apply)
	var open_dir := Button.new()
	open_dir.text = "Open data folder"
	open_dir.theme_type_variation = "GhostButton"
	open_dir.pressed.connect(func() -> void:
		DirAccess.make_dir_recursive_absolute(app.backend.data_dir)
		OS.shell_open(app.backend.data_dir))
	dcol.add_child(open_dir)

	var foot := Label.new()
	foot.text = "v%s · Loop 0 · Data stays on this computer" % ProjectSettings.get_setting("application/config/version")
	foot.theme_type_variation = "Muted"
	foot.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(foot)

	locator = PythonLocator.new()
	add_child(locator)
	locator.located.connect(_on_located)
	refresh_status()


func refresh_status() -> void:
	var state := app.backend.install_state()
	var steps: Dictionary = state.get("steps", {})
	var installed := bool(state.get("installed", false))
	if installed:
		var py: Dictionary = state.get("python", {})
		status_dot.set_status("ok")
		status_label.text = "Installed · Python %s · last ready %s" % [py.get("version", "?"),
			SbFormat.local_time(state.get("last_success_at"), true)]
		primary.text = "Start"
		primary.tooltip_text = "Verifies the installation quickly and starts the local engine."
		secondary.visible = true
	else:
		var failed := ""
		for k in steps:
			var st: Dictionary = steps[k]
			if str(st.get("status", "")) == "error":
				failed = str(k)
		if failed != "":
			status_dot.set_status("warning")
			status_label.text = "Setup incomplete · stopped at '%s' · it will resume" % failed
		elif steps.is_empty():
			status_dot.set_status("pending")
			status_label.text = "Not installed yet"
		else:
			status_dot.set_status("warning")
			status_label.text = "Setup incomplete · it will resume where it stopped"
		primary.text = "Setup"
		primary.tooltip_text = "Detects Python, prepares the engine and starts it."
		secondary.visible = false


func _run_diagnostic() -> void:
	diag_panel.visible = true
	diag_button.disabled = true
	diag_text.text = "[color=#%s]Checking…[/color]" % SbTheme.INFO.to_html(false)
	locator.locate()


func _on_located(result: Dictionary) -> void:
	diag_button.disabled = false
	var ok_c := SbTheme.MINT.to_html(false)
	var bad_c := SbTheme.ERROR.to_html(false)
	var mute_c := SbTheme.MUTED.to_html(false)
	var lines: PackedStringArray = []
	lines.append("[b]Prerequisites[/b]")
	lines.append("[color=#%s]Operating system[/color]  %s" % [mute_c, OS.get_name()])
	var gv: Dictionary = Engine.get_version_info()
	lines.append("[color=#%s]Godot[/color]  %s" % [mute_c, gv.get("string", "?")])
	lines.append("[color=#%s]Data folder[/color]  %s" % [mute_c, app.backend.data_dir])
	lines.append("[color=#%s]Engine sources[/color]  %s %s" % [mute_c, SbPaths.bootstrap_script(),
		"[color=#%s]found[/color]" % ok_c if FileAccess.file_exists(SbPaths.bootstrap_script())
		else "[color=#%s]missing[/color]" % bad_c])
	lines.append("[color=#%s]Python (supported %s)[/color]" % [mute_c, result["supported_range"]])
	var tried: Array = result["tried"]
	for t in tried:
		var entry: Dictionary = t
		var res := str(entry.get("result", ""))
		var color := ok_c if res == "compatible" else (mute_c if res == "not found" else bad_c)
		var extra := ""
		if entry.has("version"):
			extra = " %s · %s" % [entry["version"], entry.get("executable", "")]
		lines.append("  • %s → [color=#%s]%s[/color]%s" % [entry["label"], color, res, extra])
	if not bool(result["found"]):
		lines.append("[color=#%s]No compatible Python found.[/color] Install Python 3.12 or 3.13 from [url=%s]python.org[/url] (tick “Add python.exe to PATH”), then check again." % [bad_c, result["download_url"]])
	diag_text.text = "\n".join(lines)
