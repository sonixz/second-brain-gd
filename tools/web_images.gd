extends SceneTree
## Converts PNG screenshots to lightweight WebP for the website (public/).
## Headless, no window. Arguments after `--`: pairs "src.png=dst.webp[@width]".
##   godot --headless --path . --script res://tools/web_images.gd -- a.png=public/x.webp@800


func _initialize() -> void:
	var failed := 0
	for arg in OS.get_cmdline_user_args():
		var parts := arg.split("=", false, 1)
		if parts.size() != 2:
			continue
		var dst := parts[1]
		var width := 0
		if "@" in dst:
			width = int(dst.get_slice("@", 1))
			dst = dst.get_slice("@", 0)
		var img := Image.load_from_file(parts[0])
		if img == null or img.is_empty():
			push_error("cannot read " + parts[0])
			failed += 1
			continue
		if width > 0 and img.get_width() > width:
			img.resize(width, int(round(img.get_height() * float(width) / img.get_width())), Image.INTERPOLATE_LANCZOS)
		DirAccess.make_dir_recursive_absolute(dst.get_base_dir())
		if img.save_webp(dst, true, 0.82) != OK:
			failed += 1
		else:
			print("webp ", dst)
	quit(1 if failed else 0)
