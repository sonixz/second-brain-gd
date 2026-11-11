extends Control
## The Second Brain: a living graph of everything you know, a capture bar,
## a morning briefing, spaces, search and a note inspector.

const GRAPH_REFRESH_S := 20.0
const HEALTH_EVERY_S := 5.0
const SAVE_DELAY_S := 0.8

var app: SbApp
var graph: GraphView
var layers_view: GraphLayers3D
var greeting: Label
var date_label: Label
var status_dot: StatusDot
var status_label: Label
var search_edit: LineEdit
var capture_edit: LineEdit
var capture_hint: Label
var mic_button: Button
var briefing_box: VBoxContainer
var spaces_box: VBoxContainer
var inspector: PanelContainer
var title_edit: LineEdit
var body_edit: TextEdit
var space_option: OptionButton
var kind_option: OptionButton
var links_box: VBoxContainer
var related_label: Label
var related_box: VBoxContainer
var doc_row: HBoxContainer
var save_label: Label
var stats_label: Label
var spaces: Array = []
var current_note: Dictionary = {}
var current_space := ""
var health_ok := false
var notes_created := 0
var _save_timer: Timer
var _loading_note := false
# Voice
var voice_capture: VoiceCapture
var voice_stream: VoiceStream
var voice_state := "idle"   # idle | connecting | listening | finishing
var voice_text := ""
var voice_level := 0.0
var voice_notes := 0
var _voice_final := ""
var _voice_error := ""
var voice_target := "capture"   # capture | chat
# Assistant
var assistant_panel: AssistantPanel
var spaces_page: VBoxContainer
var panel_layer: SbPanelLayer
var archivist_panel: SbFloatingPanel   # the conversation with the archivist (was the « Assistant » tab)
var places_panel: SbFloatingPanel      # briefing, places, sources (was « Spaces & briefing »)
var sparring_chat: AssistantPanel      # Sparring, the thinking partner (reads, argues, saves only an approved synthesis)
var sparring_panel: SbFloatingPanel
var active_agent := "archivist"        # F8 and F9 talk to the agent you last used
var agent_chats: Dictionary = {}       # agent id -> AssistantPanel (every agent: built-in and custom)
var agent_panels: Dictionary = {}      # agent id -> SbFloatingPanel
var agent_names: Dictionary = {}       # agent id -> name, for titles
var toast: PanelContainer
var toast_label: Label
var toast_undo: Button
var toast_action := 0
var classified := 0
var last_receipt := ""
var last_pack_export := ""
var viewer: DocumentViewer
var filters_bar: GraphFilters
var card_editor: PanelContainer
var path_active := false
var results_box: VBoxContainer
var last_hits: Array = []
var _toast_timer: Timer
# Views
var view := "graph"   # graph | today | projects
var captures_view: CapturesView
# Today and Agents are set aside (2026-11-04): the Brain is the graph, its data and their relations.
# Their views stay in the code, unreachable from the interface, until they come back as modules.
static func nav_views() -> Array:
	return [["graph", I18n.t("Graph")], ["table", I18n.t("Table")], ["captures", I18n.t("Captures")], ["projects", I18n.t("Projects")]]
var today_view: TodayView
var projects_view: ProjectsView
var table_view: PanelContainer     # Loop 37C (preloaded script)
var last_opened_file := ""
var settings_button: Button         # ⚙ Settings: one entry to every setting (Loop UX-C)
var mcp_lights: Button              # the MCP in / out lights in the top bar         # the last file an assistant action opened (tests)
var agents_view: AgentsView
var view_buttons: Dictionary = {}
# Sources
var sources_box: VBoxContainer
var sources_added := 0
var last_source_error := ""
var _file_dialog: FileDialog


func bind(a: SbApp) -> void:
	app = a


func _ready() -> void:
	app.backend.load_runtime()
	app.tell_engine_language()  # the engine follows the app's language (an older engine database starts in English)
	graph = GraphView.new()
	graph.set_anchors_preset(Control.PRESET_FULL_RECT)
	graph.node_selected.connect(_on_node_selected)
	graph.item_dropped_on_place.connect(move_to_place)
	graph.details_needed.connect(_fetch_card)
	filters_bar = GraphFilters.new()
	filters_bar.set_anchors_preset(Control.PRESET_TOP_WIDE)
	filters_bar.offset_left = 388
	filters_bar.offset_right = -24
	filters_bar.offset_top = 92
	add_child(filters_bar)
	filters_bar.legend_toggled.connect(func(on: bool) -> void: graph.show_legend = on)
	filters_bar.layout_changed.connect(func(mode: String) -> void:
		if mode == "meaning":  # the engine places the items by meaning; no map (no meaning memory yet) = stay here
			if not await load_meaning_map():
				show_toast(I18n.t("No meaning map yet: it needs a few items and the meaning memory (an OpenAI key)"))
		var in_3d := mode == "layers"  # the 3D layers stand on the zones
		graph.set_layout("zones" if in_3d else mode)
		layers_view.visible = in_3d
		if in_3d:
			layers_view.spinning = true
			layers_view.show_graph(graph)
		elif graph.graph_layout != mode:  # a view with nothing to show (focus, meaning): the picker says what is shown
			filters_bar.show_view(graph.graph_layout)
		app.state["graph_layout"] = "layers" if in_3d else graph.graph_layout)
	graph.focus_changed.connect(func(id: String) -> void: app.state["graph_focus"] = id)
	filters_bar.changed.connect(func(f: Dictionary) -> void:
		graph.set_filter(f)
		_refresh_layers()
		app.state["graph_filter"] = f
		_update_stats())
	filters_bar.time_bar.set_anchors_preset(Control.PRESET_TOP_WIDE)
	filters_bar.time_bar.offset_left = 388
	filters_bar.time_bar.offset_right = -24
	filters_bar.time_bar.offset_top = 138
	add_child(filters_bar.time_bar)
	filters_bar.lanes_changed.connect(func(mode: String) -> void: graph.set_timeline_lanes(mode))
	filters_bar.play_changed.connect(func(on: bool) -> void:
		graph.set_playing(on)
		layers_view.set_playing(on))
	filters_bar.time_changed.connect(func(fraction: float) -> void:
		graph.set_time_fraction(fraction)
		_refresh_layers()
		filters_bar.time_label.text = I18n.t("Now") if graph.time_cursor < 0.0 else I18n.t("%s · %d items") % [
			Time.get_datetime_string_from_unix_time(int(graph.time_cursor) + int(Time.get_time_zone_from_system().get("bias", 0)) * 60, true).left(16),
			graph.shown_note_count()]
		_update_stats())
	filters_bar.save_view_asked.connect(save_graph_view)
	filters_bar.saved_view_opened.connect(open_graph_view)
	graph.page_needed.connect(_fetch_card_page)
	graph.node_activated.connect(func(id: String) -> void:
		var it := await app.backend.api.call_api("/brain/items/" + id)
		var src: Variant = (it["data"] as Dictionary).get("source") if it["ok"] else null
		if src is Dictionary and (src as Dictionary).get("original") != null:
			open_document_for(id)
		else:
			edit_in_card(id))
	graph.screen_offset = Vector2(182, 0)  # half the left panel: zoomed items centre in the free area
	graph.background_clicked.connect(func() -> void:
		graph.select("")
		_close_inspector())
	add_child(graph)
	layers_view = GraphLayers3D.new()  # the 3D layers (VIEW-F) cover the graph when that view is picked
	layers_view.set_anchors_preset(Control.PRESET_FULL_RECT)
	layers_view.visible = false
	layers_view.item_selected.connect(func(id: String) -> void:
		graph.select(id)
		_on_node_selected(id, "note"))
	layers_view.item_landed.connect(func(id: String) -> void:  # reading happens in 2D: land on the item there
		filters_bar.set_view("zones")
		graph.select(id)
		graph.zoom_to(GraphView.NEAR + 0.4, graph.nodes[id]["pos"], 0.9))
	add_child(layers_view)
	_build_views()
	_build_top_bar()
	_build_left_panel()
	_build_inspector()
	_build_capture_bar()
	_build_toast()
	_build_listening_overlay()
	move_child(filters_bar, layers_view.get_index() + 1)  # above the graph and its 3D layers, below the panels
	move_child(filters_bar.time_bar, filters_bar.get_index() + 1)
	get_window().files_dropped.connect(_on_files_dropped)
	voice_capture = VoiceCapture.new()
	add_child(voice_capture)
	voice_capture.chunk.connect(func(pcm: PackedByteArray) -> void: voice_stream.send_audio(pcm))
	voice_capture.level.connect(func(v: float) -> void: voice_level = lerpf(voice_level, clampf(v * 6.0, 0.0, 1.0), 0.5))
	voice_stream = VoiceStream.new()
	add_child(voice_stream)
	voice_stream.delta.connect(_on_voice_delta)
	voice_stream.final.connect(func(text: String) -> void: _voice_final = text)
	voice_stream.failed.connect(func(msg: String) -> void: _voice_error = msg)
	app.live.user_said.connect(_on_live_text.bind("user"))
	app.live.assistant_said.connect(_on_live_text.bind("assistant"))
	app.live.finished.connect(_on_live_finished)
	_save_timer = Timer.new()
	_save_timer.one_shot = true
	_save_timer.wait_time = SAVE_DELAY_S
	_save_timer.timeout.connect(_save_note)
	add_child(_save_timer)
	_every(GRAPH_REFRESH_S, func() -> void: refresh_graph())
	_every(HEALTH_EVERY_S, _check_health)
	_every(2.0, _watch_browser)
	_every(1.5, func() -> void: mcp_lights.call("poll"))
	_update_greeting()
	await _check_health()
	await refresh_spaces()
	await refresh_graph()
	await load_briefing()
	refresh_sources()
	assistant_panel.start()
	sparring_chat.start()
	refresh_agents()
	if str(app.state.get("view", "graph")) != "graph":
		set_view(str(app.state["view"]))
	var keep := str(app.state.get("selected_note", ""))
	if keep != "":
		open_note(keep)


## Pages sent by the browser extension arrive without the app asking: refresh and say so.
var browser_status: Dictionary = {}
var last_opened_url := ""
var _browser_rev := -1
var _browser_busy := false


func _watch_browser() -> void:
	if _browser_busy or not is_inside_tree():
		return
	_browser_busy = true
	var res := await app.backend.api.call_api("/browser/status")
	_browser_busy = false
	if not res["ok"] or not is_inside_tree():
		return
	browser_status = res["data"]
	var rev := int(browser_status.get("rev", 0))
	if _browser_rev >= 0 and rev != _browser_rev:
		var last: Dictionary = browser_status.get("last_added", {})
		app.audio.play("note_create", 0.04)
		show_toast(I18n.t("From your browser: “%s” → %s") % [str(last.get("title", "")).left(60), str(last.get("place", I18n.t("Inbox")))])
		await refresh_graph()
		await refresh_spaces()
		if view == "captures":
			await captures_view.refresh()
	_browser_rev = rev


## Ctrl+1 Archivist, Ctrl+2 Sparring, Ctrl+3 Places, Ctrl+4 the item tile: opens it (and talks to that agent),
## or shrinks it into the rail if it is already open.
func toggle_panel(index: int) -> void:
	var order: Array = [archivist_panel, sparring_panel, places_panel, inspector]
	for id in agent_panels:  # custom agents: Ctrl+5…
		if id != "archivist" and id != "sparring":
			order.append(agent_panels[id])
	if index < 0 or index >= order.size():
		return
	var p: SbFloatingPanel = order[index]
	if p.visible and not p.minimized:
		p.set_minimized(true)
		return
	if p == inspector and current_note.is_empty():
		show_toast(I18n.t("No item open: click one in the graph."))
		return
	p.reveal()
	for id in agent_panels:
		if agent_panels[id] == p:
			set_agent(id)
			chat_panel().input.grab_focus()


## Tab: the graph alone. Every open panel shrinks into the rail; Tab again brings back exactly those.
var _focus_restore: Array = []


func toggle_focus_mode() -> void:
	if _focus_restore.is_empty():
		for p in panel_layer.panels():
			if p.visible and not p.minimized:
				_focus_restore.append(p)
				p.set_minimized(true)
		if not _focus_restore.is_empty():
			show_toast(I18n.t("Graph only · Tab brings the panels back"))
	else:
		for p in _focus_restore:
			if is_instance_valid(p):
				(p as SbFloatingPanel).reveal()
		_focus_restore.clear()


