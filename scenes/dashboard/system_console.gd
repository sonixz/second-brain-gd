extends Control
## System Console: live, measured state of the local engine. Every value comes
## from the API or from Godot itself; anything missing shows "Not available".

const HEALTH_EVERY := 3.0
const STATUS_EVERY := 5.0
const STORAGE_EVERY := 15.0

var app: SbApp
var api_card: InfoCard
var db_card: InfoCard
var py_card: InfoCard
var storage_card: InfoCard
var proc_card: InfoCard
var voice_card: InfoCard
var sources_card: InfoCard
var billing_panel: BillingPanel
var last_voice: Dictionary = {}
var events_view: RichTextLabel
var header_dot: StatusDot
var header_state: Label
var last_check_label: Label
var restart_button: Button
var last_health: Dictionary = {}
var last_health_at := ""
var last_health_ms := 0
var last_status: Dictionary = {}
var last_storage: Dictionary = {}
var last_events: Array = []
var health_ok := false
var refresh_count := 0
var _busy := {}


func bind(a: SbApp) -> void:
	app = a


func _ready() -> void:
	app.backend.load_runtime()
	var margin := MarginContainer.new()
	margin.set_anchors_preset(Control.PRESET_FULL_RECT)
	for side in ["left", "right"]:
		margin.add_theme_constant_override("margin_" + side, 36)
	margin.add_theme_constant_override("margin_top", 26)
	margin.add_theme_constant_override("margin_bottom", 24)
	add_child(margin)
	var col := VBoxContainer.new()
	col.add_theme_constant_override("separation", 16)
	margin.add_child(col)

	var head := HBoxContainer.new()
	head.add_theme_constant_override("separation", 14)
	col.add_child(head)
	var logo := BrainLogo.new()
	logo.custom_minimum_size = Vector2(46, 46)
	head.add_child(logo)
	var htext := VBoxContainer.new()
	htext.add_theme_constant_override("separation", 0)
	htext.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	head.add_child(htext)
	var over := Label.new()
	over.text = I18n.t("SECOND BRAIN GD · TRANSPARENCY")
	over.theme_type_variation = "Overline"
	htext.add_child(over)
	var title := Label.new()
	title.text = I18n.t("Engine Room · System Console")
	title.theme_type_variation = "Heading"
	title.add_theme_font_size_override("font_size", SbTheme.fs(24))
	htext.add_child(title)
	var pill := PanelContainer.new()
	pill.theme_type_variation = "Inset"
	pill.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	head.add_child(pill)
	var prow := HBoxContainer.new()
	prow.add_theme_constant_override("separation", 8)
	pill.add_child(prow)
	header_dot = StatusDot.new()
	header_dot.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	prow.add_child(header_dot)
	header_state = Label.new()
	header_state.text = I18n.t("Connecting…")
	prow.add_child(header_state)
	last_check_label = Label.new()
	last_check_label.theme_type_variation = "Muted"
	last_check_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	head.add_child(last_check_label)
	var back := Button.new()
	back.text = I18n.t("← Back to your brain")
	back.theme_type_variation = "PrimaryButton"
	back.custom_minimum_size = Vector2(0, 44)
	back.pressed.connect(func() -> void: app.show_brain())
	head.add_child(back)
	var refresh := Button.new()
	refresh.text = I18n.t("Refresh")
	refresh.pressed.connect(func() -> void: refresh_all())
	head.add_child(refresh)
	restart_button = Button.new()
	restart_button.text = I18n.t("Restart engine")
	restart_button.visible = false
	restart_button.pressed.connect(func() -> void: app.start_setup())
	head.add_child(restart_button)

	var scroll := ScrollContainer.new()
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	col.add_child(scroll)
	var body := VBoxContainer.new()
	body.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	body.add_theme_constant_override("separation", 16)
	scroll.add_child(body)

	var grid := GridContainer.new()
	grid.columns = 3
	grid.add_theme_constant_override("h_separation", 16)
	grid.add_theme_constant_override("v_separation", 16)
	body.add_child(grid)
	api_card = InfoCard.new().setup(I18n.t("Local API"))
	db_card = InfoCard.new().setup(I18n.t("Database"))
	py_card = InfoCard.new().setup(I18n.t("Python environment"))
	storage_card = InfoCard.new().setup(I18n.t("Storage"))
	proc_card = InfoCard.new().setup(I18n.t("Processes"))
	for c in [api_card, db_card, py_card, storage_card, proc_card]:
		grid.add_child(c)
	var about := InfoCard.new().setup(I18n.t("Installation"))
	about.name = "InstallCard"
	grid.add_child(about)
	voice_card = InfoCard.new().setup(I18n.t("Voice capture"))
	grid.add_child(voice_card)
	sources_card = InfoCard.new().setup(I18n.t("Sources & memory"))
	grid.add_child(sources_card)

	# Your data: backups, export, packs, repair, start fresh, uninstall. Loaded by path, not by its class name:
	# running from the source without the editor, Godot's class list can lag behind a new class (2026-11-05).
	body.add_child(preload("res://scenes/dashboard/data_panel.gd").new().setup(app))

	# Missions (Loop 35): what they did and cost, « Run again ».
	body.add_child(preload("res://scenes/dashboard/missions_panel.gd").new().setup(app))

	billing_panel = BillingPanel.new().setup(app)
	billing_panel.name = "BillingPanel"
	body.add_child(billing_panel)

	var ev_card := PanelContainer.new()
	ev_card.theme_type_variation = "Card"
	body.add_child(ev_card)
	var ecol := VBoxContainer.new()
	ecol.add_theme_constant_override("separation", 8)
	ev_card.add_child(ecol)
	var etitle := Label.new()
	etitle.text = I18n.t("Recent operations")
	etitle.theme_type_variation = "Heading"
	etitle.add_theme_font_size_override("font_size", SbTheme.fs(16))
	ecol.add_child(etitle)
	events_view = RichTextLabel.new()
	events_view.bbcode_enabled = true
	events_view.fit_content = true
	events_view.selection_enabled = true
	ecol.add_child(events_view)

	_render()
	refresh_all()
	_every(HEALTH_EVERY, _poll_health)
	_every(STATUS_EVERY, _poll_status)
	_every(STATUS_EVERY, _poll_events)
	_every(STORAGE_EVERY, _poll_storage)
	_every(1.0, _render_process_only)


