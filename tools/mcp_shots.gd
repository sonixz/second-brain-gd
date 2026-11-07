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
	quit(0)
