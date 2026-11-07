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
	tooltip_text = I18n.t("MCP: no AI tool connected yet. Click to connect one (Claude Code, Codex, Copilot…).")
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
		tooltip_text = I18n.t("MCP: no AI tool connected yet. Click to connect one (Claude Code, Codex, Copilot…).") if (status.get("clients", []) as Array).is_empty() \
			else I18n.t("MCP in: %d tools connected, no call yet") % (status.get("clients", []) as Array).size()
	else:
		tooltip_text = I18n.t("MCP in · last call: %s · %s") % [str(last.get("client", "")), str(last.get("tool", ""))] \
			+ "\n" + _out_tip(out, out_last)
	if waiting > 0:
		tooltip_text += "\n" + I18n.t("%d proposals wait for your approval") % waiting
	queue_redraw()


func _out_tip(out: Dictionary, out_last: Dictionary) -> String:
	var act: Array = out.get("active", [])
	if not act.is_empty():
		var a0: Dictionary = act[0]
		return I18n.t("MCP out · now: %s · %s") % [str(a0.get("client", "")), str(a0.get("tool", ""))] + (" · " + str(a0.get("progress", "")) if str(a0.get("progress", "")) != "" else "")
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


## Two tabs (Loop UX-A): « ⇠ who may read your Brain » (AI tools connected, proposals, commands, recent calls) and
## « ⇢ tools for your agents » (servers as folded cards, then « add a tool »). `tab` is "in", "out" or "" (the tab
## with something waiting for you, else « in »).
func open_dialog(tab: String = "") -> AcceptDialog:
	if dialog != null and is_instance_valid(dialog):
		dialog.queue_free()
	var dlg := AcceptDialog.new()
	dialog = dlg
	dlg.name = "McpDialog"
	dlg.title = I18n.t("AI tools and your Brain")
	dlg.theme = app.theme
	dlg.add_theme_stylebox_override("panel", SbTheme.box(SbTheme.PANEL, 0, SbTheme.BORDER, 1, 18))
	dlg.ok_button_text = I18n.t("Close")
	var outer := VBoxContainer.new()
	outer.add_theme_constant_override("separation", 12)
	dlg.add_child(outer)
	var tabs := HBoxContainer.new()
	tabs.name = "Tabs"
	tabs.add_theme_constant_override("separation", 6)
	outer.add_child(tabs)
	var group := ButtonGroup.new()
	var tab_in := Button.new()
	tab_in.name = "TabIn"
	var tab_out := Button.new()
	tab_out.name = "TabOut"
	for tb in [tab_in, tab_out]:
		(tb as Button).toggle_mode = true
		(tb as Button).button_group = group
		tabs.add_child(tb)
	tab_in.tooltip_text = I18n.t("An AI tool (Claude Code, Codex, Copilot…) reads your Brain from outside")
	tab_out.tooltip_text = I18n.t("Outside services your agents may use when you ask them something")
	var gap := Control.new()
	gap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	tabs.add_child(gap)
	var tl := Button.new()
	tl.name = "TimelineButton"
	tl.theme_type_variation = "GhostButton"
	tl.text = I18n.t("Timeline of changes…")
	tl.tooltip_text = I18n.t("Who changed what, restore points, go back to a moment")
	tl.pressed.connect(open_timeline)
	tabs.add_child(tl)
	var scroll := ScrollContainer.new()  # each tab scrolls on its own; the tabs stay in view
	scroll.custom_minimum_size = Vector2(720, 560)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	outer.add_child(scroll)
	var pages := VBoxContainer.new()
	pages.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(pages)
	var page_in := VBoxContainer.new()
	page_in.name = "PageIn"
	var page_out := VBoxContainer.new()
	page_out.name = "PageOut"
	for pg in [page_in, page_out]:
		(pg as VBoxContainer).custom_minimum_size = Vector2(690, 0)
		(pg as VBoxContainer).size_flags_horizontal = Control.SIZE_EXPAND_FILL
		(pg as VBoxContainer).add_theme_constant_override("separation", 12)
		pages.add_child(pg)
	var show_tab := func(which: String) -> void:
		page_in.visible = which == "in"
		page_out.visible = which == "out"
		tab_in.set_pressed_no_signal(which == "in")
		tab_out.set_pressed_no_signal(which == "out")
		for tb in [tab_in, tab_out]:
			(tb as Button).theme_type_variation = "PrimaryButton" if (tb as Button).button_pressed else "Button"
		scroll.scroll_vertical = 0
	tab_in.pressed.connect(func() -> void: show_tab.call("in"))
	tab_out.pressed.connect(func() -> void: show_tab.call("out"))
	dlg.set_meta("show_tab", show_tab)
	# ⇠ in
	var intro := Label.new()
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.theme_type_variation = "Muted"
	intro.text = I18n.t("Any AI tool that speaks MCP (Claude Code, Codex, GitHub Copilot in VS Code, Cursor…) can read and search your Brain, on this computer only. It never writes directly: what it suggests goes through the archivist, and you decide.")
	page_in.add_child(intro)
	var props_box := VBoxContainer.new()
	props_box.name = "Proposals"
	props_box.add_theme_constant_override("separation", 6)
	page_in.add_child(props_box)
	var list := VBoxContainer.new()
	list.name = "Clients"
	list.add_theme_constant_override("separation", 8)
	page_in.add_child(list)
	var add_head := Label.new()
	add_head.theme_type_variation = "Overline"
	add_head.text = I18n.t("CONNECT A NEW TOOL")
	page_in.add_child(add_head)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	page_in.add_child(row)
	var commands := VBoxContainer.new()
	commands.name = "Commands"
	commands.add_theme_constant_override("separation", 6)
	var kind_pick := OptionButton.new()
	kind_pick.name = "ClientKind"
	kind_pick.tooltip_text = I18n.t("Which tool: its connection command or settings are shown once connected")
	for k in CLIENT_KINDS:
		kind_pick.add_item(I18n.t("Another MCP client") if k == "other" else str(CLIENT_KINDS[k]))
		kind_pick.set_item_metadata(kind_pick.item_count - 1, k)
	row.add_child(kind_pick)
	var name_edit := LineEdit.new()
	name_edit.name = "ClientName"
	name_edit.text = "Claude Code"
	kind_pick.item_selected.connect(func(i: int) -> void:
		var k := str(kind_pick.get_item_metadata(i))
		name_edit.text = str(CLIENT_KINDS[k]) if k != "other" else I18n.t("My AI tool")
		if commands.has_meta("client"):
			_show_commands(commands, commands.get_meta("client"), k))
	name_edit.tooltip_text = I18n.t("A name to recognise it in the timeline")
	name_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(name_edit)
	var connect_b := Button.new()
	connect_b.name = "ConnectButton"
	connect_b.text = I18n.t("Connect (read only)")
	connect_b.theme_type_variation = "PrimaryButton"
	row.add_child(connect_b)
	page_in.add_child(commands)
	var recent_b := Button.new()
	recent_b.name = "RecentToggle"
	recent_b.theme_type_variation = "GhostButton"
	recent_b.alignment = HORIZONTAL_ALIGNMENT_LEFT
	recent_b.visible = false
	page_in.add_child(recent_b)
	var recent := RichTextLabel.new()
	recent.name = "Recent"
	recent.bbcode_enabled = true
	recent.fit_content = true
	recent.visible = false
	recent.custom_minimum_size = Vector2(660, 0)
	page_in.add_child(recent)
	recent_b.pressed.connect(func() -> void:
		recent.visible = not recent.visible
		recent_b.text = recent_b.text.replace("▸", "▾") if recent.visible else recent_b.text.replace("▾", "▸"))
	# ⇢ out
	var out_box := VBoxContainer.new()
	out_box.name = "Servers"
	out_box.add_theme_constant_override("separation", 10)
	page_out.add_child(out_box)
	show_tab.call("out" if tab == "out" else "in")
	var fill := func() -> void:
		for c in list.get_children():
			c.queue_free()
		var res := await app.backend.api.call_api("/mcp/status")
		if not res["ok"] or not is_instance_valid(list):
			return
		var st: Dictionary = res["data"]
		for cl in st.get("clients", []):
			list.add_child(_client_card(cl))
		if (st.get("clients", []) as Array).is_empty():
			var none := Label.new()
			none.theme_type_variation = "Muted"
			none.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			none.text = I18n.t("No AI tool connected yet.")
			list.add_child(none)
		var b := PackedStringArray()
		for r in st.get("recent", []):
			var x: Dictionary = r
			b.append("[color=#%s]%s[/color]  %s · %s · %d ms" % [SbTheme.MUTED.to_html(false), str(x.get("at", "")).substr(11, 8),
				str(x.get("client", "")), str(x.get("tool", "")), int(x.get("ms", 0))])
		recent.text = "\n".join(b)
		recent_b.visible = not b.is_empty()
		recent_b.text = ("▾ " if recent.visible else "▸ ") + I18n.t("Recent calls (%d)") % b.size()
		var n_props := await _fill_proposals(props_box)
		var n_wait := await _fill_servers(out_box)
		if not is_instance_valid(tab_in):
			return
		tab_in.text = I18n.t("⇠ Who may read your Brain") + (" (%d)" % n_props if n_props > 0 else "")
		tab_out.text = I18n.t("⇢ Tools for your agents") + (" (%d)" % n_wait if n_wait > 0 else "")
		if tab == "" and n_props == 0 and n_wait > 0:
			show_tab.call("out")
	connect_b.pressed.connect(func() -> void:
		var res := await app.backend.api.call_api("/mcp/clients", true, HTTPClient.METHOD_POST,
			JSON.stringify({"name": name_edit.text.strip_edges(), "level": "read"}))
		if not res["ok"]:
			return
		commands.set_meta("client", res["data"])
		_show_commands(commands, res["data"], str(kind_pick.get_item_metadata(kind_pick.selected)))
		fill.call())
	tab_in.text = I18n.t("⇠ Who may read your Brain")
	tab_out.text = I18n.t("⇢ Tools for your agents")
	app.get_tree().root.add_child(dlg)
	dlg.popup_centered_clamped(Vector2i(770, 700))
	fill.call()
	return dlg


