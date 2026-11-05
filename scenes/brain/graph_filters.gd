class_name GraphFilters
extends HBoxContainer
## Filter bar over the graph (Loop 13): types, origins, date, a word or theme, packs.
## The summary says what is shown; ✕ clears everything.

signal changed(filter: Dictionary)
signal layout_changed(mode: String)
signal legend_toggled(on: bool)

## [id, label] pairs; the labels follow the interface language.
static func types() -> Array:
	return [["note", I18n.t("Notes")], ["idea", I18n.t("Ideas")], ["article", I18n.t("Articles")],
		["document", I18n.t("Documents")], ["image", I18n.t("Images")], ["reference", I18n.t("References")],
		["quote", I18n.t("Quotes")], ["list", I18n.t("Lists")], ["journal", I18n.t("Journal")]]


static func origins() -> Array:
	return [["typed", I18n.t("Typed")], ["voice", I18n.t("Spoken")], ["url", I18n.t("Web")], ["file", I18n.t("Files")],
		["pack", I18n.t("Packs")]]


static func days() -> Array:
	return [[0, I18n.t("Any time")], [1, I18n.t("Today")], [7, I18n.t("Last 7 days")], [30, I18n.t("Last 30 days")]]

var filter: Dictionary = {}
var summary: Label
var clear_button: Button
var timeline_button: Button
var legend_button: Button
var popup: PopupPanel
var _checks: Dictionary = {}
var _days: OptionButton
var _text: LineEdit


func _ready() -> void:
	add_theme_constant_override("separation", 8)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var open := Button.new()
	open.text = I18n.t("Filter")
	open.tooltip_text = I18n.t("Show only some items: type, origin, date, a word or theme")
	open.pressed.connect(_open)
	add_child(open)
	summary = Label.new()
	summary.theme_type_variation = "Muted"
	summary.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	add_child(summary)
	clear_button = Button.new()
	clear_button.text = I18n.t("✕ Show all")
	clear_button.theme_type_variation = "GhostButton"
	clear_button.visible = false
	clear_button.pressed.connect(func() -> void: apply({}))
	add_child(clear_button)
	timeline_button = Button.new()
	timeline_button.text = I18n.t("Timeline")
	timeline_button.toggle_mode = true
	timeline_button.tooltip_text = I18n.t("Show items on a time axis, one lane per place")
	timeline_button.toggled.connect(func(on: bool) -> void: layout_changed.emit("timeline" if on else "zones"))
	add_child(timeline_button)
	legend_button = Button.new()
	legend_button.text = "?"
	legend_button.toggle_mode = true
	legend_button.tooltip_text = I18n.t("What the lines mean")
	legend_button.toggled.connect(func(on: bool) -> void: legend_toggled.emit(on))
	add_child(legend_button)
	popup = PopupPanel.new()
	add_child(popup)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	popup.add_child(col)
	for group in [["TYPE", types(), I18n.t("TYPE")], ["ORIGIN", origins(), I18n.t("ORIGIN")]]:
		var l := Label.new()
		l.text = str(group[2])
		l.theme_type_variation = "Overline"
		col.add_child(l)
		var flow := HFlowContainer.new()
		flow.custom_minimum_size = Vector2(420, 0)
		col.add_child(flow)
		for pair in group[1]:
			var c := CheckBox.new()
			c.text = str(pair[1])
			c.toggled.connect(func(_on: bool) -> void: _from_controls())
			flow.add_child(c)
			_checks[str(group[0]) + ":" + str(pair[0])] = c
	_days = OptionButton.new()
	for d in days():
		_days.add_item(str(d[1]))
	_days.item_selected.connect(func(_i: int) -> void: _from_controls())
	col.add_child(_days)
	_text = LineEdit.new()
	_text.placeholder_text = I18n.t("A word or a theme (e.g. ai, #recipes)")
	_text.text_changed.connect(func(_t: String) -> void: _from_controls())
	col.add_child(_text)
	_render()


func _open() -> void:
	var r := get_global_rect()
	popup.popup(Rect2i(Vector2i(int(r.position.x), int(r.end.y + 6)), Vector2i(460, 0)))


func _from_controls() -> void:
	var f: Dictionary = {}
	var types: Array = []
	var origins: Array = []
	for key in _checks:
		if (_checks[key] as CheckBox).button_pressed:
			var parts := str(key).split(":")
			(types if parts[0] == "TYPE" else origins).append(parts[1])
	if not types.is_empty():
		f["types"] = types
	if not origins.is_empty():
		f["origins"] = origins
	var since := int(days()[maxi(0, _days.selected)][0])
	if since > 0:
		f["since_days"] = since
	if _text.text.strip_edges() != "":
		f["text"] = _text.text.strip_edges()
	filter = f
	_render()
	changed.emit(filter)


## Sets the filter from outside (voice, saved state) and updates the controls.
func apply(f: Dictionary) -> void:
	filter = f
	for key in _checks:
		var parts := str(key).split(":")
		var arr: Array = f.get("types" if parts[0] == "TYPE" else "origins", [])
		(_checks[key] as CheckBox).set_pressed_no_signal(arr.has(parts[1]))
	var idx := 0
	var day_list := days()
	for i in day_list.size():
		if int(day_list[i][0]) == int(f.get("since_days", 0)):
			idx = i
	_days.select(idx)
	_text.text = str(f.get("text", ""))
	_render()
	changed.emit(filter)


static func describe(f: Dictionary) -> String:
	if f.is_empty():
		return ""
	var parts: Array = []
	var labels := {}
	for pair in types() + origins():
		labels[str(pair[0])] = str(pair[1]).to_lower()
	if f.has("types"):
		parts.append(", ".join((f["types"] as Array).map(func(t: Variant) -> String: return str(labels.get(str(t), t)))))
	if f.has("origins"):
		parts.append(I18n.t("from %s") % ", ".join((f["origins"] as Array).map(func(t: Variant) -> String: return str(labels.get(str(t), t)))))
	if f.has("text"):
		parts.append("“%s”" % str(f["text"]))
	if int(f.get("since_days", 0)) > 0:
		parts.append(I18n.t("today") if int(f["since_days"]) == 1 else I18n.t("last %d days") % int(f["since_days"]))
	return I18n.t("Showing %s") % " · ".join(parts)


func _render() -> void:
	summary.text = describe(filter)
	clear_button.visible = not filter.is_empty()
