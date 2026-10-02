"""Verify real research artifact/download hashes and measured lazy-load budgets."""

import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "data/derived/research-site"
checks = []
for path in sorted((SITE / "data").glob("*/manifest.json")):
    manifest = json.loads(path.read_bytes())
    assert manifest["dataset_kind"] == "research"
    assert manifest["release_passed"] is False
    assert manifest["performance"]["initial_gzip_bytes"] <= 500000
    inventory = json.loads(
        (path.parent / manifest["audit_inventory"]["url"]).read_bytes()
    )
    for budget in inventory["budgets"]:
        assert budget["passed"], budget
    for ref in {**inventory["artifacts"], **manifest["artifacts"]}.values():
        body = (path.parent / ref["url"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == ref["sha256"]
        assert len(body) == ref["bytes"]
        assert len(gzip.compress(body, mtime=0)) == ref["gzip_bytes"]
    for key, ref in manifest["download_checksums"].items():
        body = (path.parent / manifest["downloads"][key]).read_bytes()
        assert len(body) == ref["bytes"]
        assert hashlib.sha256(body).hexdigest() == ref["sha256"]
    initial = manifest["performance"]["initial_gzip_bytes"] + len(
        gzip.compress(path.read_bytes(), mtime=0)
    )
    initial += manifest["geometry"][manifest["default_level"]]["gzip_bytes"]
    index = json.loads((path.parent / manifest["index"]["url"]).read_bytes())
    first = next(a for a in index if a["level"] == manifest["default_level"])
    initial += inventory["profiles"][first["id"]]["gzip_bytes"]
    assert initial <= 500000, (
        "Typical data loading, including manifest, map and first profile",
        initial,
    )
    checks.append(
        {
            "window": path.parent.name,
            "passed": True,
            "initial_index_indicator_gzip_bytes": manifest["performance"][
                "initial_gzip_bytes"
            ],
            "typical_data_gzip_bytes": initial,
            "artifact_count": len(manifest["artifacts"]),
        }
    )
(ROOT / "docs/audit/research-performance.json").write_text(
    json.dumps(checks, indent=2) + "\n"
)
print(json.dumps(checks, indent=2))
