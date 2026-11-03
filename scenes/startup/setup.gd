extends Control
## Setup: finds Python, runs the bootstrap, shows real progress and logs.
## Success is shown only after the bootstrap's final event, which is emitted
## after /health and an authenticated call were verified.

const STEPS: Array = [
	["python", "Python interpreter"],
	["directories", "Data directories"],
	["venv", "Virtual environment"],
	["dependencies", "Locked dependencies"],
	["database", "SQLite database"],
	["service", "Local API service"],
	["health", "Health verification"],
]
const AUTO_CONTINUE_S := 1.2

var app: SbApp
var rows: Dictionary = {}
var progress: ProgressBar
var progress_label: Label
var headline: Label
var log_view: RichTextLabel
var log_panel: PanelContainer
var log_toggle: Button
var error_panel: PanelContainer
var error_label: Label
var error_hint: RichTextLabel
var retry_button: Button
var continue_button: Button
var back_button: Button
var locator: PythonLocator
var runner: BootstrapRunner
var events_seen := 0
var succeeded := false
var _target_progress := 0.0
var _log_lines := 0


func bind(a: SbApp) -> void:
	app = a


func _ready() -> void:
	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right"]:
		margin.add_theme_constant_override("margin_" + side, 64)
	margin.add_theme_constant_override("margin_top", 40)
	margin.add_theme_constant_override("margin_bottom", 32)
	add_child(margin)
	var root := HBoxContainer.new()
	root.add_theme_constant_override("separation", 28)
	margin.add_child(root)

	var left := VBoxContainer.new()
	left.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	left.size_flags_stretch_ratio = 1.0
	left.add_theme_constant_override("separation", 12)
	root.add_child(left)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 14)
	left.add_child(head)
	var logo := BrainLogo.new()
	logo.custom_minimum_size = Vector2(54, 54)
	head.add_child(logo)
	var htext := VBoxContainer.new()
	htext.add_theme_constant_override("separation", 0)
	head.add_child(htext)
	var over := Label.new()
	over.text = "SETUP"
	over.theme_type_variation = "Overline"
	htext.add_child(over)
	headline = Label.new()
	headline.text = "Preparing your Second Brain"
	headline.theme_type_variation = "Heading"
	headline.add_theme_font_size_override("font_size", 24)
	htext.add_child(headline)

	var prow := HBoxContainer.new()
	prow.add_theme_constant_override("separation", 12)
	left.add_child(prow)
	progress = ProgressBar.new()
	progress.custom_minimum_size = Vector2(0, 12)
	progress.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	progress.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	progress.show_percentage = false
	progress.max_value = 1.0
	progress.step = 0.0001
	prow.add_child(progress)
	progress_label = Label.new()
	progress_label.custom_minimum_size = Vector2(48, 0)
	progress_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	prow.add_child(progress_label)

	for s in STEPS:
		var row := StepRow.new().setup(str(s[0]), str(s[1]))
		rows[s[0]] = row
		left.add_child(row)

	error_panel = PanelContainer.new()
	error_panel.theme_type_variation = "ErrorPanel"
	error_panel.visible = false
	left.add_child(error_panel)
	var ecol := VBoxContainer.new()
	ecol.add_theme_constant_override("separation", 6)
	error_panel.add_child(ecol)
	error_label = Label.new()
	error_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	error_label.add_theme_color_override("font_color", SbTheme.ERROR)
	ecol.add_child(error_label)
	error_hint = RichTextLabel.new()
	error_hint.bbcode_enabled = true
	error_hint.fit_content = true
	error_hint.selection_enabled = true
	error_hint.meta_clicked.connect(func(meta: Variant) -> void: OS.shell_open(str(meta)))
	ecol.add_child(error_hint)

	var brow := HBoxContainer.new()
	brow.add_theme_constant_override("separation", 10)
	left.add_child(brow)
	back_button = Button.new()
	back_button.text = "Back"
	back_button.theme_type_variation = "GhostButton"
	back_button.pressed.connect(func() -> void: app.show_welcome())
	brow.add_child(back_button)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	brow.add_child(spacer)
	retry_button = Button.new()
	retry_button.text = "Retry (resumes)"
	retry_button.visible = false
	retry_button.pressed.connect(begin)
	brow.add_child(retry_button)
	continue_button = Button.new()
	continue_button.text = "Enter your Second Brain"
	continue_button.theme_type_variation = "PrimaryButton"
	continue_button.visible = false
	continue_button.pressed.connect(func() -> void: app.after_setup())
	brow.add_child(continue_button)

	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.size_flags_stretch_ratio = 0.9
	right.add_theme_constant_override("separation", 8)
	root.add_child(right)
	var lhead := HBoxContainer.new()
	right.add_child(lhead)
	var ltitle := Label.new()
	ltitle.text = "Live log"
	ltitle.theme_type_variation = "Heading"
	ltitle.add_theme_font_size_override("font_size", 16)
	ltitle.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lhead.add_child(ltitle)
	log_toggle = Button.new()
	log_toggle.text = "Hide details"
	log_toggle.theme_type_variation = "GhostButton"
	log_toggle.toggle_mode = true
	log_toggle.toggled.connect(func(on: bool) -> void:
		_show_tool_output = not on
		log_toggle.text = "Show tool output" if on else "Hide details")
	lhead.add_child(log_toggle)
	log_panel = PanelContainer.new()
	log_panel.theme_type_variation = "Inset"
	log_panel.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(log_panel)
	log_view = RichTextLabel.new()
	log_view.bbcode_enabled = true
	log_view.scroll_following = true
	log_view.selection_enabled = true
	log_view.context_menu_enabled = true
	log_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	log_panel.add_child(log_view)

	locator = PythonLocator.new()
	add_child(locator)
	locator.located.connect(_on_located)
	runner = BootstrapRunner.new()
	add_child(runner)
	runner.event_received.connect(_on_event)
	runner.finished.connect(_on_finished)
	begin()


