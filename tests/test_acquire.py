from __future__ import annotations

import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from madrid_demography.acquire import acquire


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, length=None):
        super().__init__(body)
        self.headers = {"Content-Type": "application/json"}
        if length is not None:
            self.headers["Content-Length"] = str(length)

    def geturl(self):
        return "https://example.org/final"


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = {
            "id": "test",
            "url": "https://example.org/data",
            "kind": "json",
            "sha256": None,
        }

    def download(self, body, **kwargs):
        return acquire(
            self.source, self.root, opener=lambda *a, **k: Response(body), **kwargs
        )

    def test_repeated_acquisition_preserves_bytes_and_receipts(self):
        first = self.download(b"[1, 2]")
        second = self.download(b"[1, 2]")
        self.assertEqual(first["sha256"], hashlib.sha256(b"[1, 2]").hexdigest())
        self.assertEqual(first["path"], second["path"])
        self.assertEqual(len(list((self.root / "test").glob("*.json"))), 3)
        self.assertEqual(first["status"], "unreviewed")

    def test_checksum_drift_is_failed_and_original_preserved(self):
        self.source["sha256"] = hashlib.sha256(b"[1]").hexdigest()
        original = self.download(b"[1]")
        changed = self.download(b"[2]")
        self.assertEqual(original["status"], "pinned")
        self.assertEqual(changed["status"], "failed")
        self.assertIn("checksum changed", changed["error"])
        self.assertEqual(Path(original["path"]).read_bytes(), b"[1]")

    def test_oversized_response_is_not_installed(self):
        result = self.download(b"[123456]", max_bytes=4)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("path", result)

    def test_html_error_page_cannot_be_treated_as_json(self):
        result = self.download(b"<!DOCTYPE html><html>Denied</html>")
        self.assertEqual(result["status"], "failed")
        self.assertIn("HTML response", result["error"])

    def test_truncated_download_fails(self):
        result = acquire(
            self.source, self.root, opener=lambda *a, **k: Response(b"[1]", length=40)
        )
        self.assertEqual(result["status"], "failed")
        self.assertIn("truncated", result["error"])

    def test_network_failure_creates_receipt(self):
        def fail(*a, **k):
            raise OSError("unreachable")

        result = acquire(self.source, self.root, opener=fail)
        self.assertEqual(result["status"], "failed")
        self.assertEqual(len(list((self.root / "test").glob("receipt-*.json"))), 1)