## The agent F8 and F9 talk to: the one whose panel you last typed in, spoke to or grabbed.
func set_agent(who: String) -> void:
	active_agent = who if agent_chats.has(who) else "archivist"
	for id in agent_panels:
		(agent_panels[id] as SbFloatingPanel).title_label.text = str(agent_names.get(id, id)).to_upper() + ("  ●" if id == active_agent else "")


func chat_panel(who: String = "") -> AssistantPanel:
	var id := who if who != "" else active_agent
	return agent_chats.get(id, assistant_panel)


func agent_panel(who: String = "") -> SbFloatingPanel:
	var id := who if who != "" else active_agent
	return agent_panels.get(id, archivist_panel)


## « Ask about this »: the item becomes an @ mention in the active agent's panel, ready for the question.
func ask_about(id: String, title: String) -> void:
	var chat := chat_panel()
	if chat == null:
		return
	agent_panel().reveal()
	chat.add_mention(id, title)
	chat.input.grab_focus()


## Opens an agent's panel, makes it the one F8/F9 talk to, and optionally says something to it.
func open_agent(id: String, say_first: String = "") -> void:
	if not agent_chats.has(id):
		await refresh_agents()
	if not agent_chats.has(id):
		return
	(agent_panels[id] as SbFloatingPanel).reveal()
	set_agent(id)
	if say_first != "":
		await (agent_chats[id] as AssistantPanel).send(say_first)


## One agent: its conversation panel inside a floating panel, Voice/Live and ⓘ in the title bar.
func _make_agent(id: String, agent_name: String, letter: String, intro: String, shrunk: bool) -> AssistantPanel:
	var chat := AssistantPanel.new().setup(app, self, id)
	chat.intro = intro
	chat.note_requested.connect(_open_note_by_title)
	chat.ui_requested.connect(run_ui_actions)
	chat.brain_changed.connect(func() -> void:
		await refresh_graph()
		await refresh_spaces()
		_refresh_view())
	var panel := SbFloatingPanel.new().setup(id, agent_name.to_upper(), chat,
		{"dock": "left", "size": 340.0, "minimized": shrunk, "icon": letter,
		 "free": Rect2(420 + 20 * agent_chats.size(), 120 + 20 * agent_chats.size(), 380, 560)})
	var head := chat.get_child(0)  # Voice and Live move up into the title bar
	for c in head.get_children():
		head.remove_child(c)
		panel.extra.add_child(c)
	head.queue_free()
	var info := Button.new()
	info.icon = load("res://assets/icons/info.svg")
	info.theme_type_variation = "GhostButton"
	info.tooltip_text = I18n.t("Instructions, capabilities and model of this agent")
	info.pressed.connect(func() -> void: show_agent_info(id))
	panel.extra.add_child(info)
	panel_layer.add_panel(panel)
	chat.activated.connect(set_agent)
	panel.focused.connect(func() -> void: set_agent(id))
	agent_chats[id] = chat
	agent_panels[id] = panel
	agent_names[id] = agent_name
	return chat


## The agents stored in the Brain: new ones get their panel (on the rail), deleted ones leave, names follow.
var agent_profiles: Array = []


func refresh_agents() -> void:
	var res := await app.backend.api.call_api("/assistant/agents")
	if not res["ok"] or not is_inside_tree():
		return
	agent_profiles = (res["data"] as Dictionary).get("agents", [])
	var seen := {}
	for item in agent_profiles:
		var p: Dictionary = item
		var id := str(p["id"])
		seen[id] = true
		if not agent_chats.has(id):
			var chat := _make_agent(id, str(p.get("name", id)), str(p.get("letter", "?")), str(p.get("intro", "")), true)
			chat.start()
		else:
			agent_names[id] = str(p.get("name", id))
			(agent_chats[id] as AssistantPanel).intro = str(p.get("intro", ""))
	for id in agent_chats.keys():
		if not seen.has(id) and id != "archivist" and id != "sparring":
			(agent_panels[id] as SbFloatingPanel).queue_free()
			agent_chats.erase(id)
			agent_panels.erase(id)
			agent_names.erase(id)
	set_agent(active_agent)


## ⓘ: an agent's settings in a floating tile (move it, dock it, shrink it): name, model, on/off capabilities,
## first words, instructions; reset or delete.
var agent_settings: SbAgentSettings
var agent_settings_panel: SbFloatingPanel


func show_agent_info(id: String) -> void:
	var res := await app.backend.api.call_api("/assistant/agents")
	if not res["ok"] or not is_inside_tree():
		return
	var data: Dictionary = res["data"]
	agent_profiles = data.get("agents", [])
	var prof: Dictionary = {}
	for item in agent_profiles:
		if str((item as Dictionary)["id"]) == id:
			prof = item
	if prof.is_empty():
		return
	close_agent_settings()
	agent_settings = SbAgentSettings.new().setup(app, id, prof, data.get("capabilities", {}), data.get("models", []))
	agent_settings.changed.connect(func() -> void: refresh_agents())
	agent_settings.ask_builder.connect(func(n: String) -> void: open_agent("builder", AssistantPanel.said("modify_agent") % n))
	agent_settings.close_requested.connect(close_agent_settings)
	var w := 560.0
	agent_settings_panel = SbFloatingPanel.new().setup("agent-settings", I18n.t("%s · SETTINGS") % str(prof.get("name", id)).to_upper(),
		agent_settings, {"dock": "free", "size": w, "icon": "⚙",
		 "free": Rect2(maxf(24.0, size.x * 0.5 - w * 0.5), 110, w, maxf(420.0, size.y - 240.0))})
	agent_settings_panel.minimized = false
	agent_settings_panel.visible = true
	var close := Button.new()
	close.text = "✕"
	close.theme_type_variation = "GhostButton"
	close.tooltip_text = I18n.t("Close the settings")
	close.pressed.connect(close_agent_settings)
	agent_settings_panel.extra.add_child(close)
	panel_layer.add_panel(agent_settings_panel)
	last_agent_info = id


func close_agent_settings() -> void:
	if agent_settings_panel != null and is_instance_valid(agent_settings_panel):
		agent_settings_panel.queue_free()
		panel_layer.queue_layout()
	agent_settings_panel = null


var last_agent_info := ""


## Docked panels take room on the left and right: the graph's toolbar and centre move into the free area.
func _on_panel_edges(left: float, right: float) -> void:
	filters_bar.offset_left = panel_layer.margin_side + left
	filters_bar.time_bar.offset_left = panel_layer.margin_side + left
	graph.screen_offset = Vector2((left - right) * 0.5, 0)
	graph.legend_x = panel_layer.margin_side + left
	layers_view.screen_offset = graph.screen_offset
	layers_view.legend_x = graph.legend_x
	_refresh_layers()
	graph.right_inset = right
	graph.queue_redraw()
	for v in [captures_view, today_view, projects_view, agents_view, table_view]:  # the lists stay clear of docked panels
		if v != null:
			(v as Control).offset_left = panel_layer.margin_side + left
			(v as Control).offset_right = -(panel_layer.margin_side + right)


func _every(s: float, fn: Callable) -> void:
	var t := Timer.new()
	t.wait_time = s
	t.autostart = true
	t.timeout.connect(fn)
	add_child(t)


# ----------------------------------------------------------------- layout
func _build_top_bar() -> void:
	var bar := HBoxContainer.new()
	bar.set_anchors_preset(Control.PRESET_TOP_WIDE)
	bar.offset_left = 24
	bar.offset_right = -24
	bar.offset_top = 18
	bar.add_theme_constant_override("separation", 14)
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(bar)
	var logo := BrainLogo.new()
	logo.custom_minimum_size = Vector2(44, 44)
	bar.add_child(logo)
	var htext := VBoxContainer.new()
	htext.add_theme_constant_override("separation", -2)
	bar.add_child(htext)
	greeting = Label.new()
	greeting.theme_type_variation = "Heading"
	greeting.add_theme_font_size_override("font_size", SbTheme.fs(22))
	htext.add_child(greeting)
	date_label = Label.new()
	date_label.theme_type_variation = "Muted"
	htext.add_child(date_label)
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	spacer.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar.add_child(spacer)
	var seg := HBoxContainer.new()
	seg.add_theme_constant_override("separation", 4)
	seg.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	bar.add_child(seg)
	var group := ButtonGroup.new()
	for pair in nav_views():
		var b := Button.new()
		b.text = str(pair[1])
		b.toggle_mode = true
		b.button_group = group
		b.theme_type_variation = "GhostButton"
		b.button_pressed = pair[0] == "graph"
		var key := str(pair[0])
		b.pressed.connect(func() -> void: set_view(key))
		seg.add_child(b)
		view_buttons[key] = b
	search_edit = LineEdit.new()
	search_edit.theme_type_variation = "SearchEdit"
	search_edit.placeholder_text = I18n.t("Search your brain   ( / )")
	search_edit.custom_minimum_size = Vector2(220, 40)
	search_edit.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	search_edit.clear_button_enabled = true
	search_edit.text_changed.connect(_on_search_changed)
	search_edit.text_submitted.connect(func(_t: String) -> void: _open_first_hit())
	bar.add_child(search_edit)
	var pill := Button.new()
	pill.theme_type_variation = "GhostButton"
	pill.tooltip_text = I18n.t("Open the engine room (System Console)")
	pill.pressed.connect(func() -> void: app.show_console())
	pill.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	bar.add_child(pill)
	var prow := HBoxContainer.new()
	prow.add_theme_constant_override("separation", 8)
	prow.mouse_filter = Control.MOUSE_FILTER_IGNORE
	prow.set_anchors_preset(Control.PRESET_FULL_RECT)
	prow.offset_left = 12
	pill.add_child(prow)
	status_dot = StatusDot.new()
	status_dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	prow.add_child(status_dot)
	status_label = Label.new()
	status_label.theme_type_variation = "Muted"
	status_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	prow.add_child(status_label)
	pill.custom_minimum_size = Vector2(196, 40)
	mcp_lights = preload("res://scenes/brain/mcp_lights.gd").new().setup(app)  # MCP in / out (Loop MCP-A)
	bar.add_child(mcp_lights)
	settings_button = _settings_menu()
	bar.add_child(settings_button)
	# FR / EN: the app's language. English is the product's; the switch rebuilds the screen in the other one.
	bar.add_child(I18n.switch(app))


## ⚙ One entry to every setting (Loop UX-C): each line opens the place where that setting already lives.
const SETTINGS_ITEMS := ["agents", "tools", "voice", "ambiance", "data", "timeline"]


func _settings_menu() -> Button:
	var b := Button.new()
	b.name = "SettingsButton"
	b.text = "⚙"
	b.theme_type_variation = "GhostButton"
	b.add_theme_font_size_override("font_size", SbTheme.fs(20))
	b.custom_minimum_size = Vector2(44, 40)
	b.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	b.tooltip_text = I18n.t("Settings")
	var menu := PopupMenu.new()
	menu.name = "SettingsMenu"
	b.add_child(menu)
	var labels := {"agents": I18n.t("Agents and what they may do…"), "tools": I18n.t("AI tools: Claude Code, your agents' tools…"),
		"voice": I18n.t("Voice and OpenAI key…"), "ambiance": I18n.t("Theme, music and sounds…"),
		"data": I18n.t("Your data: backups, export, sensitive actions…"), "timeline": I18n.t("Timeline of changes…")}
	for i in SETTINGS_ITEMS.size():
		if SETTINGS_ITEMS[i] == "data":
			menu.add_separator()
		menu.add_item(str(labels[SETTINGS_ITEMS[i]]), i)
	menu.id_pressed.connect(func(id: int) -> void: open_setting(str(SETTINGS_ITEMS[id])))
	b.pressed.connect(func() -> void:
		menu.reset_size()
		var at := b.get_screen_position() + Vector2(b.size.x - menu.size.x, b.size.y + 6)
		menu.popup(Rect2i(Vector2i(at), Vector2i.ZERO)))
	return b


func open_setting(which: String) -> void:
	match which:
		"agents":
			show_agent_info("archivist")
		"tools":
			mcp_lights.call("open_dialog")
		"voice":
			_open_voice_settings()
		"ambiance":
			var w: Variant = app.get("_widget")
			if w != null:
				w.call("_open")
		"data":
			app.show_console()
		"timeline":
			mcp_lights.call("open_timeline")


