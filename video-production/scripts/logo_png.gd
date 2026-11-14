extends SceneTree
## The project's logo (public/assets/logo.svg) as a PNG for the film's closing card:
##   godot --headless --path . -s video-production/scripts/logo_png.gd -- <svg> <png> <scale>
func _initialize() -> void:
	var a := OS.get_cmdline_user_args()
	var img := Image.new()
	var err := img.load_svg_from_string(FileAccess.get_file_as_string(a[0]), float(a[2]))
	if err == OK:
		img.save_png(a[1])
	print("logo: ", error_string(err), " ", img.get_size())
	quit()