## Switches the open window to a tab ("in" or "out"): for the captures and the guides.
func show_tab(which: String) -> void:
	if dialog != null and is_instance_valid(dialog) and dialog.has_meta("show_tab"):
		(dialog.get_meta("show_tab") as Callable).call(which)


## One connected AI tool: its name and use, what it may do (plain words), apply without asking, disconnect.
func _client_card(cl: Variant) -> Control:
	var d: Dictionary = cl
	var card := PanelContainer.new()
	card.theme_type_variation = "Inset"
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 6)
	card.add_child(v)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 8)
	v.add_child(head)
	var l := Label.new()
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.text = str(d["name"])
	head.add_child(l)
	var use := Label.new()
	use.theme_type_variation = "Muted"
	use.text = (I18n.t("%d calls") % int(d.get("calls", 0))) if d.get("last_seen") != null else I18n.t("never used")
	head.add_child(use)
	var rv := Button.new()
	rv.text = I18n.t("Disconnect")
	rv.theme_type_variation = "GhostButton"
	rv.tooltip_text = I18n.t("Revokes its token: it can no longer reach the Brain")
	var cid := str(d["id"])
	rv.pressed.connect(func() -> void:
		await app.backend.api.call_api("/mcp/clients/" + cid, true, HTTPClient.METHOD_DELETE)
		card.queue_free())
	head.add_child(rv)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 10)
	v.add_child(line)
	var may := Label.new()
	may.theme_type_variation = "Muted"
	may.text = I18n.t("It may:")
	line.add_child(may)
	var lv := OptionButton.new()
	for k in ["read", "propose_items", "propose_changes"]:
		lv.add_item(_level(k))
		lv.set_item_metadata(lv.item_count - 1, k)
		if k == str(d["level"]):
			lv.select(lv.item_count - 1)
	line.add_child(lv)
	var dc := CheckBox.new()
	dc.text = I18n.t("apply its suggestions without asking me")
	dc.tooltip_text = I18n.t("Its proposals are applied at once (still through the archivist, still undoable). Off: they wait for your approval.")
	dc.button_pressed = int(d.get("direct", 0)) == 1
	dc.visible = str(d["level"]) != "read"
	line.add_child(dc)
	var save_level := func() -> void:
		dc.visible = str(lv.get_item_metadata(lv.selected)) != "read"
		await app.backend.api.call_api("/mcp/clients/%s/level" % cid, true, HTTPClient.METHOD_POST,
			JSON.stringify({"level": str(lv.get_item_metadata(lv.selected)), "direct": dc.button_pressed}))
	lv.item_selected.connect(func(_i: int) -> void: save_level.call())
	dc.toggled.connect(func(_on: bool) -> void: save_level.call())
	return card


