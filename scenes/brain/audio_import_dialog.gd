extends AcceptDialog
## Voice memos (Loop 37): recordings made anywhere, dropped on the Brain at home. The preview says, before anything
## is sent, each memo's length, when it was recorded and what it should cost; « Transcribe » sends them one by one
## to OpenAI with the user's key, and each memo comes back as ideas, tasks and notes linked to it.
## Loaded by preload path (a new class can lag in Godot's class list on Windows).

signal imported(report: Dictionary)

var app: SbApp
var paths: Array = []
var space_id := ""
var preview: Dictionary = {}
var results: Array = []          # one Dictionary per memo sent: {name, ok, data | error}
var summary_label: Label
var list_label: RichTextLabel
var progress_label: Label
var result_label: RichTextLabel
var go_button: Button
var stop_button: Button
var _busy := false
var _stop := false


func setup(a: SbApp, files: Array, space: String = "") -> AcceptDialog:
	app = a
	paths = files
	space_id = space
	name = "AudioImportDialog"
	title = I18n.t("Voice memos")
	ok_button_text = I18n.t("Close")
	theme = app.theme
	add_theme_stylebox_override("panel", SbTheme.box(SbTheme.PANEL, 0, SbTheme.BORDER, 1, 18))
	var box := VBoxContainer.new()
	box.custom_minimum_size = Vector2(620, 0)
	box.add_theme_constant_override("separation", 10)
	add_child(box)
	summary_label = Label.new()
	summary_label.name = "Summary"
	summary_label.theme_type_variation = "Heading"
	summary_label.add_theme_font_size_override("font_size", 18)
	summary_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	summary_label.text = I18n.t("Listening to the files…")
	box.add_child(summary_label)
	list_label = RichTextLabel.new()
	list_label.name = "Memos"
	list_label.bbcode_enabled = true
	list_label.fit_content = true
	list_label.custom_minimum_size = Vector2(600, 0)
	list_label.selection_enabled = true
	box.add_child(list_label)
	var hint := Label.new()
	hint.theme_type_variation = "Muted"
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.text = I18n.t("Each memo is sent to OpenAI with your key, transcribed, then cut into ideas, tasks and notes linked to it. The audio and the full transcript stay with the memo; the items are dated when it was recorded.")
	box.add_child(hint)
	progress_label = Label.new()
	progress_label.name = "Progress"
	progress_label.theme_type_variation = "Muted"
	progress_label.visible = false
	box.add_child(progress_label)
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_END
	row.add_theme_constant_override("separation", 8)
	box.add_child(row)
	stop_button = Button.new()
	stop_button.name = "StopButton"
	stop_button.text = I18n.t("Stop")
	stop_button.tooltip_text = I18n.t("Stops after the memo under way: the ones already added stay")
	stop_button.visible = false
	stop_button.pressed.connect(func() -> void:
		_stop = true
		stop_button.disabled = true
		stop_button.text = I18n.t("Stopping…"))
	row.add_child(stop_button)
	go_button = Button.new()
	go_button.name = "TranscribeButton"
	go_button.text = I18n.t("Transcribe")
	go_button.theme_type_variation = "PrimaryButton"
	go_button.disabled = true
	go_button.pressed.connect(run)
	row.add_child(go_button)
	result_label = RichTextLabel.new()
	result_label.name = "AudioReport"
	result_label.bbcode_enabled = true
	result_label.fit_content = true
	result_label.custom_minimum_size = Vector2(600, 0)
	result_label.selection_enabled = true
	result_label.visible = false
	box.add_child(result_label)
	visibility_changed.connect(func() -> void:
		if not visible and _busy:
			_stop = true)  # closed while it works: it stops after the memo under way
	return self


func open() -> void:
	popup_centered(Vector2i(680, 380))
	await refresh()


static func clock(seconds: float) -> String:
	var s := int(round(seconds))
	return "%d:%02d:%02d" % [s / 3600, s % 3600 / 60, s % 60] if s >= 3600 else "%d:%02d" % [s / 60, s % 60]


static func money(v: float) -> String:
	return "< 0.01 $" if v < 0.01 else "%.2f $" % v


static func _when(iso: String) -> String:
	var unix: int = Time.get_unix_time_from_datetime_string(iso) + int(Time.get_time_zone_from_system()["bias"]) * 60
	var d := Time.get_datetime_dict_from_unix_time(int(unix))
	return "%d-%02d-%02d %dh%02d" % [d["year"], d["month"], d["day"], d["hour"], d["minute"]]


