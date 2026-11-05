class_name BillingPanel
extends PanelContainer
## Real costs, as OpenAI bills them. Read live from OpenAI with an admin key that can only
## read usage; nothing is stored by the app. Costs come in daily buckets (UTC).

var app: SbApp
var state_label: Label
var month_value: Label
var today_value: Label
var period_value: Label
var tokens_value: Label
var chart: CostChart
var legend: HFlowContainer
var models_grid: GridContainer
var items_label: RichTextLabel
var setup_box: VBoxContainer
var data_box: VBoxContainer
var key_edit: LineEdit
var key_status: Label
var refresh_button: Button
var last: Dictionary = {}
var _loading := false


func setup(a: SbApp) -> BillingPanel:
	app = a
	return self


func _ready() -> void:
	theme_type_variation = "Card"
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 12)
	add_child(col)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 10)
	col.add_child(head)
	var t := VBoxContainer.new()
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t.add_theme_constant_override("separation", 0)
	head.add_child(t)
	var title := Label.new()
	title.text = I18n.t("Real costs · OpenAI billing")
	title.theme_type_variation = "Heading"
	title.add_theme_font_size_override("font_size", 16)
	t.add_child(title)
	state_label = Label.new()
	state_label.theme_type_variation = "Muted"
	state_label.text = I18n.t("Loading…")
	t.add_child(state_label)
	refresh_button = Button.new()
	refresh_button.text = I18n.t("Refresh")
	refresh_button.pressed.connect(func() -> void: load_billing(true))
	head.add_child(refresh_button)

	# --- no admin key yet
	setup_box = VBoxContainer.new()
	setup_box.add_theme_constant_override("separation", 8)
	setup_box.visible = false
	col.add_child(setup_box)
	var why := Label.new()
	why.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	why.text = I18n.t("To show what OpenAI actually bills, add an admin key that can only read usage. On platform.openai.com: Settings → Organization → Admin keys → Create, permissions Restricted, \"Usage API: Read\" and nothing else. It cannot call models or change anything.")
	setup_box.add_child(why)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	setup_box.add_child(row)
	key_edit = LineEdit.new()
	key_edit.secret = true
	key_edit.placeholder_text = "sk-admin-…"
	key_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(key_edit)
	var save := Button.new()
	save.text = I18n.t("Save admin key")
	save.theme_type_variation = "PrimaryButton"
	save.pressed.connect(_save_key)
	row.add_child(save)
	key_status = Label.new()
	key_status.theme_type_variation = "Muted"
	key_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	setup_box.add_child(key_status)

	# --- figures
	data_box = VBoxContainer.new()
	data_box.add_theme_constant_override("separation", 12)
	data_box.visible = false
	col.add_child(data_box)
	var tiles := HBoxContainer.new()
	tiles.add_theme_constant_override("separation", 12)
	data_box.add_child(tiles)
	month_value = _tile(tiles, I18n.t("This month"), true)
	today_value = _tile(tiles, I18n.t("Today (UTC, so far)"), false)
	period_value = _tile(tiles, I18n.t("Last 30 days"), false)
	tokens_value = _tile(tiles, I18n.t("Tokens this month"), false)
	chart = CostChart.new()
	chart.name = "CostChart"
	data_box.add_child(chart)
	legend = HFlowContainer.new()
	legend.add_theme_constant_override("h_separation", 16)
	data_box.add_child(legend)
	var mt := Label.new()
	mt.text = I18n.t("By model, this month")
	mt.theme_type_variation = "Overline"
	data_box.add_child(mt)
	models_grid = GridContainer.new()
	models_grid.columns = 5
	models_grid.add_theme_constant_override("h_separation", 22)
	models_grid.add_theme_constant_override("v_separation", 4)
	data_box.add_child(models_grid)
	var it := Label.new()
	it.text = I18n.t("Billed line items, this month")
	it.theme_type_variation = "Overline"
	data_box.add_child(it)
	items_label = RichTextLabel.new()
	items_label.bbcode_enabled = true
	items_label.fit_content = true
	data_box.add_child(items_label)
	var foot := HBoxContainer.new()
	data_box.add_child(foot)
	var src := Label.new()
	src.theme_type_variation = "Muted"
	src.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	src.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	src.text = I18n.t("Straight from OpenAI's Costs and Usage APIs (what your invoice shows). Nothing is stored by the app.")
	foot.add_child(src)
	var remove := Button.new()
	remove.text = I18n.t("Remove admin key")
	remove.theme_type_variation = "GhostButton"
	remove.pressed.connect(_remove_key)
	foot.add_child(remove)
	load_billing(false)


func _tile(parent: Control, label: String, hero: bool) -> Label:
	var box := PanelContainer.new()
	box.theme_type_variation = "Inset"
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(box)
	var v := VBoxContainer.new()
	v.add_theme_constant_override("separation", 0)
	box.add_child(v)
	var l := Label.new()
	l.text = label
	l.theme_type_variation = "Muted"
	v.add_child(l)
	var value := Label.new()
	value.text = "—"
	value.theme_type_variation = "Heading"
	value.add_theme_font_size_override("font_size", 28 if hero else 18)
	v.add_child(value)
	return value