func _build_views() -> void:
	captures_view = CapturesView.new().setup(app)
	captures_view.brain_changed.connect(func() -> void:
		refresh_graph()
		refresh_spaces())
	captures_view.open_note.connect(func(nid: String) -> void:
		await set_view("graph")
		open_note(nid, true))
	today_view = TodayView.new().setup(app)
	projects_view = ProjectsView.new().setup(app)
	agents_view = AgentsView.new().setup(app)
	agents_view.failed.connect(func(msg: String) -> void: show_toast(msg))
	table_view = preload("res://scenes/brain/table_view.gd").new().setup(app)
	table_view.connect("failed", func(msg: String) -> void: show_toast(msg))
	table_view.connect("changed", func() -> void: refresh_graph())
	table_view.connect("open_note", func(nid: String) -> void:
		await set_view("graph")
		open_note(nid, true))
	for v in [captures_view, today_view, projects_view, agents_view, table_view]:
		v.set_anchors_preset(Control.PRESET_FULL_RECT)
		v.offset_left = 388
		v.offset_right = -24
		v.offset_top = 92
		v.offset_bottom = -112
		v.visible = false
		add_child(v)
	today_view.open_project.connect(func(pid: String) -> void:
		set_view("projects")
		projects_view.show_card(pid))
	today_view.changed.connect(func() -> void: refresh_graph())
	today_view.review_requested.connect(func() -> void:
		archivist_panel.reveal()
		assistant_panel.run_review())
	projects_view.changed.connect(func() -> void:
		refresh_graph()
		refresh_spaces())
	projects_view.open_note.connect(func(nid: String) -> void: open_note(nid))
	projects_view.failed.connect(func(msg: String) -> void: show_toast(msg))
	projects_view.ask_assistant.connect(func(sid: String, prompt: String) -> void:
		current_space = sid
		archivist_panel.reveal()
		assistant_panel.send(prompt))


func set_view(name: String) -> void:
	view = name
	captures_view.visible = name == "captures"
	if filters_bar != null:
		filters_bar.visible = name == "graph"
		layers_view.visible = name == "graph" and filters_bar.view() == "layers"
		filters_bar.time_bar.visible = name == "graph" and filters_bar.time_button.button_pressed
	if results_box != null:
		(results_box.get_parent() as Control).visible = name == "graph" and search_edit.text.strip_edges() != ""
	today_view.visible = name == "today"
	projects_view.visible = name == "projects"
	agents_view.visible = name == "agents"
	table_view.visible = name == "table"
	var dim := 0.28 if name != "graph" else 1.0
	create_tween().tween_property(graph, "modulate", Color(1, 1, 1, dim), 0.25)
	graph.mouse_filter = Control.MOUSE_FILTER_STOP if name == "graph" else Control.MOUSE_FILTER_IGNORE
	for key in view_buttons:
		(view_buttons[key] as Button).button_pressed = key == name
	if name == "captures":
		await captures_view.refresh()
	elif name == "today":
		await today_view.refresh()
	elif name == "projects":
		await projects_view.refresh()
	elif name == "agents":
		await agents_view.refresh()
	elif name == "table":
		await table_view.call("refresh")
	app.state["view"] = name


func _build_left_panel() -> void:
	panel_layer = SbPanelLayer.new()
	add_child(panel_layer)
	panel_layer.edges_changed.connect(_on_panel_edges)
	panel_layer.create_requested.connect(func() -> void: open_agent("builder", AssistantPanel.said("new_agent")))
	assistant_panel = _make_agent("archivist", I18n.t("Archivist"), "A", "", false)
	archivist_panel = agent_panels["archivist"]
	sparring_chat = _make_agent("sparring", I18n.t("Sparring"), "S", "", true)
	sparring_panel = agent_panels["sparring"]
	spaces_page = VBoxContainer.new()
	spaces_page.add_theme_constant_override("separation", 10)
	spaces_page.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var places_scroll := ScrollContainer.new()
	places_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	places_scroll.add_child(spaces_page)
	places_panel = SbFloatingPanel.new().setup("places", I18n.t("PLACES · TODAY"), places_scroll,
		{"dock": "left", "size": 340.0, "minimized": true, "free": Rect2(800, 120, 320, 480)})
	panel_layer.add_panel(places_panel)
	var col := spaces_page
	var over := Label.new()
	over.text = I18n.t("BRIEFING")
	over.theme_type_variation = "Overline"
	col.add_child(over)
	briefing_box = VBoxContainer.new()
	briefing_box.add_theme_constant_override("separation", 4)
	col.add_child(briefing_box)
	col.add_child(HSeparator.new())
	var shead := HBoxContainer.new()
	col.add_child(shead)
	var sover := Label.new()
	sover.text = I18n.t("SPACES")
	sover.theme_type_variation = "Overline"
	sover.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	shead.add_child(sover)
	var add := Button.new()
	add.text = "+"
	add.theme_type_variation = "GhostButton"
	add.tooltip_text = I18n.t("New space (a project, an area of your life…)")
	add.pressed.connect(_prompt_new_space)
	shead.add_child(add)
	spaces_box = VBoxContainer.new()
	spaces_box.add_theme_constant_override("separation", 2)
	col.add_child(spaces_box)
	stats_label = Label.new()
	stats_label.theme_type_variation = "Muted"
	stats_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	col.add_child(stats_label)
	col.add_child(HSeparator.new())
	var srow := HBoxContainer.new()
	col.add_child(srow)
	var sl := Label.new()
	sl.text = I18n.t("SOURCES")
	sl.theme_type_variation = "Overline"
	sl.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	srow.add_child(sl)
	var addf := Button.new()
	addf.text = I18n.t("+ File")
	addf.theme_type_variation = "GhostButton"
	addf.tooltip_text = I18n.t("Add a PDF, Word, Markdown or text file, a voice memo, or a .zip of notes. You can also drop files on the window, or paste a link in the capture bar.")
	addf.pressed.connect(_pick_file)
	srow.add_child(addf)
	var addd := Button.new()
	addd.name = "ImportFolderButton"
	addd.text = I18n.t("+ Folder")
	addd.theme_type_variation = "GhostButton"
	addd.tooltip_text = I18n.t("Import a folder of notes (an Obsidian vault, Markdown notes). You can also drop a folder or a .zip on the window.")
	addd.pressed.connect(_pick_folder)
	srow.add_child(addd)
	sources_box = VBoxContainer.new()
	sources_box.add_theme_constant_override("separation", 0)
	col.add_child(sources_box)
	col.add_child(HSeparator.new())
	var reset := Button.new()
	reset.text = I18n.t("Reset the panel layout")
	reset.theme_type_variation = "GhostButton"
	reset.tooltip_text = I18n.t("Archivist on the left, item on the right, this panel shrunk under the archivist")
	reset.pressed.connect(func() -> void:
		panel_layer.reset_all()
		show_toast(I18n.t("Panels back in their places.")))
	col.add_child(reset)


func _build_toast() -> void:
	var wrap := CenterContainer.new()
	wrap.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	wrap.offset_top = -150
	wrap.offset_bottom = -104
	wrap.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(wrap)
	toast = PanelContainer.new()
	toast.theme_type_variation = "Pill"
	toast.visible = false
	wrap.add_child(toast)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	toast.add_child(row)
	toast_label = Label.new()
	row.add_child(toast_label)
	toast_undo = Button.new()
	toast_undo.text = I18n.t("Undo")
	toast_undo.theme_type_variation = "GhostButton"
	toast_undo.pressed.connect(_undo_toast)
	row.add_child(toast_undo)
	_toast_timer = Timer.new()
	_toast_timer.one_shot = true
	_toast_timer.wait_time = 8.0
	_toast_timer.timeout.connect(func() -> void: toast.visible = false)
	add_child(_toast_timer)


func show_toast(text: String, action_id: int = 0) -> void:
	toast_label.text = text
	toast_action = action_id
	toast_undo.visible = action_id > 0
	toast.visible = true
	toast.modulate.a = 0.0
	create_tween().tween_property(toast, "modulate:a", 1.0, 0.25)
	_toast_timer.start()


func _undo_toast() -> void:
	if toast_action <= 0:
		return
	var res := await app.backend.api.call_api("/assistant/actions/%d/undo" % toast_action, true, HTTPClient.METHOD_POST)
	if res["ok"]:
		app.audio.play("whoosh")
		show_toast(I18n.t("Put back where it was."))
		await refresh_graph()
		await refresh_spaces()


# ---------------------------------------------------------------- sources
const AUDIO_EXT := ["m4a", "mp3", "wav", "mp4", "mpeg", "mpga", "webm", "ogg", "opus", "oga", "aac", "amr", "3gp", "flac", "wma", "caf", "aiff", "aif"]


func _on_files_dropped(files: PackedStringArray) -> void:
	# Voice memos dropped together (or a folder of them) open one preview (Loop 37).
	var memos: Array = []
	for f in files:
		if f.get_extension().to_lower() in AUDIO_EXT or (DirAccess.dir_exists_absolute(f) and _is_memo_folder(f)):
			memos.append(f)
	if not memos.is_empty():
		import_audio(memos)
	for f in files:
		if f in memos:
			continue
		if DirAccess.dir_exists_absolute(f) or f.get_extension().to_lower() == "zip":  # a folder or a zip of notes: the import preview (Loops 39, 37)
			await import_folder(f)
		elif f.get_extension().to_lower() == "brain":
			await import_pack(f)
		else:
			await add_source_file(f)


## A .brain pack dropped on the window (or chosen by voice) becomes a layer.
func import_pack(path: String) -> bool:
	await set_view("captures")
	var dlg := captures_view.open_packs()
	var res: Dictionary = await dlg.import_path(path)
	if res["ok"]:
		await refresh_graph()
		await refresh_spaces()
	return bool(res["ok"])


func _pick_file() -> void:
	if _file_dialog == null:
		_file_dialog = FileDialog.new()
		_file_dialog.file_mode = FileDialog.FILE_MODE_OPEN_FILES
		_file_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_file_dialog.use_native_dialog = true
		_file_dialog.filters = PackedStringArray(["*.pdf, *.docx, *.md, *.txt, *.html, *.htm, *.csv, *.json, *.zip, *.m4a, *.mp3, *.wav, *.mp4, *.webm ; "
			+ I18n.t("Documents and voice memos"), "*.m4a, *.mp3, *.wav, *.mp4, *.webm, *.ogg, *.opus ; " + I18n.t("Voice memos")])
		_file_dialog.files_selected.connect(func(paths: PackedStringArray) -> void: _on_files_dropped(paths))
		add_child(_file_dialog)
	_file_dialog.popup_centered_ratio(0.6)


var _folder_dialog: FileDialog
var folder_import: AcceptDialog      # the open « Import a folder » dialog (tests)
var audio_import: AcceptDialog       # the open « Voice memos » dialog (tests)


## A folder of recordings and no notes (a phone's memos copied over): voice memos rather than a vault.
func _is_memo_folder(dir: String) -> bool:
	var audio := 0
	var stack: Array = [dir]
	var seen := 0
	while not stack.is_empty() and seen < 400:
		var d := str(stack.pop_back())
		for sub in DirAccess.get_directories_at(d):
			if not sub.begins_with("."):
				stack.append(d.path_join(sub))
		for f in DirAccess.get_files_at(d):
			seen += 1
			var ext := f.get_extension().to_lower()
			if ext in ["md", "markdown"]:
				return false
			if ext in AUDIO_EXT:
				audio += 1
	return audio > 0


func import_audio(files: Array) -> AcceptDialog:
	if audio_import != null and is_instance_valid(audio_import):
		audio_import.queue_free()
	audio_import = preload("res://scenes/brain/audio_import_dialog.gd").new().setup(app, files, "" if _auto_file() else current_space)
	audio_import.connect("imported", func(_r: Dictionary) -> void:
		var born := await refresh_graph()
		if not born.is_empty():
			graph.focus_on(born[0])
		await refresh_spaces()
		await refresh_sources())
	add_child(audio_import)
	audio_import.call("open")
	return audio_import


func _pick_folder() -> void:
	if _folder_dialog == null:
		_folder_dialog = FileDialog.new()
		_folder_dialog.file_mode = FileDialog.FILE_MODE_OPEN_DIR
		_folder_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_folder_dialog.use_native_dialog = true
		_folder_dialog.dir_selected.connect(func(dir: String) -> void: import_folder(dir))
		add_child(_folder_dialog)
	_folder_dialog.popup_centered_ratio(0.6)


