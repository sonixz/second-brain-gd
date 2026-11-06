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

signal activated(agent: String)       # the user typed, spoke or clicked here: F8/F9 now go to this agent

var agent := "archivist"             # an agent id (engine/assistant/agents.py): archivist, sparring, or a custom one
var intro := ""                      # what a non-archivist agent says first (from its profile)
var draft_box: VBoxContainer         # Sparring's synthesis waiting for approval
var mission_card: PanelContainer     # the agent's mission (Loop 33): MissionCard, loaded by path
var mission_row: HBoxContainer       # « Mission… »: what the agent should do
var mission_edit: LineEdit


func setup(a: SbApp, b: Control, who: String = "archivist") -> AssistantPanel:
	app = a
	brain = b
	agent = who
	add_theme_constant_override("separation", 8)
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var head := HBoxContainer.new()
	add_child(head)
	head.alignment = BoxContainer.ALIGNMENT_END
	speak_toggle = CheckButton.new()
	speak_toggle.text = ""
	speak_toggle.icon = load("res://assets/icons/speaker.svg")
	speak_toggle.tooltip_text = I18n.t("The archivist reads its answers aloud (voice: marin)")
	speak_toggle.button_pressed = bool(SbSettings.get_value("assistant", "speaks", true))
	speak_toggle.toggled.connect(func(on: bool) -> void:
		SbSettings.set_value("assistant", "speaks", on)
		if not on:
			app.audio.stop_voice())
	head.add_child(speak_toggle)
	live_button = Button.new()
	live_button.text = I18n.t("Live")
	live_button.tooltip_text = I18n.t("A spoken conversation with the archivist (F9 to start and end)")
	live_button.toggle_mode = false
	live_button.pressed.connect(func() -> void:
		activated.emit(agent)
		brain.call("toggle_live"))
	head.add_child(live_button)
	var mission_button := Button.new()
	mission_button.text = I18n.t("Mission…")
	mission_button.theme_type_variation = "GhostButton"
	mission_button.tooltip_text = I18n.t("Give this agent a longer job: it plans, researches, asks you when it needs a choice, and shows a draft before saving anything")
	mission_button.pressed.connect(func() -> void:
		activated.emit(agent)
		mission_row.visible = not mission_row.visible
		if mission_row.visible:
			mission_edit.grab_focus())
	head.add_child(mission_button)
	head.move_child(mission_button, 0)
	app.live.state_changed.connect(_on_live_state)
	_on_live_state(app.live.state)
	mission_row = HBoxContainer.new()
	mission_row.visible = false
	mission_row.add_theme_constant_override("separation", 6)
	add_child(mission_row)
	mission_edit = LineEdit.new()
	mission_edit.placeholder_text = I18n.t("What should it do? e.g. this week's menu from the grocery specials")
	mission_edit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	mission_edit.text_submitted.connect(func(_t: String) -> void: start_mission(mission_edit.text))
	mission_row.add_child(mission_edit)
	var go := Button.new()
	go.text = I18n.t("Start")
	go.theme_type_variation = "PrimaryButton"
	go.pressed.connect(func() -> void: start_mission(mission_edit.text))
	mission_row.add_child(go)
	mission_card = preload("res://scenes/components/mission_card.gd").new().setup(app, agent)
	mission_card.connect("saved", func(_n: int) -> void: brain_changed.emit())
	add_child(mission_card)
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
	input.placeholder_text = I18n.t("Ask or tell the archivist…") if agent == "archivist" else (I18n.t("Think out loud with Sparring…") if agent == "sparring" else I18n.t("Talk with this agent…"))
	input.focus_entered.connect(func() -> void: activated.emit(agent))
	input.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	input.custom_minimum_size = Vector2(0, 40)
	input.text_submitted.connect(func(t: String) -> void: send(t))
	row.add_child(input)
	mic_button = Button.new()
	mic_button.icon = load("res://assets/icons/mic.svg")
	mic_button.custom_minimum_size = Vector2(40, 40)
	mic_button.tooltip_text = I18n.t("Talk to the archivist (click, speak, click again)")
	mic_button.set_meta("sfx", "none")
	mic_button.pressed.connect(func() -> void:
		activated.emit(agent)
		brain.call("toggle_voice", "chat"))
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
		thinking.text = I18n.t("Thinking") + ".".repeat(1 + int(_dots_t * 3.0) % 3)


