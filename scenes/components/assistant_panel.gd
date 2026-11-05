class_name AssistantPanel
extends VBoxContainer
## The assistant: today's conversation, the spoken morning briefing, citations
## that open notes, undo buttons for everything it changed, and its own mic.

signal note_requested(title: String)
signal brain_changed
## Interface actions the assistant asked for (open a view, a project, a note, theme, volume…).
signal ui_requested(actions: Array)

var app: SbApp
var brain: Control
var scroll: ScrollContainer
var list: VBoxContainer
var input: LineEdit
var send_button: Button
var mic_button: Button
var speak_toggle: CheckButton
var live_button: Button
var thinking: Label
var configured := false
var busy := false
var messages_shown := 0
var last_reply := ""
var _dots_t := 0.0


var last_ui_actions: Array = []
## What can be read again: every answer shown, newest last (texts only), and the last review.
var spoken_history: Array[String] = []
var last_review := ""
var replayed := ""

func setup(a: SbApp, b: Control) -> AssistantPanel:
	app = a
	brain = b
	add_theme_constant_override("separation", 8)
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var head := HBoxContainer.new()
	add_child(head)
	head.alignment = BoxContainer.ALIGNMENT_END
	speak_toggle = CheckButton.new()
	speak_toggle.text = "Voice"
	speak_toggle.tooltip_text = "The assistant reads its answers aloud (voice: marin)"
	speak_toggle.button_pressed = bool(SbSettings.get_value("assistant", "speaks", true))
	speak_toggle.toggled.connect(func(on: bool) -> void:
		SbSettings.set_value("assistant", "speaks", on)
		if not on:
			app.audio.stop_voice())
	head.add_child(speak_toggle)
	live_button = Button.new()
	live_button.text = "Talk live"
	live_button.tooltip_text = "A spoken conversation with the assistant (F9 to start and end)"
	live_button.toggle_mode = false
	live_button.pressed.connect(func() -> void: brain.call("toggle_live"))
	head.add_child(live_button)
	app.live.state_changed.connect(_on_live_state)
	_on_live_state(app.live.state)
	scroll = ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	add_child(scroll)
	list = VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.add_theme_constant_override("separation", 10)
	scroll.add_child(list)
	thinking = Label.new()
	thinking.theme_type_variation = "Muted"
	thinking.visible = false
	add_child(thinking)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	add_child(row)
	input = LineEdit.new()
	input.placeholder_text = "Ask or tell your assistant…"
	input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input.custom_minimum_size = Vector2(0, 40)
	input.text_submitted.connect(func(t: String) -> void: send(t))
	row.add_child(input)
	mic_button = Button.new()
	mic_button.icon = load("res://assets/icons/mic.svg")
	mic_button.custom_minimum_size = Vector2(40, 40)
	mic_button.tooltip_text = "Talk to the assistant (click, speak, click again)"
	mic_button.set_meta("sfx", "none")
	mic_button.pressed.connect(func() -> void: brain.call("toggle_voice", "chat"))
	row.add_child(mic_button)
	send_button = Button.new()
	send_button.text = "↑"
	send_button.custom_minimum_size = Vector2(40, 40)
	send_button.pressed.connect(func() -> void: send(input.text))
	row.add_child(send_button)
	return self


func _process(delta: float) -> void:
	if thinking.visible:
		_dots_t += delta
		thinking.text = "Thinking" + ".".repeat(1 + int(_dots_t * 3.0) % 3)


