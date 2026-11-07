extends "res://tools/capture_base.gd"
## MCP screenshots (Loop MCP-A): tools/showcase.sh mcp-en with SBGD_CAPTURE_SCRIPT=mcp_shots (SBGD_UI_LANG=fr for
## French). A client is connected and calls one read tool; its key stays masked in the window. No model call.


func _run() -> void:
	OS.set_environment("SBGD_ASSISTANT_PROVIDER", "showcase")
	boot_env()
	if not await open_brain():
		quit(1)
		return
	var lights: Button = b.get("mcp_lights")
	var dlg: AcceptDialog = lights.call("open_dialog")
	await pause(0.8)
	(dlg.find_child("ConnectButton", true, false) as Button).pressed.emit()
	await pause(1.5)
	var c: Dictionary = await app.backend.api.call_api("/mcp/clients", true, HTTPClient.METHOD_POST, JSON.stringify({"name": "Claude Code (WSL)", "level": "read"}))
	var req := HTTPRequest.new()
	root.add_child(req)
	req.request("http://127.0.0.1:%d/mcp" % app.backend.api.port, PackedStringArray(["Content-Type: application/json",
		"Authorization: Bearer " + str((c["data"] as Dictionary)["token"])]), HTTPClient.METHOD_POST,
		JSON.stringify({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "overview", "arguments": {}}}))
	await req.request_completed
	await lights.call("poll")
	await pause(0.3)
	calm()
	await shot("m1-connect")
	dlg.hide()
	await lights.call("poll")
	await pause(0.2)
	await shot("m2-lights")
	# MCP-B1: proposals waiting for approval
	var cid := str((c["data"] as Dictionary)["id"])
	await app.backend.api.call_api("/mcp/clients/%s/level" % cid, true, HTTPClient.METHOD_POST, JSON.stringify({"level": "propose_changes", "direct": false}))
	var fr := OS.get_environment("SBGD_UI_LANG") == "fr"
	for args in [{"title": "Rappel : renouveler le passeport" if fr else "Reminder: renew the passport", "content": "Il expire en mars." if fr else "It expires in March.",
			"reason": "Noté pendant une session de travail" if fr else "Noted during a work session", "suggested_place": "Finances"},
			{"title": "Idée : vidéo du graphe pour le site" if fr else "Idea: a video of the graph for the site", "content": "Montrer le graphe en mouvement." if fr else "Show the graph moving.",
			"reason": "Sorti d'une discussion sur le site" if fr else "Came up while working on the site"}]:
		var r2 := HTTPRequest.new()
		root.add_child(r2)
		r2.request("http://127.0.0.1:%d/mcp" % app.backend.api.port, PackedStringArray(["Content-Type: application/json",
			"Authorization: Bearer " + str((c["data"] as Dictionary)["token"])]), HTTPClient.METHOD_POST,
			JSON.stringify({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "propose_item", "arguments": args}}))
		await r2.request_completed
	await lights.call("poll")
	var dlg2: AcceptDialog = lights.call("open_dialog")
	await pause(3.0)
	calm()
	await shot("m3-proposals")
	dlg2.hide()
	await app.backend.api.call_api("/mcp/proposals/all/approve", true, HTTPClient.METHOD_POST, "{}")
	var tl: AcceptDialog = lights.call("open_timeline")
	await pause(2.0)
	calm()
	await shot("m4-timeline")
	quit(0)
