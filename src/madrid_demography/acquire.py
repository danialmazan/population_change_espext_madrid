"""Bounded, content-addressed official source acquisition (standard library only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from xml.etree import ElementTree


class AcquisitionError(ValueError):
    pass


def load_manifest(path: Path) -> dict:
    # JSON is a YAML 1.2 subset; avoid a runtime YAML dependency.
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != 1:
        raise AcquisitionError("unsupported manifest version")
    seen = set()
    for source in manifest["sources"]:
        if not re.fullmatch(r"[a-z0-9_-]+", source["id"]) or source["id"] in seen:
            raise AcquisitionError("invalid or duplicate source ID")
        seen.add(source["id"])
        if urlsplit(source["url"]).scheme != "https":
            raise AcquisitionError("sources must use HTTPS")
        if source.get("sha256") is not None and not re.fullmatch(
            r"[a-f0-9]{64}", source["sha256"]
        ):
            raise AcquisitionError("invalid SHA-256 pin")
    return manifest


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            if key == "href" and value:
                self.urls.add(value)


def inspect_payload(path: Path, kind: str, base_url: str) -> dict:
    if kind == "zip":
        with zipfile.ZipFile(path) as archive:
            return {
                "members": archive.namelist(),
                "uncompressed_bytes": sum(x.file_size for x in archive.infolist()),
            }
    raw = path.read_bytes()
    if not raw:
        raise AcquisitionError("empty response")
    if kind != "html" and re.search(rb"(?i)<!doctype html|<html[\s>]", raw[:2048]):
        raise AcquisitionError("HTML response returned instead of source data")
    if kind == "pdf":
        if not raw.startswith(b"%PDF-"):
            raise AcquisitionError("invalid PDF signature")
        return {"signature": "PDF"}
    if kind == "csv":
        # Encoding and delimiter are recorded by a separate explicit profile step.
        return {"header_bytes_hex": raw.splitlines()[0].hex()}
    if kind == "json":
        value = json.loads(raw)
        return {
            "entries": len(value) if isinstance(value, (list, dict)) else None,
            "sample": value[:12] if isinstance(value, list) else None,
        }
    if kind == "xml":
        tree = ElementTree.fromstring(raw)
        urls = {
            v
            for node in tree.iter()
            for v in (*node.attrib.values(), node.text or "")
            if v.startswith(("https://", "http://", "/dataset/"))
        }
        return {"resource_urls": sorted(urljoin(base_url, v) for v in urls)}
    if kind == "html":
        parser = Links()
        parser.feed(raw.decode("utf-8", errors="replace"))
        return {
            "resource_urls": sorted(
                {
                    urljoin(base_url, v)
                    for v in parser.urls
                    if any(
                        token in v.lower()
                        for token in (
                            "download",
                            "resource",
                            ".zip",
                            ".csv",
                            ".rdf",
                            "historico",
                        )
                    )
                }
            )
        }
    raise AcquisitionError(f"unsupported source kind: {kind}")


def acquire(
    source: dict,
    root: Path,
    *,
    max_bytes: int = 128 * 1024 * 1024,
    timeout: int = 45,
    opener=urlopen,
) -> dict:
    """Never replace bytes or silently accept drift against a reviewed checksum."""
    folder = root / source["id"]
    folder.mkdir(parents=True, exist_ok=True)
    receipt = {
        "source_id": source["id"],
        "requested_url": source["url"],
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "expected_sha256": source.get("sha256"),
        "status": "failed",
    }
    try:
        with tempfile.TemporaryFile(dir=folder) as staging:
            request = Request(
                source["url"],
                headers={"User-Agent": "MadridDemography-source-audit/0.1"},
            )
            with opener(request, timeout=timeout) as response:
                receipt.update(
                    final_url=response.geturl(),
                    http_status=response.status,
                    content_type=response.headers.get("Content-Type"),
                    content_length=response.headers.get("Content-Length"),
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                )
                length = response.headers.get("Content-Length")
                if length and int(length) > max_bytes:
                    raise AcquisitionError(
                        f"Content-Length exceeds {max_bytes} byte limit"
                    )
                digest, count = hashlib.sha256(), 0
                while chunk := response.read(1024 * 1024):
                    count += len(chunk)
                    if count > max_bytes:
                        raise AcquisitionError(
                            f"response exceeds {max_bytes} byte limit"
                        )
                    digest.update(chunk)
                    staging.write(chunk)
                if length and count != int(length):
                    raise AcquisitionError(
                        "truncated response: Content-Length mismatch"
                    )
            checksum = digest.hexdigest()
            target = folder / f"{checksum}.{source['kind']}"
            staging.seek(0)
            try:
                with target.open("xb") as out:
                    while chunk := staging.read(1024 * 1024):
                        out.write(chunk)
            except FileExistsError:
                if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
                    raise AcquisitionError("existing content-addressed file is corrupt")
            receipt.update(sha256=checksum, bytes=count, path=target.as_posix())
            receipt["inspection"] = inspect_payload(
                target, source["kind"], receipt["final_url"]
            )
            if source.get("sha256") and source["sha256"] != checksum:
                raise AcquisitionError(
                    "checksum changed; review new bytes before updating the pin"
                )
            receipt["status"] = "pinned" if source.get("sha256") else "unreviewed"
    except Exception as exc:
        if isinstance(exc, HTTPError):
            receipt["http_status"] = exc.code
        receipt["error"] = f"{type(exc).__name__}: {exc}"
    receipt_path = folder / f"receipt-{uuid.uuid4().hex}.json"
    with receipt_path.open("x", encoding="utf-8") as handle:
        json.dump(receipt, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("sources.lock.yml"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--report", type=Path, default=Path("data/audit/acquisition.json")
    )
    parser.add_argument(
        "--source", action="append", help="source ID (repeatable); default: all"
    )
    parser.add_argument("--max-bytes", type=int, default=128 * 1024 * 1024)
    args = parser.parse_args()
    manifest = load_manifest(args.manifest)
    selected = set(args.source or [s["id"] for s in manifest["sources"]])
    if selected - {s["id"] for s in manifest["sources"]}:
        parser.error("unknown source ID")
    if args.max_bytes <= 0:
        parser.error("max-bytes must be positive")
    receipts = []
    for source in manifest["sources"]:
        if source["id"] in selected:
            receipt = acquire(source, args.raw_dir, max_bytes=args.max_bytes)
            receipts.append(receipt)
            print(
                f"{source['id']}: {receipt['status']} {receipt.get('error', receipt.get('sha256', ''))}",
                flush=True,
            )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "dataset_kind": "audit_only",
        "production_ready": False,
        "sources": receipts,
    }
    args.report.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return int(any(r["status"] == "failed" for r in receipts))


if __name__ == "__main__":
    raise SystemExit(main())
