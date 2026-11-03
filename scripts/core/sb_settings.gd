class_name SbSettings
extends RefCounted
## Small persistent preferences in user://settings.cfg (Godot user folder).

const PATH := "user://settings.cfg"


## Tests and capture tools set SBGD_SETTINGS so they never touch the user's real preferences.
static func path() -> String:
	var override := OS.get_environment("SBGD_SETTINGS")
	return override if override != "" else PATH


static func get_value(section: String, key: String, default: Variant) -> Variant:
	var cfg := ConfigFile.new()
	if cfg.load(path()) != OK:
		return default
	return cfg.get_value(section, key, default)


static func set_value(section: String, key: String, value: Variant) -> void:
	var cfg := ConfigFile.new()
	cfg.load(path())
	cfg.set_value(section, key, value)
	cfg.save(path())
