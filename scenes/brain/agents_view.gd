class_name AgentsView
extends PanelContainer
## The agent room: Codex agents working in folders the user chose. The engine drives
## the agent; this view lists folders and sessions, streams what the agent says and
## does, and shows an approval card for every file change or command it asks for.

signal failed(message: String)

const POLL_S := 0.5

var app: SbApp
var status_label: Label
var install_button: Button
var folders_box: VBoxContainer
var sessions_box: VBoxContainer
var transcript: RichTextLabel
var approvals_box: VBoxContainer
var input_edit: LineEdit
var send_button: Button
var stop_button: Button
var session_title: Label
var info: Dictionary = {}
var current_id := ""
var seq := 0
var entries: Array = []          # [{key, text}] rendered in order
var pending: Array = []          # approvals waiting for the user
var session_status := ""
var _poll: Timer
var _dir_dialog: FileDialog


func setup(a: SbApp) -> AgentsView:
	app = a
	theme_type_variation = "Glass"
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)
	add_child(col)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 12)
	col.add_child(head)
	var htext := VBoxContainer.new()
	htext.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(htext)
	var over := Label.new()
	over.text = "AGENT ROOM"
	over.theme_type_variation = "Overline"
	htext.add_child(over)
	var title := Label.new()
	title.text = "Agents that work in your folders, with your approval"
	title.theme_type_variation = "Heading"
	htext.add_child(title)
	status_label = Label.new()
	status_label.theme_type_variation = "Muted"
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	htext.add_child(status_label)
	install_button = Button.new()
	install_button.text = "Install agents"
	install_button.visible = false
	install_button.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	install_button.pressed.connect(install)
	head.add_child(install_button)

	var body := HBoxContainer.new()
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 18)
	col.add_child(body)
	var left := VBoxContainer.new()
	left.custom_minimum_size = Vector2(300, 0)
	left.add_theme_constant_override("separation", 8)
	body.add_child(left)
	var fl := Label.new()
	fl.text = "FOLDERS AGENTS MAY USE"
	fl.theme_type_variation = "Overline"
	left.add_child(fl)
	folders_box = VBoxContainer.new()
	folders_box.add_theme_constant_override("separation", 4)
	left.add_child(folders_box)
	var add := Button.new()
	add.text = "+ Add a folder"
	add.theme_type_variation = "GhostButton"
	add.tooltip_text = "Agents can only read and propose changes inside folders listed here."
	add.pressed.connect(_pick_folder)
	left.add_child(add)
	var sl := Label.new()
	sl.text = "SESSIONS"
	sl.theme_type_variation = "Overline"
	left.add_child(sl)
	sessions_box = VBoxContainer.new()
	sessions_box.add_theme_constant_override("separation", 2)
	left.add_child(sessions_box)

	var right := VBoxContainer.new()
	right.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	right.add_theme_constant_override("separation", 8)
	body.add_child(right)
	session_title = Label.new()
	session_title.theme_type_variation = "Muted"
	session_title.text = "Start an agent in one of your folders."
	right.add_child(session_title)
	transcript = RichTextLabel.new()
	transcript.bbcode_enabled = true
	transcript.scroll_following = true
	transcript.selection_enabled = true
	transcript.size_flags_vertical = Control.SIZE_EXPAND_FILL
	right.add_child(transcript)
	approvals_box = VBoxContainer.new()
	approvals_box.add_theme_constant_override("separation", 6)
	right.add_child(approvals_box)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	right.add_child(row)
	input_edit = LineEdit.new()
	input_edit.placeholder_text = "Ask the agent…  (Enter to send)"
	input_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input_edit.text_submitted.connect(func(t: String) -> void: send_message(t))
	row.add_child(input_edit)
	send_button = Button.new()
	send_button.text = "Send"
	send_button.pressed.connect(func() -> void: send_message(input_edit.text))
	row.add_child(send_button)
	stop_button = Button.new()
	stop_button.text = "Stop"
	stop_button.theme_type_variation = "GhostButton"
	stop_button.tooltip_text = "Interrupt the current turn"
	stop_button.pressed.connect(func() -> void:
		if current_id != "":
			await app.backend.api.call_api("/agents/sessions/%s/interrupt" % current_id, true, HTTPClient.METHOD_POST, "{}"))
	row.add_child(stop_button)
	_poll = Timer.new()
	_poll.wait_time = POLL_S
	_poll.timeout.connect(_on_poll)
	add_child(_poll)
	_update_controls()
	return self


