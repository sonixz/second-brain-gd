class_name BootstrapRunner
extends Node
## Starts `engine/bootstrap.py setup` as a separate process and tails its
## JSON Lines event stream (docs/architecture/events-protocol.md). The UI
## thread only reads new bytes every 100 ms, so rendering never blocks.

signal event_received(event: Dictionary)
signal finished(ok: bool, final_event: Dictionary)

const POLL_INTERVAL := 0.1

var pid := -1
var events_path := ""
var exit_code := -1
var _offset := 0
var _pending := PackedByteArray()
var _final: Dictionary = {}
var _timer: Timer


func start(python: String, data_dir: String) -> Error:
	if is_running():
		return ERR_BUSY
	var runtime := data_dir.path_join("runtime")
	# Create the data folder from Godot first: Microsoft Store Python redirects
	# folders it creates under AppData to a private location (see troubleshooting).
	var err := DirAccess.make_dir_recursive_absolute(runtime)
	if err != OK:
		return err
	events_path = runtime.path_join("events-%d.jsonl" % int(Time.get_unix_time_from_system() * 1000.0))
	_offset = 0
	_pending = PackedByteArray()
	_final = {}
	exit_code = -1
	var args := PackedStringArray([SbPaths.bootstrap_script(), "setup", "--quiet", "--data-dir", data_dir,
		"--events", events_path, "--parent-pid", str(OS.get_process_id())])
	pid = OS.create_process(python, args, false)
	if pid <= 0:
		pid = -1
		return ERR_CANT_CREATE
	if _timer == null:
		_timer = Timer.new()
		_timer.wait_time = POLL_INTERVAL
		_timer.timeout.connect(_poll)
		add_child(_timer)
	_timer.start()
	return OK


func is_running() -> bool:
	return pid > 0 and OS.is_process_running(pid)


func _poll() -> void:
	_read_new()
	if OS.is_process_running(pid):
		return
	_timer.stop()
	_read_new()
	exit_code = OS.get_process_exit_code(pid)
	pid = -1
	if _final.is_empty():
		_final = {"component": "bootstrap", "stage": "done", "status": "error", "progress": null,
			"timestamp": Time.get_datetime_string_from_system(true) + "Z",
			"message": I18n.t("The setup process ended (exit code %d) without reporting a result.") % exit_code}
		event_received.emit(_final)
	finished.emit(str(_final.get("status", "")) == "ok", _final)


func _read_new() -> void:
	if events_path == "" or not FileAccess.file_exists(events_path):
		return
	var f := FileAccess.open(events_path, FileAccess.READ)
	if f == null:
		return
	var length := f.get_length()
	if length <= _offset:
		return
	f.seek(_offset)
	_pending.append_array(f.get_buffer(length - _offset))
	_offset = length
	for line in take_lines():
		var parsed: Variant = JSON.parse_string(line)
		if parsed is Dictionary:
			var ev: Dictionary = parsed
			if str(ev.get("component", "")) == "bootstrap" and str(ev.get("stage", "")) == "done":
				_final = ev
			event_received.emit(ev)


## Splits complete lines off the pending buffer; keeps a partial last line.
func take_lines() -> PackedStringArray:
	var out := PackedStringArray()
	while true:
		var nl := _pending.find(10)
		if nl < 0:
			break
		var line := _pending.slice(0, nl).get_string_from_utf8().strip_edges()
		_pending = _pending.slice(nl + 1)
		if line != "":
			out.append(line)
	return out


func feed_for_test(bytes: PackedByteArray) -> PackedStringArray:
	_pending.append_array(bytes)
	return take_lines()
