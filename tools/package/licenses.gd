extends SceneTree
## Writes Godot's licence and its third-party notices (Loop 31): any exported app must carry them.
##   godot --headless --script res://tools/package/licenses.gd -- <output file>


func _init() -> void:
	var out := OS.get_cmdline_user_args()[0]
	var lines := PackedStringArray(["Godot Engine " + Engine.get_version_info().get("string", ""), "",
		Engine.get_license_text(), "", "Third-party components bundled in the Godot Engine:", ""])
	for part in Engine.get_copyright_info():
		lines.append("- %s" % part.get("name", ""))
		for p in part.get("parts", []):
			lines.append("  files: %s" % ", ".join(p.get("files", [])))
			lines.append("  copyright: %s" % "; ".join(p.get("copyright", [])))
			lines.append("  licence: %s" % p.get("license", ""))
	lines.append("")
	lines.append("Licence texts:")
	var info := Engine.get_license_info()
	for name in info:
		lines.append("")
		lines.append("== %s ==" % name)
		lines.append(str(info[name]))
	var f := FileAccess.open(out, FileAccess.WRITE)
	f.store_string("\n".join(lines))
	f.close()
	quit()