## Loads today's conversation, then the morning briefing (spoken once per day).
func start() -> void:
	var st := await app.backend.api.call_api("/assistant/status")
	var data: Dictionary = st["data"] if st["ok"] else {}
	configured = bool(data.get("configured", false))
	if not configured:
		_add_bubble("assistant", "Hi! I'm your archivist. Give me anything (a thought, a link, a PDF, your voice): I file it, link it and find it again. I need your OpenAI key first: click the microphone or open the engine room's Voice card.", [], [])
		return
	var hist := await app.backend.api.call_api("/assistant/history?limit=40")
	var had_briefing := false
	if hist["ok"]:
		var msgs: Array = (hist["data"] as Dictionary).get("messages", [])
		for item in msgs:
			var m: Dictionary = item
			var meta: Dictionary = m["meta"] if m.get("meta") is Dictionary else {}
			var role := "review" if str(meta.get("kind", "")) == "weekly_review" else str(m["role"])
			_add_bubble(role, str(m["content"]), meta.get("actions", []), meta.get("cited", []), meta.get("sources", []))
			if str(m["role"]) == "briefing":
				had_briefing = true
	if not had_briefing:
		_set_busy(true)
		var b := await app.backend.api.call_api("/assistant/briefing", true, HTTPClient.METHOD_POST)
		_set_busy(false)
		if b["ok"]:
			var bd: Dictionary = b["data"]
			_add_bubble("briefing", str(bd.get("text", "")), [], [])
			say(str(bd.get("text", "")))
		else:
			_add_bubble("assistant", "I could not prepare your briefing: %s" % _err(b), [], [])


## spoken = true when the message came by voice: the reply is read aloud even if reading is off.
var last_sources: Array = []        # web pages behind the last answer (tests, « ouvre la source »)
var last_opened_url := ""


func send(text: String, spoken: bool = false) -> void:
	var t := text.strip_edges()
	if t == "" or busy:
		return
	input.text = ""
	if not configured:
		_add_bubble("assistant", "I need your OpenAI key first (microphone or engine room → Voice).", [], [])
		return
	_add_bubble("user", t, [], [])
	_set_busy(true)
	var payload := {"text": t, "spoken": spoken}
	var open_note: Dictionary = brain.get("current_note")
	if not open_note.is_empty() and (brain.get("inspector") as Control).visible:
		payload["open_note"] = str(open_note.get("id", ""))
	var focus := str(brain.get("current_space"))
	if focus != "":
		payload["space_id"] = focus
	var res := await app.backend.api.call_api("/assistant/chat", true, HTTPClient.METHOD_POST, JSON.stringify(payload))
	_set_busy(false)
	if not is_inside_tree():
		return
	if not res["ok"]:
		app.audio.play("error")
		_add_bubble("assistant", "Something went wrong: %s" % _err(res), [], [])
		return
	var d: Dictionary = res["data"]
	last_reply = str(d.get("reply", ""))
	var actions: Array = d.get("actions", [])
	_add_bubble("assistant", last_reply, actions, d.get("cited", []), d.get("sources", []))
	app.audio.play("notification", 0.0, -8.0)
	if not actions.is_empty():
		app.audio.play("note_create", 0.04)
		brain_changed.emit()
	var ui: Array = d.get("ui_actions", [])
	last_ui_actions = ui
	var replaying := false
	for u in ui:
		replaying = replaying or str((u as Dictionary).get("action", "")) == "replay"
	if not replaying:
		say(last_reply, spoken)
	if not ui.is_empty():
		ui_requested.emit(ui)


## Guided weekly review: generated from the week's facts, shown and read aloud.
func run_review() -> bool:
	if busy or not configured:
		return false
	_set_busy(true)
	var res := await app.backend.api.call_api("/assistant/review", true, HTTPClient.METHOD_POST)
	_set_busy(false)
	if not res["ok"] or not is_inside_tree():
		_add_bubble("assistant", "I could not prepare the review: %s" % _err(res), [], [])
		return false
	var text := str((res["data"] as Dictionary).get("text", ""))
	last_reply = text
	_add_bubble("review", text, [], [])
	app.audio.play("setup_complete", 0.0, -6.0)
	say(text)
	return true


## « relis-moi ça »: the answer before the request that asked for it, or the last weekly review.
func replay(which: String = "last") -> void:
	var text := last_review
	if which != "review":
		# The newest entry is the reply to « relis-moi ça » itself; read the one before it.
		text = spoken_history[-2] if spoken_history.size() >= 2 else (spoken_history[-1] if not spoken_history.is_empty() else "")
	replay_text(text)


func replay_text(text: String) -> void:
	if text.strip_edges() == "":
		return
	app.audio.stop_voice()
	replayed = text
	say(text, true)


func say(text: String, force: bool = false) -> void:
	if not (speak_toggle.button_pressed or force) or app.audio.muted or text.strip_edges() == "":
		return
	var res := await app.backend.api.call_api("/assistant/speak", true, HTTPClient.METHOD_POST,
		JSON.stringify({"text": text, "theme": SbTheme.current}), true)
	if res["ok"] and is_inside_tree():
		app.audio.play_voice(res["bytes"])


