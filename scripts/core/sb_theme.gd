class_name SbTheme
extends RefCounted
## Visual identity: dark, forest green, mint accents. Built in code so every
## colour lives in one place (the landing page uses the same palette).

const BG := Color("0a1310")
const BG_2 := Color("0d1914")
const PANEL := Color("0f1d18")
const PANEL_2 := Color("14271f")
const BORDER := Color("1f3a2f")
const FOREST := Color("1e6b4c")
const FOREST_LIGHT := Color("2f8f68")
const MINT := Color("5ef2b0")
const MINT_SOFT := Color("a8f7d3")
const TEXT := Color("e4f1ea")
const MUTED := Color("88a598")
const FAINT := Color("4f6b5f")
const WARN := Color("f4c35a")
const ERROR := Color("ff6f6f")
const INFO := Color("7cc8ff")


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
	t.set_stylebox("hover", "Button", box(Color("1a3328"), 10, FOREST_LIGHT, 1, 18))
	t.set_stylebox("pressed", "Button", box(Color("10241b"), 10, MINT, 1, 18))
	t.set_stylebox("disabled", "Button", box(PANEL, 10, BORDER, 1, 18))
	t.set_stylebox("focus", "Button", box(Color(0, 0, 0, 0), 10, MINT_SOFT, 2, 18))
	t.set_color("font_color", "Button", TEXT)
	t.set_color("font_hover_color", "Button", MINT_SOFT)
	t.set_color("font_disabled_color", "Button", FAINT)

	t.set_stylebox("normal", "PrimaryButton", box(MINT, 12, Color(0, 0, 0, 0), 0, 26))
	t.set_stylebox("hover", "PrimaryButton", box(MINT_SOFT, 12, Color(0, 0, 0, 0), 0, 26))
	t.set_stylebox("pressed", "PrimaryButton", box(Color("3fcf92"), 12, Color(0, 0, 0, 0), 0, 26))
	t.set_stylebox("disabled", "PrimaryButton", box(FOREST, 12, Color(0, 0, 0, 0), 0, 26))
	for c in ["font_color", "font_hover_color", "font_pressed_color", "font_focus_color"]:
		t.set_color(c, "PrimaryButton", Color("06110c"))
	t.set_color("font_disabled_color", "PrimaryButton", Color("9fbfb0"))

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
	t.set_stylebox("panel", "ErrorPanel", box(Color("2a1416"), 12, Color("6b2a2e"), 1, 16))

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
