"""Second Brain GD local engine.

Everything under ``engine.paths``, ``engine.events``, ``engine.procutil``,
``engine.database`` and ``engine.installer`` uses the Python standard library
only, so the bootstrap can run before any dependency is installed.
``engine.api`` and ``engine.monitoring`` need the locked dependencies.
"""

VERSION = "0.1.0"

# Supported interpreter range. Tested on 3.12 (Linux) and 3.13 (Windows).
MIN_PYTHON = (3, 12)
MAX_PYTHON_EXCLUSIVE = (3, 14)
