"""Immutable, explicit-review acquisition. No guessed historical URLs."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import yaml
from .io import ContractError


def digest(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def read_lock(path):
    data = yaml.safe_load(Path(path).read_text())
    if data.get("version") != 1 or not isinstance(data.get("sources"), list):
        raise ContractError("unsupported source lock")
    ids = [s["id"] for s in data["sources"]]
    if len(set(ids)) != len(ids):
        raise ContractError("duplicate source IDs")
    return data


def acquire(source, root):
    """Unpinned resources are staged for review; never become verified automatically."""
    sid = source["id"]
    if not sid.replace("-", "").replace("_", "").isalnum():
        raise ContractError("unsafe source ID")
    url = source["url"]
    if urlparse(url).scheme != "https":
        raise ContractError("sources require HTTPS")
    root = Path(root) / sid
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat()
    temporary = root / ("incoming-" + hashlib.sha256(stamp.encode()).hexdigest()[:12])
    try:
        with (
            urlopen(
                Request(url, headers={"User-Agent": "MadridDemographicAudit/0.2"}),
                timeout=60,
            ) as response,
            temporary.open("xb") as f,
        ):
            headers = dict(response.headers)
            while block := response.read(1024 * 1024):
                f.write(block)
        sha, size = digest(temporary), temporary.stat().st_size
        expected_size = headers.get("Content-Length")
        if expected_size and int(expected_size) != size:
            raise ContractError("truncated download")
        pinned = source.get("sha256") == sha and source.get("bytes") == size
        destination = root / sha
        if destination.exists():
            temporary.unlink()
        else:
            temporary.rename(destination)
        receipt = {
            "id": sid,
            "url": url,
            "resolved_url": response.url,
            "sha256": sha,
            "bytes": size,
            "retrieved_at": stamp,
            "path": str(destination),
            "verified": pinned,
            "headers": {
                k: v
                for k, v in headers.items()
                if k.lower()
                in {"content-type", "content-length", "last-modified", "etag"}
            },
        }
        receipt_path = root / (sha + ".receipt.json")
        if not receipt_path.exists():
            receipt_path.write_text(json.dumps(receipt, indent=2))
        if source.get("sha256") and not pinned:
            raise ContractError(
                f"{sid}: source changed; staged {sha} ({size} bytes) for review"
            )
        return receipt
    finally:
        if temporary.exists():
            temporary.unlink()


def discover_catalogue(path):
    """Archive XML separately; return resource URLs for manual manifest selection."""
    tree = ET.parse(path)
    urls = set()
    for node in tree.iter():
        for value in [node.text or "", *node.attrib.values()]:
            value = value.strip()
            if value.startswith("https://"):
                urls.add(value)
    return sorted(urls)


def verify_sources(lock_path, root):
    results = []
    for source in read_lock(lock_path)["sources"]:
        sha = source.get("sha256")
        path = Path(root) / source["id"] / str(sha)
        ok = bool(
            sha
            and path.exists()
            and digest(path) == sha
            and path.stat().st_size == source.get("bytes")
        )
        results.append(
            {
                "id": source["id"],
                "passed": ok,
                "reference_date": source.get("reference_date"),
                "reviewed_by": source.get("reviewed_by"),
                "license": source.get("license"),
            }
        )
    return results
