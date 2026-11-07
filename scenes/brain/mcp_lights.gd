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
var _last_out_call := ""
var _out_flash_until := 0.0
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
	var out: Dictionary = status["out"] if status.get("out") is Dictionary else {}
	var out_last: Dictionary = out["last"] if out.get("last") is Dictionary else {}
	var out_key := str(out_last.get("at", ""))
	if out_key != "" and out_key != _last_out_call:
		if _last_out_call != "":
			_out_flash_until = Time.get_ticks_msec() / 1000.0 + 1.4
		_last_out_call = out_key
	var out_ready := (out.get("servers", []) as Array).any(func(x: Variant) -> bool: return str((x as Dictionary).get("status", "")) == "ready")
	out_state = "busy" if not (out.get("active", []) as Array).is_empty() or Time.get_ticks_msec() / 1000.0 < _out_flash_until \
		else ("on" if out_ready else "off")
	var busy := not (status.get("active", []) as Array).is_empty() or Time.get_ticks_msec() / 1000.0 < _flash_until
	var connected := not (status.get("connected", []) as Array).is_empty()
	in_state = "busy" if busy else ("on" if connected or not (status.get("clients", []) as Array).is_empty() else "off")
	var waiting := int(status.get("pending", 0))
	if last.is_empty() and not out_last.is_empty():
		tooltip_text = _out_tip(out, out_last)
	elif last.is_empty():
		tooltip_text = I18n.t("MCP: no AI tool connected yet. Click to connect Claude Code.") if (status.get("clients", []) as Array).is_empty() \
			else I18n.t("MCP in: %d tools connected, no call yet") % (status.get("clients", []) as Array).size()
	else:
		tooltip_text = I18n.t("MCP in · last call: %s · %s") % [str(last.get("client", "")), str(last.get("tool", ""))] \
			+ "\n" + _out_tip(out, out_last)
	if waiting > 0:
		tooltip_text += "\n" + I18n.t("%d proposals wait for your approval") % waiting
	queue_redraw()


func _out_tip(out: Dictionary, out_last: Dictionary) -> String:
	if not out_last.is_empty():
		return I18n.t("MCP out · last call: %s · %s") % [str(out_last.get("client", "")), str(out_last.get("tool", ""))]
	var n := (out.get("servers", []) as Array).size()
	return I18n.t("MCP out: no server connected yet") if n == 0 else I18n.t("MCP out: %d servers ready for the agents") % n


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
	var pending := int(status.get("pending", 0))
	if pending > 0:  # proposals waiting for approval: a small count by the « in » light
		var bp := Vector2(31, y - 9)
		draw_circle(bp, 7.0, Color(0.95, 0.75, 0.35))
		draw_string(font, bp + Vector2(-3.5 if pending < 10 else -7.0, 4), str(mini(pending, 99)), HORIZONTAL_ALIGNMENT_LEFT, -1, 10, Color(0.1, 0.1, 0.1))


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
	var tl := Button.new()
	tl.name = "TimelineButton"
	tl.text = I18n.t("Timeline of changes…")
	tl.tooltip_text = I18n.t("Who changed what, restore points, go back to a moment")
	tl.pressed.connect(open_timeline)
	row.add_child(tl)
	var commands := VBoxContainer.new()
	commands.name = "Commands"
	commands.add_theme_constant_override("separation", 6)
	box.add_child(commands)
	var props_box := VBoxContainer.new()
	props_box.name = "Proposals"
	box.add_child(props_box)
	var out_box := VBoxContainer.new()
	out_box.name = "Servers"
	out_box.add_theme_constant_override("separation", 6)
	box.add_child(out_box)
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
			l.clip_text = true
			l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
			l.custom_minimum_size.x = 160
			l.tooltip_text = str(d["name"])
			l.text = "%s · %s" % [str(d["name"]),
				(I18n.t("%d calls") % int(d.get("calls", 0))) if d.get("last_seen") != null else I18n.t("never used")]
			line.add_child(l)
			var lv := OptionButton.new()
			for k in ["read", "propose_items", "propose_changes"]:
				lv.add_item(_level(k))
				lv.set_item_metadata(lv.item_count - 1, k)
				if k == str(d["level"]):
					lv.select(lv.item_count - 1)
			var dc := CheckBox.new()
			dc.text = I18n.t("without waiting")
			dc.tooltip_text = I18n.t("Its proposals are applied at once (still through the archivist, still undoable). Off: they wait for your approval.")
			dc.button_pressed = int(d.get("direct", 0)) == 1
			var cid0 := str(d["id"])
			var save_level := func() -> void:
				await app.backend.api.call_api("/mcp/clients/%s/level" % cid0, true, HTTPClient.METHOD_POST,
					JSON.stringify({"level": str(lv.get_item_metadata(lv.selected)), "direct": dc.button_pressed}))
			lv.item_selected.connect(func(_i: int) -> void: save_level.call())
			dc.toggled.connect(func(_on: bool) -> void: save_level.call())
			line.add_child(lv)
			line.add_child(dc)
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
		await _fill_proposals(props_box)
		await _fill_servers(out_box)
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