func _every(seconds: float, fn: Callable) -> void:
	var t := Timer.new()
	t.wait_time = seconds
	t.autostart = true
	t.timeout.connect(fn)
	add_child(t)


func refresh_all() -> void:
	await _poll_health()
	await _poll_status()
	await _poll_storage()
	await _poll_events()
	await _poll_voice()
	await _poll_sources()
	refresh_count += 1


func _guard(key: String) -> bool:
	if _busy.get(key, false):
		return false
	_busy[key] = true
	return true


func _poll_health() -> void:
	if not _guard("health"):
		return
	var res := await app.backend.api.call_api("/health", false)
	_busy["health"] = false
	last_health_at = Time.get_time_string_from_system()
	last_health_ms = int(res["ms"])
	var data: Dictionary = res["data"]
	health_ok = bool(res["ok"]) and str(data.get("status", "")) == "ok"
	last_health = data if res["ok"] else {"error": res["error"]}
	_render()


func _poll_status() -> void:
	if not _guard("status"):
		return
	var res := await app.backend.api.call_api("/system/status")
	_busy["status"] = false
	if res["ok"]:
		last_status = res["data"]
	_render()


func _poll_storage() -> void:
	if not _guard("storage"):
		return
	var res := await app.backend.api.call_api("/system/storage")
	_busy["storage"] = false
	if res["ok"]:
		last_storage = res["data"]
	_render()


