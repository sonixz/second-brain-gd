extends "res://tools/capture_base.gd"
## Folder import screenshots (Loop 39): tools/showcase.sh with SBGD_CAPTURE_SCRIPT=folder_shots and SBGD_VAULT=<a vault
## folder> (SBGD_UI_LANG=fr for French). The website uses kepano/kepano-obsidian (MIT licence). No model call.


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	var vault := OS.get_environment("SBGD_VAULT")
	g.zoom_to(0.45, Vector2(-60, 0), 0.3)
	await pause(1.0)
	var dlg: AcceptDialog = b.call("import_folder", vault)
	var end := Time.get_ticks_msec() + 15000
	while (dlg.get("scan") as Dictionary).is_empty() and Time.get_ticks_msec() < end:
		await pause(0.2)
	calm()
	await pause(0.8)
	await shot("f1-preview")
	await dlg.call("run_import")
	await pause(1.0)
	await shot("f2-report")
	dlg.hide()
	await b.call("refresh_graph")
	await pause(2.5)
	var nid := g.find_node("Bass on Top")
	if nid != "":
		g.zoom_to(0.9, g.nodes[nid]["pos"] if (g.nodes[nid] as Dictionary).has("pos") else Vector2.ZERO, 0.6)
	await pause(2.0)
	calm()
	await shot("f3-graph")
	quit(0)
