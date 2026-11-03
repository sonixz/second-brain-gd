class_name ApiClient
extends Node
## Minimal async JSON client for the local engine API on 127.0.0.1.

var port := 0
var token := ""
var timeout_s := 4.0


func base_url() -> String:
	return "http://127.0.0.1:%d" % port


func call_api(path: String, auth: bool = true, method: int = HTTPClient.METHOD_GET, body: String = "",
		raw: bool = false) -> Dictionary:
	if port <= 0:
		return {"ok": false, "code": 0, "error": "API port unknown", "data": {}, "ms": 0}
	var req := HTTPRequest.new()
	req.timeout = 90.0 if path.begins_with("/assistant") or path.begins_with("/agents") else timeout_s
	add_child(req)
	var headers := PackedStringArray(["Accept: application/json"])
	if auth:
		headers.append("Authorization: Bearer " + token)
	if body != "":
		headers.append("Content-Type: application/json")
	var started := Time.get_ticks_msec()
	var err := req.request(base_url() + path, headers, method, body)
	if err != OK:
		req.queue_free()
		return {"ok": false, "code": 0, "error": "request failed to start (%s)" % error_string(err), "data": {},
			"ms": 0}
	var res: Array = await req.request_completed
	req.queue_free()
	var elapsed := Time.get_ticks_msec() - started
	var result: int = res[0]
	var code: int = res[1]
	var body_bytes: PackedByteArray = res[3]
	if result != HTTPRequest.RESULT_SUCCESS:
		return {"ok": false, "code": code, "error": _result_text(result), "data": {}, "ms": elapsed}
	if raw and code >= 200 and code < 300:
		return {"ok": true, "code": code, "error": "", "data": {}, "bytes": body_bytes, "ms": elapsed}
	var text := body_bytes.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text) if text != "" else {}
	var data: Dictionary = parsed if parsed is Dictionary else {}
	if code < 200 or code >= 300:
		return {"ok": false, "code": code, "error": "HTTP %d" % code, "data": data, "ms": elapsed}
	return {"ok": true, "code": code, "error": "", "data": data, "ms": elapsed}


static func _result_text(result: int) -> String:
	match result:
		HTTPRequest.RESULT_CANT_CONNECT, HTTPRequest.RESULT_CONNECTION_ERROR:
			return "connection refused"
		HTTPRequest.RESULT_TIMEOUT:
			return "timeout"
		HTTPRequest.RESULT_CANT_RESOLVE:
			return "cannot resolve host"
	return "network error %d" % result