## Proposals waiting for approval: what, who, why; approve or reject one by one, or all at once.
func _fill_proposals(box: VBoxContainer) -> int:
	for c in box.get_children():
		c.queue_free()
	var res := await app.backend.api.call_api("/mcp/proposals?status=pending")
	if not res["ok"] or not is_instance_valid(box):
		return 0
	var items: Array = (res["data"] as Dictionary).get("proposals", [])
	if items.is_empty():
		return 0
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
	return items.size()


## ⇢ out: what waits for you first (a server's question, a call to confirm, a warning), then the servers as folded
## cards, then « add a tool »: the catalogue checked by hand, the official registry search, a local program (advanced).
## Returns how many things wait for the user (for the tab's count).
func _fill_servers(box: VBoxContainer) -> int:
	for c in box.get_children():
		c.queue_free()
	var res := await app.backend.api.call_api("/mcp/servers")
	var ag := await app.backend.api.call_api("/assistant/agents")
	if not res["ok"] or not is_instance_valid(box):
		return 0
	var data: Dictionary = res["data"]
	var agents_list: Array = (ag["data"] as Dictionary).get("agents", []) if ag["ok"] else []
	var intro := Label.new()
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.theme_type_variation = "Muted"
	intro.text = I18n.t("Outside services your agents may use when you ask them something (documentation, search, your accounts). Anything that writes outside asks you first.")
	box.add_child(intro)
	for qu in data.get("questions", []):
		box.add_child(_question_row(qu, box))
	for cf in data.get("confirmations", []):
		box.add_child(_confirm_row(cf, box))
	for rk in data.get("risks", []):
		var w := Label.new()
		w.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		w.add_theme_color_override("font_color", SbTheme.WARM)
		w.text = I18n.t("⚠ %s reads your Brain and may write outside with %s: each such call waits for your confirmation.") % [
			str((rk as Dictionary).get("name", "")), ", ".join(PackedStringArray((rk as Dictionary).get("servers", [])))]
		box.add_child(w)
	var mine := Label.new()
	mine.theme_type_variation = "Overline"
	mine.text = I18n.t("YOUR TOOLS")
	box.add_child(mine)
	for sv in data.get("servers", []):
		box.add_child(_server_row(sv, agents_list, box))
	if (data.get("servers", []) as Array).is_empty():
		var none := Label.new()
		none.theme_type_variation = "Muted"
		none.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		none.text = I18n.t("None yet. Add one below: your agents can use it right away.")
		box.add_child(none)
	if not (status.get("out", {}) as Dictionary).get("active", []).is_empty():
		var stop := Button.new()
		stop.text = I18n.t("Stop the calls under way")
		stop.pressed.connect(func() -> void: await app.backend.api.call_api("/mcp/out/stop", true, HTTPClient.METHOD_POST, "{}"))
		box.add_child(stop)
	var add_head := Label.new()
	add_head.theme_type_variation = "Overline"
	add_head.text = I18n.t("ADD A TOOL")
	box.add_child(add_head)
	var cat := Label.new()
	cat.theme_type_variation = "Muted"
	cat.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	cat.text = I18n.t("Checked by hand, no account needed:")
	box.add_child(cat)
	var sugg := HFlowContainer.new()
	sugg.add_theme_constant_override("h_separation", 6)
	sugg.add_theme_constant_override("v_separation", 6)
	box.add_child(sugg)
	for sg in data.get("suggested", []):
		var g: Dictionary = sg
		var add := Button.new()
		add.name = "AddSuggested"
		add.text = I18n.t("+ Connect %s") % str(g.get("name", ""))
		add.tooltip_text = "%s · %s\n%s" % [str(g.get("publisher", "")), I18n.t("no account"), str(g.get("about", ""))]
		add.pressed.connect(func() -> void:
			add.disabled = true
			add.text = I18n.t("Connecting…")
			await app.backend.api.call_api("/mcp/servers", true, HTTPClient.METHOD_POST, JSON.stringify(
				{"name": str(g["name"]), "url": str(g["url"]), "publisher": str(g.get("publisher", ""))}))
			await _fill_servers(box)
			poll())
		sugg.add_child(add)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	var q := LineEdit.new()
	q.name = "CatalogSearch"
	q.placeholder_text = I18n.t("Or find another (notion, github, weather…) or paste its address https://…")
	q.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(q)
	var go := Button.new()
	go.text = I18n.t("Search")
	row.add_child(go)
	box.add_child(row)
	var results := VBoxContainer.new()
	results.name = "CatalogResults"
	results.visible = false  # an empty box would still take a gap
	box.add_child(results)
	var err := Label.new()
	err.theme_type_variation = "Muted"
	err.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	err.visible = false
	box.add_child(err)
	var say := func(text: String) -> void:
		err.text = text
		err.visible = text != ""
	var adv := Button.new()
	adv.name = "LocalToggle"
	adv.theme_type_variation = "GhostButton"
	adv.alignment = HORIZONTAL_ALIGNMENT_LEFT
	adv.text = "▸ " + I18n.t("Advanced: a program on this computer")
	box.add_child(adv)
	var lbox := VBoxContainer.new()
	lbox.visible = false
	box.add_child(lbox)
	adv.pressed.connect(func() -> void:
		lbox.visible = not lbox.visible
		adv.text = ("▾ " if lbox.visible else "▸ ") + I18n.t("Advanced: a program on this computer"))
	var lhelp := Label.new()
	lhelp.theme_type_variation = "Muted"
	lhelp.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	lhelp.text = I18n.t("For developers: the exact command, with a pinned version. Nothing runs before you approve it, and the Brain never installs anything.")
	lbox.add_child(lhelp)
	var lrow := HBoxContainer.new()
	lrow.add_theme_constant_override("separation", 6)
	var lcmd := LineEdit.new()
	lcmd.placeholder_text = "npx -y @scope/server@1.2.3"
	lcmd.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lrow.add_child(lcmd)
	var ladd := Button.new()
	ladd.text = I18n.t("Prepare")
	ladd.pressed.connect(func() -> void:
		var r := await app.backend.api.call_api("/mcp/servers/local", true, HTTPClient.METHOD_POST, JSON.stringify({"name": "", "command": lcmd.text.strip_edges()}))
		if not r["ok"]:
			lcmd.text = ""
			lcmd.placeholder_text = str((r["data"] as Dictionary).get("detail", r["error"]))
			return
		await _fill_servers(box))
	lrow.add_child(ladd)
	lbox.add_child(lrow)
	var do_search := func() -> void:
		var text := q.text.strip_edges()
		say.call("")
		results.visible = false
		for c in results.get_children():
			c.queue_free()
		if text.begins_with("https://") or text.begins_with("http://127.0.0.1"):
			var r := await app.backend.api.call_api("/mcp/servers", true, HTTPClient.METHOD_POST, JSON.stringify({"name": "", "url": text}))
			if not r["ok"]:
				say.call(str((r["data"] as Dictionary).get("detail", r["error"])))
				return
			await _fill_servers(box)
			poll()
			return
		var r2 := await app.backend.api.call_api("/mcp/catalog?q=" + text.uri_encode())
		if not r2["ok"]:
			say.call(str((r2["data"] as Dictionary).get("detail", r2["error"])))
			return
		for e in ((r2["data"] as Dictionary).get("results", []) as Array).slice(0, 12):
			results.add_child(_catalog_row(e, box))
		results.visible = results.get_child_count() > 0
		if results.get_child_count() == 0:
			say.call(I18n.t("Nothing found in the registry."))
	go.pressed.connect(func() -> void: do_search.call())
	q.text_submitted.connect(func(_t: String) -> void: do_search.call())
	return (data.get("questions", []) as Array).size() + (data.get("confirmations", []) as Array).size()


