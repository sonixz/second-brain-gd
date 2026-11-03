class_name AudioWidget
extends Control
## Bottom-right "ambiance" control on every screen: now playing, theme,
## music / effects / ambience volumes, next track, mute.

var app: SbApp
var button: Button
var now_label: Label
var popup: PopupPanel
var theme_option: OptionButton


func setup(a: SbApp) -> AudioWidget:
	app = a
	set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	offset_left = -260
	offset_top = -62
	offset_right = -20
	offset_bottom = -18
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var row := HBoxContainer.new()
	row.set_anchors_preset(Control.PRESET_FULL_RECT)
	row.alignment = BoxContainer.ALIGNMENT_END
	row.add_theme_constant_override("separation", 8)
	row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(row)
	now_label = Label.new()
	now_label.theme_type_variation = "Muted"
	now_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	now_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	row.add_child(now_label)
	button = Button.new()
	button.custom_minimum_size = Vector2(44, 44)
	button.tooltip_text = "Ambiance: theme, music, sounds"
	button.set_meta("sfx", "none")
	button.pressed.connect(_open)
	row.add_child(button)
	app.audio.track_changed.connect(func(_t: String) -> void: _refresh())
	_build_popup()
	_refresh()
	return self


func _refresh() -> void:
	button.text = "🔇" if app.audio.muted else "♪"
	var t := app.audio.current_title
	now_label.text = "" if t == "" or app.audio.muted else "♪ " + t


func _build_popup() -> void:
	popup = PopupPanel.new()
	add_child(popup)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	col.custom_minimum_size = Vector2(300, 0)
	popup.add_child(col)
	var over := Label.new()
	over.text = "AMBIANCE"
	over.theme_type_variation = "Overline"
	col.add_child(over)
	theme_option = OptionButton.new()
	var choice := str(SbSettings.get_value("ui", "theme", "auto"))
	for key in ["auto", "morning", "focus", "evening", "forest"]:
		theme_option.add_item(str(SbTheme.THEME_LABELS[key]))
		theme_option.set_item_metadata(theme_option.item_count - 1, key)
		if key == choice:
			theme_option.select(theme_option.item_count - 1)
	theme_option.item_selected.connect(func(i: int) -> void:
		app.set_theme_choice(str(theme_option.get_item_metadata(i))))
	col.add_child(_labelled("Theme", theme_option))
	col.add_child(_slider_row("Music", "Music", app.audio.music_enabled,
		func(on: bool) -> void: app.audio.set_music_enabled(on)))
	col.add_child(_slider_row("Effects", "SFX", true, Callable()))
	col.add_child(_slider_row("Ambience", "Ambience", app.audio.ambience_enabled,
		func(on: bool) -> void: app.audio.set_ambience_enabled(on)))
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	col.add_child(row)
	var next := Button.new()
	next.text = "Next track"
	next.pressed.connect(func() -> void: app.audio.next_track())
	row.add_child(next)
	var mute := Button.new()
	mute.text = "Unmute all" if app.audio.muted else "Mute all"
	mute.pressed.connect(func() -> void:
		app.audio.set_muted(not app.audio.muted)
		mute.text = "Unmute all" if app.audio.muted else "Mute all"
		_refresh())
	row.add_child(mute)


func _labelled(text: String, control: Control) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	var l := Label.new()
	l.text = text
	l.custom_minimum_size = Vector2(80, 0)
	row.add_child(l)
	control.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(control)
	return row


func _slider_row(text: String, bus: String, enabled: bool, toggle: Callable) -> HBoxContainer:
	var slider := HSlider.new()
	slider.min_value = 0.0
	slider.max_value = 1.0
	slider.step = 0.01
	slider.value = app.audio.volume(bus)
	slider.custom_minimum_size = Vector2(120, 24)
	slider.value_changed.connect(func(v: float) -> void:
		app.audio.set_volume(bus, v)
		if bus == "SFX":
			app.audio.play("click"))
	var row := _labelled(text, slider)
	if toggle.is_valid():
		var cb := CheckButton.new()
		cb.button_pressed = enabled
		cb.toggled.connect(func(on: bool) -> void: toggle.call(on))
		row.add_child(cb)
	return row


func _open() -> void:
	app.audio.play("click")
	popup.reset_size()
	var r := get_global_rect()
	popup.popup(Rect2i(Vector2i(int(r.end.x - 320), int(r.position.y - popup.size.y - 10)), Vector2i(320, 0)))