var _show_tool_output := true


func _process(delta: float) -> void:
	if progress.value < _target_progress:
		progress.value = minf(_target_progress, progress.value + maxf(0.002, (_target_progress - progress.value) * delta * 6.0))
	progress_label.text = "%d %%" % int(round(progress.value * 100.0))


func begin() -> void:
	succeeded = false
	error_panel.visible = false
	retry_button.visible = false
	continue_button.visible = false
	back_button.disabled = true
	for k in rows:
		var row: StepRow = rows[k]
		row.set_state("pending", "Waiting")
	_target_progress = 0.0
	progress.value = 0.0
	headline.text = "Preparing your Second Brain"
	var row_py: StepRow = rows["python"]
	row_py.set_state("checking", "Looking for a compatible Python (3.12 or 3.13)…")
	_log("ui", "info", "Data folder: %s" % app.backend.data_dir)
	_log("ui", "info", "Looking for Python…")
	locator.locate()


func _on_located(result: Dictionary) -> void:
	var tried: Array = result["tried"]
	for t in tried:
		var entry: Dictionary = t
		_log("python", "log", "%s → %s %s" % [entry["label"], entry["result"], entry.get("version", "")])
	if not bool(result["found"]):
		var row: StepRow = rows["python"]
		row.set_state("error", "No compatible Python found")
		_fail("No compatible Python (3.12 or 3.13) was found on this computer.",
			"Install Python from [url=%s]python.org/downloads[/url]. On Windows, tick [b]Add python.exe to PATH[/b] in the installer. Then press Retry. You can also set a custom python path in [i]Check prerequisites[/i] on the welcome screen." % result["download_url"])
		return
	var py: Dictionary = result["python"]
	app.backend.python = py
	_log("ui", "info", "Using Python %s at %s" % [py["version"], py["executable"]])
	var err := runner.start(str(py["executable"]), app.backend.data_dir)
	if err != OK:
		_fail("Could not start the setup process (%s)." % error_string(err), "Check that the data folder is writable: %s" % app.backend.data_dir)


func _on_event(ev: Dictionary) -> void:
	events_seen += 1
	var component := str(ev.get("component", ""))
	var status := str(ev.get("status", ""))
	var message := str(ev.get("message", ""))
	var p: Variant = ev.get("progress")
	if p != null:
		_target_progress = maxf(_target_progress, float(p))
	if rows.has(component):
		var row: StepRow = rows[component]
		row.set_state(status, message)
		if status in ["ok", "skipped"] and component != "bootstrap":
			app.audio.play("step_done", 0.06, -4.0 if status == "skipped" else 0.0)
	if status == "error":
		var details: Dictionary = ev.get("details", {}) if ev.get("details") is Dictionary else {}
		if component != "bootstrap":
			_fail(message, _escape(str(details.get("hint", ""))), str(details.get("tail", "")))
	_log(component, status, message)


func _on_finished(ok: bool, final_event: Dictionary) -> void:
	back_button.disabled = false
	if ok:
		succeeded = true
		app.audio.play("setup_complete")
		_target_progress = 1.0
		headline.text = "Your Second Brain is ready"
		continue_button.visible = true
		continue_button.grab_focus()
		app.backend.load_runtime()
		get_tree().create_timer(AUTO_CONTINUE_S).timeout.connect(func() -> void:
			if is_inside_tree() and app.current_screen == "setup":
				app.after_setup())
	else:
		headline.text = "Setup needs attention"
		if not error_panel.visible:
			_fail(str(final_event.get("message", "Setup failed.")), "")
		retry_button.visible = true


func _fail(message: String, hint_bbcode: String, tail: String = "") -> void:
	if not error_panel.visible:
		app.audio.play("error")
	error_panel.visible = true
	error_label.text = message
	var hint := hint_bbcode
	if tail != "":
		hint += "\n[code]%s[/code]" % _escape(tail)
	error_hint.text = hint
	error_hint.visible = hint != ""
	retry_button.visible = true
	back_button.disabled = false
	headline.text = "Setup needs attention"


func _log(component: String, status: String, message: String) -> void:
	if status == "log" and not _show_tool_output:
		return
	_log_lines += 1
	if _log_lines > 4000:
		log_view.clear()
		_log_lines = 0
	var c := SbTheme.MUTED if status == "log" else SbTheme.status_color(status)
	if status == "info":
		c = SbTheme.TEXT
	var time := Time.get_time_string_from_system()
	if status == "log":
		log_view.append_text("[color=#%s][code]%s  %s[/code][/color]\n" % [SbTheme.FAINT.to_html(false), time, _escape(message)])
	else:
		log_view.append_text("[color=#%s]%s[/color]  [color=#%s][b]%s[/b][/color]  %s\n" % [SbTheme.FAINT.to_html(false), time,
			c.to_html(false), component, _escape(message)])


static func _escape(text: String) -> String:
	return text.replace("[", "[lb]")
