extends "res://tools/capture_base.gd"
## Settings screens (Loops UX-A/B/C): tools/showcase.sh ux-fr with SBGD_CAPTURE_SCRIPT=ux_shots SBGD_UI_LANG=fr
## SBGD_SHOT_SIZE=1600x1000. An agent's settings tile, the ⚙ Settings menu, the engine room's « Your data ». No model call.


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	await b.call("show_agent_info", "sparring")
	await pause(1.0)
	calm()
	await shot("u1-agent-settings")
	b.call("close_agent_settings")
	(b.get("settings_button") as Button).pressed.emit()
	await pause(0.6)
	await shot("u2-settings-menu")
	var menu: PopupMenu = (b.get("settings_button") as Button).find_child("SettingsMenu", true, false)
	menu.hide()
	await app.backend.api.call_api("/backup/now", true, HTTPClient.METHOD_POST, "{}")
	app.show_console()
	await pause(6.0)
	var dp: DataPanel = app.current().find_child("DataPanel", true, false)
	if dp != null:
		var sc0: ScrollContainer = app.current().find_children("*", "ScrollContainer", true, false)[0]
		sc0.scroll_vertical = int(dp.global_position.y - (sc0.get_child(0) as Control).global_position.y - 4.0)
		await pause(1.0)
	await shot("u3-your-data")
	quit(0)
