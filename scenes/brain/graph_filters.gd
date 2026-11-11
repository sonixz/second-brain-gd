class_name GraphFilters
extends HBoxContainer
## Filter bar over the graph (Loop 13): types, origins, date, a word or theme, packs.
## The summary says what is shown; ✕ clears everything.

signal changed(filter: Dictionary)
signal layout_changed(mode: String)
signal legend_toggled(on: bool)
signal lanes_changed(mode: String)              # the timeline's lanes: place, type, origin (VIEW-D)
signal time_changed(fraction: float)            # the time cursor: 0 = the first item, 1 = now (everything)
signal save_view_asked(view_name: String)       # « save what I see under this name » (VIEW-B)
signal saved_view_opened(view: Dictionary)      # {name, layout, filter, center, zoom}

## [id, label] pairs; the labels follow the interface language.
static func types() -> Array:
	return [["note", I18n.t("Notes")], ["idea", I18n.t("Ideas")], ["article", I18n.t("Articles")],
		["document", I18n.t("Documents")], ["image", I18n.t("Images")], ["reference", I18n.t("References")],
		["quote", I18n.t("Quotes")], ["list", I18n.t("Lists")], ["journal", I18n.t("Journal")]]


static func origins() -> Array:
	return [["typed", I18n.t("Typed")], ["voice", I18n.t("Spoken")], ["url", I18n.t("Web")], ["file", I18n.t("Files")],
		["pack", I18n.t("Packs")]]


## The views of the graph, in the picker's order: [layout id, label]. The ids are GraphView.LAYOUTS.
static func views() -> Array:
	return [["zones", I18n.t("Zones")], ["timeline", I18n.t("Timeline")], ["focus", I18n.t("Focus")]]


static func days() -> Array:
	return [[0, I18n.t("Any time")], [1, I18n.t("Today")], [7, I18n.t("Last 7 days")], [30, I18n.t("Last 30 days")],
		[90, I18n.t("Last 90 days")], [365, I18n.t("Last year")]]


## What a lane of the timeline can stand for: [GraphView.LANES id, label].
static func lanes() -> Array:
	return [["place", I18n.t("Lanes: places")], ["type", I18n.t("Lanes: types")], ["origin", I18n.t("Lanes: origins")]]

var filter: Dictionary = {}
var summary: Label
var clear_button: Button
var view_pick: OptionButton
var legend_button: Button
var saved_button: Button
var lanes_pick: OptionButton
var time_button: Button
var time_bar: HBoxContainer      # a second row, placed under this bar by the brain screen
var time_slider: HSlider
var time_label: Label
var play_button: Button
var playing := false
var _play_at := 1.0
const PLAY_SECONDS := 18.0       # the whole life of the brain replayed in about this long
var saved_popup: PopupPanel
var _saved_rows: VBoxContainer
var _saved_name: LineEdit
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
	view_pick = OptionButton.new()
	view_pick.name = "ViewPick"
	view_pick.tooltip_text = I18n.t("The view of the graph. Zones: items around their place. Timeline: items on a time axis, one lane per place. Focus: one item and what is linked to it, ring by ring")
	for v in views():
		view_pick.add_item(str(v[1]))
	view_pick.item_selected.connect(func(i: int) -> void:
		lanes_pick.visible = str(views()[i][0]) == "timeline"
		layout_changed.emit(str(views()[i][0])))
	add_child(view_pick)
	lanes_pick = OptionButton.new()
	lanes_pick.name = "LanesPick"
	lanes_pick.visible = false
	lanes_pick.tooltip_text = I18n.t("One lane per place, per type of item, or per origin (typed, spoken, web, files)")
	for l in lanes():
		lanes_pick.add_item(str(l[1]))
	lanes_pick.item_selected.connect(func(i: int) -> void: lanes_changed.emit(str(lanes()[i][0])))
	add_child(lanes_pick)
	time_button = Button.new()
	time_button.name = "TimeButton"
	time_button.text = I18n.t("Time")
	time_button.toggle_mode = true
	time_button.tooltip_text = I18n.t("Go back in time: see the brain as it was, or play it growing")
	time_button.toggled.connect(_toggle_time)
	add_child(time_button)
	time_bar = HBoxContainer.new()
	time_bar.name = "TimeBar"
	time_bar.visible = false
	time_bar.add_theme_constant_override("separation", 8)
	play_button = Button.new()
	play_button.text = "▶"
	play_button.tooltip_text = I18n.t("Play: the brain grows from its first item to now")
	play_button.pressed.connect(func() -> void: set_playing(not playing))
	time_bar.add_child(play_button)
	time_slider = HSlider.new()
	time_slider.min_value = 0.0
	time_slider.max_value = 1.0
	time_slider.step = 0.001
	time_slider.value = 1.0
	time_slider.custom_minimum_size = Vector2(360, 0)
	time_slider.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	time_slider.value_changed.connect(func(v: float) -> void: time_changed.emit(v))
	time_bar.add_child(time_slider)
	time_label = Label.new()
	time_label.theme_type_variation = "Muted"
	time_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	time_bar.add_child(time_label)
	set_process(false)
	saved_button = Button.new()
	saved_button.name = "SavedViews"
	saved_button.text = I18n.t("★ Views")
	saved_button.tooltip_text = I18n.t("Your saved views: the view, its filters and where you were looking, under a name")
	saved_button.pressed.connect(_open_saved)
	add_child(saved_button)
	saved_popup = PopupPanel.new()
	add_child(saved_popup)
	var saved_col := VBoxContainer.new()
	saved_col.custom_minimum_size = Vector2(320, 0)
	saved_col.add_theme_constant_override("separation", 6)
	saved_popup.add_child(saved_col)
	_saved_rows = VBoxContainer.new()
	saved_col.add_child(_saved_rows)
	var save_line := HBoxContainer.new()
	saved_col.add_child(save_line)
	_saved_name = LineEdit.new()
	_saved_name.placeholder_text = I18n.t("A name for what you see now")
	_saved_name.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_saved_name.text_submitted.connect(func(_t: String) -> void: _ask_save())
	save_line.add_child(_saved_name)
	var save := Button.new()
	save.text = I18n.t("Save")
	save.pressed.connect(_ask_save)
	save_line.add_child(save)
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