func _poll_voice() -> void:
	var res := await app.backend.api.call_api("/voice/status")
	if not is_inside_tree() or voice_card == null:
		return
	if not res["ok"]:
		voice_card.set_state("error" if not last_health.is_empty() else "checking", I18n.t("No data"))
		return
	last_voice = res["data"]
	var v := last_voice
	var sources := {"keyring": I18n.t("System credential store"), "file": I18n.t("Private file (no credential store)"),
		"env": I18n.t("Environment variable (dev)"), "none": I18n.t("Not configured")}
	if bool(v.get("configured", false)):
		voice_card.set_state("ok", I18n.t("Ready"))
	else:
		voice_card.set_state("pending", I18n.t("No API key"))
	voice_card.set_rows([
		[I18n.t("Provider"), I18n.t("OpenAI realtime")],
		[I18n.t("Model"), str(v.get("model", SbFormat.na()))],
		[I18n.t("Key"), str(v.get("hint", "")) if bool(v.get("configured", false)) else SbFormat.na()],
		[I18n.t("Stored in"), str(sources.get(str(v.get("source", "none")), "?"))],
		[I18n.t("Backend"), str(v.get("backend", SbFormat.na()))],
		[I18n.t("List price"), I18n.t("$%s / min of audio") % str(v.get("price_per_minute_usd", "?"))],
	])
	voice_card.set_footer(I18n.t("The key never reaches Godot, logs or the database."))


func _poll_sources() -> void:
	var res := await app.backend.api.call_api("/sources")
	if not is_inside_tree() or sources_card == null or not res["ok"]:
		return
	var d: Dictionary = res["data"]
	var list: Array = d.get("sources", [])
	var emb: Dictionary = d.get("embeddings", {})
	var chunks := 0
	for item in list:
		chunks += int((item as Dictionary).get("chunks", 0))
	var mres := await app.backend.api.call_api("/brain/meaning/status")
	if not is_inside_tree():
		return
	var m: Dictionary = mres["data"] if mres["ok"] else {}
	var avail: Variant = emb.get("available")
	if avail == null and m.has("embeddings"):
		emb = m["embeddings"]
		avail = emb.get("available")
	if avail == true:
		sources_card.set_state("ok", I18n.t("Search by meaning"))
	elif avail == false:
		sources_card.set_state("warning", I18n.t("Words only"))
	else:
		sources_card.set_state("pending", I18n.t("No sources yet"))
	sources_card.set_rows([
		[I18n.t("Sources"), SbFormat.number(list.size())],
		[I18n.t("Passages indexed"), SbFormat.number(chunks)],
		[I18n.t("Notes by meaning"), (I18n.t("%s of %s") % [SbFormat.number(m.get("embedded", 0)), SbFormat.number(m.get("notes", 0))]) if not m.is_empty() else SbFormat.na()],
		[I18n.t("Related idea pairs"), SbFormat.number(m.get("related_pairs", 0)) if not m.is_empty() else SbFormat.na()],
		[I18n.t("Embeddings model"), str(emb.get("model", "text-embedding-3-small"))],
		[I18n.t("Embeddings"), I18n.t("available") if avail == true else (I18n.t("unavailable: %s") % str(emb.get("error", "")).left(70) if avail == false else SbFormat.na())],
		[I18n.t("Formats"), I18n.t("PDF, Word, Markdown, text, HTML, web links")],
	])


func _poll_events() -> void:
	if not _guard("events"):
		return
	var res := await app.backend.api.call_api("/system/events?limit=40")
	_busy["events"] = false
	if res["ok"]:
		var data: Dictionary = res["data"]
		last_events = data.get("events", [])
	_render_events()


