class_name SbPaths
extends RefCounted
## Mirrors engine/paths.py. Godot always passes --data-dir to the bootstrap,
## so these two only need to agree on the default location.

const APP_DIR_WINDOWS_MAC := "SecondBrainGD"
const APP_DIR_LINUX := "second-brain-gd"


static func data_dir() -> String:
	var override := OS.get_environment("SBGD_HOME")
	if override != "":
		return override
	match OS.get_name():
		"Windows":
			var base := OS.get_environment("LOCALAPPDATA")
			if base == "":
				base = OS.get_environment("USERPROFILE").path_join("AppData").path_join("Local")
			return base.path_join(APP_DIR_WINDOWS_MAC)
		"macOS":
			return OS.get_environment("HOME").path_join("Library/Application Support").path_join(APP_DIR_WINDOWS_MAC)
	var xdg := OS.get_environment("XDG_DATA_HOME")
	if xdg == "":
		xdg = OS.get_environment("HOME").path_join(".local/share")
	return xdg.path_join(APP_DIR_LINUX)


static func repo_root() -> String:
	return ProjectSettings.globalize_path("res://").trim_suffix("/")


static func bootstrap_script() -> String:
	return repo_root().path_join("engine").path_join("bootstrap.py")


static func runtime_dir() -> String:
	return data_dir().path_join("runtime")


static func state_file() -> String:
	return data_dir().path_join("install_state.json")


static func server_file() -> String:
	return runtime_dir().path_join("server.json")


static func token_file() -> String:
	return runtime_dir().path_join("api_token")


static func read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var text := FileAccess.get_file_as_string(path)
	var parsed: Variant = JSON.parse_string(text)
	if parsed is Dictionary:
		return parsed
	return {}


static func read_text(path: String) -> String:
	if not FileAccess.file_exists(path):
		return ""
	return FileAccess.get_file_as_string(path).strip_edges()