## « Import a folder… », a dropped folder, or « importe mon vault Obsidian »: the preview, then the import.
func import_folder(dir: String) -> AcceptDialog:
	if folder_import != null and is_instance_valid(folder_import):
		folder_import.queue_free()
	folder_import = preload("res://scenes/brain/folder_import_dialog.gd").new().setup(app, dir)
	folder_import.connect("imported", func(_r: Dictionary) -> void:
		await refresh_graph()
		await refresh_spaces())
	folder_import.connect("add_documents", func(paths: Array) -> void:
		for p in paths.slice(0, 50):
			await add_source_file(str(p)))
	add_child(folder_import)
	folder_import.call("open")
	return folder_import


func add_source_file(path: String) -> bool:
	show_toast(I18n.t("Reading %s…") % path.get_file())
	var payload := {"path": path}
	if not _auto_file():
		payload["space_id"] = current_space
	return await _ingest("/sources/file", payload)


func add_source_url(url: String) -> bool:
	show_toast(I18n.t("Reading %s…") % url.left(60))
	var payload := {"url": url}
	if not _auto_file():
		payload["space_id"] = current_space
	return await _ingest("/sources/url", payload)


func _ingest(path: String, payload: Dictionary) -> bool:
	var job := "%d-%d" % [Time.get_ticks_usec(), randi()]
	payload["job"] = job
	var what := str(payload.get("path", payload.get("url", ""))).get_file().left(48)
	var state := {"busy": true}
	_follow_progress(job, what, state)
	var res := await app.backend.api.call_api(path, true, HTTPClient.METHOD_POST, JSON.stringify(payload))
	state["busy"] = false
	if not is_inside_tree():
		return false
	if not res["ok"]:
		var d: Dictionary = res["data"]
		last_source_error = str(d.get("detail", res["error"]))
		app.audio.play("error")
		show_toast(I18n.t("Could not add it: %s") % last_source_error)
		return false
	var src: Dictionary = res["data"]
	if bool(src.get("duplicate", false)):
		show_toast(I18n.t("Already in your brain: “%s”") % src.get("title", ""))
		return true
	sources_added += 1
	app.audio.play("note_create", 0.04)
	show_toast(I18n.t("Added “%s” · %d passages indexed") % [src.get("title", ""), int(src.get("chunks", 0))])
	var born := await refresh_graph()
	if not born.is_empty():
		graph.focus_on(born[0])
	await refresh_spaces()
	await refresh_sources()
	if _auto_file() and src.get("note_id") != null:
		_classify(str(src["note_id"]))
	return true


## While a document is being read: « Reading CV.pdf · page 3 / 9 (local OCR) », every half second.
func _follow_progress(job: String, what: String, state: Dictionary) -> void:
	await get_tree().create_timer(0.6).timeout
	while bool(state["busy"]) and is_inside_tree():
		var res := await app.backend.api.call_api("/sources/progress/" + job)
		if not bool(state["busy"]) or not is_inside_tree():
			return
		if res["ok"]:
			var line := progress_text(res["data"])
			if line != "":
				show_toast(I18n.t("Reading %s · %s") % [what, line])
		await get_tree().create_timer(0.5).timeout


static func progress_text(p: Dictionary) -> String:
	var done := int(p.get("done", 0))
	var total := int(p.get("total", 0))
	match str(p.get("stage", "")):
		"render":
			return I18n.t("preparing page %d / %d") % [done, total]
		"ocr":
			return I18n.t("page %d / %d read (local OCR)") % [done, total]
		"ai":
			return I18n.t("page %d / %d (AI)") % [mini(done + 1, total), total]
		"summary":
			return I18n.t("writing the summary")
		"transcribe":
			return I18n.t("transcribing the recording")
		"structure":
			return I18n.t("finding the ideas")
		"indexing":
			return I18n.t("indexing by meaning")
	return ""


func refresh_sources() -> void:
	var res := await app.backend.api.call_api("/sources")
	if not res["ok"] or not is_inside_tree() or sources_box == null:
		return
	for c in sources_box.get_children():
		c.queue_free()
	var data: Dictionary = res["data"]
	var list: Array = data.get("sources", [])
	for item in list.slice(0, 8):
		var s: Dictionary = item
		var b := Button.new()
		b.theme_type_variation = "GhostButton"
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.text = ("↗ " if str(s["kind"]) == "url" else "▤ ") + str(s["title"]).left(34)
		b.tooltip_text = str(s["uri"])
		var nid := str(s.get("note_id", ""))
		b.pressed.connect(func() -> void: open_note(nid, true))
		sources_box.add_child(b)
	if list.is_empty():
		var l := Label.new()
		l.theme_type_variation = "Muted"
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		l.text = I18n.t("Drop files on the window or paste a link in the capture bar.")
		sources_box.add_child(l)


# ------------------------------------------------------------ hands-free (Loop 7a)
const PTT_KEY := KEY_F8
var ptt_active := false
var listening_overlay: PanelContainer
var listening_label: Label


## Performs interface actions decided by the assistant. A theme change rebuilds this
## screen, so it always runs last.
func run_ui_actions(actions: Array) -> void:
	var theme_choice := ""
	for item in actions:
		var a: Dictionary = item
		match str(a.get("action", "")):
			"open_file":  # an export made by voice (Loop 37D): the PDF opens in the user's viewer
				if str(a.get("path", "")) != "" and OS.get_environment("SBGD_NO_OPEN") == "":
					OS.shell_open(str(a["path"]))
				last_opened_file = str(a.get("path", ""))
			"open_view":
				if str(a.get("view", "")) == "table":
					table_view.set("type_id", str(a.get("type", "")))
					(table_view.get("search") as LineEdit).text = str(a.get("query", ""))
				await set_view(str(a.get("view", "graph")))
				if str(a.get("view", "")) == "table" and str(a.get("saved", "")) != "":
					await table_view.call("show_view", str(a["saved"]))
			"open_project":
				await set_view("projects")
				projects_view.show_card(str(a.get("space_id", "")))
			"open_note":
				await set_view("graph")
				await open_note(str(a.get("note_id", "")), true)
			"weekly_review":
				archivist_panel.reveal()
				assistant_panel.run_review()
			"set_volume":
				_change_volume(str(a.get("change", "")))
			"replay":
				assistant_panel.replay(str(a.get("which", "last")))
			"search":
				await show_search(str(a.get("query", "")))
			"path":
				await set_view("graph")
				await refresh_graph()
				graph.set_path(a.get("ids", []), a.get("steps", []))
				path_active = true
			"layout":
				await set_view("graph")
				filters_bar.set_view(str(a.get("mode", "zones")))
			"filter":
				await set_view("graph")
				var f: Dictionary = a.get("filter", {})
				filters_bar.apply(f)
			"fold":
				await set_view("graph")
				var place := str(a.get("place", ""))
				if place == "*":
					for nid in graph.nodes:
						if str((graph.nodes[nid] as Dictionary)["type"]) == "space":
							fold_place(str(nid), bool(a.get("fold", true)))
				else:
					fold_place(place, bool(a.get("fold", true)))
			"open_document", "open_original":
				var tid := ""
				var tgt := str(a.get("target", ""))
				if tgt != "":
					tid = graph.find_node(tgt)
				elif viewer != null and viewer.visible:
					tid = str(viewer.doc.get("note_id", ""))
				elif not current_note.is_empty():
					tid = str(current_note.get("id", ""))
				else:
					tid = graph.selected
				if tid == "" or tid.begins_with("space:") or tid.begins_with("tag:"):
					show_toast(I18n.t("Which document? Say its title."))
				elif await open_document_for(tid) and str(a.get("action", "")) == "open_original":
					viewer.open_original()
			"page":
				if viewer != null and viewer.visible:
					var ch := str(a.get("change", "next"))
					match ch:
						"next":
							viewer.go_page(viewer.page + 1)
						"previous":
							viewer.go_page(viewer.page - 1)
						"first":
							viewer.go_page(1)
						"last":
							viewer.go_page(viewer.pages())
						_:
							viewer.go_page(int(ch))
			"close_document":
				if viewer != null:
					viewer.hide_viewer()
			"zoom":
				await set_view("graph")
				var target := str(a.get("target", ""))
				var hit := graph.find_node(target) if target != "" else ""
				if target != "" and hit == "":
					show_toast(I18n.t("Nothing called “%s” in the graph.") % target)
				graph.zoom_level(str(a.get("level", "closer")), hit)
				if hit != "" and str(a.get("level", "")) == "read":
					graph.select(hit)
			"import_pack":
				await set_view("captures")
				captures_view.open_packs().pick_file()
			"import_folder":
				var where := str(a.get("path", ""))
				if where != "":
					import_folder(where)
				else:
					_pick_folder()
			"pack_exported":
				show_toast(I18n.t("Pack saved: %s") % str(a.get("path", "")).get_file())
				last_pack_export = str(a.get("path", ""))
			"open_agent":
				open_agent(str(a.get("agent", "archivist")))
			"agent_draft":
				agent_panel("builder").reveal()
				await chat_panel("builder").show_agent_draft()
			"agents_changed":
				await refresh_agents()
				var made := str(a.get("agent", ""))
				if agent_panels.has(made):
					(agent_panels[made] as SbFloatingPanel).reveal()
				show_toast(I18n.t("“%s” is ready: talk to it in its own panel.") % str(a.get("name", made)))
			"mission":  # an agent started a mission (chat or voice): its card follows it
				var who := str(a.get("agent", "archivist"))
				agent_panel(who).reveal()
				await chat_panel(who).mission_card.call("follow")
			"synthesis_draft":
				var drafter := str(a.get("agent", "sparring"))
				agent_panel(drafter).reveal()
				await chat_panel(drafter).show_draft()
			"open_url":
				var url := str(a.get("url", ""))
				last_opened_url = url
				if url.begins_with("http") and OS.get_environment("SBGD_TEST_NO_SHELL") != "1":
					OS.shell_open(url)
			"capture_clipboard":
				var clip := clipboard_text().strip_edges()
				if clip == "":
					show_toast(I18n.t("The clipboard is empty: copy a link or a text first."))
				else:
					await capture(clip, "typed")
			"context":
				var ctx: Variant = a.get("context")
				capture_hint.text = (I18n.t("Working on %s: new items are filed there.") % str((ctx as Dictionary).get("name", ""))) \
					if ctx is Dictionary else I18n.t("No working context: the archivist files freely.")
				await refresh_spaces()
			"set_voice_speed":
				app.audio.change_voice_speed(str(a.get("change", "normal")))
			"refresh":
				await refresh_graph()
				await refresh_spaces()
				_refresh_view()
			"set_theme":
				theme_choice = str(a.get("theme", ""))
	if theme_choice != "":
		app.set_theme_choice(theme_choice)


## Headless runs have no clipboard: tests put their text in test_clipboard.
var test_clipboard := ""


func clipboard_text() -> String:
	return test_clipboard if test_clipboard != "" else DisplayServer.clipboard_get()


func _change_volume(change: String) -> void:
	match change:
		"mute":
			app.audio.set_muted(true)
		"unmute":
			app.audio.set_muted(false)
		"up", "down":
			app.audio.set_muted(false)
			var f := 1.35 if change == "up" else 0.7
			for bus in ["Music", "Ambience", "SFX", "Voice"]:
				app.audio.set_volume(bus, clampf(app.audio.volume(bus) * f, 0.05, 1.0))


## Hold F8 to talk to the assistant, release to send: the reply is spoken.
## use_mic = false lets tests feed audio frames instead.
func push_to_talk(pressed: bool, use_mic: bool = true) -> void:
	if app.live.active:
		return
	if pressed and not ptt_active and voice_state == "idle":
		ptt_active = true
		agent_panel().reveal()
		voice_target = "chat"
		var res := await app.backend.api.call_api("/voice/status")
		var st: Dictionary = res["data"] if res["ok"] else {}
		if not bool(st.get("configured", false)) and OS.get_environment("SBGD_VOICE_PROVIDER") != "fake":
			ptt_active = false
			_open_voice_settings()
			return
		_show_listening(true)
		if not await start_voice(use_mic):
			ptt_active = false
			_show_listening(false)
	elif not pressed and ptt_active:
		ptt_active = false
		# The key can be released while the connection is still opening: wait for it.
		var deadline := Time.get_ticks_msec() + 10000
		while voice_state == "connecting" and Time.get_ticks_msec() < deadline:
			await get_tree().process_frame
		listening_label.text = I18n.t("Transcribing…")
		await stop_voice()
		_show_listening(false)


