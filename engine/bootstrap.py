"""Second Brain GD bootstrap entry point.

Run with any Python 3. The version check below uses old syntax on purpose so
that an incompatible interpreter gets a clear message instead of a crash.

    python engine/bootstrap.py detect
    python engine/bootstrap.py setup [--data-dir DIR] [--events FILE] [--port N] [--parent-pid PID]
    python engine/bootstrap.py status [--data-dir DIR]
    python engine/bootstrap.py stop   [--data-dir DIR]
"""
import json
import os
import sys

MIN = (3, 12)
MAX_EXCLUSIVE = (3, 14)
DOWNLOAD_URL = "https://www.python.org/downloads/"


def _version_ok():
    return MIN <= sys.version_info[:2] < MAX_EXCLUSIVE


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "detect":
        info = {
            "executable": sys.executable,
            "version": "%d.%d.%d" % sys.version_info[:3],
            "compatible": _version_ok(),
            "supported_range": ">=%d.%d,<%d.%d" % (MIN + MAX_EXCLUSIVE),
            "platform": sys.platform,
        }
        # The app's own Python (Loop 28) needs no venv: its marker sits next to it.
        bundled = any(os.path.isfile(os.path.join(p, "sbgd-runtime.json")) for p in {sys.prefix, sys.base_prefix})
        info["bundled"] = bundled
        if _version_ok():
            try:
                import ensurepip  # noqa: F401
                import venv  # noqa: F401
                info["venv_available"] = True
            except ImportError:
                info["venv_available"] = bundled
        print(json.dumps(info))
        return 0 if info["compatible"] else 3
    if not _version_ok():
        sys.stderr.write(
            "Second Brain GD needs Python %d.%d to %d.%d; this is %d.%d.%d at %s.\n"
            "Install a supported version from %s\n"
            % (MIN + (MAX_EXCLUSIVE[0], MAX_EXCLUSIVE[1] - 1) + tuple(sys.version_info[:3]) + (sys.executable, DOWNLOAD_URL))
        )
        return 3
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from engine.installer.cli import run

    return run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
