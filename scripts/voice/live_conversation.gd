class_name LiveConversation
extends Control
## Loop 7b: a real spoken conversation with the assistant. Owned by the app (not a screen),
## so it survives theme changes and screen switches. F9 starts and ends it; F8 interrupts.
##
## Echo: Godot has no echo cancellation. With speakers, the microphone is paused while the
## assistant speaks (interrupt with F8); with headphones, you can simply talk over it.

signal state_changed(state: String)
signal user_said(text: String)
signal assistant_said(text: String)
signal finished(reason: String)

const KEY_TOGGLE := KEY_F9
const ENDINGS := {"goodbye": "Conversation ended. À la prochaine!", "user": "Conversation ended.",
	"idle": "Conversation ended after a few quiet minutes.", "cap": "Conversation ended: this conversation reached its spending limit.",
	"max_minutes": "Conversation ended: maximum length reached.", "closed": "Conversation ended."}

var app: SbApp
var stream: LiveStream
var player: LivePlayer
var capture: VoiceCapture
var state := "idle"          # idle | connecting | listening | speaking | thinking
var active := false
var cost_usd: Variant = 0.0
var minutes := 0.0
var last_error := ""
var last_end := ""
var headphones := false
var _pill: PanelContainer
var _dot: Label
var _label: Label
var _meter: Label
var _ending := false


func setup(a: SbApp) -> LiveConversation:
	app = a
	return self


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	z_index = 50
	stream = LiveStream.new()
	add_child(stream)
	player = LivePlayer.new()
	add_child(player)
	capture = VoiceCapture.new()
	add_child(capture)
	capture.chunk.connect(_on_mic)
	stream.audio.connect(func(pcm: PackedByteArray) -> void: player.push_pcm(pcm))
	app.audio.voice_speed_changed.connect(func(s: float) -> void: player.set_speed(s))
	stream.audio_start.connect(func() -> void:
		player.new_answer()
		_set_state("speaking"))
	stream.speech_started.connect(_on_user_speaks)
	stream.user_text.connect(func(t: String) -> void: user_said.emit(t))
	stream.assistant_text.connect(func(t: String) -> void: assistant_said.emit(t))
	stream.tool.connect(func(_n: String) -> void: _set_state("thinking"))
	stream.ui_actions.connect(_on_ui)
	stream.cost.connect(func(usd: Variant, m: float) -> void:
		cost_usd = usd
		minutes = m
		_refresh())
	stream.ended.connect(func(reason: String) -> void: stop(reason))
	stream.failed.connect(func(msg: String) -> void:
		last_error = msg
		if active:
			_label.text = msg
		if state == "connecting":
			stop("error"))
	stream.closed.connect(func() -> void:
		if active:
			stop("closed"))
	_build_pill()


func _build_pill() -> void:
	_pill = PanelContainer.new()
	_pill.theme_type_variation = "Glass"
	# Just above the capture bar, where it covers nothing important.
	_pill.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	_pill.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_pill.grow_vertical = Control.GROW_DIRECTION_BEGIN
	_pill.offset_bottom = -108
	_pill.offset_top = -152
	_pill.offset_left = -260
	_pill.offset_right = 260
	_pill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_pill.visible = false
	add_child(_pill)
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 10)
	_pill.add_child(row)
	_dot = Label.new()
	_dot.text = "●"
	_dot.add_theme_font_size_override("font_size", 18)
	row.add_child(_dot)
	_label = Label.new()
	_label.add_theme_font_size_override("font_size", 17)
	row.add_child(_label)
	_meter = Label.new()
	_meter.theme_type_variation = "Muted"
	row.add_child(_meter)


func _process(_delta: float) -> void:
	if not active:
		return
	# Back to listening once the assistant's voice has finished playing.
	if state == "speaking" and not player.is_playing():
		_set_state("listening")
	_dot.modulate.a = 0.55 + 0.45 * sin(Time.get_ticks_msec() / 260.0) if state == "listening" else 1.0