func _build_listening_overlay() -> void:
	listening_overlay = PanelContainer.new()
	listening_overlay.theme_type_variation = "Glass"
	listening_overlay.set_anchors_preset(Control.PRESET_CENTER_TOP)
	listening_overlay.offset_top = 96
	listening_overlay.offset_left = -170
	listening_overlay.offset_right = 170
	listening_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	listening_overlay.visible = false
	add_child(listening_overlay)
	listening_label = Label.new()
	listening_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	listening_label.add_theme_color_override("font_color", SbTheme.WARM)
	listening_label.add_theme_font_size_override("font_size", SbTheme.fs(18))
	listening_overlay.add_child(listening_label)


func _show_listening(on: bool) -> void:
	listening_label.text = I18n.t("●  Listening — release F8 to send")
	listening_overlay.visible = on
	if on:
		listening_overlay.modulate.a = 0.0
		create_tween().tween_property(listening_overlay, "modulate:a", 1.0, 0.15)


func _refresh_view() -> void:
	if view == "captures":
		captures_view.refresh()
	elif view == "today":
		today_view.refresh()
	elif view == "projects":
		projects_view.refresh()
	elif view == "agents":
		agents_view.refresh()


func _open_note_by_title(title: String) -> void:
	for id in graph.nodes:
		var n: Dictionary = graph.nodes[id]
		if str(n["type"]) == "note" and str(n["label"]).to_lower() == title.to_lower():
			open_note(str(id), true)
			return


## The archivist files the item and answers with a receipt (spoken when the input was spoken).
## An item dragged into another zone (or « déplace X dans Y »): it now belongs to that place.
func move_to_place(note_id: String, space_id: String) -> bool:
	var res := await _post("/brain/notes/" + note_id, {"space_id": space_id}, HTTPClient.METHOD_PATCH)
	if not is_inside_tree():
		return false
	if not res["ok"]:
		show_toast(I18n.t("Could not move it: %s") % str(res["error"]))
		await refresh_graph()
		return false
	app.audio.play("node_link", 0.05)
	show_toast(I18n.t("Moved to %s.") % _space_name(space_id))
	await refresh_graph()
	await refresh_spaces()
	if not current_note.is_empty() and str(current_note["id"]) == note_id:
		open_note(note_id)
	return true


## No place chosen (or only the Inbox selected): the archivist decides where a new item goes.
func _auto_file() -> bool:
	return current_space == "" or current_space == "inbox"


func _classify(note_id: String, spoken: bool = false) -> void:
	if not assistant_panel.configured:
		return
	var res := await app.backend.api.call_api("/assistant/classify/" + note_id, true, HTTPClient.METHOD_POST)
	if not is_inside_tree():
		return
	if not res["ok"]:
		var d0: Variant = res["data"]
		var why := str((d0 as Dictionary).get("detail", res["error"])) if d0 is Dictionary else str(res["error"])
		show_toast(I18n.t("The archivist could not file it (%s). It stays in the Inbox.") % why.left(120))
		return
	var d: Dictionary = res["data"]
	var item: Dictionary = d.get("item", {})
	var receipt := str(d.get("receipt", ""))
	last_receipt = receipt
	assistant_panel.add_receipt(item, receipt, bool(d.get("applied", false)), int(d.get("action_id", 0)))
	if spoken:
		assistant_panel.say(receipt, true)
	if bool(d.get("applied", false)):
		classified += 1
		app.audio.play("node_link", 0.05)
		show_toast(receipt, int(d.get("action_id", 0)))
		await refresh_graph()
		await refresh_spaces()
	else:
		show_toast(receipt)
	_refresh_view()


func _build_inspector() -> void:
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 10)
	inspector = SbFloatingPanel.new().setup("item", I18n.t("ITEM"), col, {"dock": "right", "size": 380.0, "free": Rect2(900, 120, 380, 560)})
	inspector.visible = false
	panel_layer.add_panel(inspector)
	var head := HBoxContainer.new()
	col.add_child(head)
	save_label = Label.new()
	save_label.theme_type_variation = "Muted"
	save_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(save_label)
	var ask := Button.new()
	ask.name = "AskAbout"
	ask.text = I18n.t("Ask about this")
	ask.theme_type_variation = "GhostButton"
	ask.tooltip_text = I18n.t("Pins this item to your next question to the active agent (@)")
	ask.pressed.connect(func() -> void:
		if not current_note.is_empty():
			ask_about(str(current_note.get("id", "")), str(current_note.get("title", ""))))
	head.add_child(ask)
	var del := Button.new()
	del.text = I18n.t("Delete")
	del.theme_type_variation = "GhostButton"
	del.pressed.connect(_delete_note)
	head.add_child(del)
	var close := Button.new()
	close.text = "✕"
	close.theme_type_variation = "GhostButton"
	close.tooltip_text = I18n.t("Close (Esc)")
	close.pressed.connect(func() -> void:
		graph.select("")
		_close_inspector())
	head.add_child(close)
	title_edit = LineEdit.new()
	title_edit.add_theme_font_override("font", SbTheme.font(650))
	title_edit.add_theme_font_size_override("font_size", SbTheme.fs(20))
	title_edit.text_changed.connect(func(_t: String) -> void: _queue_save())
	col.add_child(title_edit)
	var meta := HBoxContainer.new()
	meta.add_theme_constant_override("separation", 8)
	col.add_child(meta)
	space_option = OptionButton.new()
	space_option.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	space_option.clip_text = true
	space_option.custom_minimum_size.x = 120
	space_option.item_selected.connect(func(_i: int) -> void: _queue_save(true))
	meta.add_child(space_option)
	kind_option = OptionButton.new()
	var kinds := {"note": I18n.t("Note"), "idea": I18n.t("Idea"), "task": I18n.t("Task"), "journal": I18n.t("Journal"),
		"reference": I18n.t("Reference")}
	for k in kinds:
		kind_option.add_item(str(kinds[k]))
		kind_option.set_item_metadata(kind_option.item_count - 1, k)
	kind_option.item_selected.connect(func(_i: int) -> void: _queue_save(true))
	meta.add_child(kind_option)
	body_edit = TextEdit.new()
	body_edit.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body_edit.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	body_edit.placeholder_text = I18n.t("Write freely. [[Another note]] links it, #tag groups it.")
	body_edit.text_changed.connect(func() -> void: _queue_save())
	col.add_child(body_edit)
	var lover := Label.new()
	lover.text = I18n.t("CONNECTIONS")
	lover.theme_type_variation = "Overline"
	col.add_child(lover)
	links_box = VBoxContainer.new()
	links_box.add_theme_constant_override("separation", 0)
	col.add_child(links_box)
	doc_row = HBoxContainer.new()
	doc_row.add_theme_constant_override("separation", 8)
	doc_row.visible = false
	col.add_child(doc_row)
	var view_doc := Button.new()
	view_doc.text = I18n.t("View document")
	view_doc.pressed.connect(func() -> void: open_document_for(str(current_note.get("id", ""))))
	doc_row.add_child(view_doc)
	var orig_doc := Button.new()
	orig_doc.text = I18n.t("Open original")
	orig_doc.theme_type_variation = "GhostButton"
	orig_doc.pressed.connect(func() -> void:
		if await open_document_for(str(current_note.get("id", ""))):
			viewer.open_original())
	doc_row.add_child(orig_doc)
	related_label = Label.new()
	related_label.text = I18n.t("RELATED IDEAS")
	related_label.theme_type_variation = "Overline"
	related_label.tooltip_text = I18n.t("Found by meaning, in any language. Dashed warm lines in the graph.")
	related_label.visible = false
	col.add_child(related_label)
	related_box = VBoxContainer.new()
	related_box.add_theme_constant_override("separation", 0)
	col.add_child(related_box)


func _build_capture_bar() -> void:
	var wrap := CenterContainer.new()
	wrap.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	wrap.offset_top = -96
	wrap.offset_bottom = -26
	wrap.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(wrap)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 6)
	wrap.add_child(col)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	col.add_child(row)
	capture_edit = LineEdit.new()
	capture_edit.theme_type_variation = "CaptureEdit"
	capture_edit.placeholder_text = I18n.t("Type, paste a link…   (Enter · Ctrl+Shift+V adds the clipboard · F8 to speak)")
	capture_edit.custom_minimum_size = Vector2(620, 54)
	capture_edit.text_submitted.connect(func(t: String) -> void: capture(t))
	capture_edit.focus_entered.connect(func() -> void: app.audio.play("capture_open", 0.0, -4.0))
	row.add_child(capture_edit)
	mic_button = Button.new()
	mic_button.icon = load("res://assets/icons/mic.svg")
	mic_button.icon_alignment = HORIZONTAL_ALIGNMENT_CENTER
	mic_button.expand_icon = false
	mic_button.custom_minimum_size = Vector2(54, 54)
	mic_button.tooltip_text = I18n.t("Speak a thought (Ctrl+M). Click again to finish.")
	mic_button.set_meta("sfx", "none")
	mic_button.pressed.connect(toggle_voice)
	row.add_child(mic_button)
	var ring := _MicRing.new()
	ring.brain = self
	ring.set_anchors_preset(Control.PRESET_FULL_RECT)
	mic_button.add_child(ring)
	capture_hint = Label.new()
	capture_hint.theme_type_variation = "Muted"
	capture_hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	col.add_child(capture_hint)
	_update_capture_hint()


# ------------------------------------------------------------------- data
func _update_greeting() -> void:
	var d := Time.get_datetime_dict_from_system()
	var hour: int = d["hour"]
	var part := I18n.t("Good evening")
	if hour >= 5 and hour < 12:
		part = I18n.t("Good morning")
	elif hour >= 12 and hour < 18:
		part = I18n.t("Good afternoon")
	greeting.text = part
	var days := [I18n.t("Sunday"), I18n.t("Monday"), I18n.t("Tuesday"), I18n.t("Wednesday"), I18n.t("Thursday"),
		I18n.t("Friday"), I18n.t("Saturday")]
	var months := [I18n.t("January"), I18n.t("February"), I18n.t("March"), I18n.t("April"), I18n.t("May"), I18n.t("June"),
		I18n.t("July"), I18n.t("August"), I18n.t("September"), I18n.t("October"), I18n.t("November"), I18n.t("December")]
	# Named fields: French puts the day before the month (« jeudi 5 novembre »).
	var line := I18n.t("{weekday}, {month} {day} · {theme} theme").format({"weekday": days[int(d["weekday"])],
		"month": months[int(d["month"]) - 1], "day": int(d["day"]),
		"theme": SbTheme.theme_label(SbTheme.current)})
	date_label.text = line.left(1).to_upper() + line.substr(1)


func _check_health() -> void:
	var res := await app.backend.api.call_api("/health", false)
	if not is_inside_tree():
		return
	var data: Dictionary = res["data"]
	health_ok = bool(res["ok"]) and str(data.get("status", "")) == "ok"
	status_dot.set_status("ok" if health_ok else "error")
	status_label.text = I18n.t("All systems operational") if health_ok else I18n.t("Engine unreachable")


func refresh_graph() -> Array[String]:
	var res := await app.backend.api.call_api("/brain/graph")
	if not res["ok"] or not is_inside_tree():
		return []
	var restore := graph.nodes.is_empty()
	var born := graph.set_graph(res["data"])
	if restore:  # filters and folded places survive a theme switch
		for key in app.state.get("graph_folded", {}):
			graph.fold(str(key), true)
		if app.state.has("graph_filter") and not (app.state["graph_filter"] as Dictionary).is_empty():
			filters_bar.apply(app.state["graph_filter"])
		graph.focus_id = str(app.state.get("graph_focus", ""))
		filters_bar.set_view(str(app.state.get("graph_layout", "zones")))
	if not born.is_empty():
		_refresh_layers()
	if graph.graph_layout == "meaning" and not born.is_empty():  # new items take their seat on the meaning map
		load_meaning_map()
	graph.details.clear()  # cards fetch their place, themes and text again when they are on screen
	graph._asked.clear()
	_update_stats()
	return born


## A card in the zoomed graph needs its item: summary, place, themes and full text.
func _fetch_card(id: String) -> void:
	if not id.begins_with("note:") and not graph.nodes.has(id):
		return
	var nid := id.trim_prefix("note:")
	var res := await app.backend.api.call_api("/brain/items/" + nid)
	if res["ok"] and is_inside_tree():
		graph.set_details(id, res["data"])


func _fetch_card_page(id: String, source_id: String, width: int) -> void:
	var w := 320
	for bw in [320, 640, 1024, 1600, 2400]:
		w = bw
		if bw >= width:
			break
	var res := await app.backend.api.call_api("/sources/%s/page/1?width=%d" % [source_id, w], true, HTTPClient.METHOD_GET, "", true)
	if res["ok"] and is_inside_tree():
		var src: Dictionary = (graph.details.get(id, {}) as Dictionary).get("source", {}) if graph.details.get(id, {}).get("source") is Dictionary else {}
		var tex := DocumentViewer.texture_from(res["bytes"], str(src.get("mime", "image/png")))
		if tex != null:
			graph.set_page(id, w, tex)


