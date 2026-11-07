extends Button
## The MCP lights (Loop MCP-A), in the top bar beside the engine status: « ⇠ in » (AI tools connected to the Brain)
## and « ⇢ out » (MCP servers the agents use, MCP-C). Grey when nothing is plugged in, green when connected, a soft
## red while a call is under way. Hover: the last call. Click: clients, commands to connect, recent calls.
## Loaded by preload path (a new class can lag in Godot's class list on Windows).

var app: SbApp
var status: Dictionary = {}
var in_state := "off"     # off, on, busy
var out_state := "off"
var _pulse := 0.0
var _flash_until := 0.0
var _last_seen_call := ""
var dialog: AcceptDialog  # tests


func setup(a: SbApp) -> Button:
	app = a
	name = "McpLights"
	theme_type_variation = "GhostButton"
	custom_minimum_size = Vector2(64, 40)
	size_flags_vertical = Control.SIZE_SHRINK_CENTER
	tooltip_text = I18n.t("MCP: no AI tool connected yet. Click to connect Claude Code.")
	pressed.connect(open_dialog)
	return self


func _process(delta: float) -> void:
	_pulse += delta
	if in_state == "busy" or out_state == "busy":
		queue_redraw()


func poll() -> void:
	var res := await app.backend.api.call_api("/mcp/status")
	if not res["ok"] or not is_inside_tree():
		return
	status = res["data"]
	var last: Dictionary = status["last"] if status.get("last") is Dictionary else {}
	var key := str(last.get("at", ""))
	if key != "" and key != _last_seen_call:
		if _last_seen_call != "":
			_flash_until = Time.get_ticks_msec() / 1000.0 + 1.4  # a short call still shows: the light stays red a moment
		_last_seen_call = key
	var busy := not (status.get("active", []) as Array).is_empty() or Time.get_ticks_msec() / 1000.0 < _flash_until
	var connected := not (status.get("connected", []) as Array).is_empty()
	in_state = "busy" if busy else ("on" if connected or not (status.get("clients", []) as Array).is_empty() else "off")
	if last.is_empty():
		tooltip_text = I18n.t("MCP: no AI tool connected yet. Click to connect Claude Code.") if (status.get("clients", []) as Array).is_empty() \
			else I18n.t("MCP in: %d tools connected, no call yet") % (status.get("clients", []) as Array).size()
	else:
		tooltip_text = I18n.t("MCP in · last call: %s · %s") % [str(last.get("client", "")), str(last.get("tool", ""))] \
			+ "\n" + I18n.t("MCP out: no server connected yet")
	queue_redraw()


func _color(state: String) -> Color:
	match state:
		"busy":
			return Color(0.95, 0.42, 0.42, 0.65 + 0.35 * sin(_pulse * 7.0))
		"on":
			return Color(0.45, 0.85, 0.6, 0.95)
	return Color(SbTheme.MUTED, 0.55)


func _draw() -> void:
	# Compact: « ⇠● ⇢● ». The words « in » and « out » are in the tooltip.
	var font := get_theme_default_font()
	var y := size.y * 0.5
	var x := 10.0
	for pair in [[in_state, "⇠"], [out_state, "⇢"]]:
		var c := _color(str(pair[0]))
		draw_string(font, Vector2(x, y + 5), str(pair[1]), HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color(SbTheme.MUTED, 0.95))
		var dot := Vector2(x + 17, y)
		if str(pair[0]) == "busy":
			draw_circle(dot, 8.0, Color(c, 0.18))
		draw_circle(dot, 4.5, c)
		x += 28.0


