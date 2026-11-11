extends "res://tools/capture_base.gd"
## Screenshots of the graph's views (docs/plans/plan-graph-views.md): the picker, the timeline, the focus view,
## saved views. Run with: SBGD_CAPTURE_SCRIPT=views_shots tools/showcase.sh views


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	var fb: GraphFilters = b.get("filters_bar")
	g.zoom_to(0.5, Vector2(-60, 0), 0.3)
	await pause(2.5)
	await shot("01-zones")
	fb.set_view("timeline")
	await pause(3.0)
	await shot("02-timeline")
	fb.set_view("zones")
	await pause(1.0)
	calm()
	fb.set_view("focus")
	await pause(3.0)
	await shot("03-focus")
	for id in g.nodes:
		if int(g._focus_hops.get(id, -1)) == 1:
			g.set_focus(str(id))
			break
	await pause(3.0)
	await shot("04-focus-walk")
	b.call("save_graph_view", "Around this idea")
	fb.saved_button.pressed.emit()
	await pause(0.8)
	await shot("05-saved-views")
	fb.saved_popup.hide()
	calm()
	fb.set_view("timeline")
	fb.set_lanes("type")
	fb.time_button.button_pressed = true
	fb.time_slider.value = 0.6
	await pause(3.0)
	await shot("06-timeline-types-cursor")
	fb.set_lanes("place")
	fb.set_view("zones")
	fb.time_slider.value = 0.35
	g.zoom_to(0.5, Vector2(-60, 0), 0.3)
	await pause(3.0)
	await shot("07-zones-back-in-time")
	fb.time_button.button_pressed = false
	fb.set_view("meaning")
	await pause(4.0)
	await shot("08-meaning-map")
	fb.set_view("layers")
	await pause(2.5)
	await shot("09-layers-3d")
	await pause(4.0)
	await shot("10-layers-3d-turned")
	quit(0)