## Opens an item's original (PDF pages or the image) in the full-screen viewer.
func open_document_for(note_id: String, at_page: int = 1) -> bool:
	var res := await app.backend.api.call_api("/brain/items/" + note_id)
	if not res["ok"]:
		return false
	var src: Variant = (res["data"] as Dictionary).get("source")
	if not src is Dictionary:
		show_toast(I18n.t("This item has no document to show."))
		return false
	if viewer == null:
		viewer = DocumentViewer.new().setup(app)
		add_child(viewer)
	var ok := await viewer.open(str((src as Dictionary).get("id", "")), at_page)
	if not ok:
		show_toast(I18n.t("No kept original for this item (added before originals were kept?)."))
	return ok


func _update_stats() -> void:
	var notes := graph.node_count("note")
	var shown := graph.shown_note_count()
	var n_spaces := graph.node_count("space")
	var n_tags := graph.node_count("tag")
	var notes_part := ((I18n.t("%d note") if notes == 1 else I18n.t("%d notes")) % notes) if shown == notes \
		else I18n.t("%d of %d notes shown") % [shown, notes]
	stats_label.text = "%s · %s · %s" % [notes_part, (I18n.t("%d space") if n_spaces == 1 else I18n.t("%d spaces")) % n_spaces,
		(I18n.t("%d tag") if n_tags == 1 else I18n.t("%d tags")) % n_tags]


## Fold or unfold a place by name (voice) or node id.
func fold_place(name_or_id: String, on: bool) -> bool:
	var id := name_or_id if name_or_id.begins_with("space:") else ""
	if id == "":
		for nid in graph.nodes:
			var n: Dictionary = graph.nodes[nid]
			if str(n["type"]) == "space" and str(n["label"]).to_lower() == name_or_id.strip_edges().to_lower():
				id = str(nid)
		if id == "":
			var hit := graph.find_node(name_or_id)
			id = hit if hit.begins_with("space:") else ""
	if id == "":
		show_toast(I18n.t("No place called “%s”.") % name_or_id)
		return false
	graph.fold(id, on)
	var f: Dictionary = app.state.get("graph_folded", {})
	if on:
		f[id] = true
	else:
		f.erase(id)
	app.state["graph_folded"] = f
	_update_stats()
	return true


func refresh_spaces() -> void:
	var res := await app.backend.api.call_api("/brain/spaces")
	if not res["ok"] or not is_inside_tree():
		return
	var data: Dictionary = res["data"]
	spaces = data.get("spaces", [])
	for c in spaces_box.get_children():
		c.queue_free()
	for item in spaces:
		var s: Dictionary = item
		var b := Button.new()
		b.theme_type_variation = "GhostButton"
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.toggle_mode = true
		b.button_pressed = str(s["id"]) == current_space
		b.text = "%s   %s" % [s["name"], SbFormat.number(s.get("note_count", 0))]
		var col := Color(str(s["color"])) if s.get("color") != null else SbTheme.FOREST_LIGHT
		b.icon = _dot_texture(col)
		b.add_theme_color_override("font_color", SbTheme.TEXT)
		b.tooltip_text = I18n.t("Capture into %s; click again to show everything") % s["name"]
		var sid := str(s["id"])
		b.pressed.connect(func() -> void: _toggle_space(sid))
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		b.clip_text = true
		var row := HBoxContainer.new()
		row.add_child(b)
		if sid != "inbox":
			var x := Button.new()
			x.text = "✕"
			x.theme_type_variation = "GhostButton"
			x.tooltip_text = I18n.t("Remove this place: its items go back to the Inbox (Undo available)")
			var sname := str(s["name"])
			var count := int(s.get("note_count", 0))
			x.pressed.connect(func() -> void: _confirm_remove_place(sid, sname, count))
			row.add_child(x)
		spaces_box.add_child(row)
	_rebuild_space_option()
	_update_capture_hint()


func _confirm_remove_place(sid: String, sname: String, count: int) -> void:
	var dlg := ConfirmationDialog.new()
	dlg.title = I18n.t("Remove a place")
	dlg.dialog_text = I18n.t("Remove “%s”?\n%s") % [sname, (I18n.t("Its %d item(s) go back to the Inbox; nothing is deleted.") % count)
		if count > 0 else I18n.t("It is empty.")]
	dlg.ok_button_text = I18n.t("Remove")
	dlg.confirmed.connect(func() -> void: remove_place(sid))
	dlg.visibility_changed.connect(func() -> void:
		if not dlg.visible:
			dlg.queue_free())
	add_child(dlg)
	dlg.popup_centered()


## Removes a place (button ✕ or « supprime la place X »): items back in the Inbox, Undo in the toast.
func remove_place(sid: String) -> bool:
	var res := await app.backend.api.call_api("/brain/spaces/" + sid, true, HTTPClient.METHOD_DELETE)
	if not is_inside_tree():
		return false
	if not res["ok"]:
		var d: Variant = res["data"]
		show_toast(I18n.t("Could not remove it: %s") % (str((d as Dictionary).get("detail", res["error"])) if d is Dictionary else str(res["error"])))
		return false
	var out: Dictionary = res["data"]
	if current_space == sid:
		current_space = ""
	var n := (out.get("moved_to_inbox", []) as Array).size()
	app.audio.play("whoosh")
	var gone := str(out.get("removed", ""))
	show_toast(I18n.t("“%s” removed, %d item(s) back in the Inbox.") % [gone, n] if n > 0 else I18n.t("“%s” removed.") % gone,
		int(out.get("action_id", 0)))
	await refresh_graph()
	await refresh_spaces()
	return true


static func _dot_texture(col: Color) -> ImageTexture:
	var img := Image.create(14, 14, false, Image.FORMAT_RGBA8)
	for y in 14:
		for x in 14:
			var d := Vector2(x + 0.5, y + 0.5).distance_to(Vector2(7, 7))
			img.set_pixel(x, y, Color(col, clampf(5.5 - d, 0.0, 1.0)))
	return ImageTexture.create_from_image(img)


func _toggle_space(sid: String) -> void:
	current_space = "" if current_space == sid else sid
	var ids: Array = []
	if current_space != "":
		ids.append("space:" + current_space)
		for id in graph.nodes:
			var n: Dictionary = graph.nodes[id]
			if str(n.get("space_id", "")) == current_space:
				ids.append(id)
		graph.focus_on("space:" + current_space)
	graph.set_highlight(ids)
	await refresh_spaces()


func load_briefing() -> void:
	# The briefing records a visit, so fetch it once per session (theme
	# switches rebuild this screen) and reuse it.
	var b: Dictionary = app.state.get("briefing", {})
	var fresh := b.is_empty()
	if fresh:
		var res := await app.backend.api.call_api("/brain/briefing")
		if not res["ok"] or not is_inside_tree():
			return
		b = res["data"]
		app.state["briefing"] = b
	for c in briefing_box.get_children():
		c.queue_free()
	var created: Array = b.get("created", [])
	var updated: Array = b.get("updated", [])
	var totals: Dictionary = b.get("totals", {})
	var head := Label.new()
	head.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	if b.get("previous_visit_at") == null:
		head.text = I18n.t("Welcome. Your brain is ready with %d starter notes.") % int(totals.get("notes", 0))
	elif created.is_empty() and updated.is_empty():
		head.text = I18n.t("Nothing new since %s. A calm start.") % SbFormat.local_time(b.get("previous_visit_at"), true)
	else:
		head.text = I18n.t("Since your last visit: %d new, %d updated.") % [created.size(), updated.size()]
		if fresh:
			app.audio.play("notification", 0.0, -3.0)
	briefing_box.add_child(head)
	var inbox := int(totals.get("inbox", 0))
	if inbox > 0:
		var ib := Label.new()
		ib.theme_type_variation = "Muted"
		ib.text = (I18n.t("%d thought waiting in the Inbox") if inbox == 1 else I18n.t("%d thoughts waiting in the Inbox")) % inbox
		briefing_box.add_child(ib)
	var recent: Array = b.get("recent", [])
	for item in recent.slice(0, 4):
		var n: Dictionary = item
		var link := Button.new()
		link.theme_type_variation = "GhostButton"
		link.alignment = HORIZONTAL_ALIGNMENT_LEFT
		link.text = "→ " + str(n["title"]).left(30)
		var nid := str(n["id"])
		link.pressed.connect(func() -> void: open_note(nid, true))
		briefing_box.add_child(link)


# ---------------------------------------------------------------- capture
func capture(text: String, source: String = "typed") -> void:
	var t := text.strip_edges()
	if t == "":
		return
	if (t.begins_with("http://") or t.begins_with("https://")) and not t.contains(" "):
		capture_edit.text = ""
		await add_source_url(t)
		return
	capture_edit.text = ""
	var title := t
	var body := ""
	if t.length() > 80:
		title = t.left(72).strip_edges() + "…"
		body = t
	elif t.contains("[[") or t.contains("#"):
		body = t
	var payload := {"title": title, "body": body, "source": source}
	if source == "voice" and body == "":
		payload["body"] = t
	if current_space != "":
		payload["space_id"] = current_space
	var res := await _post("/brain/notes", payload)
	if not res["ok"]:
		app.audio.play("error")
		capture_hint.text = I18n.t("Could not save: %s") % res["error"]
		return
	notes_created += 1
	if source == "voice":
		voice_notes += 1
	var note: Dictionary = res["data"]
	var born := await refresh_graph()
	app.audio.play("note_create", 0.04)
	var links: Array = note.get("links_out", [])
	if not links.is_empty():
		get_tree().create_timer(0.5).timeout.connect(func() -> void: app.audio.play("node_link", 0.06))
	if not born.is_empty():
		graph.select("")
		graph.focus_on(born[0])
	await refresh_spaces()
	capture_hint.text = I18n.t("Saved to %s. Keep going.") % _space_name(str(note["space_id"]))
	if _auto_file():
		await _classify(str(note["id"]), source == "voice")
	_refresh_view()


func _post(path: String, payload: Dictionary, method: int = HTTPClient.METHOD_POST) -> Dictionary:
	return await app.backend.api.call_api(path, true, method, JSON.stringify(payload))


func _update_capture_hint() -> void:
	if capture_hint == null:
		return
	capture_hint.text = I18n.t("Lands in %s · [[links]], #tags, and links to web pages work here · drop files on the window") % (
		_space_name(current_space) if current_space != "" else I18n.t("your Inbox"))


func _space_name(sid: String) -> String:
	for item in spaces:
		var s: Dictionary = item
		if str(s["id"]) == sid:
			return str(s["name"])
	return I18n.t("Inbox")


func _prompt_new_space() -> void:
	var dlg := AcceptDialog.new()
	dlg.title = I18n.t("New space")
	dlg.ok_button_text = I18n.t("Create")
	var edit := LineEdit.new()
	edit.placeholder_text = I18n.t("Project or area name")
	edit.custom_minimum_size = Vector2(320, 0)
	dlg.add_child(edit)
	add_child(dlg)
	dlg.popup_centered()
	edit.grab_focus()
	var create := func() -> void:
		var name := edit.text.strip_edges()
		dlg.queue_free()
		if name == "":
			return
		var palette := [SbTheme.WARM, SbTheme.INFO, SbTheme.MINT, SbTheme.MINT_SOFT, SbTheme.WARN]
		var col: Color = palette[spaces.size() % palette.size()]
		var res := await _post("/brain/spaces", {"name": name, "kind": "project", "color": "#" + col.to_html(false)})
		if res["ok"]:
			app.audio.play("confirm")
			await refresh_spaces()
			await refresh_graph()
	dlg.confirmed.connect(create)
	edit.text_submitted.connect(func(_t: String) -> void:
		dlg.hide()
		create.call())
	dlg.canceled.connect(dlg.queue_free)


# -------------------------------------------------------------- inspector
func _on_node_selected(id: String, type: String) -> void:
	if type == "note":
		open_note(id)
	elif type == "space":
		_toggle_space(id.trim_prefix("space:"))
	elif type == "tag":
		search_edit.text = id.trim_prefix("tag:")
		_on_search_changed(search_edit.text)