func _set_busy(on: bool) -> void:
	busy = on
	thinking.visible = on
	send_button.disabled = on
	_dots_t = 0.0


func _err(res: Dictionary) -> String:
	var d: Dictionary = res.get("data", {})
	return str(d.get("detail", res.get("error", "?")))


func _on_live_state(st: String) -> void:
	live_button.text = "End live (F9)" if st != "idle" else "Talk live"


## The archivist's receipt for an item that came in: where it went, or what it is waiting on.
func add_receipt(item: Dictionary, receipt: String, filed: bool, action_id: int) -> void:
	var lines := [receipt]
	var summary: Variant = item.get("summary")
	if summary != null and str(summary) != "":
		lines.append(str(summary))
	var themes: Array = item.get("themes", [])
	if not themes.is_empty():
		lines.append(" ".join(themes.map(func(t: Variant) -> String: return "#" + str(t))))
	var acts: Array = []
	if filed and action_id > 0:
		acts.append({"kind": "classify", "title": str(item.get("title", "")), "action_id": action_id})
	_add_bubble("receipt" if filed else "waiting", "\n".join(lines), acts, [])


## A line of the live conversation (already saved by the engine in today's conversation).
func add_live(role: String, text: String) -> void:
	_add_bubble(role, text, [], [])
	last_reply = text if role == "assistant" else last_reply
	await get_tree().process_frame
	scroll.scroll_vertical = int(scroll.get_v_scroll_bar().max_value)


func _add_bubble(role: String, text: String, actions: Array, cited: Array, sources: Array = []) -> void:
	messages_shown += 1
	var mine := role == "user"
	var wrap := HBoxContainer.new()
	wrap.alignment = BoxContainer.ALIGNMENT_END if mine else BoxContainer.ALIGNMENT_BEGIN
	list.add_child(wrap)
	var bubble := PanelContainer.new()
	var special := role in ["briefing", "review", "receipt", "waiting"]
	var col := SbTheme.MINT if mine else (SbTheme.WARM if role in ["briefing", "waiting"] else (SbTheme.INFO if role in ["review", "receipt"] else SbTheme.PANEL_2))
	bubble.add_theme_stylebox_override("panel", SbTheme.box(Color(col, 0.22 if mine or special else 0.9), 14,
		Color(col, 0.35), 1, 12))
	bubble.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if mine:
		var spacer := Control.new()
		spacer.custom_minimum_size = Vector2(36, 0)
		wrap.add_child(spacer)
	wrap.add_child(bubble)
	var inner := VBoxContainer.new()
	inner.add_theme_constant_override("separation", 4)
	bubble.add_child(inner)
	if special:
		var over := Label.new()
		over.text = {"briefing": "TODAY", "review": "WEEKLY REVIEW", "receipt": "FILED", "waiting": "IN THE INBOX · WAITING"}.get(role, "")
		over.theme_type_variation = "Overline"
		over.add_theme_color_override("font_color", col)
		inner.add_child(over)
	var rt := RichTextLabel.new()
	rt.bbcode_enabled = true
	rt.fit_content = true
	rt.selection_enabled = true
	rt.custom_minimum_size = Vector2(200, 0)
	rt.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	rt.add_theme_color_override("default_color", SbTheme.TEXT)
	rt.add_theme_font_size_override("normal_font_size", 14)
	rt.text = _linkify(text)
	rt.meta_clicked.connect(_on_link)
	inner.add_child(rt)
	if not sources.is_empty():  # the web pages behind this answer, opened in the browser
		var src := RichTextLabel.new()
		src.bbcode_enabled = true
		src.fit_content = true
		src.custom_minimum_size = Vector2(200, 0)
		src.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		src.add_theme_font_size_override("normal_font_size", 12)
		src.add_theme_color_override("default_color", SbTheme.MUTED)
		var lines: Array[String] = ["SOURCES"]
		for item in sources:
			var sd: Dictionary = item
			var url := str(sd.get("url", ""))
			lines.append("↗ [url=%s][color=#%s]%s[/color][/url]  [color=#%s]%s[/color]" % [url, SbTheme.MINT.to_html(false),
				_bb(str(sd.get("title", url)).left(70)), SbTheme.MUTED.to_html(false), _bb(_host(url))])
		src.text = "\n".join(lines)
		src.meta_clicked.connect(_on_link)
		inner.add_child(src)
		last_sources = sources
	if not mine and text.strip_edges() != "":
		spoken_history.append(text)
		if role == "review":
			last_review = text
		var tools := HBoxContainer.new()
		tools.alignment = BoxContainer.ALIGNMENT_END
		inner.add_child(tools)
		var play := Button.new()
		play.text = "▶ Replay"
		play.tooltip_text = "Read this answer aloud again (free: the audio is cached)"
		play.theme_type_variation = "GhostButton"
		play.add_theme_font_size_override("font_size", 12)
		play.set_meta("sfx", "none")
		play.pressed.connect(func() -> void: replay_text(text))
		tools.add_child(play)
	for item in actions:
		var a: Dictionary = item
		var line := HBoxContainer.new()
		inner.add_child(line)
		var l := Label.new()
		l.theme_type_variation = "Muted"
		l.text = str({"create_note": "✚ Created ", "classify": "⇢ Filed ", "move": "⇢ Moved ", "trash": "✕ Deleted ",
			"web_page": "✚ Added from the web ", "remove_place": "✕ Removed place ", "link": "— Linked ", "unlink": "✕ Unlinked ",
			"untag": "✕ Tag removed "}.get(str(a.get("kind")), "✎ Updated ")) + "« %s »" % str(a.get("title", ""))
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		l.clip_text = true
		line.add_child(l)
		var undo := Button.new()
		undo.text = "Undo"
		undo.theme_type_variation = "GhostButton"
		var aid := int(a.get("action_id", 0))
		undo.pressed.connect(func() -> void:
			var r := await app.backend.api.call_api("/assistant/actions/%d/undo" % aid, true, HTTPClient.METHOD_POST)
			if r["ok"]:
				undo.disabled = true
				undo.text = "Undone"
				app.audio.play("whoosh")
				brain_changed.emit())
		line.add_child(undo)
	await get_tree().process_frame
	if is_inside_tree():
		scroll.scroll_vertical = int(scroll.get_v_scroll_bar().max_value)