## Proposals waiting for approval: what, who, why; approve or reject one by one, or all at once.
func _fill_proposals(box: VBoxContainer) -> void:
	for c in box.get_children():
		c.queue_free()
	var res := await app.backend.api.call_api("/mcp/proposals?status=pending")
	if not res["ok"] or not is_instance_valid(box):
		return
	var items: Array = (res["data"] as Dictionary).get("proposals", [])
	if items.is_empty():
		return
	var head := HBoxContainer.new()
	var t := Label.new()
	t.theme_type_variation = "Heading"
	t.text = I18n.t("%d proposals wait for your approval") % items.size()
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(t)
	var all := Button.new()
	all.name = "ApproveAll"
	all.text = I18n.t("Approve all")
	all.theme_type_variation = "PrimaryButton"
	all.pressed.connect(func() -> void:
		await app.backend.api.call_api("/mcp/proposals/all/approve", true, HTTPClient.METHOD_POST, "{}")
		await _fill_proposals(box)
		_changed())
	head.add_child(all)
	box.add_child(head)
	for p in items.slice(0, 30):
		var d: Dictionary = p
		var line := HBoxContainer.new()
		var l := Label.new()
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.custom_minimum_size.x = 300
		l.text = "%s · %s\n%s" % [str(d.get("client_name", "")), str(d.get("summary", "")), str((d.get("payload", {}) as Dictionary).get("reason", ""))]
		line.add_child(l)
		var pid := str(d["id"])
		for choice in [["approve", I18n.t("Approve")], ["reject", I18n.t("Reject")]]:
			var b := Button.new()
			b.text = str(choice[1])
			var ch := str(choice[0])
			b.pressed.connect(func() -> void:
				await app.backend.api.call_api("/mcp/proposals/%s/%s" % [pid, ch], true, HTTPClient.METHOD_POST, "{}")
				await _fill_proposals(box)
				_changed())
			line.add_child(b)
		box.add_child(line)