func open_note(id: String, focus: bool = false) -> void:
	if id.strip_edges() == "":
		return
	if not current_note.is_empty() and _save_timer.time_left > 0.0:
		_save_timer.stop()
		await _save_note()
	var res := await app.backend.api.call_api("/brain/notes/" + id.uri_encode())
	if not res["ok"] or not (res["data"] as Dictionary).has("title"):
		return
	current_note = res["data"]
	app.state["selected_note"] = id
	_loading_note = true
	title_edit.text = str(current_note["title"])
	body_edit.text = str(current_note["body"])
	_select_option(space_option, str(current_note["space_id"]))
	_select_option(kind_option, str(current_note["kind"]))
	_loading_note = false
	save_label.text = I18n.t("Edited %s") % SbFormat.local_time(current_note["updated_at"], true)
	_render_links()
	_load_related(id)
	_show_doc_buttons(id)
	graph.select(id)
	if focus:
		graph.focus_on(id)
	if not inspector.visible:
		(inspector as SbFloatingPanel).reveal()
		var glide := panel_layer.animate
		panel_layer.animate = false
		panel_layer.relayout()  # its place first, at once: the slide-in starts from there, not from the corner
		panel_layer.animate = glide
		inspector.modulate.a = 0.0
		inspector.position.x += 30
		var tw := create_tween().set_parallel()
		tw.tween_property(inspector, "modulate:a", 1.0, 0.25)
		tw.tween_property(inspector, "position:x", inspector.position.x - 30, 0.3).set_trans(Tween.TRANS_CUBIC)


func _show_doc_buttons(id: String) -> void:
	doc_row.visible = false
	var res := await app.backend.api.call_api("/brain/items/" + id)
	if res["ok"] and str(current_note.get("id", "")) == id:
		var src: Variant = (res["data"] as Dictionary).get("source")
		doc_row.visible = src is Dictionary and (src as Dictionary).get("original") != null


func _render_links() -> void:
	for c in links_box.get_children():
		c.queue_free()
	var out: Array = current_note.get("links_out", [])
	var inc: Array = current_note.get("links_in", [])
	var tags: Array = current_note.get("tags", [])
	if out.is_empty() and inc.is_empty() and tags.is_empty():
		var l := Label.new()
		l.theme_type_variation = "Muted"
		l.text = I18n.t("No connections yet.")
		links_box.add_child(l)
	for pair in [[out, "→ "], [inc, "← "]]:
		for item in pair[0]:
			var n: Dictionary = item
			var b := Button.new()
			b.theme_type_variation = "GhostButton"
			b.alignment = HORIZONTAL_ALIGNMENT_LEFT
			b.text = str(pair[1]) + str(n["title"])
			b.tooltip_text = str(n["title"])
			_trim_button(b)
			var nid := str(n["id"])
			b.pressed.connect(func() -> void: open_note(nid, true))
			links_box.add_child(b)
	if not tags.is_empty():
		var t := Label.new()
		t.theme_type_variation = "Muted"
		t.text = "  ".join(tags.map(func(x: Variant) -> String: return "#" + str(x)))
		links_box.add_child(t)


## A button whose long label would widen the inspector past the screen edge: one line, trimmed with « … ».
func _trim_button(b: Button) -> void:
	b.clip_text = true
	b.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	b.custom_minimum_size.x = 40


## Related ideas come from the meaning index; the section stays hidden when there are none
## (no key, no embeddings model, or nothing close enough).
func _load_related(id: String) -> void:
	for c in related_box.get_children():
		c.queue_free()
	related_label.visible = false
	var res := await app.backend.api.call_api("/brain/notes/" + id.uri_encode() + "/related")
	if not res["ok"] or current_note.is_empty() or str(current_note["id"]) != id:
		return
	var items: Array = (res["data"] as Dictionary).get("related", [])
	related_label.visible = not items.is_empty()
	for item in items:
		var n: Dictionary = item
		var b := Button.new()
		b.theme_type_variation = "GhostButton"
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		b.text = "≈ " + str(n["title"])
		b.tooltip_text = I18n.t("%s · similarity %d%%") % [str(n["title"]), int(round(float(n.get("score", 0.0)) * 100.0))]
		_trim_button(b)
		var nid := str(n["id"])
		b.pressed.connect(func() -> void: open_note(nid, true))
		b.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		var row := HBoxContainer.new()
		related_box.add_child(row)
		row.add_child(b)
		for spec in [["✓", "keep", I18n.t("Keep: make it a real link")], ["✕", "dismiss", I18n.t("Dismiss: never suggest it again")]]:
			var c := Button.new()
			c.text = str(spec[0])
			c.tooltip_text = str(spec[2])
			c.theme_type_variation = "GhostButton"
			var choice := str(spec[1])
			c.pressed.connect(func() -> void: answer_related(id, nid, choice))
			row.add_child(c)


## « garde ce lien » / « enlève cette idée liée »: the suggestion becomes a link, or disappears for good.
func answer_related(a: String, b: String, choice: String) -> void:
	var res := await app.backend.api.call_api("/brain/related/%s/%s/%s" % [a, b, choice], true, HTTPClient.METHOD_POST)
	if res["ok"] and is_inside_tree():
		show_toast(I18n.t("Kept as a link.") if choice == "keep" else I18n.t("Suggestion dismissed."))
		await refresh_graph()
		if not current_note.is_empty() and str(current_note["id"]) == a:
			open_note(a)


## Search on screen: hits light up in the graph and are listed with why they matched.
func show_search(query: String) -> void:
	await set_view("graph")
	search_edit.text = query
	await _on_search_changed(query)


## Double-click an item without a document: edit its title and text right on its card.
func edit_in_card(id: String) -> void:
	if not graph.nodes.has(id) or str((graph.nodes[id] as Dictionary)["type"]) != "note":
		return
	if graph.zoom < GraphView.NEAR:
		graph.zoom_level("read", id)
		await get_tree().create_timer(0.85).timeout
	var res := await app.backend.api.call_api("/brain/notes/" + id)
	if not res["ok"]:
		return
	var n: Dictionary = res["data"]
	if card_editor != null:
		card_editor.queue_free()
	card_editor = PanelContainer.new()
	card_editor.theme_type_variation = "Glass"
	var center := graph.world_to_screen(graph.nodes[id]["pos"] as Vector2)
	var sz := (GraphView.CARD * graph.zoom).clamp(Vector2(420, 280), Vector2(760, 560))
	card_editor.position = (center - sz * 0.5).clamp(Vector2(380, 90), size - sz - Vector2(24, 110))
	card_editor.size = sz
	add_child(card_editor)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 8)
	card_editor.add_child(col)
	var t := LineEdit.new()
	t.text = str(n.get("title", ""))
	col.add_child(t)
	var body := TextEdit.new()
	body.text = str(n.get("body", ""))
	body.wrap_mode = TextEdit.LINE_WRAPPING_BOUNDARY
	body.size_flags_vertical = Control.SIZE_EXPAND_FILL
	col.add_child(body)
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_END
	col.add_child(row)
	var cancel := Button.new()
	cancel.text = I18n.t("Cancel")
	cancel.theme_type_variation = "GhostButton"
	cancel.pressed.connect(func() -> void:
		card_editor.queue_free()
		card_editor = null)
	row.add_child(cancel)
	var save := Button.new()
	save.text = I18n.t("Save (Ctrl+Enter)")
	save.theme_type_variation = "PrimaryButton"
	var do_save := func() -> void:
		var r := await _post("/brain/notes/" + id, {"title": t.text.strip_edges(), "body": body.text}, HTTPClient.METHOD_PATCH)
		if r["ok"]:
			show_toast(I18n.t("Saved in its card."))
			if card_editor != null:
				card_editor.queue_free()
				card_editor = null
			await refresh_graph()
	save.pressed.connect(do_save)
	row.add_child(save)
	body.gui_input.connect(func(e: InputEvent) -> void:
		if e is InputEventKey and (e as InputEventKey).pressed and (e as InputEventKey).keycode == KEY_ENTER and (e as InputEventKey).ctrl_pressed:
			do_save.call()
			body.accept_event()
		elif e is InputEventKey and (e as InputEventKey).pressed and (e as InputEventKey).keycode == KEY_ESCAPE:
			cancel.pressed.emit())
	body.grab_focus()


func _rebuild_space_option() -> void:
	space_option.clear()
	for item in spaces:
		var s: Dictionary = item
		space_option.add_item(str(s["name"]))
		space_option.set_item_metadata(space_option.item_count - 1, str(s["id"]))
	if not current_note.is_empty():
		_select_option(space_option, str(current_note["space_id"]))


func _select_option(opt: OptionButton, value: String) -> void:
	for i in opt.item_count:
		if str(opt.get_item_metadata(i)) == value:
			opt.select(i)
			return


func _queue_save(now: bool = false) -> void:
	if _loading_note or current_note.is_empty():
		return
	save_label.text = I18n.t("Saving…")
	if now:
		_save_timer.stop()
		_save_note()
	else:
		_save_timer.start()


func _save_note() -> void:
	if current_note.is_empty():
		return
	var title := title_edit.text.strip_edges()
	if title == "":
		save_label.text = I18n.t("A title is needed")
		return
	var payload := {"title": title, "body": body_edit.text,
		"space_id": str(space_option.get_item_metadata(space_option.selected)) if space_option.selected >= 0 else null,
		"kind": str(kind_option.get_item_metadata(kind_option.selected))}
	var before_links: int = (current_note.get("links_out", []) as Array).size()
	var res := await _post("/brain/notes/" + str(current_note["id"]), payload, HTTPClient.METHOD_PATCH)
	if not res["ok"]:
		save_label.text = I18n.t("Not saved: %s") % res["error"]
		app.audio.play("error")
		return
	current_note = res["data"]
	save_label.text = I18n.t("Saved %s") % Time.get_time_string_from_system()
	_render_links()
	if (current_note.get("links_out", []) as Array).size() > before_links:
		app.audio.play("node_link", 0.05)
	await refresh_graph()
	await refresh_spaces()


func _delete_note() -> void:
	if current_note.is_empty():
		return
	var id := str(current_note["id"])
	var res := await app.backend.api.call_api("/brain/notes/" + id, true, HTTPClient.METHOD_DELETE)
	if res["ok"]:
		app.audio.play("whoosh")
		_close_inspector()
		await refresh_graph()
		await refresh_spaces()


func _close_inspector() -> void:
	if _save_timer.time_left > 0.0:
		_save_timer.stop()
		_save_note()
	current_note = {}
	app.state.erase("selected_note")
	inspector.visible = false
	graph.select("")


# ----------------------------------------------------------------- search
func _render_results(query: String, hits: Array) -> void:
	if results_box == null:
		var panel := PanelContainer.new()
		panel.theme_type_variation = "Glass"
		panel.set_anchors_preset(Control.PRESET_TOP_LEFT)
		panel.position = Vector2(388, 140)
		panel.custom_minimum_size = Vector2(330, 0)
		add_child(panel)
		results_box = VBoxContainer.new()
		results_box.add_theme_constant_override("separation", 2)
		panel.add_child(results_box)
	for c in results_box.get_children():
		c.queue_free()
	var panel_node := results_box.get_parent() as Control
	panel_node.visible = query != "" and view == "graph"
	var head := Label.new()
	head.theme_type_variation = "Overline"
	head.text = (I18n.t("%d RESULT FOR “%s”") if hits.size() == 1 else I18n.t("%d RESULTS FOR “%s”")) % [hits.size(), query.to_upper()]
	results_box.add_child(head)
	for h in hits.slice(0, 8):
		var hd: Dictionary = h
		var b := Button.new()
		b.theme_type_variation = "GhostButton"
		b.alignment = HORIZONTAL_ALIGNMENT_LEFT
		var why := (I18n.t("by meaning · %d%%") % int(round(float(hd.get("score", 0.0)) * 100.0))) if str(hd.get("match", "")) == "meaning" else I18n.t("by words")
		b.text = "%s   —  %s" % [str(hd.get("title", "")), why]
		b.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		b.custom_minimum_size = Vector2(320, 0)
		var hid := str(hd.get("id", ""))
		b.pressed.connect(func() -> void:
			graph.zoom_level("read", hid)
			graph.select(hid))
		results_box.add_child(b)


