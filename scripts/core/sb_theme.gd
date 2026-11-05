class_name SbTheme
extends RefCounted
## Visual identity. Colours are roles (the names come from the first green
## palette): BG/PANEL = surfaces, FOREST = primary deep, FOREST_LIGHT = primary,
## MINT = accent, MINT_SOFT = soft accent, WARM = secondary accent (ideas).
## Several themes swap these roles; `apply()` switches and rebuilds the Theme.

const THEMES := ["morning", "focus", "evening", "forest"]
const THEME_LABELS := {"auto": "Auto (time of day)", "morning": "Morning", "focus": "Focus",
	"evening": "Evening", "forest": "Forest"}  # English; shown text is theme_label()


## A theme's name as shown, in the interface language ("auto" included).
static func theme_label(key: String) -> String:
	match key:
		"auto":
			return I18n.t("Auto (time of day)")
		"morning":
			return I18n.t("Morning")
		"focus":
			return I18n.t("Focus")
		"evening":
			return I18n.t("Evening")
		"forest":
			return I18n.t("Forest")
	return str(THEME_LABELS.get(key, key.capitalize()))

const PALETTES := {
	# Soft, felted blue: calm, cosy, not too dark. Sunrise peach as second accent.
	"morning": {"BG": "2b3c54", "BG_2": "31445e", "PANEL": "33475f", "PANEL_2": "3b5270", "BORDER": "4b6483",
		"FOREST": "3e6189", "FOREST_LIGHT": "79a5d3", "MINT": "a9d4ff", "MINT_SOFT": "d9edff", "WARM": "ffd2a1",
		"TEXT": "f1f6fc", "MUTED": "b5c6da", "FAINT": "8196ae", "WARN": "ffd27a", "ERROR": "ff9d9d",
		"INFO": "a6dcff", "ON_ACCENT": "13233a"},
	# Deeper night-blue with aqua: concentration.
	"focus": {"BG": "172331", "BG_2": "1b293a", "PANEL": "1f2f42", "PANEL_2": "263a51", "BORDER": "33506d",
		"FOREST": "2b5a7a", "FOREST_LIGHT": "5596bb", "MINT": "8fe3ef", "MINT_SOFT": "c9f4f9", "WARM": "c8b6ff",
		"TEXT": "e8f1f7", "MUTED": "9fb6c8", "FAINT": "617c92", "WARN": "f5cf74", "ERROR": "ff8f8f",
		"INFO": "93cff5", "ON_ACCENT": "0d1d26"},
	# Dusk indigo with amber: winding down.
	"evening": {"BG": "29233f", "BG_2": "2f2846", "PANEL": "352d4f", "PANEL_2": "3e355c", "BORDER": "554a78",
		"FOREST": "5b4a8c", "FOREST_LIGHT": "9483c9", "MINT": "ffc296", "MINT_SOFT": "ffe2cc", "WARM": "ffa9c6",
		"TEXT": "f6f0fb", "MUTED": "c6bad8", "FAINT": "8c80a6", "WARN": "ffd27a", "ERROR": "ff9a9a",
		"INFO": "b9c8ff", "ON_ACCENT": "2a1a14"},
	# The original Loop 0 identity.
	"forest": {"BG": "0a1310", "BG_2": "0d1914", "PANEL": "0f1d18", "PANEL_2": "14271f", "BORDER": "1f3a2f",
		"FOREST": "1e6b4c", "FOREST_LIGHT": "2f8f68", "MINT": "5ef2b0", "MINT_SOFT": "a8f7d3", "WARM": "f4d58d",
		"TEXT": "e4f1ea", "MUTED": "88a598", "FAINT": "4f6b5f", "WARN": "f4c35a", "ERROR": "ff6f6f",
		"INFO": "7cc8ff", "ON_ACCENT": "06110c"},
}

static var current := "morning"
static var BG := Color("2b3c54")
static var BG_2 := Color("31445e")
static var PANEL := Color("33475f")
static var PANEL_2 := Color("3b5270")
static var BORDER := Color("4b6483")
static var FOREST := Color("3e6189")
static var FOREST_LIGHT := Color("79a5d3")
static var MINT := Color("a9d4ff")
static var MINT_SOFT := Color("d9edff")
static var WARM := Color("ffd2a1")
static var TEXT := Color("f1f6fc")
static var MUTED := Color("b5c6da")
static var FAINT := Color("8196ae")
static var WARN := Color("ffd27a")
static var ERROR := Color("ff9d9d")
static var INFO := Color("a6dcff")
static var ON_ACCENT := Color("13233a")