## Starts a mission for this agent; its card follows it.
func start_mission(goal: String) -> void:
	goal = goal.strip_edges()
	if goal.length() < 4:
		return
	var res: Dictionary = await mission_card.call("start_mission", goal)
	if res.get("ok", false):
		mission_edit.text = ""
		mission_row.visible = false


## Loads today's conversation, then the morning briefing (spoken once per day).
func start() -> void:
	mission_card.call("refresh")
	var st := await app.backend.api.call_api("/assistant/status")
	var data: Dictionary = st["data"] if st["ok"] else {}
	configured = bool(data.get("configured", false))
	if not configured:
		_add_bubble("assistant", I18n.t("Hi! I'm your archivist. Give me anything (a thought, a link, a PDF, your voice): I file it, link it and find it again. I need your OpenAI key first: click the microphone or open the engine room's Voice card."), [], [])
		return
	var hist := await app.backend.api.call_api("/assistant/history?limit=40&agent=" + agent)
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
	if agent != "archivist":  # no briefing: the other agents wait for you
		if messages_shown == 0:
			if intro == "":
				var r := await app.backend.api.call_api("/assistant/agents")
				for item in ((r["data"] as Dictionary).get("agents", []) if r["ok"] else []):
					if str((item as Dictionary)["id"]) == agent:
						intro = str((item as Dictionary).get("intro", ""))
			if intro != "":
				_add_bubble("assistant", intro, [], [])
		return
	if not had_briefing:
		_set_busy(true)
		var b := await app.backend.api.call_api("/assistant/briefing", true, HTTPClient.METHOD_POST)
		_set_busy(false)
		if b["ok"]:
			var bd: Dictionary = b["data"]
			_add_bubble("briefing", str(bd.get("text", "")), [], [])
			say(str(bd.get("text", "")))
		else:
			_add_bubble("assistant", I18n.t("I could not prepare your briefing: %s") % _err(b), [], [])


## spoken = true when the message came by voice: the reply is read aloud even if reading is off.
var last_sources: Array = []        # web pages behind the last answer (tests, « ouvre la source »)
var last_opened_url := ""


func send(text: String, spoken: bool = false) -> void:
	var t := text.strip_edges()
	if t == "" or busy:
		return
	input.text = ""
	if not configured:
		_add_bubble("assistant", I18n.t("I need your OpenAI key first (microphone or engine room → Voice)."), [], [])
		return
	_add_bubble("user", t, [], [])
	_set_busy(true)
	activated.emit(agent)
	var payload := {"text": t, "spoken": spoken, "agent": agent}
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
		_add_bubble("assistant", I18n.t("Something went wrong: %s") % _err(res), [], [])
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


## Sparring drafted a synthesis: it is shown in full, with a button to save it (or say « oui, sauvegarde »).
func show_draft() -> void:
	var res := await app.backend.api.call_api("/assistant/draft?agent=" + agent)
	if not res["ok"] or not is_inside_tree():
		return
	var d: Variant = (res["data"] as Dictionary).get("draft")
	if not d is Dictionary:
		return
	if draft_box != null and is_instance_valid(draft_box):
		draft_box.get_parent().get_parent().queue_free()
	var lines: Array[String] = []
	for line in str(d.get("body", "")).split("\n"):  # markdown headings read as plain capitals here
		lines.append(line.lstrip("#").strip_edges().to_upper() if line.begins_with("#") else line)
	_add_bubble("draft", str(d.get("title", "")).to_upper() + "\n\n" + "\n".join(lines), [], [])
	var bubble: Control = list.get_child(list.get_child_count() - 1)
	draft_box = bubble.get_child(bubble.get_child_count() - 1).get_child(0) as VBoxContainer
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	draft_box.add_child(row)
	var save_b := Button.new()
	save_b.text = I18n.t("Save to the Brain")
	save_b.theme_type_variation = "PrimaryButton"
	save_b.pressed.connect(func() -> void:
		save_b.disabled = true
		send(said("save_synthesis")))
	row.add_child(save_b)
	var change := Button.new()
	change.text = I18n.t("Change it…")
	change.theme_type_variation = "GhostButton"
	change.pressed.connect(func() -> void:
		input.text = said("change_synthesis")
		input.grab_focus()
		input.caret_column = input.text.length())
	row.add_child(change)
	last_draft = str(d.get("title", ""))