func _on_search_changed(q: String) -> void:
	var query := q.strip_edges()
	if query == "":
		graph.set_highlight([])
		last_hits = []
		if results_box != null:
			(results_box.get_parent() as Control).visible = false
		return
	var res := await app.backend.api.call_api("/brain/search?q=" + query.uri_encode())
	if not res["ok"] or search_edit.text.strip_edges() != query:
		return
	var data: Dictionary = res["data"]
	var hits: Array = data.get("results", [])
	last_hits = hits
	_render_results(query, hits)
	var ids: Array = hits.map(func(h: Variant) -> String: return str((h as Dictionary)["id"]))
	if query.begins_with("#") or graph.nodes.has("tag:" + query.to_lower()):
		ids.append("tag:" + query.trim_prefix("#").to_lower())
	graph.set_highlight(ids if not ids.is_empty() else ["-none-"])


func _open_first_hit() -> void:
	for id in graph.highlight:
		if graph.nodes.has(id) and str((graph.nodes[id] as Dictionary)["type"]) == "note":
			open_note(str(id), true)
			return


func _unhandled_key_input(event: InputEvent) -> void:
	var k := event as InputEventKey
	if k == null:
		return
	if k.keycode == PTT_KEY and not k.echo:
		if app.live.active:
			if k.pressed:
				app.live.barge_in()
		else:
			push_to_talk(k.pressed)
		accept_event()
		return
	if not k.pressed:
		return
	if view == "graph" and not k.ctrl_pressed and (k.keycode in [KEY_EQUAL, KEY_PLUS, KEY_KP_ADD, KEY_MINUS, KEY_KP_SUBTRACT, KEY_0, KEY_KP_0]) \
			and not (get_viewport().gui_get_focus_owner() is LineEdit or get_viewport().gui_get_focus_owner() is TextEdit):
		var lvl: String = str({KEY_EQUAL: "closer", KEY_PLUS: "closer", KEY_KP_ADD: "closer", KEY_MINUS: "out", KEY_KP_SUBTRACT: "out"}.get(k.keycode, "overview"))
		graph.zoom_level(lvl, graph.selected if lvl == "closer" else "")
		accept_event()
	elif k.keycode == KEY_V and k.ctrl_pressed and k.shift_pressed:
		# Ctrl+Shift+V: whatever is in the clipboard (a link, a text) goes straight to the archivist.
		run_ui_actions([{"action": "capture_clipboard"}])
		accept_event()
	elif k.keycode == KEY_SPACE and k.ctrl_pressed:
		capture_edit.grab_focus()
		accept_event()
	elif k.keycode == KEY_SLASH and not k.ctrl_pressed:
		search_edit.grab_focus()
		accept_event()
	elif k.keycode == KEY_M and k.ctrl_pressed:
		toggle_voice()
		accept_event()
	elif k.ctrl_pressed and k.keycode >= KEY_1 and k.keycode <= KEY_9:
		toggle_panel(int(k.keycode - KEY_1))
		accept_event()
	elif k.keycode == KEY_TAB and not k.ctrl_pressed and view == "graph" \
			and not (get_viewport().gui_get_focus_owner() is LineEdit or get_viewport().gui_get_focus_owner() is TextEdit):
		toggle_focus_mode()
		accept_event()
	elif k.keycode == KEY_ESCAPE:
		graph.select("")
		if path_active:
			graph.clear_path()
			path_active = false
		_close_inspector()
		accept_event()


# ------------------------------------------------------------------ voice
func toggle_voice(target: String = "capture") -> void:
	if app.live.active:
		return  # the live conversation owns the microphone
	match voice_state:
		"idle":
			voice_target = target
			var res := await app.backend.api.call_api("/voice/status")
			var st: Dictionary = res["data"] if res["ok"] else {}
			if not bool(st.get("configured", false)) and OS.get_environment("SBGD_VOICE_PROVIDER") != "fake":
				_open_voice_settings()
				return
			start_voice(true)
		"listening":
			stop_voice()


## use_mic = false lets tests push audio with voice_capture.feed_frames().
func start_voice(use_mic: bool) -> bool:
	if voice_state != "idle":
		return false
	voice_state = "connecting"
	voice_text = ""
	_voice_final = ""
	_voice_error = ""
	capture_hint.text = I18n.t("Connecting to voice…")
	var err := voice_stream.connect_to(app.backend.api.port, app.backend.api.token)
	if err != OK:
		_voice_fail(I18n.t("Cannot open the voice connection (%s).") % error_string(err))
		return false
	var deadline := Time.get_ticks_msec() + 10000
	while voice_stream._open == false and _voice_error == "" and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	if not voice_stream._open:
		_voice_fail(_voice_error if _voice_error != "" else I18n.t("Voice service did not answer."))
		return false
	if use_mic:
		voice_capture.start()
	else:
		voice_capture.recording = false
	voice_state = "listening"
	app.audio.play("mic_start")
	capture_edit.text = ""
	capture_edit.editable = false
	capture_edit.placeholder_text = I18n.t("Listening…  speak, then release F8") if ptt_active else I18n.t("Listening…  speak, then click the microphone again")
	var who := I18n.t("Sparring") if active_agent == "sparring" else I18n.t("the archivist")
	capture_hint.text = (I18n.t("Listening for %s · release F8 to send") % who if ptt_active else I18n.t("Listening for %s · click the mic to finish") % who) if voice_target == "chat" \
		else I18n.t("Listening · Ctrl+M or click the mic to finish")
	return true


func stop_voice() -> void:
	if voice_state != "listening":
		return
	voice_state = "finishing"
	if voice_capture.recording:
		voice_capture.stop()
	else:
		voice_capture._flush()
	await get_tree().process_frame
	voice_stream.commit()
	app.audio.play("mic_stop")
	capture_hint.text = I18n.t("Transcribing…")
	var deadline := Time.get_ticks_msec() + 20000
	while _voice_final == "" and _voice_error == "" and Time.get_ticks_msec() < deadline:
		await get_tree().process_frame
	voice_stream.stop()
	capture_edit.editable = true
	capture_edit.placeholder_text = I18n.t("Type, paste a link…   (Enter · Ctrl+Shift+V adds the clipboard · F8 to speak)")
	voice_state = "idle"
	var text := _voice_final.strip_edges()
	if text == "":
		_voice_fail(_voice_error if _voice_error != "" else I18n.t("No speech was transcribed."))
		return
	capture_edit.text = ""
	if voice_target == "chat":
		voice_target = "capture"
		await chat_panel().send(text, true)
	else:
		await capture(text, "voice")


func _on_voice_delta(text: String) -> void:
	voice_text += text
	capture_edit.text = voice_text
	capture_edit.caret_column = capture_edit.text.length()


func _on_live_text(text: String, role: String) -> void:
	var who := str(app.live.agent)
	if agent_panel(who) != null:
		agent_panel(who).reveal()
	chat_panel(who).add_live(role, text)


func _on_live_finished(reason: String) -> void:
	if reason == "error":
		capture_hint.text = app.live.last_error
	else:
		capture_hint.text = LiveConversation.ending_text(reason)
	if reason != "error":
		refresh_graph()
		_refresh_view()


## F9 or the Live button: start or end a spoken conversation with the assistant.
func toggle_live() -> void:
	if app.live.active:
		app.live.stop("user")
		return
	var res := await app.backend.api.call_api("/voice/status")
	var st: Dictionary = res["data"] if res["ok"] else {}
	if not bool(st.get("configured", false)) and OS.get_environment("SBGD_VOICE_PROVIDER") != "fake":
		_open_voice_settings()
		return
	if voice_state != "idle":
		return
	agent_panel().reveal()
	app.live.agent = active_agent
	app.live.start(true)


func _voice_fail(msg: String) -> void:
	if voice_capture.recording:
		voice_capture.stop()
	voice_stream.stop()
	voice_state = "idle"
	capture_edit.editable = true
	capture_hint.text = msg
	app.audio.play("error")


func _open_voice_settings() -> void:
	var dlg := AcceptDialog.new()
	dlg.title = I18n.t("Voice capture")
	dlg.ok_button_text = I18n.t("Close")
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(560, 0)
	dlg.add_child(box)
	var intro := Label.new()
	intro.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	intro.text = I18n.t("Voice capture uses OpenAI realtime transcription with your own API key.")
	box.add_child(intro)
	var panel := VoiceKeyPanel.new().setup(app, false)
	box.add_child(panel)
	panel.saved.connect(func(st: Dictionary) -> void:
		if bool(st.get("configured", false)):
			capture_hint.text = I18n.t("Voice is ready. Click the microphone and speak."))
	var speed_row := HBoxContainer.new()
	speed_row.add_theme_constant_override("separation", 10)
	box.add_child(speed_row)
	var speed_label := Label.new()
	speed_label.text = I18n.t("Voice speed  %.2f×") % app.audio.voice_speed
	speed_label.custom_minimum_size = Vector2(150, 0)
	speed_row.add_child(speed_label)
	var speed := HSlider.new()
	speed.min_value = SbAudio.VOICE_SPEED_MIN
	speed.max_value = SbAudio.VOICE_SPEED_MAX
	speed.step = 0.05
	speed.value = app.audio.voice_speed
	speed.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	speed.value_changed.connect(func(v: float) -> void:
		app.audio.set_voice_speed(v)
		speed_label.text = I18n.t("Voice speed  %.2f×") % app.audio.voice_speed)
	speed_row.add_child(speed)
	var phones := CheckButton.new()
	phones.text = I18n.t("I use headphones (in a live conversation, just talk over the assistant to interrupt it)")
	phones.button_pressed = bool(SbSettings.get_value("voice", "headphones", false))
	phones.toggled.connect(func(on: bool) -> void: SbSettings.set_value("voice", "headphones", on))
	box.add_child(phones)
	var live_note := Label.new()
	live_note.theme_type_variation = "Muted"
	live_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	live_note.text = I18n.t("Live conversation (F9): speech to speech with OpenAI Realtime. With speakers, the microphone pauses while the assistant talks so it never hears itself; press F8 to interrupt it.")
	box.add_child(live_note)
	add_child(dlg)
	dlg.popup_centered()
	dlg.confirmed.connect(dlg.queue_free)
	dlg.canceled.connect(dlg.queue_free)


class _MicRing:
	extends Control
	## Pulsing ring around the mic button while listening, driven by the input level.
	var brain: Node
	var _t := 0.0

	func _ready() -> void:
		mouse_filter = Control.MOUSE_FILTER_IGNORE

	func _process(delta: float) -> void:
		_t += delta
		queue_redraw()

	func _draw() -> void:
		var state := str(brain.get("voice_state"))
		if state == "idle":
			return
		var c := size * 0.5
		var r := minf(size.x, size.y) * 0.5
		var lvl: float = brain.get("voice_level")
		if state == "listening":
			draw_circle(c, r + 4.0 + lvl * 16.0, Color(SbTheme.MINT, 0.18 + lvl * 0.3))
			draw_arc(c, r + 3.0, 0, TAU, 48, SbTheme.MINT, 2.0, true)
		else:
			draw_arc(c, r + 3.0, _t * 4.0, _t * 4.0 + PI * 1.2, 32, SbTheme.INFO, 2.5, true)


# ------------------------------------------------------------ saved views (VIEW-B)
## Saves what the graph shows now (its view, its filters, where you look) under a name.
func save_graph_view(view_name: String) -> void:
	GraphFilters.store_view({"name": view_name, "layout": filters_bar.view(), "filter": filters_bar.filter.duplicate(true),
		"center": graph.view_center(), "zoom": graph.zoom, "focus": graph.focus_id if graph.graph_layout == "focus" else "",
		"lanes": graph.timeline_lanes})


## Opens a saved view: its filters, its layout, then the camera glides to where it was.
func open_graph_view(view: Dictionary) -> void:
	filters_bar.apply((view.get("filter", {}) as Dictionary).duplicate(true))
	if str(view.get("layout", "")) == "focus":  # the focus view opens around the item it was saved on
		graph.select("")
		graph.focus_id = str(view.get("focus", ""))
	filters_bar.set_lanes(str(view.get("lanes", "place")))
	filters_bar.set_view(str(view.get("layout", "zones")))
	graph.follow = ""
	var center: Variant = view.get("center", null)
	graph.zoom_to(float(view.get("zoom", 1.0)), center if center is Vector2 else null, 0.9)


## Asks the engine where each item sits by meaning (VIEW-E) and gives it to the graph; false when there is no map.
func load_meaning_map() -> bool:
	var res: Dictionary = await app.backend.api.call_api("/brain/meaning/map")
	if not res["ok"] or not is_inside_tree():
		return false
	graph.set_meaning_points((res["data"] as Dictionary).get("points", {}))
	return not graph.meaning_points.is_empty()


## The 3D layers follow the graph: its filters, its time cursor, its new items.
func _refresh_layers() -> void:
	if layers_view != null and layers_view.visible:
		layers_view.show_graph(graph)

