extends "res://tools/capture_base.gd"
## The showcase film (video-production/): the real app, filmed by Godot's movie mode (tools/film.sh) with the
## English showcase Brain in a temporary home. One step per run (SBGD_FILM_STEP); each step is a film_* function
## below and leaves « mark <name> <frame> » lines (SBGD_MARKS) the cut is made from, so the cut follows the app
## when a screen moves. The sound is the app's own: its music and its effects, as a user hears them.
## Step « prepare » only installs and opens the Brain (the base home every step starts from).

var marks_path := ""


func mark(name: String) -> void:
	var line := "mark %s %d" % [name, Engine.get_frames_drawn()]
	print(line)
	if OS.get_environment("FILM_STILLS") == "1":  # a quick look at the framing: one picture per mark, no film
		root.get_texture().get_image().save_png(out_dir.path_join(name + ".png"))
	if marks_path == "":
		return
	var f := FileAccess.open(marks_path, FileAccess.READ_WRITE if FileAccess.file_exists(marks_path) else FileAccess.WRITE)
	if f != null:
		f.seek_end()
		f.store_line(line)
		f.close()


func _run() -> void:
	var step := OS.get_environment("SBGD_FILM_STEP")
	marks_path = OS.get_environment("SBGD_MARKS")
	# FILM_REAL=1: the real archivist (a model call each time it files); else the scripted one, no key, no cost
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "openai" if OS.get_environment("FILM_REAL") == "1" else "showcase")
	boot_env()
	# The film is 1920x1080 and is watched much smaller on the page: the interface is drawn one and a half times
	# larger (the layout of a 1280x720 window, with the sharpness of the full frame). FILM_SCALE changes it.
	var scale := OS.get_environment("FILM_SCALE")
	root.content_scale_factor = float(scale) if scale != "" else 1.5
	if not await open_brain():
		quit(1)
		return
	mark("open")
	if step != "prepare":
		var fn := "film_" + step.replace("-", "_")
		if not has_method(fn):
			push_error("film: no step « %s »" % step)
			quit(1)
			return
		await call(fn)
		mark("end")
	await finish()


## Types in a line edit one letter at a time, as a hand would.
func type_in(edit: LineEdit, text: String, per_letter: float = 0.045) -> void:
	edit.grab_focus()
	for i in text.length():
		edit.text = text.substr(0, i + 1)
		edit.caret_column = i + 1
		await pause(per_letter)


## Scenes 1 and 2: the graph alive with a slow push in, then a thought typed and filed, with its receipt.
func film_open() -> void:
	g.zoom_to(0.27, Vector2(-60, -140), 0.1)   # the whole Brain, beside the Archivist's panel
	await pause(1.0)
	mark("graph")
	g.zoom_to(0.335, Vector2(-60, -140), 6.0)
	await pause(6.5)
	mark("typing")
	var ce: LineEdit = b.get("capture_edit")
	await type_in(ce, "Ask Marc if the induction cooktop needs its own 40 A circuit")
	await pause(0.6)
	ce.text_submitted.emit(ce.text)
	mark("sent")
	var end := Time.get_ticks_msec() + 30000
	while int(b.get("classified")) == 0 and Time.get_ticks_msec() < end:
		await pause(0.2)
	mark("receipt")
	await pause(1.6)
	mark("receipt-shown")
	await pause(2.4)


## The Captures view: everything that came in, how (typed, spoken, a page, a file) and where it went.
func film_captures() -> void:
	(b.get("toast") as Control).visible = false
	await b.call("set_view", "captures")
	await pause(1.5)
	stage()
	mark("captures")
	await pause(3.0)