func refresh() -> void:
	var res := await app.backend.api.call_api("/agents/status")
	if not res["ok"] or not is_inside_tree():
		status_label.text = "Agent room: Not available (%s)" % str(res.get("error", ""))
		return
	info = res["data"]
	var job: Dictionary = info.get("install", {})
	if bool(info.get("installed", false)):
		status_label.text = "Codex %s · model %s · every change waits for your approval" % [info.get("version", "?"), info.get("agents_model", "?")]
	elif bool(job.get("running", false)):
		status_label.text = str(job.get("message", "Installing…"))
	elif job.get("error") != null:
		status_label.text = "Install failed: %s" % str(job.get("error"))
	else:
		status_label.text = "Agents are not installed yet (download of about 160 MB, fingerprint checked)."
	install_button.visible = not bool(info.get("installed", false)) and not bool(job.get("running", false))
	_render_folders()
	_render_sessions()
	if bool(job.get("running", false)) and is_visible_in_tree():
		get_tree().create_timer(1.0).timeout.connect(refresh)


func install() -> void:
	install_button.visible = false
	await app.backend.api.call_api("/agents/install", true, HTTPClient.METHOD_POST, "{}")
	await refresh()


func add_folder(path: String) -> bool:
	var res := await app.backend.api.call_api("/agents/folders", true, HTTPClient.METHOD_POST, JSON.stringify({"path": path}))
	if not res["ok"]:
		failed.emit(str((res["data"] as Dictionary).get("detail", res["error"])))
		return false
	await refresh()
	return true


func start_session(cwd: String) -> bool:
	status_label.text = "Starting an agent in %s…" % cwd
	var res := await app.backend.api.call_api("/agents/sessions", true, HTTPClient.METHOD_POST, JSON.stringify({"cwd": cwd}))
	if not res["ok"]:
		failed.emit(str((res["data"] as Dictionary).get("detail", res["error"])))
		await refresh()
		return false
	open_session(str((res["data"] as Dictionary)["id"]))
	await refresh()
	return true


func open_session(sid: String) -> void:
	current_id = sid
	seq = 0
	entries.clear()
	pending.clear()
	_render_transcript()
	_render_approvals()
	_poll.start()
	await _on_poll()


func send_message(text: String) -> bool:
	text = text.strip_edges()
	if text == "" or current_id == "":
		return false
	input_edit.text = ""
	var res := await app.backend.api.call_api("/agents/sessions/%s/messages" % current_id, true, HTTPClient.METHOD_POST,
		JSON.stringify({"text": text}))
	if not res["ok"]:
		failed.emit(str((res["data"] as Dictionary).get("detail", res["error"])))
		return false
	_poll.start()
	return true


func decide(request_id: int, decision: String) -> bool:
	var res := await app.backend.api.call_api("/agents/sessions/%s/approvals/%d" % [current_id, request_id], true,
		HTTPClient.METHOD_POST, JSON.stringify({"decision": decision}))
	if res["ok"]:
		app.audio.play("confirm" if decision.begins_with("accept") else "whoosh", 0.0, -4.0)
	await _on_poll()
	return bool(res["ok"])


func _on_poll() -> void:
	if current_id == "" or not is_inside_tree():
		return
	var res := await app.backend.api.call_api("/agents/sessions/%s?after=%d" % [current_id, seq])
	if not res["ok"]:
		return
	var d: Dictionary = res["data"]
	session_status = str(d.get("status", ""))
	session_title.text = "%s · %s · %s" % [str(d.get("cwd", "")).get_file(), str(d.get("model", "")), _status_text(session_status)]
	for ev in d.get("events", []):
		_apply(ev as Dictionary)
	seq = int(d.get("seq", seq))
	pending = d.get("pending", [])
	_render_approvals()
	_render_transcript()
	_update_controls()
	if session_status in ["stopped", "error"]:
		_poll.stop()