func _render() -> void:
	if not is_inside_tree():
		return
	var na := SbFormat.na()
	if last_health.is_empty():
		header_dot.set_status("checking")
		header_state.text = I18n.t("Connecting…")
	elif health_ok:
		header_dot.set_status("ok")
		header_state.text = I18n.t("All systems operational")
	else:
		header_dot.set_status("error")
		header_state.text = I18n.t("Engine unreachable") if last_health.has("error") else I18n.t("Engine degraded")
	restart_button.visible = not health_ok and not last_health.is_empty()
	last_check_label.text = I18n.t("Last health check %s") % (last_health_at if last_health_at != "" else "—")

	# API
	var api: Dictionary = last_status.get("api", {})
	if health_ok:
		api_card.set_state("ok", I18n.t("Healthy"))
	elif last_health.is_empty():
		api_card.set_state("checking", I18n.t("Checking"))
	else:
		api_card.set_state("error", str(last_health.get("error", I18n.t("Degraded"))))
	api_card.set_rows([
		[I18n.t("Address"), "http://127.0.0.1:%d" % app.backend.api.port if app.backend.api.port > 0 else na],
		["/health", "%s · %d ms" % [str(last_health.get("status", last_health.get("error", "—"))), last_health_ms] if not last_health.is_empty() else na],
		[I18n.t("Last check"), last_health_at if last_health_at != "" else na],
		[I18n.t("Uptime"), SbFormat.duration(last_health.get("uptime_s"))],
		[I18n.t("Started"), SbFormat.local_time(api.get("started_at"), true)],
		[I18n.t("Version"), str(last_health.get("version", na))],
		[I18n.t("Auth"), I18n.t("Bearer token (local)") if app.backend.api.token != "" else I18n.t("No token found")],
	])

	# Database
	var db: Dictionary = last_status.get("database", {})
	var storage_entries: Dictionary = last_storage.get("entries", {})
	var db_entry: Dictionary = storage_entries.get("database", {})
	var db_status := str(db.get("status", last_health.get("database", "")))
	if not health_ok and not last_status.is_empty():
		db_card.set_state("warning", I18n.t("Last known · engine offline"))
	elif db_status == "ok":
		db_card.set_state("ok", I18n.t("Connected"))
	elif db_status == "":
		db_card.set_state("checking", I18n.t("Checking"))
	else:
		db_card.set_state("error", db_status)
	db_card.set_rows([
		[I18n.t("Engine"), "SQLite (WAL)"],
		[I18n.t("Schema version"), SbFormat.value_or_na(db.get("schema_version"))],
		[I18n.t("Size"), SbFormat.bytes(db_entry.get("bytes"))],
		[I18n.t("Installed"), SbFormat.local_time(db.get("installed_at"), true)],
		[I18n.t("File"), str(db.get("path", na))],
	])

	# Python
	var py: Dictionary = last_status.get("python", {})
	var plat: Dictionary = last_status.get("platform", {})
	if not health_ok and not py.is_empty():
		py_card.set_state("warning", I18n.t("Last known · engine offline"))
	elif py.is_empty():
		py_card.set_state("checking" if last_health.is_empty() else "error", I18n.t("Checking") if last_health.is_empty() else I18n.t("No data"))
	else:
		py_card.set_state("ok" if bool(py.get("in_venv", false)) else "warning",
			I18n.t("Isolated venv") if bool(py.get("in_venv", false)) else I18n.t("Not in a venv"))
	py_card.set_rows([
		["Python", SbFormat.value_or_na(py.get("version"))],
		[I18n.t("Implementation"), SbFormat.value_or_na(py.get("implementation"))],
		[I18n.t("Virtual env"), SbFormat.value_or_na(py.get("prefix"))],
		[I18n.t("Base interpreter"), SbFormat.value_or_na(py.get("base_prefix"))],
		[I18n.t("Platform"), "%s %s %s" % [plat.get("system", ""), plat.get("release", ""), plat.get("machine", "")] if not plat.is_empty() else na],
	])

	# Storage
	var disk: Dictionary = last_storage.get("disk", {})
	if last_storage.is_empty():
		storage_card.set_state("checking", I18n.t("Checking"))
	elif not health_ok:
		storage_card.set_state("warning", I18n.t("Last known · engine offline"))
	else:
		var free: Variant = disk.get("free_bytes")
		var total: Variant = disk.get("total_bytes")
		var low := free != null and total != null and float(free) / maxf(1.0, float(total)) < 0.05
		storage_card.set_state("warning" if low else "ok", I18n.t("Low disk space") if low else "OK")
	var srows: Array = [[I18n.t("Data folder"), str(last_storage.get("data_dir", app.backend.data_dir))]]
	var entry_names := {"database": I18n.t("Database"), "notes": I18n.t("Notes"), "logs": I18n.t("Logs"), "venv": I18n.t("Venv")}
	for key in ["database", "notes", "logs", "venv"]:
		var e: Dictionary = storage_entries.get(key, {})
		srows.append([entry_names[key], (I18n.t("%s · %s file") if int(e.get("files", 0)) == 1 else I18n.t("%s · %s files")) % [SbFormat.bytes(e.get("bytes")), SbFormat.number(e.get("files", 0))] if not e.is_empty() else na])
	srows.append([I18n.t("Disk free"), I18n.t("%s of %s") % [SbFormat.bytes(disk.get("free_bytes")), SbFormat.bytes(disk.get("total_bytes"))] if disk.get("free_bytes") != null else na])
	storage_card.set_rows(srows)

	_render_process_only()

	# Installation
	var install: Dictionary = last_status.get("install", {})
	var card: InfoCard = find_child("InstallCard", true, false)
	if card != null:
		var steps: Dictionary = install.get("steps", {})
		var ok_steps := 0
		for k in steps:
			var st: Dictionary = steps[k]
			if str(st.get("status", "")) == "ok":
				ok_steps += 1
		if install.is_empty():
			card.set_state("checking", I18n.t("Checking"))
		elif not health_ok:
			card.set_state("warning", I18n.t("Last known · engine offline"))
		else:
			card.set_state("ok" if bool(install.get("installed", false)) else "warning",
				I18n.t("Complete") if bool(install.get("installed", false)) else I18n.t("Incomplete"))
		card.set_rows([
			[I18n.t("Verified steps"), "%d / %d" % [ok_steps, steps.size()] if not steps.is_empty() else na],
			[I18n.t("Last ready"), SbFormat.local_time(install.get("last_success_at"), true)],
			["Godot", str(Engine.get_version_info().get("string", na))],
			["OS", OS.get_name()],
		])