## The preview: what each file is, how long, when it was recorded, what it should cost. Nothing is sent here.
func refresh() -> void:
	var res := await app.backend.api.call_api("/sources/audio/probe", true, HTTPClient.METHOD_POST,
		JSON.stringify({"paths": paths}))
	if not is_inside_tree():
		return
	if not res["ok"]:
		summary_label.text = I18n.t("This cannot be read: %s") % str((res["data"] as Dictionary).get("detail", res["error"]))
		return
	preview = res["data"]
	var lines := PackedStringArray()
	for f in preview.get("files", []):
		var d: Dictionary = f
		var nm := str(d.get("name", "")).replace("[", "[lb]")
		if bool(d.get("ok", false)):
			lines.append("[color=#%s]●[/color] %s · %s%s · %s · ≈ %s" % [SbTheme.MINT.to_html(false), nm,
				"" if bool(d.get("exact", false)) else "≈ ", clock(float(d.get("seconds", 0))),
				_when(str(d.get("recorded_at", ""))), money(float(d.get("cost_usd", 0)))])
		else:
			lines.append("[color=#%s]✕[/color] %s — %s" % [SbTheme.WARM.to_html(false), nm, str(d.get("why", ""))])
	list_label.text = "\n".join(lines)
	var ready := int(preview.get("ready", 0))
	if ready == 0:
		summary_label.text = I18n.t("No voice memo to transcribe here")
	elif ready == 1:
		summary_label.text = I18n.t("One voice memo · %s · estimated %s") % [clock(float(preview.get("seconds", 0))),
			money(float(preview.get("cost_usd", 0)))]
	else:
		summary_label.text = I18n.t("%d voice memos · %s · estimated %s") % [ready, clock(float(preview.get("seconds", 0))),
			money(float(preview.get("cost_usd", 0)))]
	var has_key := bool(preview.get("has_key", false))
	var model_ok := bool(preview.get("model_ok", true))
	if ready > 0 and not has_key:
		progress_label.visible = true
		progress_label.text = I18n.t("Add your OpenAI key in Settings first: it is what transcribes the memos.")
	elif ready > 0 and not model_ok:
		progress_label.visible = true
		progress_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		progress_label.text = I18n.t("Your OpenAI project does not allow a transcription model yet. On platform.openai.com: Settings → Project → Limits, allow gpt-transcribe, then drop the memo again. Nothing was sent.")
	go_button.disabled = ready == 0 or not has_key or not model_ok
	go_button.text = I18n.t("Transcribe %d memos") % ready if ready > 1 else I18n.t("Transcribe")
	await get_tree().process_frame
	if is_inside_tree():
		reset_size()


## One memo after the other; the report lists the ideas each one gave.
func run() -> void:
	if _busy or preview.is_empty():
		return
	_busy = true
	_stop = false
	go_button.disabled = true
	stop_button.visible = true
	stop_button.disabled = false
	stop_button.text = I18n.t("Stop")
	progress_label.visible = true
	results.clear()
	var todo: Array = (preview.get("files", []) as Array).filter(func(f: Variant) -> bool: return bool((f as Dictionary).get("ok", false)))
	for k in todo.size():
		if _stop or not is_inside_tree():
			break
		var f: Dictionary = todo[k]
		var job := "%d-%d" % [Time.get_ticks_usec(), randi()]
		var state := {"busy": true}
		_follow(job, k + 1, todo.size(), str(f.get("name", "")), state)
		var payload := {"path": str(f["path"]), "job": job}
		if space_id != "":
			payload["space_id"] = space_id
		var res := await app.backend.api.call_api("/sources/audio", true, HTTPClient.METHOD_POST, JSON.stringify(payload))
		state["busy"] = false
		if not is_inside_tree():
			return
		if res["ok"]:
			results.append({"name": f["name"], "ok": true, "data": res["data"]})
		else:
			results.append({"name": f["name"], "ok": false, "error": str((res["data"] as Dictionary).get("detail", res["error"]))})
		_show_report(todo.size())
	_busy = false
	stop_button.visible = false
	progress_label.text = I18n.t("Stopped: the memos already added stay.") if _stop and results.size() < todo.size() else I18n.t("Done.")
	go_button.text = I18n.t("Done")
	imported.emit({"results": results})


func _follow(job: String, n: int, total: int, what: String, state: Dictionary) -> void:
	progress_label.text = I18n.t("Memo %d / %d · %s · sending…") % [n, total, what]
	while bool(state["busy"]) and is_inside_tree():
		await get_tree().create_timer(0.5).timeout
		if not bool(state["busy"]) or not is_inside_tree():
			return
		var res := await app.backend.api.call_api("/sources/progress/" + job)
		if res["ok"] and bool(state["busy"]):
			var stage := str((res["data"] as Dictionary).get("stage", ""))
			var line := I18n.t("transcribing the recording") if stage == "transcribe" else (I18n.t("finding the ideas") if stage == "structure" else "")
			if line != "":
				progress_label.text = I18n.t("Memo %d / %d · %s · %s") % [n, total, what, line]


func _show_report(total: int) -> void:
	var b := PackedStringArray()
	var ideas := 0
	for r in results:
		var d: Dictionary = r
		var nm := str(d["name"]).replace("[", "[lb]")
		if not bool(d["ok"]):
			b.append("[color=#%s]✕[/color] %s — %s" % [SbTheme.WARM.to_html(false), nm, str(d["error"]).replace("[", "[lb]")])
			continue
		var data: Dictionary = d["data"]
		if bool(data.get("duplicate", false)):
			b.append(I18n.t("%s is already in your Brain.") % nm)
			continue
		var items: Array = data.get("items", [])
		ideas += items.size()
		b.append("[b]%s[/b]" % str(data.get("title", nm)).replace("[", "[lb]"))
		for it in items:
			var i: Dictionary = it
			var mark := "☐ " if str(i.get("kind", "")) == "task" else "• "
			var at := "" if i.get("at") == null else "  [color=#%s](%s)[/color]" % [SbTheme.MUTED.to_html(false), clock(float(i["at"]))]
			b.append("    " + mark + str(i.get("title", "")).replace("[", "[lb]") + at)
	var added := results.filter(func(x: Variant) -> bool: return bool((x as Dictionary)["ok"])).size()
	b.insert(0, I18n.t("Memo added · %d items") % ideas if total == 1 and added == 1 else I18n.t("%d of %d memos added · %d items") % [added, total, ideas])
	result_label.text = "\n".join(b)
	result_label.visible = true
	await get_tree().process_frame
	if is_inside_tree():
		reset_size()
		popup_centered()