func _apply(ev: Dictionary) -> void:
	var t := str(ev.get("type", ""))
	match t:
		"ready":
			_put("ready", "[color=#%s]Agent ready in %s[/color]" % [SbTheme.FAINT.to_html(false), _esc(str(ev.get("cwd", "")))])
		"user":
			_put("u%d" % int(ev["seq"]), "[b]You[/b]  %s" % _esc(str(ev.get("text", ""))))
		"delta":
			var key := "m:" + str(ev.get("item_id", ""))
			var prev := _entry_text(key)
			_put(key, (prev if prev != "" else "[b]Agent[/b]  ") + _esc(str(ev.get("text", ""))))
		"item":
			_apply_item(str(ev.get("phase", "")), ev.get("item", {}))
		"approval":
			app.audio.play("notification", 0.0, -2.0)
		"decision":
			var verdict := "approved" if str(ev.get("decision", "")).begins_with("accept") else "declined"
			_put("d%d" % int(ev["seq"]), "[color=#%s]You %s this %s.[/color]" % [SbTheme.FAINT.to_html(false), verdict,
				"command" if str(ev.get("kind", "")) == "command" else "change"])
		"turn_completed":
			var err := str(ev.get("error", "")) if ev.get("error") != null else ""
			_put("t%d" % int(ev["seq"]), "[color=#%s]— %s%s[/color]" % [SbTheme.FAINT.to_html(false), str(ev.get("status", "done")),
				(": " + _esc(err)) if err != "" else ""])
		"stopped":
			_put("stop", "[color=#%s]Agent stopped. %s[/color]" % [SbTheme.WARN.to_html(false), _esc(str(ev.get("error", "") if ev.get("error") != null else ""))])


func _apply_item(phase: String, item: Dictionary) -> void:
	var kind := str(item.get("type", ""))
	var id := str(item.get("id", ""))
	if kind == "agentMessage":
		if phase == "completed":
			_put("m:" + id, "[b]Agent[/b]  " + _esc(str(item.get("text", ""))))
	elif kind == "commandExecution":
		var line := "[code]$ %s[/code]" % _esc(str(item.get("command", "")))
		if phase == "completed":
			line += "  [color=#%s]%s[/color]" % [SbTheme.FAINT.to_html(false), str(item.get("status", ""))]
			if item.get("output") != null:
				line += "\n[code]%s[/code]" % _esc(str(item["output"]).right(1200))
		_put("c:" + id, line)
	elif kind == "fileChange":
		var parts: Array = []
		var diffs: Array = []
		for c in item.get("changes", []):
			var ch: Dictionary = c
			parts.append("%s %s" % [str(ch.get("kind", "")), str(ch.get("path", ""))])
			diffs.append("%s\n%s" % [str(ch.get("path", "")), str(ch.get("diff", ""))])
		_diffs[id] = "\n".join(diffs)
		var status := str(item.get("status", ""))
		_put("f:" + id, "[color=#%s]Files:[/color] %s  [color=#%s]%s[/color]" % [SbTheme.MINT.to_html(false),
			_esc(", ".join(parts)), SbTheme.FAINT.to_html(false), status if phase == "completed" else "proposed"])


func _put(key: String, text: String) -> void:
	for e in entries:
		if str((e as Dictionary)["key"]) == key:
			e["text"] = text
			return
	entries.append({"key": key, "text": text})


func _entry_text(key: String) -> String:
	for e in entries:
		if str((e as Dictionary)["key"]) == key:
			return str(e["text"])
	return ""


func _esc(s: String) -> String:
	return s.replace("[", "[lb]")


func _render_transcript() -> void:
	var parts: Array = []
	for e in entries:
		parts.append(str((e as Dictionary)["text"]))
	transcript.text = "\n\n".join(parts)