func _set_state(s: String) -> void:
	state = s
	_refresh()
	state_changed.emit(s)


func _refresh() -> void:
	if _label == null:
		return
	var texts := {"connecting": "Connecting…", "listening": "Live · I'm listening", "speaking":
		"Live · speaking" + ("" if headphones else " — F8 to interrupt"), "thinking": "Live · looking it up…"}
	_label.text = str(texts.get(state, "Live"))
	var col := SbTheme.WARM if state == "listening" else (SbTheme.MINT if state == "speaking" else SbTheme.INFO)
	_dot.add_theme_color_override("font_color", col)
	var money := ("$%.3f" % float(cost_usd)) if cost_usd != null else "cost unknown"
	_meter.text = "%s · %.1f min · F9 to end" % [money, minutes]


## use_mic = false lets tests feed audio frames with capture.feed_frames().
func start(use_mic: bool = true) -> bool:
	if active or app == null:
		return false
	last_error = ""
	last_end = ""
	cost_usd = 0.0
	minutes = 0.0
	headphones = bool(SbSettings.get_value("voice", "headphones", false))
	player.set_speed(app.audio.voice_speed)
	active = true
	_pill.visible = true
	_set_state("connecting")
	var err := stream.connect_to(app.backend.api.port, app.backend.api.token)
	if err != OK:
		last_error = "Cannot open the live connection (%s)." % error_string(err)
		stop("error")
		return false
	var deadline := Time.get_ticks_msec() + 15000
	while not stream.is_ready and last_error == "" and active and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	if not stream.is_ready:
		if last_error == "":
			last_error = "The live conversation did not start."
		stop("error")
		return false
	if use_mic:
		capture.start()
	app.audio.play("mic_start")
	app.audio._set_duck(true)
	_set_state("listening")
	return true


func stop(reason: String = "user") -> void:
	if not active or _ending:
		return
	_ending = true
	active = false
	last_end = reason
	if capture.recording:
		capture.stop()
	stream.stop()
	player.clear()
	app.audio._set_duck(false)
	app.audio.play("mic_stop" if reason != "error" else "error")
	state = "idle"
	_pill.visible = reason == "error"
	if reason == "error":
		_label.text = last_error
		_meter.text = ""
		get_tree().create_timer(6.0).timeout.connect(func() -> void:
			if not active:
				_pill.visible = false)
	_ending = false
	state_changed.emit("idle")
	finished.emit(reason)


func toggle() -> void:
	if active:
		stop("user")
	else:
		start(true)


## F8 while the assistant speaks: stop its voice and tell OpenAI how much was heard.
func barge_in() -> void:
	if not active:
		return
	if player.is_playing():
		var heard := player.heard_ms()
		player.clear()
		stream.interrupt(heard)
	_set_state("listening")


func _on_user_speaks() -> void:
	if player.is_playing():
		barge_in()  # with headphones the user can just talk over the assistant
	elif state != "thinking":
		_set_state("listening")


func _on_mic(pcm: PackedByteArray) -> void:
	if not active:
		return
	# Speakers: never send the assistant's own voice back as if the user said it.
	if not headphones and player.is_playing():
		return
	stream.send_audio(pcm)


func _on_ui(actions: Array) -> void:
	if app.current_screen != "brain":
		app.show_brain()
		for _i in 30:
			await get_tree().process_frame
	var brain := app.current()
	if brain != null and brain.has_method("run_ui_actions"):
		brain.call("run_ui_actions", actions)


func _unhandled_key_input(event: InputEvent) -> void:
	var k := event as InputEventKey
	if k == null or k.echo or not k.pressed:
		return
	if k.keycode == KEY_TOGGLE and app.current_screen in ["brain", "console"]:
		var screen := app.current()
		if not active and screen != null and screen.has_method("toggle_live"):
			screen.call("toggle_live")  # checks the key and shows the assistant panel first
		else:
			toggle()
		get_viewport().set_input_as_handled()
