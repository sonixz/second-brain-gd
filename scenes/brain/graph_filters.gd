class_name GraphFilters
extends HBoxContainer
## Filter bar over the graph (Loop 13): types, origins, date, a word or theme, packs.
## The summary says what is shown; ✕ clears everything.

signal changed(filter: Dictionary)

const TYPES := [["note", "Notes"], ["idea", "Ideas"], ["article", "Articles"], ["document", "Documents"],
	["image", "Images"], ["reference", "References"], ["quote", "Quotes"], ["list", "Lists"], ["journal", "Journal"]]
const ORIGINS := [["typed", "Typed"], ["voice", "Spoken"], ["url", "Web"], ["file", "Files"], ["pack", "Packs"]]
const DAYS := [[0, "Any time"], [1, "Today"], [7, "Last 7 days"], [30, "Last 30 days"]]

var filter: Dictionary = {}
var summary: Label
var clear_button: Button
var popup: PopupPanel
var _checks: Dictionary = {}
var _days: OptionButton
var _text: LineEdit


func _ready() -> void:
	add_theme_constant_override("separation", 8)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var open := Button.new()
	open.text = "Filter"
	open.tooltip_text = "Show only some items: type, origin, date, a word or theme"
	open.pressed.connect(_open)
	add_child(open)
	summary = Label.new()
	summary.theme_type_variation = "Muted"
	summary.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	add_child(summary)
	clear_button = Button.new()
	clear_button.text = "✕ Show all"
	clear_button.theme_type_variation = "GhostButton"
	clear_button.visible = false
	clear_button.pressed.connect(func() -> void: apply({}))
	add_child(clear_button)
	popup = PopupPanel.new()
	add_child(popup)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	popup.add_child(col)
	for group in [["TYPE", TYPES], ["ORIGIN", ORIGINS]]:
		var l := Label.new()
		l.text = str(group[0])
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
	for d in DAYS:
		_days.add_item(str(d[1]))
	_days.item_selected.connect(func(_i: int) -> void: _from_controls())
	col.add_child(_days)
	_text = LineEdit.new()
	_text.placeholder_text = "A word or a theme (e.g. ia, #recettes)"
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
	var days := int(DAYS[maxi(0, _days.selected)][0])
	if days > 0:
		f["since_days"] = days
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
	for i in DAYS.size():
		if int(DAYS[i][0]) == int(f.get("since_days", 0)):
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
	for pair in TYPES + ORIGINS:
		labels[str(pair[0])] = str(pair[1]).to_lower()
	if f.has("types"):
		parts.append(", ".join((f["types"] as Array).map(func(t: Variant) -> String: return str(labels.get(str(t), t)))))
	if f.has("origins"):
		parts.append("from " + ", ".join((f["origins"] as Array).map(func(t: Variant) -> String: return str(labels.get(str(t), t)))))
	if f.has("text"):
		parts.append("« %s »" % str(f["text"]))
	if int(f.get("since_days", 0)) > 0:
		parts.append("today" if int(f["since_days"]) == 1 else "last %d days" % int(f["since_days"]))
	return "Showing " + " · ".join(parts)


func _render() -> void:
	summary.text = describe(filter)
	clear_button.visible = not filter.is_empty()