func _render_approvals() -> void:
	for c in approvals_box.get_children():
		c.queue_free()
	for item in pending:
		var a: Dictionary = item
		var card := PanelContainer.new()
		card.theme_type_variation = "Glass"
		approvals_box.add_child(card)
		var col := VBoxContainer.new()
		col.add_theme_constant_override("separation", 6)
		card.add_child(col)
		var l := Label.new()
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		var what := "run a command" if str(a.get("kind")) == "command" else "change files"
		l.text = "The agent asks to %s%s" % [what, (": " + str(a.get("reason"))) if a.get("reason") != null else "."]
		l.add_theme_color_override("font_color", SbTheme.WARM)
		col.add_child(l)
		if a.get("command") != null:
			var cmd := Label.new()
			cmd.text = "$ " + str(a["command"])
			cmd.theme_type_variation = "Muted"
			col.add_child(cmd)
		var diff := _diff_for(str(a.get("item_id", "")))
		if diff != "":
			var dl := Label.new()
			dl.text = diff.left(900)
			dl.theme_type_variation = "Muted"
			dl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			col.add_child(dl)
		var row := HBoxContainer.new()
		row.add_theme_constant_override("separation", 8)
		col.add_child(row)
		var rid := int(a.get("request_id", 0))
		for pair in [["accept", "Approve"], ["acceptForSession", "Approve for this session"], ["decline", "Decline"]]:
			if not (a.get("decisions", []) as Array).has(pair[0]):
				continue
			var b := Button.new()
			b.text = str(pair[1])
			if pair[0] != "accept":
				b.theme_type_variation = "GhostButton"
			var dec := str(pair[0])
			b.pressed.connect(func() -> void: decide(rid, dec))
			row.add_child(b)


## The proposed diff for a file-change approval, from the item streamed just before it.
var _diffs: Dictionary = {}


func _diff_for(item_id: String) -> String:
	return str(_diffs.get(item_id, ""))


func _render_folders() -> void:
	for c in folders_box.get_children():
		c.queue_free()
	var folders: Array = info.get("agents_folders", [])
	if folders.is_empty():
		var l := Label.new()
		l.text = "No folder yet."
		l.theme_type_variation = "Muted"
		folders_box.add_child(l)
	for f in folders:
		var path := str(f)
		var row := HBoxContainer.new()
		folders_box.add_child(row)
		var b := Button.new()
		b.text = "▶ " + path.get_file()
		b.tooltip_text = "Start an agent in " + path
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.disabled = not bool(info.get("installed", false))
		b.pressed.connect(func() -> void: start_session(path))
		row.add_child(b)
		var x := Button.new()
		x.text = "✕"
		x.theme_type_variation = "GhostButton"
		x.tooltip_text = "Remove this folder from the agent room"
		x.pressed.connect(func() -> void:
			await app.backend.api.call_api("/agents/folders?path=" + path.uri_encode(), true, HTTPClient.METHOD_DELETE)
			await refresh())
		row.add_child(x)


func _render_sessions() -> void:
	for c in sessions_box.get_children():
		c.queue_free()
	for s in info.get("sessions", []):
		var d: Dictionary = s
		var b := Button.new()
		b.theme_type_variation = "GhostButton"
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.text = "%s · %s" % [str(d.get("cwd", "")).get_file(), _status_text(str(d.get("status", "")))]
		var sid := str(d["id"])
		b.pressed.connect(func() -> void: open_session(sid))
		sessions_box.add_child(b)


func _status_text(s: String) -> String:
	return {"starting": "starting", "idle": "ready", "working": "working…", "waiting_approval": "needs your approval",
		"stopped": "stopped", "error": "error"}.get(s, s)


func _update_controls() -> void:
	var live := current_id != "" and session_status in ["idle", "working", "waiting_approval"]
	input_edit.editable = live and session_status == "idle"
	send_button.disabled = not (live and session_status == "idle")
	stop_button.disabled = not (live and session_status in ["working", "waiting_approval"])


func _pick_folder() -> void:
	if _dir_dialog == null:
		_dir_dialog = FileDialog.new()
		_dir_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
		_dir_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_dir_dialog.use_native_dialog = true
		_dir_dialog.dir_selected.connect(func(p: String) -> void: add_folder(p))
		add_child(_dir_dialog)
	_dir_dialog.popup_centered_ratio(0.6)
