"""Enforce initial-data, geometry and typical-profile gzip limits in CI."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "web" / "data"
count = 0
for path in ROOT.glob("**/manifest.json"):
    manifest = json.loads(path.read_text())
    assert manifest["performance"]["initial_gzip_bytes"] < 500000
    for budget in manifest["performance"]["budgets"]:
        assert budget["passed"], budget
    for artifact in manifest["artifacts"].values():
        target = path.parent / artifact["url"]
        assert hashlib.sha256(target.read_bytes()).hexdigest() == artifact["sha256"]
    count += 1
assert count, "build fixtures before checking budgets"
print(f"Payload budgets and checksums passed for {count} manifests")