## Clients, « Connect an AI tool », the commands to paste, recent calls.
func open_dialog() -> AcceptDialog:
	if dialog != null and is_instance_valid(dialog):
		dialog.queue_free()
	var dlg := AcceptDialog.new()
	dialog = dlg
	dlg.name = "McpDialog"
	dlg.title = I18n.t("MCP — AI tools and the Brain")
	dlg.theme = app.theme
	dlg.add_theme_stylebox_override("panel", SbTheme.box(SbTheme.PANEL, 0, SbTheme.BORDER, 1, 18))
	dlg.ok_button_text = I18n.t("Close")
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(660, 0)
	box.add_theme_constant_override("separation", 10)
	dlg.add_child(box)
	var intro := Label.new()
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.theme_type_variation = "Muted"
	intro.text = I18n.t("Connect Claude Code (or another MCP tool) to your Brain: it can read and search everything here. It never writes directly: what it proposes goes through the archivist. Local only: this computer, nothing on the network.")
	box.add_child(intro)
	var list := VBoxContainer.new()
	list.name = "Clients"
	box.add_child(list)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	box.add_child(row)
	var name_edit := LineEdit.new()
	name_edit.name = "ClientName"
	name_edit.text = "Claude Code"
	name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name_edit)
	var connect_b := Button.new()
	connect_b.name = "ConnectButton"
	connect_b.text = I18n.t("Connect an AI tool (read)")
	connect_b.theme_type_variation = "PrimaryButton"
	row.add_child(connect_b)
	var commands := VBoxContainer.new()
	commands.name = "Commands"
	commands.add_theme_constant_override("separation", 6)
	box.add_child(commands)
	var recent := RichTextLabel.new()
	recent.name = "Recent"
	recent.bbcode_enabled = true
	recent.fit_content = true
	recent.custom_minimum_size = Vector2(640, 0)
	box.add_child(recent)
	var fill := func() -> void:
		for c in list.get_children():
			c.queue_free()
		var res := await app.backend.api.call_api("/mcp/status")
		if not res["ok"] or not is_instance_valid(list):
			return
		var st: Dictionary = res["data"]
		for cl in st.get("clients", []):
			var d: Dictionary = cl
			var line := HBoxContainer.new()
			var l := Label.new()
			l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			l.text = "%s · %s · %s" % [str(d["name"]), _level(str(d["level"])),
				(I18n.t("%d calls, last %s") % [int(d.get("calls", 0)), str(d.get("last_seen", "")).left(16).replace("T", " ")]) if d.get("last_seen") != null else I18n.t("never used")]
			line.add_child(l)
			var rv := Button.new()
			rv.text = I18n.t("Disconnect")
			rv.tooltip_text = I18n.t("Revokes its token: it can no longer reach the Brain")
			var cid := str(d["id"])
			rv.pressed.connect(func() -> void:
				await app.backend.api.call_api("/mcp/clients/" + cid, true, HTTPClient.METHOD_DELETE)
				line.queue_free())
			line.add_child(rv)
			list.add_child(line)
		var b := PackedStringArray()
		for r in st.get("recent", []):
			var x: Dictionary = r
			b.append("[color=#%s]%s[/color]  %s · %s · %d ms" % [SbTheme.MUTED.to_html(false), str(x.get("at", "")).substr(11, 8),
				str(x.get("client", "")), str(x.get("tool", "")), int(x.get("ms", 0))])
		recent.text = ("[b]" + I18n.t("Recent calls") + "[/b]\n" + "\n".join(b)) if not b.is_empty() else ""
	connect_b.pressed.connect(func() -> void:
		var res := await app.backend.api.call_api("/mcp/clients", true, HTTPClient.METHOD_POST,
			JSON.stringify({"name": name_edit.text.strip_edges(), "level": "read"}))
		if not res["ok"]:
			return
		_show_commands(commands, res["data"])
		fill.call())
	app.get_tree().root.add_child(dlg)
	dlg.popup_centered_clamped(Vector2i(720, 560))
	fill.call()
	return dlg


static func _level(level: String) -> String:
	return {"read": I18n.t("read"), "propose_items": I18n.t("proposes items"), "propose_changes": I18n.t("proposes changes")}.get(level, level)


## The commands with this client's token, shown once (only its hash is kept).
func _show_commands(box: VBoxContainer, c: Dictionary) -> void:
	for ch in box.get_children():
		ch.queue_free()
	var port: int = app.backend.api.port
	var token := str(c.get("token", ""))
	var relay := ProjectSettings.globalize_path("res://engine/mcp/relay.py").replace("/", "\\")
	var py := OS.get_environment("LOCALAPPDATA").path_join("SecondBrainGD/.venv/Scripts/python.exe").replace("\\", "/")
	var wsl_py := "/mnt/" + py.left(1).to_lower() + py.substr(2) if py.length() > 2 and py[1] == ":" else py
	var warn := Label.new()
	warn.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	warn.text = I18n.t("Copy one command now: the key it holds is shown only this once. Then restart Claude Code (a session sees new MCP servers when it starts).")
	box.add_child(warn)
	for pair in [
			[I18n.t("Claude Code on Windows"), "claude mcp add --transport http second-brain http://127.0.0.1:%d/mcp --header \"Authorization: Bearer %s\"" % [port, token]],
			[I18n.t("Claude Code in WSL (through a small relay, no network setting)"), "claude mcp add second-brain -- \"%s\" \"%s\" --client %s" % [wsl_py, relay, str(c.get("id", ""))]]]:
		var head := Label.new()
		head.theme_type_variation = "Muted"
		head.text = str(pair[0])
		box.add_child(head)
		var line := HBoxContainer.new()
		var edit := LineEdit.new()
		edit.editable = false
		edit.secret = str(pair[1]).contains(token) and token != ""
		edit.text = str(pair[1])
		edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		line.add_child(edit)
		var copy := Button.new()
		copy.text = I18n.t("Copy")
		var cmd := str(pair[1])
		copy.pressed.connect(func() -> void:
			DisplayServer.clipboard_set(cmd)
			copy.text = I18n.t("Copied"))
		line.add_child(copy)
		box.add_child(line)
