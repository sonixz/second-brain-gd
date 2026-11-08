extends PanelContainer
## Missions (Loop 35), in the engine room: what each agent's missions did and cost, this month's total, and
## « Run again » to start the same goal with the same agent (next week's menu). A click on a mission shows its
## plan, its findings with their source links, the question and the answer, the draft and what was saved.
## Loaded by preload path (a new class can lag in Godot's class list on Windows).

var app: SbApp
var summary_label: Label
var list_box: VBoxContainer
var open_id := ""
var missions: Array = []
var _loading := false



func _status(st: String) -> String:
	match st:
		"running": return I18n.t("Working")
		"waiting": return I18n.t("Waiting for you")
		"draft": return I18n.t("Draft ready")
		"saved": return I18n.t("Saved")
		"stopped": return I18n.t("Stopped")
		"failed": return I18n.t("Failed")
	return st


func setup(a: SbApp) -> Control:
	app = a
	return self


func _ready() -> void:
	theme_type_variation = "Card"
	name = "MissionsPanel"
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
	title.text = I18n.t("Missions")
	title.theme_type_variation = "Heading"
	title.add_theme_font_size_override("font_size", SbTheme.fs(16))
	t.add_child(title)
	summary_label = Label.new()
	summary_label.theme_type_variation = "Muted"
	summary_label.text = I18n.t("Loading…")
	summary_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	t.add_child(summary_label)
	var refresh_button := Button.new()
	refresh_button.text = I18n.t("Refresh")
	refresh_button.pressed.connect(refresh)
	head.add_child(refresh_button)
	list_box = VBoxContainer.new()
	list_box.add_theme_constant_override("separation", 4)
	col.add_child(list_box)
	var timer := Timer.new()
	timer.wait_time = 15.0
	timer.autostart = true
	timer.timeout.connect(refresh)
	add_child(timer)
	refresh()


func refresh() -> void:
	if _loading or app == null:
		return
	_loading = true
	var r: Dictionary = await app.backend.api.call_api("/missions?limit=30", true)
	_loading = false
	if not is_inside_tree():
		return
	if not r.get("ok", false):
		summary_label.text = I18n.t("Could not read the missions: %s") % _s(r.get("error", ""))
		return
	var data: Dictionary = r["data"] if r["data"] is Dictionary else {}
	missions = data.get("missions", []) if data.get("missions") is Array else []
	var s: Dictionary = data.get("summary", {}) if data.get("summary") is Dictionary else {}
	var n := int(s.get("count", 0))
	var month := I18n.t("This month: 1 mission") if n == 1 else I18n.t("This month: %d missions") % n
	summary_label.text = month + " · %s · %s min · " % [_money(float(s.get("cost", 0))), _s(s.get("minutes", 0))] \
		+ I18n.t("in all: %s") % _money(float(s.get("cost_all", 0)))
	_rebuild()


func _money(v: float) -> String:
	return "%.2f $" % v if v >= 0.01 or v == 0.0 else "< 0.01 $"


func _rebuild() -> void:
	for c in list_box.get_children():
		c.queue_free()
	if missions.is_empty():
		var empty := Label.new()
		empty.theme_type_variation = "Muted"
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		empty.text = I18n.t("No mission yet. Turn on an agent's Missions capability, then « Mission… » in its panel.")
		list_box.add_child(empty)
		return
	for m in missions:
		if m is Dictionary:
			_row(m)


func _row(m: Dictionary) -> void:
	var id := _s(m.get("id", ""))
	var row := HBoxContainer.new()
	row.name = "Mission_" + id
	row.add_theme_constant_override("separation", 10)
	list_box.add_child(row)
	var open := Button.new()
	open.theme_type_variation = "GhostButton"
	open.alignment = HORIZONTAL_ALIGNMENT_LEFT
	open.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	open.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	open.clip_text = true
	open.text = "%s %s · %s · %s" % ["▾" if id == open_id else "▸", _s(m.get("created_at", "")).substr(0, 10),
		_s(m.get("agent_name", m.get("agent", ""))), _s(m.get("goal", ""))]
	open.tooltip_text = _s(m.get("goal", ""))
	open.pressed.connect(func() -> void:
		open_id = "" if open_id == id else id
		_rebuild())
	row.add_child(open)
	var facts := Label.new()
	facts.theme_type_variation = "Muted"
	facts.text = "%s · %d %s · %s min · %s" % [_status(_s(m.get("status", ""))),
		int(m.get("rounds", 0)), I18n.t("rounds"), _s(m.get("minutes", 0)), _money(float(m.get("cost", 0)))]
	row.add_child(facts)
	var again := Button.new()
	again.text = I18n.t("Run again")
	again.tooltip_text = I18n.t("The same goal with the same agent, as a new mission")
	again.disabled = _s(m.get("status", "")) in ["running", "waiting", "draft"]
	again.pressed.connect(func() -> void: _again(id))
	row.add_child(again)
	if id == open_id:
		list_box.add_child(_detail(m))


