extends Control
## Onboarding step after the first setup: bring your own OpenAI key for voice
## capture, or skip (typing works without it). Shown once.

var app: SbApp
var panel: VoiceKeyPanel
var continue_button: Button


func bind(a: SbApp) -> void:
	app = a


func _ready() -> void:
	var center := CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	add_child(center)
	var card := PanelContainer.new()
	card.theme_type_variation = "Glass"
	card.custom_minimum_size = Vector2(620, 0)
	center.add_child(card)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 14)
	card.add_child(col)
	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 14)
	col.add_child(head)
	var icon := TextureRect.new()
	icon.texture = load("res://assets/icons/mic.svg")
	icon.custom_minimum_size = Vector2(40, 40)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.modulate = SbTheme.MINT
	head.add_child(icon)
	var htext := VBoxContainer.new()
	head.add_child(htext)
	var over := Label.new()
	over.text = I18n.t("ONE LAST THING · OPTIONAL")
	over.theme_type_variation = "Overline"
	htext.add_child(over)
	var title := Label.new()
	title.text = I18n.t("Talk to your Second Brain")
	title.theme_type_variation = "Heading"
	title.add_theme_font_size_override("font_size", 24)
	htext.add_child(title)
	var body := Label.new()
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.text = I18n.t("Press the microphone, speak, and watch your words appear live. Voice capture uses OpenAI's realtime transcription with your own API key, so it is billed to your account and you stay in control.")
	col.add_child(body)
	panel = VoiceKeyPanel.new().setup(app, true)
	panel.saved.connect(func(st: Dictionary) -> void:
		if bool(st.get("configured", false)):
			continue_button.visible = true
			continue_button.grab_focus())
	panel.skipped.connect(finish)
	col.add_child(panel)
	continue_button = Button.new()
	continue_button.text = I18n.t("Enter your Second Brain")
	continue_button.theme_type_variation = "PrimaryButton"
	continue_button.visible = false
	continue_button.custom_minimum_size = Vector2(0, 48)
	continue_button.pressed.connect(finish)
	col.add_child(continue_button)


func finish() -> void:
	SbSettings.set_value("onboarding", "voice_done", true)
	app.show_brain()
