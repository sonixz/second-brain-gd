class_name PythonLocator
extends Node
## Finds a compatible Python without blocking the UI: each candidate runs
## `engine/bootstrap.py detect` on a worker thread and reports JSON.

signal located(result: Dictionary)

const SETTINGS_PATH := "user://settings.cfg"
const PYTHON_DOWNLOAD := "https://www.python.org/downloads/"

var _thread: Thread


## A candidate's result id ("compatible", "not found"…) as shown to the user, in the current language.
static func result_text(result: String) -> String:
	match result:
		"compatible":
			return I18n.t("compatible")
		"incompatible":
			return I18n.t("incompatible")
		"not found":
			return I18n.t("not found")
		"unreadable answer":
			return I18n.t("unreadable answer")
		"missing venv module":
			return I18n.t("missing venv module")
	return result


static func custom_python() -> String:
	var env := OS.get_environment("SBGD_PYTHON")
	if env != "":
		return env
	return str(SbSettings.get_value("python", "path", ""))


static func save_custom_python(path: String) -> void:
	SbSettings.set_value("python", "path", path.strip_edges())


static func candidates() -> Array[Dictionary]:
	var list: Array[Dictionary] = []
	var bundled := SbPaths.bundled_python()
	if bundled != "":  # the app's own Python comes first: nothing to install
		list.append({"label": I18n.t("Python shipped with the app"), "cmd": bundled, "args": []})
	var custom := custom_python()
	if custom != "":
		list.append({"label": I18n.t("%s (custom)") % custom, "cmd": custom, "args": []})
	if OS.get_name() == "Windows":
		for v in ["3.13", "3.12"]:
			list.append({"label": "py -" + v, "cmd": "py", "args": ["-" + v]})
		list.append({"label": "python", "cmd": "python", "args": []})
		list.append({"label": "python3", "cmd": "python3", "args": []})
	else:
		for c in ["python3.13", "python3.12", "python3", "python"]:
			list.append({"label": c, "cmd": c, "args": []})
	return list


func locate() -> void:
	if _thread != null and _thread.is_alive():
		return
	if _thread != null:
		_thread.wait_to_finish()
	_thread = Thread.new()
	_thread.start(_worker.bind(SbPaths.bootstrap_script(), candidates()))


func is_busy() -> bool:
	return _thread != null and _thread.is_alive()


func _worker(bootstrap: String, cands: Array[Dictionary]) -> void:
	var tried: Array[Dictionary] = []
	var found: Dictionary = {}
	for c in cands:
		var resolved := which(str(c["cmd"]))
		if resolved == "":
			# Not on PATH: skip without spawning (avoids engine errors in the log).
			tried.append({"label": c["label"], "result": "not found", "exit_code": -1, "ms": 0})
			continue
		var args: Array = c["args"].duplicate()
		args.append(bootstrap)
		args.append("detect")
		var output: Array = []
		var started := Time.get_ticks_msec()
		var code := OS.execute(resolved, PackedStringArray(args), output, true)
		var text := ""
		if output.size() > 0:
			text = str(output[0])
		var info := _parse_detect(text)
		var entry := {"label": c["label"], "exit_code": code, "ms": Time.get_ticks_msec() - started}
		if info.is_empty():
			entry["result"] = "not found" if code != 0 else "unreadable answer"
			entry["detail"] = text.strip_edges().left(160)
		else:
			entry["result"] = "compatible" if bool(info.get("compatible", false)) else "incompatible"
			entry["version"] = info.get("version", "?")
			entry["executable"] = info.get("executable", "")
			if bool(info.get("compatible", false)) and not bool(info.get("venv_available", true)):
				entry["result"] = "missing venv module"
			if entry["result"] == "compatible" and found.is_empty():
				found = info
		tried.append(entry)
		if not found.is_empty():
			break
	var result := {"found": not found.is_empty(), "python": found, "tried": tried,
		"supported_range": ">=3.12,<3.14", "download_url": PYTHON_DOWNLOAD}
	call_deferred("_finish", result)


func _finish(result: Dictionary) -> void:
	if _thread != null:
		_thread.wait_to_finish()
		_thread = null
	located.emit(result)


## Resolves a command like the shell would: absolute paths are checked as is,
## bare names are searched on PATH (with .exe on Windows). "" when missing.
static func which(cmd: String) -> String:
	if cmd.is_absolute_path() or cmd.contains("/") or cmd.contains("\\"):
		return cmd if FileAccess.file_exists(cmd) else ""
	var windows := OS.get_name() == "Windows"
	var sep := ";" if windows else ":"
	var names := [cmd + ".exe", cmd] if windows and not cmd.ends_with(".exe") else [cmd]
	for dir in OS.get_environment("PATH").split(sep, false):
		for n in names:
			var candidate := dir.strip_edges().trim_suffix("\\").trim_suffix("/").path_join(n)
			if FileAccess.file_exists(candidate):
				return candidate
	return ""


static func _parse_detect(text: String) -> Dictionary:
	var lines := text.split("\n", false)
	for i in range(lines.size() - 1, -1, -1):
		var line := lines[i].strip_edges()
		if line.begins_with("{"):
			var parsed: Variant = JSON.parse_string(line)
			if parsed is Dictionary:
				return parsed
	return {}


func _exit_tree() -> void:
	if _thread != null:
		_thread.wait_to_finish()