## A web link opens in the browser; anything else is an item title ([[Title]]).
func _on_link(meta: Variant) -> void:
	var m := str(meta)
	if m.begins_with("http://") or m.begins_with("https://"):
		last_opened_url = m
		if OS.get_environment("SBGD_TEST_NO_SHELL") != "1":
			OS.shell_open(m)
	else:
		note_requested.emit(m)


static func _host(url: String) -> String:
	var h := url.get_slice("://", 1).get_slice("/", 0)
	return h.trim_prefix("www.")


static func _bb(t: String) -> String:
	return t.replace("[", "(").replace("]", ")")


## [[Title]] -> clickable item; [label](https://…) and bare https://… -> clickable web links
static func _linkify(text: String) -> String:
	var safe := text.replace("[", "\u0001").replace("]", "\u0002")
	var mint := SbTheme.MINT.to_html(false)
	var md := RegEx.create_from_string("\u0001([^\u0001\u0002]+)\u0002\\((https?://[^\\s)]+)\\)")
	safe = md.sub(safe, "\u0003$2\u0004$1\u0005", true)
	var bare := RegEx.create_from_string("(?<![\u0003\\w/])(https?://[^\\s\u0001\u0002\u0003\u0004\u0005)]+)")
	safe = bare.sub(safe, "\u0003$1\u0004$1\u0005", true)
	var re := RegEx.create_from_string("\u0001\u0001([^\u0001\u0002|]+)(?:\\|[^\u0001\u0002]*)?\u0002\u0002")
	var out := re.sub(safe, "[url=$1][color=#%s]$1[/color][/url]" % mint, true)
	var web := RegEx.create_from_string("\u0003([^\u0004]+)\u0004([^\u0005]*)\u0005")
	out = web.sub(out, "[url=$1][color=#%s]$2[/color][/url]" % mint, true)
	return out.replace("\u0001", "[lb]").replace("\u0002", "[rb]")
