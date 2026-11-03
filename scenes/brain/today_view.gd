class_name TodayView
extends PanelContainer
## "Today": what needs attention now. Overdue, due today and this week, the
## next action of every project, projects that have none, and checklists.

signal open_project(space_id: String)
signal review_requested
signal changed

var app: SbApp
var body: HBoxContainer
var title_label: Label
var summary: Label
var task_rows := 0
var data: Dictionary = {}


func setup(a: SbApp) -> TodayView:
	app = a
	theme_type_variation = "Glass"
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)
	add_child(col)
	var head := HBoxContainer.new()
	col.add_child(head)
	var htext := VBoxContainer.new()
	htext.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(htext)
	var over := Label.new()
	over.text = "TODAY"
	over.theme_type_variation = "Overline"
	htext.add_child(over)
	title_label = Label.new()
	title_label.theme_type_variation = "Heading"
	htext.add_child(title_label)
	summary = Label.new()
	summary.theme_type_variation = "Muted"
	summary.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	head.add_child(summary)
	var review := Button.new()
	review.text = "Weekly review"
	review.tooltip_text = "The assistant walks through each project: progress, blockers, next step, and questions for your vision"
	review.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	review.pressed.connect(func() -> void: review_requested.emit())
	head.add_child(review)
	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	col.add_child(scroll)
	body = HBoxContainer.new()
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 22)
	scroll.add_child(body)
	return self


func refresh() -> void:
	var res := await app.backend.api.call_api("/brain/today")
	if not res["ok"] or not is_inside_tree():
		return
	data = res["data"]
	for c in body.get_children():
		c.queue_free()
	task_rows = 0
	var d := Time.get_datetime_dict_from_system()
	var days := ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
	var months := ["January", "February", "March", "April", "May", "June", "July", "August", "September",
		"October", "November", "December"]
	title_label.text = "%s, %s %d" % [days[int(d["weekday"])], months[int(d["month"]) - 1], int(d["day"])]
	var overdue: Array = data.get("overdue", [])
	var today: Array = data.get("today", [])
	var soon: Array = data.get("soon", [])
	summary.text = "%d overdue · %d today · %d this week · %d in Inbox" % [overdue.size(), today.size(), soon.size(),
		int(data.get("inbox_count", 0))]
	var left := _column(1.3)
	var right := _column(1.0)
	_task_section(left, "Overdue", overdue, SbTheme.ERROR)
	_task_section(left, "Today", today, SbTheme.WARM)
	_task_section(left, "This week", soon, SbTheme.INFO)
	var next: Array = data.get("next_actions", [])
	_task_section(left, "Next action per project", next, SbTheme.MINT, true)
	var stuck: Array = data.get("projects_without_next_action", [])
	if not stuck.is_empty():
		_section_title(left, "Projects without a next action", SbTheme.WARN)
		for item in stuck:
			var p: Dictionary = item
			var b := Button.new()
			b.theme_type_variation = "GhostButton"
			b.alignment = HORIZONTAL_ALIGNMENT_LEFT
			b.text = "◇  %s  · define the next step" % p["name"]
			var pid := str(p["id"])
			b.pressed.connect(func() -> void: open_project.emit(pid))
			left.add_child(b)
	if overdue.is_empty() and today.is_empty() and soon.is_empty() and next.is_empty():
		var calm := Label.new()
		calm.theme_type_variation = "Muted"
		calm.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		calm.text = "Nothing due. Add a task by typing it below, or ask the assistant: « ajoute une tâche… »."
		left.add_child(calm)
	var lists: Array = data.get("checklists", [])
	for item in lists:
		right.add_child(_checklist_card(item))


func _column(ratio: float) -> VBoxContainer:
	var c := VBoxContainer.new()
	c.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	c.size_flags_stretch_ratio = ratio
	c.add_theme_constant_override("separation", 6)
	body.add_child(c)
	return c


func _section_title(parent: Control, text: String, color: Color) -> void:
	var l := Label.new()
	l.text = text.to_upper()
	l.theme_type_variation = "Overline"
	l.add_theme_color_override("font_color", color)
	parent.add_child(l)


func _task_section(parent: Control, title: String, items: Array, color: Color, show_remaining: bool = false) -> void:
	if items.is_empty():
		return
	_section_title(parent, title, color)
	for item in items:
		parent.add_child(_task_row(item, show_remaining))
	var gap := Control.new()
	gap.custom_minimum_size = Vector2(0, 6)
	parent.add_child(gap)


