# Event protocol: bootstrap → Godot

The bootstrap writes one JSON object per line (JSON Lines, UTF-8, `\n`) to the file given with `--events`.
Godot creates the file path inside `<data dir>/runtime/` and polls it every 100 ms, reading only new bytes and
keeping any partial last line for the next read. The same events go to `logs/bootstrap.log`, and every event
except `log` lines is stored in the `system_events` table once the database exists (earlier events are
buffered and flushed then).

## Fields

| Field | Type | Always | Meaning |
|---|---|---|---|
| `v` | int | yes | protocol version, currently `1` |
| `timestamp` | string | yes | UTC ISO-8601 with milliseconds, `Z` suffix |
| `run_id` | string | yes | one id per bootstrap run |
| `component` | string | yes | `bootstrap`, `python`, `directories`, `venv`, `dependencies`, `database`, `service`, `health` |
| `stage` | string | yes | sub-step, e.g. `begin`, `check`, `create`, `pip`, `download`, `migrate`, `spawn`, `verify`, `done` |
| `status` | string | yes | `started`, `progress`, `log`, `ok`, `skipped`, `warning`, `unavailable` (an optional step ended without its feature, setup goes on), `error` |
| `message` | string | yes | human-readable, shown in the UI |
| `progress` | float | no | overall progress 0..1, never decreasing |
| `details` | object | no | extra data: `hint` (what to do), `tail` (last log lines), paths, versions |

## Rules

- Every step starts with `started` and ends with exactly one of `ok`, `skipped` or `error`.
- `log` lines are raw tool output (pip). They are not persisted in SQLite.
- The run ends with `component: "bootstrap", stage: "done"`, status `ok` or `error`. `ok` is only emitted after
  the health step verified the running API.
- If the process exits without a final event, Godot reports the exit code itself.

## Example

```json
{"v":1,"timestamp":"2026-11-03T00:55:55.843Z","run_id":"0c87ff6cbb56","component":"health","stage":"verify","status":"ok","message":"/health OK, database ok, auth enforced, pid 123421","progress":1.0,"details":{"port":8765,"pid":123421}}
```