## "auto" picks by local hour: 5-11 morning, 11-17 focus, otherwise evening.
static func resolve(name: String) -> String:
	if name in THEMES:
		return name
	var hour: int = Time.get_datetime_dict_from_system()["hour"]
	if hour >= 5 and hour < 11:
		return "morning"
	if hour >= 11 and hour < 17:
		return "focus"
	return "evening"


static func apply(name: String) -> String:
	var resolved := resolve(name)
	var p: Dictionary = PALETTES[resolved]
	current = resolved
	BG = Color(str(p["BG"]))
	BG_2 = Color(str(p["BG_2"]))
	PANEL = Color(str(p["PANEL"]))
	PANEL_2 = Color(str(p["PANEL_2"]))
	BORDER = Color(str(p["BORDER"]))
	FOREST = Color(str(p["FOREST"]))
	FOREST_LIGHT = Color(str(p["FOREST_LIGHT"]))
	MINT = Color(str(p["MINT"]))
	MINT_SOFT = Color(str(p["MINT_SOFT"]))
	WARM = Color(str(p["WARM"]))
	TEXT = Color(str(p["TEXT"]))
	MUTED = Color(str(p["MUTED"]))
	FAINT = Color(str(p["FAINT"]))
	WARN = Color(str(p["WARN"]))
	ERROR = Color(str(p["ERROR"]))
	INFO = Color(str(p["INFO"]))
	ON_ACCENT = Color(str(p["ON_ACCENT"]))
	return resolved


static func kind_color(kind: String) -> Color:
	match kind:
		"idea":
			return WARM
		"task":
			return INFO
		"journal":
			return MINT_SOFT
		"reference":
			return MUTED
	return MINT


static func status_color(status: String) -> Color:
	match status:
		"ok", "running", "ready":
			return MINT
		"skipped":
			return FOREST_LIGHT
		"started", "progress", "pending_active", "checking":
			return INFO
		"warning", "degraded":
			return WARN
		"error", "unreachable", "stopped":
			return ERROR
	return FAINT


static func box(color: Color, radius: int = 10, border: Color = Color(0, 0, 0, 0), border_w: int = 0,
		pad: float = 12.0) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = color
	s.set_corner_radius_all(radius)
	s.border_color = border
	s.set_border_width_all(border_w)
	s.content_margin_left = pad
	s.content_margin_right = pad
	s.content_margin_top = pad * 0.6
	s.content_margin_bottom = pad * 0.6
	s.anti_aliasing = true
	return s


static func glass() -> StyleBoxFlat:
	var s := box(Color(PANEL, 0.86), 18, Color(BORDER, 0.9), 1, 18)
	s.shadow_color = Color(0, 0, 0, 0.22)
	s.shadow_size = 18
	s.shadow_offset = Vector2(0, 6)
	return s


static func font(weight: int = 400) -> SystemFont:
	var f := SystemFont.new()
	f.font_names = PackedStringArray(["Segoe UI Variable Text", "Segoe UI", "Inter", "Ubuntu", "Noto Sans",
		"Helvetica Neue", "Arial", "sans-serif"])
	f.font_weight = weight
	f.antialiasing = TextServer.FONT_ANTIALIASING_GRAY
	return f


static func mono() -> SystemFont:
	var f := SystemFont.new()
	f.font_names = PackedStringArray(["Cascadia Mono", "Consolas", "JetBrains Mono", "DejaVu Sans Mono",
		"monospace"])
	return f