static func family_label(f: String) -> String:
	return {"open": I18n.t("no account"), "key": I18n.t("key needed"), "signin": I18n.t("account sign-in"),
		"local": I18n.t("local program")}.get(f, f)


func _catalog_row(e: Variant, box: VBoxContainer) -> Control:
	var d: Dictionary = e
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 6)
	var l := Label.new()
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.clip_text = true
	l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	l.text = "%s · %s · %s" % [str(d.get("name", "")), family_label(str(d.get("family", ""))), str(d.get("publisher", ""))]
	l.tooltip_text = str(d.get("about", "")) + "\n" + str(d.get("source", "")) + ("\n" + str(d.get("key_about", "")) if str(d.get("key_about", "")) != "" else "")
	line.add_child(l)
	var fam := str(d.get("family", ""))
	var key := LineEdit.new()
	key.secret = true
	key.placeholder_text = I18n.t("key") + (" (" + I18n.t("optional") + ")" if bool(d.get("key_optional", false)) else "")
	key.custom_minimum_size = Vector2(130, 0)
	key.visible = fam == "key" or bool(d.get("key_optional", false))
	line.add_child(key)
	var b := Button.new()
	b.text = I18n.t("Connect") if fam != "local" else I18n.t("Prepare (local)")
	b.tooltip_text = I18n.t("A program on this computer: nothing runs before you approve its exact command") if fam == "local" else ""
	b.pressed.connect(func() -> void:
		b.disabled = true
		if fam == "local":
			var rl := await app.backend.api.call_api("/mcp/servers/local", true, HTTPClient.METHOD_POST, JSON.stringify({
				"name": str(d.get("name", "")).left(40), "package_type": str(d.get("package_type", "")), "package_id": str(d.get("package_id", "")),
				"package_version": str(d.get("package_version", "")), "env_names": (d.get("env", []) as Array).map(func(x: Variant) -> String: return str((x as Dictionary).get("name", ""))),
				"publisher": str(d.get("publisher", "")), "source": str(d.get("source", ""))}))
			if rl["ok"]:
				await _fill_servers(box)
			else:
				b.disabled = false
				b.text = str((rl["data"] as Dictionary).get("detail", rl["error"])).left(40)
			return
		var r := await app.backend.api.call_api("/mcp/servers", true, HTTPClient.METHOD_POST, JSON.stringify({
			"name": str(d.get("name", "")).left(40), "url": str(d.get("url", "")), "key": key.text, "key_header": str(d.get("key_header", "Authorization")),
			"publisher": str(d.get("publisher", "")), "source": str(d.get("source", ""))}))
		if r["ok"]:
			await _fill_servers(box)
			poll()
		else:
			b.disabled = false
			b.text = str((r["data"] as Dictionary).get("detail", r["error"])).left(40))
	line.add_child(b)
	return line


