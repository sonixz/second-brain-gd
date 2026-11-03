class_name Backend
extends Node
## Owns everything the UI knows about the engine: install state, the running
## API (port, pid, token) and its shutdown when the app closes.

signal runtime_changed

var api: ApiClient
var data_dir := ""
var server: Dictionary = {}
var python: Dictionary = {}


func _ready() -> void:
	data_dir = SbPaths.data_dir()
	api = ApiClient.new()
	api.name = "ApiClient"
	add_child(api)


func install_state() -> Dictionary:
	return SbPaths.read_json(data_dir.path_join("install_state.json"))


func is_installed() -> bool:
	return bool(install_state().get("installed", false))


## Reads runtime/server.json and the token written by the bootstrap.
func load_runtime() -> bool:
	server = SbPaths.read_json(data_dir.path_join("runtime").path_join("server.json"))
	var token := SbPaths.read_text(data_dir.path_join("runtime").path_join("api_token"))
	api.port = int(server.get("port", 0))
	api.token = token
	runtime_changed.emit()
	return api.port > 0 and token != ""


func server_pid() -> int:
	return int(server.get("pid", 0))


## True when the API answers /health as the instance recorded in server.json.
func engine_alive() -> bool:
	if api.port <= 0:
		return false
	var res := await api.call_api("/health", false)
	if not res["ok"]:
		return false
	var data: Dictionary = res["data"]
	return str(data.get("instance_id", "")) == str(server.get("instance_id", "-"))


## Asks the API to stop and waits until /health stops answering. If it still
## answers as our instance after the delay, kills the pid from server.json.
## Godot cannot use OS.is_process_running() here: the API is a grandchild
## (started by the bootstrap), and Godot only tracks processes it spawned.
func shutdown_engine(wait_s: float = 3.0) -> Dictionary:
	if server.is_empty():
		load_runtime()
	if not await engine_alive():
		return {"stopped": false, "reason": "not running"}
	var res := await api.call_api("/system/shutdown", true, HTTPClient.METHOD_POST)
	var deadline := Time.get_ticks_msec() + int(wait_s * 1000.0)
	var alive := true
	while Time.get_ticks_msec() < deadline:
		await get_tree().create_timer(0.15).timeout
		alive = await engine_alive()
		if not alive:
			break
	var graceful := not alive
	if alive and server_pid() > 0:
		OS.kill(server_pid())
	return {"stopped": true, "graceful": graceful, "request_ok": res["ok"]}