func load_billing(refresh: bool) -> void:
	if _loading or app == null:
		return
	_loading = true
	refresh_button.disabled = true
	state_label.text = I18n.t("Asking OpenAI…")
	var res := await app.backend.api.call_api("/billing?days=30" + ("&refresh=true" if refresh else ""))
	_loading = false
	if not is_inside_tree():
		return
	refresh_button.disabled = false
	if not res["ok"]:
		state_label.text = I18n.t("Engine not reachable (%s).") % str(res.get("error", ""))
		return
	render(res["data"])


func render(d: Dictionary) -> void:
	last = d
	var configured := bool(d.get("configured", false))
	setup_box.visible = not configured or d.has("error")
	data_box.visible = configured and not d.has("error")
	refresh_button.visible = configured
	if not configured:
		state_label.text = I18n.t("Admin key needed")
		return
	if d.has("error"):
		state_label.text = I18n.t("OpenAI did not answer")
		key_status.text = str(d.get("error", ""))
		return
	var cur := str(d.get("currency", "usd"))
	state_label.text = (I18n.t("Updated %s (cached)") if bool(d.get("cached", false)) else I18n.t("Updated %s")) \
		% SbFormat.local_time(d.get("fetched_at", ""), true)
	month_value.text = CostChart.money(float(d.get("month", 0.0)), cur)
	today_value.text = CostChart.money(float(d.get("today", 0.0)), cur)
	period_value.text = CostChart.money(float(d.get("period", 0.0)), cur)
	var tok: Dictionary = d.get("tokens", {})
	tokens_value.text = SbFormat.number(int(tok.get("input_tokens", 0)) + int(tok.get("output_tokens", 0))
		+ int(tok.get("audio_in_tokens", 0)) + int(tok.get("audio_out_tokens", 0)))
	var groups: Array = d.get("groups", [])
	chart.set_data(d.get("days", []), groups, cur)
	for c in legend.get_children():
		c.queue_free()
	var totals := {}
	for day in d.get("days", []):
		var split: Dictionary = (day as Dictionary).get("by_group", {})
		for g in split:
			totals[g] = float(totals.get(g, 0.0)) + float(split[g])
	for g in groups:
		var item := HBoxContainer.new()
		item.add_theme_constant_override("separation", 6)
		var sw := ColorRect.new()
		sw.color = CostChart.color_for(str(g), groups)
		sw.custom_minimum_size = Vector2(12, 12)
		sw.size_flags_vertical = Control.SIZE_SHRINK_CENTER
		item.add_child(sw)
		var l := Label.new()
		l.text = "%s  %s" % [str(g), CostChart.money(float(totals.get(g, 0.0)), cur)]
		item.add_child(l)
		legend.add_child(item)
	for c in models_grid.get_children():
		c.queue_free()
	for h in [I18n.t("Model"), I18n.t("Requests"), I18n.t("Input tokens"), I18n.t("Cached"), I18n.t("Output tokens")]:
		var hl := Label.new()
		hl.text = h
		hl.theme_type_variation = "Muted"
		models_grid.add_child(hl)
	for m in d.get("models", []):
		var md: Dictionary = m
		var kind := str(md.get("kind", ""))
		var input := SbFormat.number(md.get("input_tokens", 0))
		var output := SbFormat.number(md.get("output_tokens", 0))
		if kind == "audio_speeches":
			input = I18n.t("%s chars") % SbFormat.number(md.get("characters", 0))
			output = "—"
		elif kind == "audio_transcriptions":
			input = I18n.t("%s s audio") % SbFormat.number(md.get("seconds", 0))
			output = "—"
		for v in [str(md.get("model", "?")), SbFormat.number(md.get("requests", 0)), input,
				SbFormat.number(md.get("cached_tokens", 0)), output]:
			var l := Label.new()
			l.text = v
			models_grid.add_child(l)
	var lines := []
	for li in d.get("line_items", []):
		lines.append("%s  [color=#%s]%s[/color]" % [CostChart.money(float(li.get("cost", 0.0)), cur),
			SbTheme.MUTED.to_html(false), str(li.get("name", ""))])
	items_label.text = "\n".join(lines) if not lines.is_empty() else I18n.t("Nothing billed yet this month.")


func _save_key() -> void:
	var key := key_edit.text.strip_edges()
	if key.length() < 20:
		key_status.text = I18n.t("That does not look like a complete key.")
		return
	key_status.text = I18n.t("Checking the key with OpenAI…")
	var res := await app.backend.api.call_api("/billing/key", true, HTTPClient.METHOD_PUT, JSON.stringify({"api_key": key}))
	key_edit.text = ""
	if not is_inside_tree():
		return
	if not res["ok"]:
		key_status.text = str((res["data"] as Dictionary).get("detail", res.get("error", I18n.t("Refused."))))
		return
	key_status.text = I18n.t("Saved in %s.") % str(res["data"].get("backend", I18n.t("the credential store")))
	load_billing(true)


func _remove_key() -> void:
	await app.backend.api.call_api("/billing/key", true, HTTPClient.METHOD_DELETE)
	if is_inside_tree():
		load_billing(true)
