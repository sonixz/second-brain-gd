# Process lifecycle

| Process | Started by | Ends |
|---|---|---|
| Godot app | the user | window closed |
| `bootstrap.py detect` | Godot (worker thread, `OS.execute`) | immediately |
| `bootstrap.py setup` | Godot (`OS.create_process`, no console) | after the health check, or on error |
| API server (`python -m engine.api.server`) | the bootstrap, detached | see below |

## How the API stops

1. **Normal close.** On `NOTIFICATION_WM_CLOSE_REQUEST` Godot calls `POST /system/shutdown`, waits up to 2.5 s
   until `/health` stops answering, then kills the pid from `runtime/server.json` only if that API still
   answers with our instance id.
2. **Godot crashes or is killed.** The bootstrap passes `--parent-pid <Godot pid>`. A watchdog thread in the
   server checks it every second and shuts the server down when it is gone. Tested on Linux and Windows.
3. **Command line.** `python engine/bootstrap.py stop`.

On exit the server records a `stop` event, sets `service_status` to `stopped`, and deletes `server.json` and
`api_token`.

## Reuse and restart

- A setup run finds a running API through `server.json` and `/health` (same `instance_id`). It reuses it if it
  belongs to the same parent; if a different app instance asks, it restarts it so the watchdog follows the new
  parent.
- A stale `server.json` (process gone) is cleaned up. The bootstrap never terminates a pid that is not recorded
  in its own `server.json`.
- `runtime/bootstrap.lock` holds the pid of a running setup; a second concurrent setup is refused, a lock left by
  a dead process is ignored.

## Why Godot does not watch the API pid

`OS.is_process_running()` only knows processes Godot started itself. The API is a grandchild (Godot →
bootstrap → API), so Godot uses `/health` to know whether it runs.