func _toggle_time(on: bool) -> void:
	time_bar.visible = on
	if not on:  # closing the bar comes back to now
		set_playing(false)
		time_slider.value = 1.0


## Plays the brain growing: from the cursor (or from the start when it is at the end) to now.
func set_playing(on: bool) -> void:
	playing = on
	play_button.text = "⏸" if on else "▶"
	if on and time_slider.value >= 1.0:
		time_slider.value = 0.0
	_play_at = time_slider.value
	set_process(on)


func _process(delta: float) -> void:
	_play_at = minf(1.0, _play_at + delta / PLAY_SECONDS)  # kept apart: one frame is less than a step of the slider
	time_slider.value = _play_at
	if _play_at >= 1.0:
		set_playing(false)


## Sets the timeline's lanes from outside (saved views).
func set_lanes(mode: String) -> void:
	var all := lanes()
	for i in all.size():
		if str(all[i][0]) == mode and lanes_pick.selected != i:
			lanes_pick.select(i)
			lanes_changed.emit(mode)


## The view shown in the picker ("zones", "timeline"…).
func view() -> String:
	return str(views()[maxi(0, view_pick.selected)][0])


## Picks a view from outside (the assistant, saved state, the tools); unknown ids are ignored.
func set_view(mode: String) -> void:
	var all := views()
	for i in all.size():
		if str(all[i][0]) == mode and view_pick.selected != i:
			view_pick.select(i)
			lanes_pick.visible = mode == "timeline"
			layout_changed.emit(mode)


## Shows a view in the picker without asking for it again (the graph refused or changed it by itself).
func show_view(mode: String) -> void:
	var all := views()
	for i in all.size():
		if str(all[i][0]) == mode:
			view_pick.select(i)
			lanes_pick.visible = mode == "timeline"


# ------------------------------------------------------------ saved views (VIEW-B)
## Saved views live with the app's preferences: [{name, layout, filter, center, zoom}], in the order they were saved.
static func saved_views() -> Array:
	var all: Variant = SbSettings.get_value("graph", "saved_views", [])
	return all if all is Array else []


## The saved view with this name (case does not matter), or {}.
static func find_view(view_name: String) -> Dictionary:
	for v in saved_views():
		if str((v as Dictionary).get("name", "")).to_lower() == view_name.strip_edges().to_lower():
			return v
	return {}


## Saves a view; one with the same name is replaced, in its place.
static func store_view(view: Dictionary) -> void:
	var all := saved_views()
	for i in all.size():
		if str((all[i] as Dictionary).get("name", "")).to_lower() == str(view.get("name", "")).to_lower():
			all[i] = view
			SbSettings.set_value("graph", "saved_views", all)
			return
	all.append(view)
	SbSettings.set_value("graph", "saved_views", all)


static func forget_view(view_name: String) -> void:
	SbSettings.set_value("graph", "saved_views", saved_views().filter(func(v: Variant) -> bool:
		return str((v as Dictionary).get("name", "")).to_lower() != view_name.to_lower()))


func _open_saved() -> void:
	_render_saved()
	var r := saved_button.get_global_rect()
	saved_popup.popup(Rect2i(Vector2i(int(r.position.x), int(r.end.y + 6)), Vector2i(340, 0)))


func _ask_save() -> void:
	var view_name := _saved_name.text.strip_edges()
	if view_name == "":
		return
	_saved_name.text = ""
	save_view_asked.emit(view_name)  # the brain screen adds the camera and stores it
	_render_saved()


func _render_saved() -> void:
	for c in _saved_rows.get_children():
		_saved_rows.remove_child(c)
		c.queue_free()
	var all := saved_views()
	if all.is_empty():
		var none := Label.new()
		none.text = I18n.t("No saved view yet")
		none.theme_type_variation = "Muted"
		_saved_rows.add_child(none)
	for v in all:
		var view: Dictionary = v
		var row := HBoxContainer.new()
		_saved_rows.add_child(row)
		var open := Button.new()
		open.text = str(view.get("name", ""))
		open.alignment = HORIZONTAL_ALIGNMENT_LEFT
		open.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		open.tooltip_text = "%s%s" % [_view_label(str(view.get("layout", "zones"))),
			(" · " + describe(view.get("filter", {}))) if not (view.get("filter", {}) as Dictionary).is_empty() else ""]
		open.pressed.connect(func() -> void:
			saved_popup.hide()
			saved_view_opened.emit(view))
		row.add_child(open)
		var forget := Button.new()
		forget.text = "✕"
		forget.theme_type_variation = "GhostButton"
		forget.tooltip_text = I18n.t("Forget this view")
		forget.pressed.connect(func() -> void:
			forget_view(str(view.get("name", "")))
			_render_saved())
		row.add_child(forget)


static func _view_label(mode: String) -> String:
	for v in views():
		if str(v[0]) == mode:
			return str(v[1])
	return mode


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
