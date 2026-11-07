class_name ApiClient
extends Node
## Minimal async JSON client for the local engine API on 127.0.0.1.

var port := 0
var token := ""
var timeout_s := 4.0


func base_url() -> String:
	return "http://127.0.0.1:%d" % port


## Reading a document (local OCR of many pages, then a summary) can take minutes; AI calls up to 90 s;
## everything else answers at once.
func timeout_for(path_and_query: String, method: int) -> float:
	var path := path_and_query.get_slice("?", 0)  # « /sources/<id>/reread?job=… » is still a long reading
	if method == HTTPClient.METHOD_POST and (path.begins_with("/sources/file") or path.begins_with("/sources/audio") or path.begins_with("/sources/url")
			or path.ends_with("/reread") or path.begins_with("/data/") or path.begins_with("/brain/import/") or path == "/brain/export"):
		return 600.0  # also backups, restore, export (Your data), a folder or zip import (1,000 notes)
	if path.begins_with("/assistant") or path.begins_with("/agents") or path.begins_with("/billing") or path.begins_with("/packs") or path.begins_with("/mcp/servers"):
		return 90.0
	return timeout_s


func call_api(path: String, auth: bool = true, method: int = HTTPClient.METHOD_GET, body: String = "",
		raw: bool = false) -> Dictionary:
	if port <= 0:
		return {"ok": false, "code": 0, "error": I18n.t("API port unknown"), "data": {}, "ms": 0}
	var req := HTTPRequest.new()
	req.timeout = timeout_for(path, method)
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
		return {"ok": false, "code": 0, "error": I18n.t("request failed to start (%s)") % error_string(err), "data": {},
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
			return I18n.t("connection refused")
		HTTPRequest.RESULT_TIMEOUT:
			return I18n.t("timeout")
		HTTPRequest.RESULT_CANT_RESOLVE:
			return I18n.t("cannot resolve host")
	return I18n.t("network error %d") % result