## A server's state in plain words (one line under its name).
static func server_status(d: Dictionary) -> String:
	var tools: Array = d.get("tools", [])
	var off: Array = d.get("off", [])
	var use: Dictionary = d.get("usage", {})
	match str(d.get("status", "")):
		"ready":
			return I18n.t("Ready · %d of %d tools on · used %d times this month") % [tools.size() - off.size(), tools.size(), int(use.get("calls", 0))]
		"approval":
			return I18n.t("Waits for your approval before it starts")
		"missing":
			return I18n.t("Install %s first (the Brain never installs anything)") % str(d.get("error", "")).trim_prefix("needs ")
		"signin":
			return I18n.t("Needs you to sign in to your account")
	return I18n.t("Unreachable for now: %s") % str(d.get("error", ""))


## « read_web_page » → « Read web page ».
static func tool_label(name: String) -> String:
	var s := name.replace("_", " ").replace("-", " ").strip_edges()
	return s.left(1).to_upper() + s.substr(1) if s != "" else name


func _section(text: String) -> Label:
	var l := Label.new()
	l.theme_type_variation = "Overline"
	l.text = text
	return l


## One server as a folded card: name, plain state, who may use it, the one action it needs; « Settings » opens what
## it may do (its tools) and its access and limits (key, account, monthly limit, writing with your model, remove).
func _server_row(sv: Variant, agents_list: Array, box: VBoxContainer) -> Control:
	var d: Dictionary = sv
	var sid := str(d["id"])
	var ready := str(d.get("status", "")) == "ready"
	var needs_signin := str(d.get("status", "")) == "signin"
	var is_local := str(d.get("transport", "")) == "stdio"
	var waits := str(d.get("status", "")) == "approval"
	var missing := str(d.get("status", "")) == "missing"
	var tools: Array = d.get("tools", [])
	var off: Array = d.get("off", [])
	var use: Dictionary = d.get("usage", {})
	var card := PanelContainer.new()
	card.name = "ServerCard"
	card.theme_type_variation = "Inset"
	var wrap := VBoxContainer.new()
	wrap.add_theme_constant_override("separation", 6)
	card.add_child(wrap)
	var line := HBoxContainer.new()
	line.add_theme_constant_override("separation", 8)
	wrap.add_child(line)
	var dot := Label.new()
	dot.text = "●" if ready else "○"
	dot.add_theme_color_override("font_color", Color(0.55, 0.88, 0.65) if ready else SbTheme.WARM)
	line.add_child(dot)
	var names := VBoxContainer.new()
	names.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	names.add_theme_constant_override("separation", 0)
	line.add_child(names)
	var l := Label.new()
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.text = str(d.get("name", ""))
	l.tooltip_text = "%s\n%s%s" % [str(d.get("url", "")), str(d.get("publisher", "")), ("\n" + I18n.t("key saved")) if bool(d.get("has_key", false)) else ""]
	names.add_child(l)
	var st := Label.new()
	st.name = "ServerStatus"
	st.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	st.theme_type_variation = "Muted"
	st.text = server_status(d)
	if not ready:
		st.add_theme_color_override("font_color", SbTheme.WARM)
	names.add_child(st)
	var who := OptionButton.new()
	who.tooltip_text = I18n.t("Which agents may use it")
	who.add_item(I18n.t("All agents"))
	who.set_item_metadata(0, "*")
	var current: Array = d.get("agents", ["*"])
	for a in agents_list:
		var ad: Dictionary = a
		who.add_item(I18n.t("Only %s") % str(ad.get("name", ad.get("id", ""))))
		who.set_item_metadata(who.item_count - 1, str(ad.get("id", "")))
		if current.size() == 1 and str(current[0]) == str(ad.get("id", "")):
			who.select(who.item_count - 1)
	who.item_selected.connect(func(i: int) -> void:
		await app.backend.api.call_api("/mcp/servers/%s/agents" % sid, true, HTTPClient.METHOD_POST,
			JSON.stringify({"agents": [str(who.get_item_metadata(i))]})))
	line.add_child(who)
	var more := Button.new()
	more.name = "ServerSettings"
	more.text = "▸ " + I18n.t("Settings")
	line.add_child(more)
	if is_local:
		var cmd := Label.new()
		cmd.text = "$ " + " ".join(PackedStringArray(d.get("command", [])))
		cmd.add_theme_font_size_override("font_size", 12)
		cmd.theme_type_variation = "Muted"
		cmd.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
		wrap.add_child(cmd)
	if waits or missing or needs_signin:
		var arow := HBoxContainer.new()
		wrap.add_child(arow)
		if waits or missing:
			var ap := Button.new()
			ap.name = "Approve"
			ap.text = I18n.t("Approve and start")
			ap.theme_type_variation = "PrimaryButton"
			ap.tooltip_text = I18n.t("Runs exactly this command on this computer, with a clean environment, until the app closes")
			ap.pressed.connect(func() -> void:
				ap.disabled = true
				await app.backend.api.call_api("/mcp/servers/%s/approve" % sid, true, HTTPClient.METHOD_POST, "{}")
				await _fill_servers(box)
				poll())
			arow.add_child(ap)
		if needs_signin:
			var si := Button.new()
			si.name = "SignIn"
			si.text = I18n.t("Sign in")
			si.theme_type_variation = "PrimaryButton"
			si.tooltip_text = I18n.t("Opens the sign-in page in your browser; the Brain keeps the access in Windows' credential store")
			si.pressed.connect(func() -> void:
				si.disabled = true
				var r := await app.backend.api.call_api("/mcp/servers/%s/signin" % sid, true, HTTPClient.METHOD_POST, "{}")
				if not r["ok"]:
					si.text = str((r["data"] as Dictionary).get("detail", r["error"])).left(48)
					return
				if OS.get_environment("SBGD_NO_OPEN") == "":
					OS.shell_open(str((r["data"] as Dictionary).get("url", "")))
				si.text = I18n.t("Waiting for the sign-in…")
				for _i in 600:
					await app.get_tree().create_timer(0.5).timeout
					var ss_res := await app.backend.api.call_api("/mcp/servers/%s/signin" % sid)
					var ss := str((ss_res["data"] as Dictionary).get("status", "")) if ss_res["ok"] else ""
					if ss == "done" or ss == "failed":
						if ss == "failed":
							si.text = str((ss_res["data"] as Dictionary).get("error", "")).left(48)
							si.disabled = false
							return
						break
				if is_instance_valid(box):
					await _fill_servers(box)
				poll())
			arow.add_child(si)
	var details := VBoxContainer.new()
	details.name = "ServerDetails"
	details.visible = false
	details.add_theme_constant_override("separation", 4)
	wrap.add_child(details)
	more.pressed.connect(func() -> void:
		details.visible = not details.visible
		more.text = ("▾ " if details.visible else "▸ ") + I18n.t("Settings"))
	if not tools.is_empty():
		details.add_child(_section(I18n.t("WHAT IT MAY DO")))
	for t in tools:
		var td: Dictionary = t
		var cb := CheckBox.new()
		var tname := str(td.get("name", ""))
		cb.text = tool_label(tname) + ("   ✎ " + I18n.t("writes outside: asks you each time") if bool(td.get("write", false)) else "")
		cb.tooltip_text = tname + "\n" + str(td.get("description", "")).left(300)
		cb.button_pressed = not off.has(td.get("name", ""))
		cb.toggled.connect(func(on: bool) -> void:
			var now: Array = off.duplicate()
			if on:
				now.erase(tname)
			elif not now.has(tname):
				now.append(tname)
			off = now
			await app.backend.api.call_api("/mcp/servers/%s/off" % sid, true, HTTPClient.METHOD_POST, JSON.stringify({"off": now})))
		details.add_child(cb)
	details.add_child(_section(I18n.t("ACCESS AND LIMITS")))
	var krow := HBoxContainer.new()
	var key := LineEdit.new()
	key.secret = true
	key.placeholder_text = I18n.t("key saved (type to replace)") if bool(d.get("has_key", false)) else I18n.t("API key, if it asks for one (kept in Windows' credential store)")
	key.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	krow.add_child(key)
	var ksave := Button.new()
	ksave.text = I18n.t("Save the key")
	ksave.pressed.connect(func() -> void:
		await app.backend.api.call_api("/mcp/servers/%s/key" % sid, true, HTTPClient.METHOD_POST, JSON.stringify({"key": key.text}))
		await _fill_servers(box))
	krow.add_child(ksave)
	details.add_child(krow)
	if bool(d.get("oauth", false)):
		var so := Button.new()
		so.text = I18n.t("Disconnect the account")
		so.tooltip_text = I18n.t("Revokes the access at the service and forgets it here")
		so.pressed.connect(func() -> void:
			await app.backend.api.call_api("/mcp/servers/%s/signout" % sid, true, HTTPClient.METHOD_POST, "{}")
			await _fill_servers(box))
		details.add_child(so)
	for ev in d.get("env_names", []):
		var erow := HBoxContainer.new()
		var el := Label.new()
		el.text = str(ev)
		el.custom_minimum_size.x = 160
		erow.add_child(el)
		var evv := LineEdit.new()
		evv.secret = true
		evv.placeholder_text = I18n.t("value (kept in Windows' credential store)")
		evv.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		erow.add_child(evv)
		var es := Button.new()
		es.text = I18n.t("Save")
		var evname := str(ev)
		es.pressed.connect(func() -> void:
			await app.backend.api.call_api("/mcp/servers/%s/env" % sid, true, HTTPClient.METHOD_POST, JSON.stringify({"name": evname, "value": evv.text}))
			evv.text = ""
			evv.placeholder_text = I18n.t("saved"))
		erow.add_child(es)
		details.add_child(erow)
	var crow := HBoxContainer.new()
	crow.add_theme_constant_override("separation", 8)
	var cl := Label.new()
	cl.text = I18n.t("Monthly limit (thousands of tokens, 0 = no limit):")
	cl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	cl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	crow.add_child(cl)
	var cap := SpinBox.new()
	cap.min_value = 0
	cap.max_value = 100000
	cap.value = int(d.get("cap_tokens", 0)) / 1000
	cap.value_changed.connect(func(v: float) -> void:
		await app.backend.api.call_api("/mcp/servers/%s/cap" % sid, true, HTTPClient.METHOD_POST, JSON.stringify({"tokens": int(v) * 1000})))
	crow.add_child(cap)
	details.add_child(crow)
	var used := Label.new()
	used.theme_type_variation = "Muted"
	used.text = I18n.t("This month: %d calls, ≈ %s tokens") % [int(use.get("calls", 0)), _k(int(use.get("tokens", 0)))]
	details.add_child(used)
	var samp := CheckBox.new()
	samp.text = I18n.t("Let it ask your AI model to write (at most 20 times a month)")
	samp.tooltip_text = I18n.t("Off by default: it would use your OpenAI key")
	samp.button_pressed = bool(d.get("sampling", false))
	samp.toggled.connect(func(on: bool) -> void:
		await app.backend.api.call_api("/mcp/servers/%s/sampling" % sid, true, HTTPClient.METHOD_POST, JSON.stringify({"allow": on, "cap": 20})))
	details.add_child(samp)
	var brow := HBoxContainer.new()
	brow.add_theme_constant_override("separation", 6)
	details.add_child(brow)
	if is_local:
		var stopb := Button.new()
		stopb.text = I18n.t("Stop the program")
		stopb.pressed.connect(func() -> void: await app.backend.api.call_api("/mcp/servers/%s/stop" % sid, true, HTTPClient.METHOD_POST, "{}"))
		brow.add_child(stopb)
		var logb := Button.new()
		logb.text = I18n.t("Show its log")
		var logl := Label.new()
		logl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		logl.theme_type_variation = "Muted"
		logb.pressed.connect(func() -> void:
			var lg := await app.backend.api.call_api("/mcp/servers/%s/log" % sid)
			logl.text = "\n".join(PackedStringArray((lg["data"] as Dictionary).get("log", []))) if lg["ok"] else ""
			if logl.text == "":
				logl.text = I18n.t("(nothing yet: it starts at its first call)"))
		brow.add_child(logb)
		details.add_child(logl)
	var bgap := Control.new()
	bgap.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	brow.add_child(bgap)
	var rm := Button.new()
	rm.name = "RemoveServer"
	rm.text = I18n.t("Remove this tool")
	rm.add_theme_color_override("font_color", SbTheme.ERROR)
	rm.tooltip_text = I18n.t("Your agents can no longer use it; its key is forgotten")
	rm.pressed.connect(func() -> void:
		await app.backend.api.call_api("/mcp/servers/" + sid, true, HTTPClient.METHOD_DELETE)
		await _fill_servers(box))
	brow.add_child(rm)
	return card