static func build() -> Theme:
	var t := Theme.new()
	t.default_font = font(400)
	t.default_font_size = 15

	t.set_color("font_color", "Label", TEXT)
	t.set_type_variation("Muted", "Label")
	t.set_color("font_color", "Muted", MUTED)
	t.set_font_size("font_size", "Muted", 13)
	t.set_type_variation("Heading", "Label")
	t.set_font("font", "Heading", font(650))
	t.set_font_size("font_size", "Heading", 20)
	t.set_type_variation("Title", "Label")
	t.set_font("font", "Title", font(750))
	t.set_font_size("font_size", "Title", 34)
	t.set_type_variation("Overline", "Label")
	t.set_font("font", "Overline", font(650))
	t.set_font_size("font_size", "Overline", 11)
	t.set_color("font_color", "Overline", MINT)

	for type in ["Button", "PrimaryButton", "GhostButton"]:
		if type != "Button":
			t.set_type_variation(type, "Button")
		t.set_font("font", type, font(600))
		t.set_font_size("font_size", type, 15)
	t.set_stylebox("normal", "Button", box(PANEL_2, 10, BORDER, 1, 18))
	t.set_stylebox("hover", "Button", box(PANEL_2.lightened(0.06), 10, FOREST_LIGHT, 1, 18))
	t.set_stylebox("pressed", "Button", box(PANEL_2.darkened(0.08), 10, MINT, 1, 18))
	t.set_stylebox("disabled", "Button", box(PANEL, 10, BORDER, 1, 18))
	t.set_stylebox("focus", "Button", box(Color(0, 0, 0, 0), 10, MINT_SOFT, 2, 18))
	t.set_color("font_color", "Button", TEXT)
	t.set_color("font_hover_color", "Button", MINT_SOFT)
	t.set_color("font_disabled_color", "Button", FAINT)

	t.set_stylebox("normal", "PrimaryButton", box(MINT, 12, Color(0, 0, 0, 0), 0, 26))
	t.set_stylebox("hover", "PrimaryButton", box(MINT_SOFT, 12, Color(0, 0, 0, 0), 0, 26))
	t.set_stylebox("pressed", "PrimaryButton", box(MINT.darkened(0.12), 12, Color(0, 0, 0, 0), 0, 26))
	t.set_stylebox("disabled", "PrimaryButton", box(FOREST, 12, Color(0, 0, 0, 0), 0, 26))
	for c in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		t.set_color(c, "PrimaryButton", ON_ACCENT)
	t.set_color("font_disabled_color", "PrimaryButton", MUTED)

	t.set_stylebox("normal", "GhostButton", box(Color(0, 0, 0, 0), 10, Color(0, 0, 0, 0), 0, 12))
	t.set_stylebox("hover", "GhostButton", box(Color(1, 1, 1, 0.04), 10, Color(0, 0, 0, 0), 0, 12))
	t.set_stylebox("pressed", "GhostButton", box(Color(1, 1, 1, 0.07), 10, Color(0, 0, 0, 0), 0, 12))
	t.set_color("font_color", "GhostButton", MUTED)
	t.set_color("font_hover_color", "GhostButton", MINT_SOFT)

	t.set_stylebox("panel", "PanelContainer", box(PANEL, 14, BORDER, 1, 20))
	t.set_type_variation("Card", "PanelContainer")
	t.set_stylebox("panel", "Card", box(PANEL, 14, BORDER, 1, 20))
	t.set_type_variation("Inset", "PanelContainer")
	t.set_stylebox("panel", "Inset", box(BG_2, 10, BORDER, 1, 14))
	t.set_type_variation("ErrorPanel", "PanelContainer")
	t.set_stylebox("panel", "ErrorPanel", box(BG.lerp(ERROR, 0.12), 12, ERROR.darkened(0.35), 1, 16))
	# Floating glass panels over the graph
	t.set_type_variation("Glass", "PanelContainer")
	t.set_stylebox("panel", "Glass", glass())
	t.set_type_variation("Pill", "PanelContainer")
	t.set_stylebox("panel", "Pill", box(Color(PANEL, 0.82), 22, Color(BORDER, 0.9), 1, 14))
	t.set_stylebox("normal", "OptionButton", box(PANEL_2, 10, BORDER, 1, 14))
	t.set_stylebox("hover", "OptionButton", box(PANEL_2.lightened(0.06), 10, FOREST_LIGHT, 1, 14))
	t.set_stylebox("pressed", "OptionButton", box(PANEL_2, 10, MINT, 1, 14))
	t.set_color("font_color", "OptionButton", TEXT)
	t.set_stylebox("panel", "PopupMenu", box(PANEL_2, 10, BORDER, 1, 8))
	t.set_color("font_color", "PopupMenu", TEXT)
	t.set_color("font_hover_color", "PopupMenu", MINT_SOFT)
	t.set_stylebox("hover", "PopupMenu", box(Color(MINT, 0.12), 6, Color(0, 0, 0, 0), 0, 8))
	t.set_stylebox("panel", "PopupPanel", box(PANEL, 14, BORDER, 1, 16))
	t.set_stylebox("normal", "TextEdit", box(Color(BG, 0.55), 10, BORDER, 1, 12))
	t.set_stylebox("focus", "TextEdit", box(Color(BG, 0.55), 10, FOREST_LIGHT, 1, 12))
	t.set_color("font_color", "TextEdit", TEXT)
	t.set_color("caret_color", "TextEdit", MINT)
	t.set_color("selection_color", "TextEdit", Color(MINT, 0.25))
	t.set_color("caret_color", "LineEdit", MINT)
	t.set_color("selection_color", "LineEdit", Color(MINT, 0.25))
	# Check boxes stay light: no button frame, a soft highlight on hover.
	for cb_type in ["CheckBox"]:
		t.set_stylebox("normal", cb_type, box(Color(0, 0, 0, 0), 8, Color(0, 0, 0, 0), 0, 6))
		t.set_stylebox("pressed", cb_type, box(Color(0, 0, 0, 0), 8, Color(0, 0, 0, 0), 0, 6))
		t.set_stylebox("hover", cb_type, box(Color(1, 1, 1, 0.05), 8, Color(0, 0, 0, 0), 0, 6))
		t.set_stylebox("hover_pressed", cb_type, box(Color(1, 1, 1, 0.05), 8, Color(0, 0, 0, 0), 0, 6))
		t.set_stylebox("focus", cb_type, box(Color(0, 0, 0, 0), 8, Color(MINT, 0.5), 1, 6))
		t.set_color("font_color", cb_type, TEXT)
		t.set_color("font_pressed_color", cb_type, MUTED)
		t.set_color("font_hover_color", cb_type, MINT_SOFT)
		t.set_color("font_hover_pressed_color", cb_type, MUTED)
	t.set_type_variation("CaptureEdit", "LineEdit")
	t.set_stylebox("normal", "CaptureEdit", box(Color(PANEL, 0.92), 26, BORDER, 1, 22))
	t.set_stylebox("focus", "CaptureEdit", box(Color(PANEL, 0.97), 26, MINT, 2, 22))
	t.set_font_size("font_size", "CaptureEdit", 17)
	t.set_color("font_uneditable_color", "CaptureEdit", TEXT)  # live transcript stays readable
	t.set_type_variation("SearchEdit", "LineEdit")
	t.set_stylebox("normal", "SearchEdit", box(Color(PANEL, 0.8), 20, BORDER, 1, 16))
	t.set_stylebox("focus", "SearchEdit", box(Color(PANEL, 0.95), 20, FOREST_LIGHT, 1, 16))
	var track := box(BG_2, 4, BORDER, 1, 0)
	track.content_margin_top = 3
	track.content_margin_bottom = 3
	t.set_stylebox("slider", "HSlider", track)
	var filled := box(FOREST_LIGHT, 4, Color(0, 0, 0, 0), 0, 0)
	filled.content_margin_top = 3
	filled.content_margin_bottom = 3
	t.set_stylebox("grabber_area", "HSlider", filled)
	var filled_hi := filled.duplicate() as StyleBoxFlat
	filled_hi.bg_color = MINT
	t.set_stylebox("grabber_area_highlight", "HSlider", filled_hi)

	var bar_bg := box(BG_2, 6, BORDER, 1, 0)
	var bar_fill := box(MINT, 6, Color(0, 0, 0, 0), 0, 0)
	t.set_stylebox("background", "ProgressBar", bar_bg)
	t.set_stylebox("fill", "ProgressBar", bar_fill)
	t.set_color("font_color", "ProgressBar", TEXT)

	t.set_stylebox("normal", "LineEdit", box(BG_2, 8, BORDER, 1, 10))
	t.set_stylebox("focus", "LineEdit", box(BG_2, 8, MINT, 1, 10))
	t.set_color("font_color", "LineEdit", TEXT)
	t.set_color("font_placeholder_color", "LineEdit", FAINT)

	t.set_stylebox("normal", "RichTextLabel", box(Color(0, 0, 0, 0), 0, Color(0, 0, 0, 0), 0, 0))
	t.set_color("default_color", "RichTextLabel", MUTED)
	t.set_font("mono_font", "RichTextLabel", mono())
	t.set_font("normal_font", "RichTextLabel", font(400))
	t.set_font("bold_font", "RichTextLabel", font(650))
	t.set_font_size("normal_font_size", "RichTextLabel", 13)
	t.set_font_size("mono_font_size", "RichTextLabel", 12)
	t.set_font_size("bold_font_size", "RichTextLabel", 13)

	t.set_stylebox("panel", "TooltipPanel", box(PANEL_2, 8, BORDER, 1, 10))
	t.set_color("font_color", "TooltipLabel", TEXT)
	t.set_constant("separation", "HSeparator", 12)
	t.set_stylebox("separator", "HSeparator", box(BORDER, 0, Color(0, 0, 0, 0), 0, 0))
	return t
