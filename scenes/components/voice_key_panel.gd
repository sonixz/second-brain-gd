class_name VoiceKeyPanel
extends VBoxContainer
## Bring-your-own-key form for voice capture. The key goes straight to the
## engine (local API), which verifies it with OpenAI and stores it in the OS
## credential store. Godot keeps nothing.

signal saved(status: Dictionary)
signal skipped

const KEYS_URL := "https://platform.openai.com/api-keys"

var app: SbApp
var key_edit: LineEdit
var save_button: Button
var result: RichTextLabel
var status_label: Label
var remove_button: Button
var status: Dictionary = {}


func setup(a: SbApp, with_skip: bool) -> VoiceKeyPanel:
	app = a
	add_theme_constant_override("separation", 12)
	status_label = Label.new()
	status_label.theme_type_variation = "Muted"
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(status_label)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	add_child(row)
	key_edit = LineEdit.new()
	key_edit.secret = true
	key_edit.placeholder_text = "sk-…   your OpenAI API key"
	key_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	key_edit.custom_minimum_size = Vector2(0, 44)
	key_edit.text_submitted.connect(func(_t: String) -> void: _save())
	row.add_child(key_edit)
	save_button = Button.new()
	save_button.text = "Verify & save"
	save_button.theme_type_variation = "PrimaryButton"
	save_button.custom_minimum_size = Vector2(0, 44)
	save_button.pressed.connect(_save)
	row.add_child(save_button)
	result = RichTextLabel.new()
	result.bbcode_enabled = true
	result.fit_content = true
	result.meta_clicked.connect(func(meta: Variant) -> void: OS.shell_open(str(meta)))
	result.text = "Get a key at [url=%s]platform.openai.com/api-keys[/url]. Voice uses about $0.017 per minute of speech, billed by OpenAI to your account." % KEYS_URL
	add_child(result)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 8)
	add_child(actions)
	remove_button = Button.new()
	remove_button.text = "Remove key"
	remove_button.theme_type_variation = "GhostButton"
	remove_button.visible = false
	remove_button.pressed.connect(_remove)
	actions.add_child(remove_button)
	if with_skip:
		var spacer := Control.new()
		spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		actions.add_child(spacer)
		var skip := Button.new()
		skip.text = "Skip for now"
		skip.theme_type_variation = "GhostButton"
		skip.pressed.connect(func() -> void: skipped.emit())
		actions.add_child(skip)
	refresh()
	return self


func refresh() -> void:
	var res := await app.backend.api.call_api("/voice/status")
	if not res["ok"] or not is_inside_tree():
		status_label.text = "Voice settings unavailable: %s" % res["error"]
		return
	_show_status(res["data"])


func _show_status(st: Dictionary) -> void:
	status = st
	var where := {"keyring": "your system's credential store (%s)" % st.get("backend", ""),
		"file": "a private file in your data folder (no system credential store found)",
		"env": "the OPENAI_API_KEY environment variable (developer mode)"}
	if bool(st.get("configured", false)):
		status_label.text = "✓ Key %s saved in %s · model %s" % [st.get("hint", ""), where.get(str(st.get("source")), "?"), st.get("model", "")]
		status_label.add_theme_color_override("font_color", SbTheme.MINT)
		remove_button.visible = str(st.get("source")) != "env"
		key_edit.placeholder_text = "Paste a new key to replace it"
	else:
		status_label.text = "No key yet. Your key stays on this computer, in your system's credential store. Godot never keeps it."
		status_label.remove_theme_color_override("font_color")
		remove_button.visible = false


func _save() -> void:
	var key := key_edit.text.strip_edges()
	if key.length() < 20:
		result.text = "[color=#%s]That does not look like an OpenAI key.[/color]" % SbTheme.ERROR.to_html(false)
		return
	save_button.disabled = true
	result.text = "Checking with OpenAI…"
	var res := await app.backend.api.call_api("/voice/key", true, HTTPClient.METHOD_PUT, JSON.stringify({"api_key": key}))
	key_edit.text = ""  # never keep the key in the UI
	save_button.disabled = false
	if not res["ok"]:
		var data: Dictionary = res["data"]
		app.audio.play("error")
		result.text = "[color=#%s]%s[/color]" % [SbTheme.ERROR.to_html(false), str(data.get("detail", res["error"]))]
		return
	var st: Dictionary = res["data"]
	var check: Dictionary = st.get("check", {})
	_show_status(st)
	if bool(check.get("ok", false)):
		app.audio.play("confirm")
		result.text = "[color=#%s]%s[/color]" % [SbTheme.MINT.to_html(false), check.get("message", "Saved.")]
	else:
		result.text = "[color=#%s]Saved, but: %s[/color]" % [SbTheme.WARN.to_html(false), check.get("message", "")]
	saved.emit(st)


func _remove() -> void:
	var res := await app.backend.api.call_api("/voice/key", true, HTTPClient.METHOD_DELETE)
	if res["ok"]:
		_show_status(res["data"])
		result.text = "Key removed."