static func _k(n: int) -> String:
	return ("%.1f k" % (n / 1000.0)) if n >= 1000 else str(n)


## A server's question during a call (elicitation): its message and the fields it asks, answered here.
func _question_row(qu: Variant, box: VBoxContainer) -> Control:
	var d: Dictionary = qu
	var wrap := VBoxContainer.new()
	var l := Label.new()
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size.x = 300
	l.add_theme_color_override("font_color", Color(0.95, 0.75, 0.35))
	l.text = I18n.t("%s asks (for %s): %s") % [str(d.get("server_name", "")), str(d.get("agent", "")), str(d.get("message", ""))]
	wrap.add_child(l)
	var fields: Dictionary = {}
	var props: Dictionary = ((d.get("schema", {}) as Dictionary).get("properties", {}) as Dictionary)
	for k in props:
		var spec: Dictionary = props[k]
		var row := HBoxContainer.new()
		var name_l := Label.new()
		name_l.text = str(spec.get("title", k))
		name_l.custom_minimum_size.x = 140
		row.add_child(name_l)
		var w: Control
		if spec.has("enum"):
			var ob := OptionButton.new()
			for v in spec["enum"]:
				ob.add_item(str(v))
			w = ob
		elif str(spec.get("type", "")) == "boolean":
			w = CheckBox.new()
		elif str(spec.get("type", "")) in ["number", "integer"]:
			var sb := SpinBox.new()
			sb.min_value = float(spec.get("minimum", -1000000))
			sb.max_value = float(spec.get("maximum", 1000000))
			sb.step = 1.0 if str(spec.get("type", "")) == "integer" else 0.01
			w = sb
		else:
			var le := LineEdit.new()
			le.custom_minimum_size.x = 260
			w = le
		fields[k] = w
		row.add_child(w)
		wrap.add_child(row)
	var buttons := HBoxContainer.new()
	var qid := str(d["id"])
	for choice in [["accept", I18n.t("Answer")], ["decline", I18n.t("Decline")]]:
		var b := Button.new()
		b.text = str(choice[1])
		var ch := str(choice[0])
		b.pressed.connect(func() -> void:
			var content := {}
			for k in fields:
				var w: Control = fields[k]
				if w is OptionButton:
					content[k] = (w as OptionButton).get_item_text((w as OptionButton).selected)
				elif w is CheckBox:
					content[k] = (w as CheckBox).button_pressed
				elif w is SpinBox:
					content[k] = (w as SpinBox).value
				else:
					content[k] = (w as LineEdit).text
			await app.backend.api.call_api("/mcp/questions/" + qid, true, HTTPClient.METHOD_POST, JSON.stringify({"action": ch, "content": content}))
			await _fill_servers(box)
			poll())
		buttons.add_child(b)
	wrap.add_child(buttons)
	return wrap


