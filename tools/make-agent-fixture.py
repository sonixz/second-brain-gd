"""Rebuilds tests/fixtures/agents/fake-codex.tar.gz and manifest.json from fake_codex.py (deterministic)."""
import gzip
import hashlib
import io
import json
import tarfile
from pathlib import Path

D = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "agents"
data = (D / "fake_codex.py").read_bytes()
buf = io.BytesIO()
with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT) as t:
    ti = tarfile.TarInfo("bin/fake-codex.py")
    ti.size, ti.mtime, ti.mode = len(data), 0, 0o755
    t.addfile(ti, io.BytesIO(data))
gz = gzip.compress(buf.getvalue(), mtime=0)
(D / "fake-codex.tar.gz").write_bytes(gz)
spec = {"url": "fake-codex.tar.gz", "sha256": hashlib.sha256(gz).hexdigest(), "size": len(gz),
        "binary": "bin/fake-codex.py"}
plats = ["windows-x86_64", "linux-x86_64", "macos-aarch64", "macos-x86_64", "linux-aarch64", "windows-aarch64"]
(D / "manifest.json").write_text(json.dumps({
    "_comment": "Test fixture: a fake app-server package (bin/fake-codex.py). Regenerate with tools/make-agent-fixture.py after editing fake_codex.py.",
    "name": "fake-codex", "version": "test-1", "platforms": {k: spec for k in plats}}, indent=2))
print(spec["sha256"])
