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
	over.text = "SECOND BRAIN GD · TRANSPARENCY"
	over.theme_type_variation = "Overline"
	htext.add_child(over)
	var title := Label.new()
	title.text = "Engine Room · System Console"
	title.theme_type_variation = "Heading"
	title.add_theme_font_size_override("font_size", 24)
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
	header_state.text = "Connecting…"
	prow.add_child(header_state)
	last_check_label = Label.new()
	last_check_label.theme_type_variation = "Muted"
	last_check_label.size_flags_vertical = Control.SIZE_SHRINK_CENTER
	head.add_child(last_check_label)
	var back := Button.new()
	back.text = "← Back to your brain"
	back.theme_type_variation = "PrimaryButton"
	back.custom_minimum_size = Vector2(0, 44)
	back.pressed.connect(func() -> void: app.show_brain())
	head.add_child(back)
	var refresh := Button.new()
	refresh.text = "Refresh"
	refresh.pressed.connect(func() -> void: refresh_all())
	head.add_child(refresh)
	restart_button = Button.new()
	restart_button.text = "Restart engine"
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
	api_card = InfoCard.new().setup("Local API")
	db_card = InfoCard.new().setup("Database")
	py_card = InfoCard.new().setup("Python environment")
	storage_card = InfoCard.new().setup("Storage")
	proc_card = InfoCard.new().setup("Processes")
	for c in [api_card, db_card, py_card, storage_card, proc_card]:
		grid.add_child(c)
	var about := InfoCard.new().setup("Installation")
	about.name = "InstallCard"
	grid.add_child(about)
	voice_card = InfoCard.new().setup("Voice capture")
	grid.add_child(voice_card)

	var ev_card := PanelContainer.new()
	ev_card.theme_type_variation = "Card"
	body.add_child(ev_card)
	var ecol := VBoxContainer.new()
	ecol.add_theme_constant_override("separation", 8)
	ev_card.add_child(ecol)
	var etitle := Label.new()
	etitle.text = "Recent operations"
	etitle.theme_type_variation = "Heading"
	etitle.add_theme_font_size_override("font_size", 16)
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
		voice_card.set_state("error" if not last_health.is_empty() else "checking", "No data")
		return
	last_voice = res["data"]
	var v := last_voice
	var sources := {"keyring": "System credential store", "file": "Private file (no credential store)",
		"env": "Environment variable (dev)", "none": "Not configured"}
	if bool(v.get("configured", false)):
		voice_card.set_state("ok", "Ready")
	else:
		voice_card.set_state("pending", "No API key")
	voice_card.set_rows([
		["Provider", "OpenAI realtime"],
		["Model", str(v.get("model", SbFormat.NA))],
		["Key", str(v.get("hint", "")) if bool(v.get("configured", false)) else SbFormat.NA],
		["Stored in", str(sources.get(str(v.get("source", "none")), "?"))],
		["Backend", str(v.get("backend", SbFormat.NA))],
		["List price", "$%s / min of audio" % str(v.get("price_per_minute_usd", "?"))],
	])
	voice_card.set_footer("The key never reaches Godot, logs or the database.")


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
	var na := SbFormat.NA
	if last_health.is_empty():
		header_dot.set_status("checking")
		header_state.text = "Connecting…"
	elif health_ok:
		header_dot.set_status("ok")
		header_state.text = "All systems operational"
	else:
		header_dot.set_status("error")
		header_state.text = "Engine unreachable" if last_health.has("error") else "Engine degraded"
	restart_button.visible = not health_ok and not last_health.is_empty()
	last_check_label.text = "Last health check %s" % (last_health_at if last_health_at != "" else "—")

	# API
	var api: Dictionary = last_status.get("api", {})
	if health_ok:
		api_card.set_state("ok", "Healthy")
	elif last_health.is_empty():
		api_card.set_state("checking", "Checking")
	else:
		api_card.set_state("error", str(last_health.get("error", "Degraded")))
	api_card.set_rows([
		["Address", "http://127.0.0.1:%d" % app.backend.api.port if app.backend.api.port > 0 else na],
		["/health", "%s · %d ms" % [str(last_health.get("status", last_health.get("error", "—"))), last_health_ms] if not last_health.is_empty() else na],
		["Last check", last_health_at if last_health_at != "" else na],
		["Uptime", SbFormat.duration(last_health.get("uptime_s"))],
		["Started", SbFormat.local_time(api.get("started_at"), true)],
		["Version", str(last_health.get("version", na))],
		["Auth", "Bearer token (local)" if app.backend.api.token != "" else "No token found"],
	])

	# Database
	var db: Dictionary = last_status.get("database", {})
	var storage_entries: Dictionary = last_storage.get("entries", {})
	var db_entry: Dictionary = storage_entries.get("database", {})
	var db_status := str(db.get("status", last_health.get("database", "")))
	if not health_ok and not last_status.is_empty():
		db_card.set_state("warning", "Last known · engine offline")
	elif db_status == "ok":
		db_card.set_state("ok", "Connected")
	elif db_status == "":
		db_card.set_state("checking", "Checking")
	else:
		db_card.set_state("error", db_status)
	db_card.set_rows([
		["Engine", "SQLite (WAL)"],
		["Schema version", SbFormat.value_or_na(db.get("schema_version"))],
		["Size", SbFormat.bytes(db_entry.get("bytes"))],
		["Installed", SbFormat.local_time(db.get("installed_at"), true)],
		["File", str(db.get("path", na))],
	])

	# Python
	var py: Dictionary = last_status.get("python", {})
	var plat: Dictionary = last_status.get("platform", {})
	if not health_ok and not py.is_empty():
		py_card.set_state("warning", "Last known · engine offline")
	elif py.is_empty():
		py_card.set_state("checking" if last_health.is_empty() else "error", "Checking" if last_health.is_empty() else "No data")
	else:
		py_card.set_state("ok" if bool(py.get("in_venv", false)) else "warning",
			"Isolated venv" if bool(py.get("in_venv", false)) else "Not in a venv")
	py_card.set_rows([
		["Python", SbFormat.value_or_na(py.get("version"))],
		["Implementation", SbFormat.value_or_na(py.get("implementation"))],
		["Virtual env", SbFormat.value_or_na(py.get("prefix"))],
		["Base interpreter", SbFormat.value_or_na(py.get("base_prefix"))],
		["Platform", "%s %s %s" % [plat.get("system", ""), plat.get("release", ""), plat.get("machine", "")] if not plat.is_empty() else na],
	])

	# Storage
	var disk: Dictionary = last_storage.get("disk", {})
	if last_storage.is_empty():
		storage_card.set_state("checking", "Checking")
	elif not health_ok:
		storage_card.set_state("warning", "Last known · engine offline")
	else:
		var free: Variant = disk.get("free_bytes")
		var total: Variant = disk.get("total_bytes")
		var low := free != null and total != null and float(free) / maxf(1.0, float(total)) < 0.05
		storage_card.set_state("warning" if low else "ok", "Low disk space" if low else "OK")
	var srows: Array = [["Data folder", str(last_storage.get("data_dir", app.backend.data_dir))]]
	for key in ["database", "notes", "logs", "venv"]:
		var e: Dictionary = storage_entries.get(key, {})
		srows.append([key.capitalize(), "%s · %s files" % [SbFormat.bytes(e.get("bytes")), SbFormat.number(e.get("files", 0))] if not e.is_empty() else na])
	srows.append(["Disk free", "%s of %s" % [SbFormat.bytes(disk.get("free_bytes")), SbFormat.bytes(disk.get("total_bytes"))] if disk.get("free_bytes") != null else na])
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
			card.set_state("checking", "Checking")
		elif not health_ok:
			card.set_state("warning", "Last known · engine offline")
		else:
			card.set_state("ok" if bool(install.get("installed", false)) else "warning",
				"Complete" if bool(install.get("installed", false)) else "Incomplete")
		card.set_rows([
			["Verified steps", "%d / %d" % [ok_steps, steps.size()] if not steps.is_empty() else na],
			["Last ready", SbFormat.local_time(install.get("last_success_at"), true)],
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
		proc_card.set_state("warning", "API not measured · engine offline")
	elif proc.is_empty():
		proc_card.set_state("checking" if last_health.is_empty() else "error", "Checking" if last_health.is_empty() else "No data")
	else:
		proc_card.set_state("ok", "Measured")
	var mem_sys := SbFormat.NA
	if sys.get("memory_total_bytes") != null and sys.get("memory_available_bytes") != null:
		mem_sys = "%s free of %s" % [SbFormat.bytes(sys.get("memory_available_bytes")), SbFormat.bytes(sys.get("memory_total_bytes"))]
	proc_card.set_rows([
		["API pid", SbFormat.value_or_na(proc.get("pid"))],
		["API CPU", SbFormat.value_or_na(proc.get("cpu_percent"), " %")],
		["API memory (RSS)", SbFormat.bytes(proc.get("rss_bytes"))],
		["API threads", SbFormat.value_or_na(proc.get("threads"))],
		["Godot pid", str(OS.get_process_id())],
		["Godot memory", SbFormat.bytes(OS.get_static_memory_usage())],
		["Godot FPS", SbFormat.number(Engine.get_frames_per_second())],
		["System RAM", mem_sys],
	])


func _render_events() -> void:
	var lines: PackedStringArray = []
	if last_events.is_empty():
		lines.append("[color=#%s]%s[/color]" % [SbTheme.FAINT.to_html(false), "No operations recorded yet" if health_ok else SbFormat.NA])
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