func _confirm_row(cf: Variant, box: VBoxContainer) -> Control:
	var d: Dictionary = cf
	var line := HBoxContainer.new()
	var l := Label.new()
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	l.custom_minimum_size.x = 300
	l.add_theme_color_override("font_color", Color(0.95, 0.75, 0.35))
	l.text = I18n.t("%s wants to use %s · %s:") % [str(d.get("agent", "")), str(d.get("server_name", "")), str(d.get("tool", ""))] + " " + JSON.stringify(d.get("args", {})).left(160)
	line.add_child(l)
	var cid := str(d["id"])
	for choice in [["approve", I18n.t("Allow once")], ["refuse", I18n.t("Refuse")]]:
		var b := Button.new()
		b.text = str(choice[1])
		var ch := str(choice[0])
		b.pressed.connect(func() -> void:
			await app.backend.api.call_api("/mcp/confirmations/%s/%s" % [cid, ch], true, HTTPClient.METHOD_POST, "{}")
			await _fill_servers(box)
			poll())
		line.add_child(b)
	return line


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
	return {"read": I18n.t("read only"), "propose_items": I18n.t("read, suggest new notes"), "propose_changes": I18n.t("read, suggest changes")}.get(level, level)


const CLIENT_KINDS := {"claude": "Claude Code", "codex": "Codex", "vscode": "VS Code (GitHub Copilot)",
	"cursor": "Cursor", "other": "Another MCP client"}