var last_draft := ""
var last_agent_draft := ""


## The Agent Builder drafted an agent (or changes to one): shown in full, with Create / Apply and Change.
func show_agent_draft() -> void:
	var res := await app.backend.api.call_api("/assistant/agent-draft")
	if not res["ok"] or not is_inside_tree():
		return
	var data: Dictionary = res["data"]
	var d: Variant = data.get("draft")
	if not d is Dictionary:
		return
	var labels: Dictionary = data.get("capabilities", {})
	var update := str(d.get("mode", "")) == "update"
	var caps: Array = (d.get("capabilities", []) as Array).map(func(c: Variant) -> String: return str(labels.get(str(c), c)))
	var head := "%s\n%s\n\n" % [str(d.get("name", d.get("agent_id", ""))).to_upper(),
		(I18n.t("Capabilities: %s") % ", ".join(caps)) if not caps.is_empty() else I18n.t("Capabilities unchanged")]
	if str(d.get("intro", "")) != "":
		head += I18n.t("First words: %s") % str(d.get("intro", "")) + "\n\n"
	var lines: Array[String] = []
	for line in str(d.get("instructions", "")).split("\n"):  # markdown headings read as plain capitals here
		lines.append(line.lstrip("#").strip_edges().to_upper() if line.begins_with("#") else line)
	_add_bubble("agent_draft_update" if update else "agent_draft", head + "\n".join(lines), [], [])
	var wrap: Control = list.get_child(list.get_child_count() - 1)
	var inner := wrap.get_child(wrap.get_child_count() - 1).get_child(0) as VBoxContainer
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 8)
	inner.add_child(row)
	var go := Button.new()
	go.text = I18n.t("Apply it") if update else I18n.t("Create it")
	go.theme_type_variation = "PrimaryButton"
	go.pressed.connect(func() -> void:
		go.disabled = true
		send(said("apply_agent") if update else said("create_agent")))
	row.add_child(go)
	var change := Button.new()
	change.text = I18n.t("Change it…")
	change.theme_type_variation = "GhostButton"
	change.pressed.connect(func() -> void:
		input.text = said("change_agent")
		input.grab_focus()
		input.caret_column = input.text.length())
	row.add_child(change)
	last_agent_draft = str(d.get("name", d.get("agent_id", "")))