## ⇢ out: the MCP servers the agents may use (Microsoft Learn suggested), who may use each, add or remove one.
func _fill_servers(box: VBoxContainer) -> void:
	for c in box.get_children():
		c.queue_free()
	var res := await app.backend.api.call_api("/mcp/servers")
	var ag := await app.backend.api.call_api("/assistant/agents")
	if not res["ok"] or not is_instance_valid(box):
		return
	var agents_list: Array = (ag["data"] as Dictionary).get("agents", []) if ag["ok"] else []
	var head := Label.new()
	head.theme_type_variation = "Heading"
	head.text = I18n.t("MCP servers for your agents (⇢ out)")
	box.add_child(head)
	for sv in (res["data"] as Dictionary).get("servers", []):
		var d: Dictionary = sv
		var line := HBoxContainer.new()
		line.add_theme_constant_override("separation", 8)
		var l := Label.new()
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		l.clip_text = true
		l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		var dot := "●" if str(d.get("status", "")) == "ready" else "○"
		l.text = "%s %s · %s" % [dot, str(d.get("name", "")), I18n.t("%d tools") % (d.get("tools", []) as Array).size() if str(d.get("status", "")) == "ready" else I18n.t("unreachable: %s") % str(d.get("error", ""))]
		l.add_theme_color_override("font_color", Color(0.55, 0.88, 0.65) if str(d.get("status", "")) == "ready" else SbTheme.WARM)
		l.tooltip_text = str(d.get("url", "")) + "\n" + ", ".join(PackedStringArray((d.get("tools", []) as Array).map(func(t: Variant) -> String: return str((t as Dictionary).get("name", "")))))
		line.add_child(l)
		var who := OptionButton.new()
		who.add_item(I18n.t("All agents"))
		who.set_item_metadata(0, "*")
		var current: Array = d.get("agents", ["*"])
		for a in agents_list:
			var ad: Dictionary = a
			who.add_item(I18n.t("Only %s") % str(ad.get("name", ad.get("id", ""))))
			who.set_item_metadata(who.item_count - 1, str(ad.get("id", "")))
			if current.size() == 1 and str(current[0]) == str(ad.get("id", "")):
				who.select(who.item_count - 1)
		var sid := str(d["id"])
		who.item_selected.connect(func(i: int) -> void:
			await app.backend.api.call_api("/mcp/servers/%s/agents" % sid, true, HTTPClient.METHOD_POST,
				JSON.stringify({"agents": [str(who.get_item_metadata(i))]})))
		line.add_child(who)
		var rm := Button.new()
		rm.text = I18n.t("Remove")
		rm.pressed.connect(func() -> void:
			await app.backend.api.call_api("/mcp/servers/" + sid, true, HTTPClient.METHOD_DELETE)
			await _fill_servers(box))
		line.add_child(rm)
		box.add_child(line)
	for sg in (res["data"] as Dictionary).get("suggested", []):
		var g: Dictionary = sg
		var add := Button.new()
		add.name = "AddSuggested"
		add.text = I18n.t("+ Connect %s") % str(g.get("name", ""))
		add.tooltip_text = str(g.get("about", ""))
		add.pressed.connect(func() -> void:
			add.disabled = true
			add.text = I18n.t("Connecting…")
			await app.backend.api.call_api("/mcp/servers", true, HTTPClient.METHOD_POST, JSON.stringify({"name": str(g["name"]), "url": str(g["url"])}))
			await _fill_servers(box)
			poll())
		box.add_child(add)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var url := LineEdit.new()
	url.placeholder_text = I18n.t("Another server: https://…/mcp")
	url.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(url)
	var other := Button.new()
	other.text = I18n.t("Connect")
	var err := Label.new()
	err.theme_type_variation = "Muted"
	err.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	other.pressed.connect(func() -> void:
		var r := await app.backend.api.call_api("/mcp/servers", true, HTTPClient.METHOD_POST, JSON.stringify({"name": "", "url": url.text.strip_edges()}))
		if not r["ok"]:
			err.text = str((r["data"] as Dictionary).get("detail", r["error"]))
			return
		await _fill_servers(box)
		poll())
	row.add_child(other)
	box.add_child(row)
	box.add_child(err)


func _changed() -> void:
	var brain := get_parent()
	while brain != null and not brain.has_method("refresh_graph"):
		brain = brain.get_parent()
	if brain != null:
		brain.call("refresh_graph")
	poll()


var timeline: AcceptDialog   # tests


func open_timeline() -> AcceptDialog:
	if timeline != null and is_instance_valid(timeline):
		timeline.queue_free()
	timeline = preload("res://scenes/brain/timeline_dialog.gd").new().setup(app)
	timeline.connect("changed", func() -> void: _changed())
	app.get_tree().root.add_child(timeline)
	timeline.call("open")
	return timeline


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