func _again(id: String) -> void:
	var r: Dictionary = await app.backend.api.call_api("/missions/%s/again" % id, true, HTTPClient.METHOD_POST, "{}")
	if not is_inside_tree():
		return
	if r.get("ok", false) and r["data"] is Dictionary:
		open_id = str((r["data"] as Dictionary).get("id", ""))
		summary_label.text = I18n.t("Started again: follow it in the agent's panel.")
	else:
		summary_label.text = I18n.t("Could not start it again: %s") % _s(r.get("error", ""))
	refresh()


## Plan, findings with their links, the question and the answer, the draft, what was saved.
func _detail(m: Dictionary) -> Control:
	var rt := RichTextLabel.new()
	rt.name = "MissionDetail"
	rt.bbcode_enabled = true
	rt.fit_content = true
	rt.selection_enabled = true
	rt.meta_clicked.connect(func(meta: Variant) -> void:
		var url := str(meta)
		if url.begins_with("https://") or url.begins_with("http://"):
			OS.shell_open(url))
	var b := PackedStringArray()
	b.append("[b]%s[/b] %s" % [I18n.t("Goal:"), _esc(_s(m.get("goal", "")))])
	var plan: Array = m.get("plan", []) if m.get("plan") is Array else []
	if not plan.is_empty():
		b.append("\n[b]%s[/b]" % I18n.t("Plan"))
		for st in plan:
			if st is Dictionary:
				var mark: String = {"done": "✓", "skipped": "–"}.get(_s(st.get("status", "")), "○")
				var note := _s(st.get("note", ""))
				b.append("  %s %s%s" % [mark, _esc(_s(st.get("title", ""))), (" · [i]%s[/i]" % _esc(note)) if note != "" else ""])
	var found: Dictionary = m.get("findings", {}) if m.get("findings") is Dictionary else {}
	for kind in found:
		var rows: Array = found[kind] if found[kind] is Array else []
		b.append("\n[b]%s[/b] (%d)" % [_esc(str(kind).capitalize()), rows.size()])
		for row in rows.slice(0, 60):
			if row is Dictionary:
				b.append("  • " + _finding(row))
	for f in (m.get("feed", []) if m.get("feed") is Array else []):
		if f is Dictionary and _s(f.get("kind", "")) in ["question", "answer"]:
			b.append("\n[b]%s[/b] %s" % [I18n.t("Question:") if f["kind"] == "question" else I18n.t("Your answer:"), _esc(_s(f.get("detail", "")))])
	var draft: Dictionary = m.get("draft", {}) if m.get("draft") is Dictionary else {}
	if not draft.is_empty():
		b.append("\n[b]%s[/b] %s" % [I18n.t("Draft:"), _esc(_s(draft.get("title", "")))])
		for it in (draft.get("items", []) if draft.get("items") is Array else []):
			if it is Dictionary:
				var url := _s(it.get("url", ""))
				b.append("  • %s%s" % [_esc(_s(it.get("title", ""))), (" · [url=%s]%s[/url]" % [url, I18n.t("source")]) if url.begins_with("http") else ""])
	var result: Dictionary = m.get("result", {}) if m.get("result") is Dictionary else {}
	if not result.is_empty():
		b.append("\n" + I18n.t("Saved in your Brain: %d items.") % (result.get("note_ids", []) as Array).size())
	if _s(m.get("reason", "")) != "":
		b.append("\n[i]%s[/i]" % _esc(_s(m.get("reason", ""))))
	rt.text = "\n".join(b)
	return rt


## One finding: its fields in a line, its link as « source ».
func _finding(row: Dictionary) -> String:
	var parts := PackedStringArray()
	var url := ""
	for k in row:
		var v := _s(row[k])
		if k in ["url", "source", "link"] and v.begins_with("http"):
			url = v
		elif v != "":
			parts.append(_esc(v))
	return " · ".join(parts) + ((" · [url=%s]%s[/url]" % [url, I18n.t("source")]) if url != "" else "")


## A field as text; a missing one (null) is empty, never « <null> ».
func _s(v: Variant) -> String:
	return "" if v == null else str(v)


func _esc(s: String) -> String:
	return s.replace("[", "[lb]")