## Guided weekly review: generated from the week's facts, shown and read aloud.
func run_review() -> bool:
	if busy or not configured:
		return false
	_set_busy(true)
	var res := await app.backend.api.call_api("/assistant/review", true, HTTPClient.METHOD_POST)
	_set_busy(false)
	if not res["ok"] or not is_inside_tree():
		_add_bubble("assistant", I18n.t("I could not prepare the review: %s") % _err(res), [], [])
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
		JSON.stringify({"text": spoken(text), "theme": SbTheme.current}), true)
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
	live_button.text = I18n.t("End (F9)") if st != "idle" else I18n.t("Live")


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
	var special := role in ["briefing", "review", "receipt", "waiting", "draft", "agent_draft", "agent_draft_update"]
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
		over.text = {"briefing": I18n.t("TODAY"), "review": I18n.t("WEEKLY REVIEW"), "receipt": I18n.t("FILED"),
			"waiting": I18n.t("IN THE INBOX · WAITING"), "draft": I18n.t("SYNTHESIS · NOT SAVED YET"),
			"agent_draft": I18n.t("NEW AGENT · NOT CREATED YET"), "agent_draft_update": I18n.t("CHANGES · NOT APPLIED YET")}.get(role, "")
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
		var lines: Array[String] = [I18n.t("SOURCES")]
		for item in sources:
			var sd: Dictionary = item
			var url := str(sd.get("url", ""))
			lines.append("↗ [url=%s][color=#%s]%s[/color][/url]  [color=#%s]%s[/color]" % [url, SbTheme.MINT.to_html(false),
				_bb(one_line(str(sd.get("title", url))).left(70)), SbTheme.MUTED.to_html(false), _bb(_host(url))])
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
		play.text = I18n.t("▶ Replay")
		play.tooltip_text = I18n.t("Read this answer aloud again (free: the audio is cached)")
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
		l.text = str({"create_note": I18n.t("✚ Created “%s”"), "classify": I18n.t("⇢ Filed “%s”"),
			"move": I18n.t("⇢ Moved “%s”"), "trash": I18n.t("✕ Deleted “%s”"),
			"web_page": I18n.t("✚ Added from the web “%s”"), "remove_place": I18n.t("✕ Removed place “%s”"),
			"link": I18n.t("— Linked “%s”"), "unlink": I18n.t("✕ Unlinked “%s”"), "untag": I18n.t("✕ Tag removed “%s”"),
			"agent_created": I18n.t("✚ Created the agent “%s”"), "agent_changed": I18n.t("✎ Changed the agent “%s”")}.get(
				str(a.get("kind")), I18n.t("✎ Updated “%s”"))) % str(a.get("title", ""))
		l.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		l.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		l.clip_text = true
		line.add_child(l)
		var aid := int(a.get("action_id", 0))
		if aid <= 0:  # not journaled (an agent created or changed: ⓘ has Delete and Back to the original)
			continue
		var undo := Button.new()
		undo.text = I18n.t("Undo")
		undo.theme_type_variation = "GhostButton"
		undo.pressed.connect(func() -> void:
			var r := await app.backend.api.call_api("/assistant/actions/%d/undo" % aid, true, HTTPClient.METHOD_POST)
			if r["ok"]:
				undo.disabled = true
				undo.text = I18n.t("Undone")
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


## What the app says on your behalf (a button that approves, the rail's « + »…), in the language you speak to the
## agents: in the app's language (I18n, the FR / EN switch).
const SAID := {
	"save_synthesis": {"fr": "Oui, sauvegarde cette synthèse dans le Brain.", "en": "Yes, save this synthesis to the Brain."},
	"change_synthesis": {"fr": "Change la synthèse: ", "en": "Change the synthesis: "},
	"apply_agent": {"fr": "Oui, applique ces changements.", "en": "Yes, apply these changes."},
	"create_agent": {"fr": "Oui, crée-le.", "en": "Yes, create it."},
	"change_agent": {"fr": "Change: ", "en": "Change: "},
	"new_agent": {"fr": "Je veux créer un nouvel agent.", "en": "I want to create a new agent."},
	"modify_agent": {"fr": "Je veux modifier l'agent %s.", "en": "I want to change the agent %s."},
}


static func said(key: String) -> String:
	var lang := I18n.lang  # the app's language (FR / EN switch)
	var d: Dictionary = SAID.get(key, {})
	return str(d.get(lang, d.get("fr", "")))


## A title on one line (a PDF's title can carry line breaks).
static func one_line(t: String) -> String:
	return RegEx.create_from_string("\\s+").sub(t, " ", true).strip_edges()


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
	# Agents are asked for plain text, but a model sometimes writes **bold** anyway: show it as bold, never the stars.
	out = RegEx.create_from_string("\\*\\*([^*\n]+)\\*\\*").sub(out, "[b]$1[/b]", true)
	return out.replace("\u0001", "[lb]").replace("\u0002", "[rb]")


## What is read aloud: the same text without Markdown marks.
static func spoken(text: String) -> String:
	return RegEx.create_from_string("\\*\\*([^*\n]+)\\*\\*").sub(text, "$1", true)
