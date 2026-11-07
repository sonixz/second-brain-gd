extends "res://tools/capture_base.gd"
## Voice memo screenshots (Loop 37): tools/showcase.sh audio-memos-en with SBGD_CAPTURE_SCRIPT=audio_shots
## (SBGD_UI_LANG=fr for French). The memo is a silent WAV; ShowcaseChat scripts the transcript and the ideas.
## No model call.


func _memo(path: String, seconds: int) -> void:
	var rate := 8000
	var n := rate * seconds
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_buffer("RIFF".to_ascii_buffer())
	f.store_32(36 + n * 2)
	f.store_buffer("WAVEfmt ".to_ascii_buffer())
	f.store_32(16)
	f.store_16(1)
	f.store_16(1)
	f.store_32(rate)
	f.store_32(rate * 2)
	f.store_16(2)
	f.store_16(16)
	f.store_buffer("data".to_ascii_buffer())
	f.store_32(n * 2)
	var pcm := PackedByteArray()
	pcm.resize(n * 2)
	f.store_buffer(pcm)
	f.close()


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	var dir := OS.get_environment("SBGD_HOME").path_join("Phone memos")
	DirAccess.make_dir_recursive_absolute(dir)
	var memo := dir.path_join("Recording_20261107_091500.wav")
	_memo(memo, 47)
	g.zoom_to(0.45, Vector2(-60, 0), 0.3)
	await pause(1.0)
	var dlg: AcceptDialog = b.call("import_audio", [memo])
	var end := Time.get_ticks_msec() + 15000
	while (dlg.get("preview") as Dictionary).is_empty() and Time.get_ticks_msec() < end:
		await pause(0.2)
	calm()
	await pause(0.8)
	await shot("a1-preview")
	(dlg.get("go_button") as Button).pressed.emit()
	end = Time.get_ticks_msec() + 20000
	while ((dlg.get("results") as Array).is_empty() or bool(dlg.get("_busy"))) and Time.get_ticks_msec() < end:
		await pause(0.2)
	await pause(1.0)
	await shot("a2-report")
	dlg.hide()
	await b.call("refresh_graph")
	await pause(2.5)
	var nid := g.find_node("Paella")
	if nid != "":
		g.select(nid)
		g.zoom_to(1.1, (g.nodes[nid] as Dictionary)["pos"], 0.6)
	await pause(2.5)
	calm()
	await shot("a3-graph")
	quit(0)
