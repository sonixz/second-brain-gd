# Troubleshooting

Logs: `%LOCALAPPDATA%\SecondBrainGD\logs\bootstrap.log` (every setup event, including pip output) and
`server.log` (the API). On the welcome screen, **Check prerequisites** lists every Python that was tried.

## "No compatible Python found"

- Install Python 3.12 or 3.13 from https://www.python.org/downloads/ and tick **Add python.exe to PATH**.
- Restart Godot after installing (PATH is read at start).
- Or paste the full path of `python.exe` in **Check prerequisites → Use & re-check**
  (saved in Godot's `user://settings.cfg`), or set the environment variable `SBGD_PYTHON`.
- Python 3.14 and newer are refused until they are tested; 3.11 and older are too old.

## Typing `python` opens the Microsoft Store

That is the Windows "App execution alias" with no Python installed. Install Python, or disable the alias in
*Settings → Apps → Advanced app settings → App execution aliases*.

## Microsoft Store Python

The Store Python redirects folders it *creates* under `%LOCALAPPDATA%` to a private package folder, invisible to
other programs. Godot therefore creates the data folder before starting the bootstrap, and writes then land in the
real folder (verified on Windows 11 with Python 3.13). From the command line, create the folder first:

```powershell
mkdir $env:LOCALAPPDATA\SecondBrainGD
python engine\bootstrap.py setup
```

The bootstrap refuses to start with a clear message if this would happen.

## "This Python has no venv/ensurepip module" (Linux)

`sudo apt install python3.12-venv` (or the package for your version).

## Dependencies step fails

- It needs internet access to `pypi.org` and `files.pythonhosted.org` the first time.
- Behind a proxy, set `HTTPS_PROXY` before starting Godot.
- A hash mismatch means a download was altered; nothing is installed in that case. Retry.
- Press **Retry**: the steps already done are skipped.

## Port already in use

The API uses port 8765 by default. If it is busy, the next free port (up to +19) is used and a warning is shown.
To choose another port, edit `config.json` in the data folder: `{"port": 9000}`.

## The console says "Engine unreachable"

Press **Restart engine** (it runs the fast setup again). Check `logs/server.log` for the reason.

## Start over completely

Close the app, delete `%LOCALAPPDATA%\SecondBrainGD` (this deletes your local database), run Setup again.
To rebuild only the environment, delete the `.venv` folder in it; the database is kept.

## An API process seems to stay alive

It stops by itself within about a second after Godot exits. Otherwise:
`python engine\bootstrap.py stop --data-dir %LOCALAPPDATA%\SecondBrainGD`.
