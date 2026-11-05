class_name I18n
extends RefCounted
## The app's two languages (Loop 26). English is the product's language: every interface text is written in
## English in the code and goes through I18n.t(); in French it is looked up in res://i18n/fr.json (English → French).
## The FR / EN switch at the top of the app sets it (settings ui/language, English by default) and tells the engine,
## so the agents' default language, the Live transcription and the engine's own words follow.
## tools/i18n.py --check keeps fr.json in step with the code (the tests run it).

const LANGUAGES := ["en", "fr"]
const FR_PATH := "res://i18n/fr.json"

static var lang := "en"
static var _fr: Dictionary = {}


## The language saved in the settings (English the first time).
static func load_saved() -> void:
	use(str(SbSettings.get_value("ui", "language", "en")))


static func use(code: String) -> void:
	lang = code if code in LANGUAGES else "en"
	if lang == "fr" and _fr.is_empty():
		var f := FileAccess.open(FR_PATH, FileAccess.READ)
		if f != null:
			var parsed: Variant = JSON.parse_string(f.get_as_text())
			if parsed is Dictionary:
				_fr = parsed


## An interface text, in the current language. Write the English; with a format, translate first:
## I18n.t("%d of %d notes shown") % [a, b].
static func t(text: String) -> String:
	if lang == "en" or text == "":
		return text
	var out: Variant = _fr.get(text)
	return str(out) if out != null and str(out) != "" else text


static func is_french() -> bool:
	return lang == "fr"


## The FR / EN switch (top right of the welcome screen and of the Brain): pressing one rebuilds the screen in it.
static func switch(app: Node) -> HBoxContainer:
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 0)
	row.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	var group := ButtonGroup.new()
	for code in ["fr", "en"]:
		var b := Button.new()
		b.text = code.to_upper()
		b.toggle_mode = true
		b.button_group = group
		b.button_pressed = lang == code
		b.theme_type_variation = "GhostButton"
		b.custom_minimum_size = Vector2(44, 40)
		b.tooltip_text = "Français" if code == "fr" else "English"  # each language named in itself
		b.name = "Lang" + code.to_upper()
		var c: String = code
		b.pressed.connect(func() -> void: app.call("set_language", c))
		row.add_child(b)
	return row