## How this client connects, with its token, shown once (only its hash is kept). Any MCP client works: over HTTP
## on 127.0.0.1 with the token, or through the stdio relay (a command the client starts; no token in its settings).
func _show_commands(box: VBoxContainer, c: Dictionary, kind: String = "claude") -> void:
	for ch in box.get_children():
		ch.queue_free()
	var port: int = app.backend.api.port
	var token := str(c.get("token", ""))
	var url := "http://127.0.0.1:%d/mcp" % port
	var relay := ProjectSettings.globalize_path("res://engine/mcp/relay.py").replace("/", "\\")
	var py := OS.get_environment("LOCALAPPDATA").path_join("SecondBrainGD/.venv/Scripts/python.exe").replace("\\", "/")
	var wsl_py := "/mnt/" + py.left(1).to_lower() + py.substr(2) if py.length() > 2 and py[1] == ":" else py
	var stdio := "\"%s\" \"%s\" --client %s" % [py.replace("/", "\\"), relay, str(c.get("id", ""))]
	var stdio_wsl := "\"%s\" \"%s\" --client %s" % [wsl_py, relay, str(c.get("id", ""))]
	var auth := "Bearer " + token
	var pairs: Array = {
		"claude": [[I18n.t("Claude Code on Windows"), "claude mcp add --transport http second-brain %s --header \"Authorization: %s\"" % [url, auth]],
			[I18n.t("Claude Code in WSL (through a small relay, no network setting)"), "claude mcp add second-brain -- " + stdio_wsl]],
		"codex": [[I18n.t("Codex on Windows"), "codex mcp add second-brain -- " + stdio],
			[I18n.t("Codex in WSL (through a small relay, no network setting)"), "codex mcp add second-brain -- " + stdio_wsl]],
		"vscode": [[I18n.t("VS Code: add to mcp.json (Command palette › MCP: Open User Configuration), then use Copilot in agent mode"),
			JSON.stringify({"servers": {"second-brain": {"type": "http", "url": url, "headers": {"Authorization": auth}}}})]],
		"cursor": [[I18n.t("Cursor: add to ~/.cursor/mcp.json"),
			JSON.stringify({"mcpServers": {"second-brain": {"url": url, "headers": {"Authorization": auth}}}})]],
		"other": [[I18n.t("Address (Streamable HTTP)"), url], [I18n.t("Header to send"), "Authorization: " + auth],
			[I18n.t("Or a command it starts (stdio relay, no key in its settings)"), stdio]],
	}.get(kind, [])
	var warn := Label.new()
	warn.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	warn.text = I18n.t("Copy it now: the key it holds is shown only this once. Then restart the tool (it sees new MCP servers when it starts).")
	box.add_child(warn)
	for pair in pairs:
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