func _task_row(t: Dictionary, show_remaining: bool) -> HBoxContainer:
	task_rows += 1
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	var cb := CheckBox.new()
	cb.button_pressed = str(t.get("status", "active")) == "done"
	var tid := str(t["id"])
	cb.toggled.connect(func(on: bool) -> void: set_done(tid, on, cb))
	cb.set_meta("sfx", "none")
	row.add_child(cb)
	var l := Label.new()
	l.text = str(t["title"])
	l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	l.clip_text = true
	row.add_child(l)
	var meta := Label.new()
	meta.theme_type_variation = "Muted"
	var bits: PackedStringArray = []
	var proj := str(t.get("project", t.get("space_name", "")))
	if proj != "" and proj != "Inbox":
		bits.append(proj)
	if t.get("due_date") != null:
		bits.append(str(t["due_date"]))
	if show_remaining and int(t.get("remaining", 1)) > 1:
		bits.append("+%d" % (int(t["remaining"]) - 1))
	meta.text = " · ".join(bits)
	row.add_child(meta)
	return row


func set_done(task_id: String, done: bool, cb: CheckBox = null) -> void:
	var res := await app.backend.api.call_api("/brain/tasks/" + task_id, true, HTTPClient.METHOD_PATCH,
		JSON.stringify({"done": done}))
	if res["ok"]:
		app.audio.play("step_done" if done else "click", 0.05)
		if cb != null and done:
			var row := cb.get_parent() as Control
			create_tween().tween_property(row, "modulate:a", 0.35, 0.4)
		changed.emit()
		get_tree().create_timer(0.7).timeout.connect(func() -> void:
			if is_inside_tree():
				refresh())


func _checklist_card(cl: Dictionary) -> PanelContainer:
	var card := PanelContainer.new()
	card.theme_type_variation = "Inset"
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 4)
	card.add_child(col)
	var head := HBoxContainer.new()
	col.add_child(head)
	var t := Label.new()
	t.text = "☰  %s" % cl["name"]
	t.add_theme_font_override("font", SbTheme.font(650))
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(t)
	var space := Label.new()
	space.theme_type_variation = "Muted"
	space.text = str(cl.get("space_name", ""))
	head.add_child(space)
	var cid := str(cl["id"])
	var items: Array = cl.get("items", [])
	var done_count := 0
	for item in items:
		var it: Dictionary = item
		var cb := CheckBox.new()
		cb.text = str(it["text"])
		cb.button_pressed = int(it["done"]) == 1
		if cb.button_pressed:
			done_count += 1
			cb.modulate.a = 0.5
		cb.set_meta("sfx", "none")
		var iid := int(it["id"])
		cb.toggled.connect(func(on: bool) -> void:
			cb.modulate.a = 0.5 if on else 1.0
			app.audio.play("click", 0.08)
			await app.backend.api.call_api("/brain/checklist-items/%d" % iid, true, HTTPClient.METHOD_PATCH,
				JSON.stringify({"done": on})))
		col.add_child(cb)
	if items.is_empty():
		var empty := Label.new()
		empty.theme_type_variation = "Muted"
		empty.text = "Empty. Say « ajoute du lait à l'épicerie »."
		col.add_child(empty)
	var add := LineEdit.new()
	add.placeholder_text = "Add items (comma separated)…"
	add.text_submitted.connect(func(text: String) -> void: add_items(cid, text))
	col.add_child(add)
	if done_count > 0:
		var clear := Button.new()
		clear.text = "Clear %d checked" % done_count
		clear.theme_type_variation = "GhostButton"
		clear.pressed.connect(func() -> void:
			await app.backend.api.call_api("/brain/checklists/%s/clear" % cid, true, HTTPClient.METHOD_POST)
			app.audio.play("whoosh")
			refresh())
		col.add_child(clear)
	return card


func add_items(checklist_id: String, text: String) -> void:
	var parts: Array = []
	for p in text.split(","):
		if p.strip_edges() != "":
			parts.append(p.strip_edges())
	if parts.is_empty():
		return
	var res := await app.backend.api.call_api("/brain/checklists/%s/items" % checklist_id, true, HTTPClient.METHOD_POST,
		JSON.stringify({"items": parts}))
	if res["ok"]:
		app.audio.play("confirm", 0.05)
		await refresh()