func _render_process_only() -> void:
	if proc_card == null:
		return
	var proc: Dictionary = last_status.get("process", {})
	var sys: Dictionary = last_status.get("system", {})
	if not health_ok and not last_health.is_empty():
		# Live measurements are never shown stale: the API process is not answering.
		proc = {}
		sys = {}
		proc_card.set_state("warning", I18n.t("API not measured · engine offline"))
	elif proc.is_empty():
		proc_card.set_state("checking" if last_health.is_empty() else "error", I18n.t("Checking") if last_health.is_empty() else I18n.t("No data"))
	else:
		proc_card.set_state("ok", I18n.t("Measured"))
	var mem_sys := SbFormat.na()
	if sys.get("memory_total_bytes") != null and sys.get("memory_available_bytes") != null:
		mem_sys = I18n.t("%s free of %s") % [SbFormat.bytes(sys.get("memory_available_bytes")), SbFormat.bytes(sys.get("memory_total_bytes"))]
	proc_card.set_rows([
		[I18n.t("API pid"), SbFormat.value_or_na(proc.get("pid"))],
		[I18n.t("API CPU"), SbFormat.value_or_na(proc.get("cpu_percent"), " %")],
		[I18n.t("API memory (RSS)"), SbFormat.bytes(proc.get("rss_bytes"))],
		[I18n.t("API threads"), SbFormat.value_or_na(proc.get("threads"))],
		[I18n.t("Godot pid"), str(OS.get_process_id())],
		[I18n.t("Godot memory"), SbFormat.bytes(OS.get_static_memory_usage())],
		[I18n.t("Godot FPS"), SbFormat.number(Engine.get_frames_per_second())],
		[I18n.t("System RAM"), mem_sys],
	])


func _render_events() -> void:
	var lines: PackedStringArray = []
	if last_events.is_empty():
		lines.append("[color=#%s]%s[/color]" % [SbTheme.FAINT.to_html(false), I18n.t("No operations recorded yet") if health_ok else SbFormat.na()])
	var shown := 0
	for item in last_events:
		var e: Dictionary = item
		var st := str(e.get("status", ""))
		if st in ["started", "progress"] or shown >= 18:
			continue  # intermediate steps stay in logs/bootstrap.log
		shown += 1
		lines.append("[color=#%s]%s[/color]   [color=#%s]●[/color] [b]%s[/b] [color=#%s]%s[/color]   %s" % [
			SbTheme.FAINT.to_html(false), SbFormat.local_time(e.get("timestamp"), true),
			SbTheme.status_color(st).to_html(false), str(e.get("component", "")),
			SbTheme.MUTED.to_html(false), st, str(e.get("message", "")).replace("[", "[lb]")])
	events_view.text = "\n".join(lines)
