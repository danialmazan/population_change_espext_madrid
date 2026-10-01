import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from madrid_demography.acquisition import acquire
from madrid_demography.io import ContractError


class Response(io.BytesIO):
    def __init__(self, data, reported_length=None):
        super().__init__(data)
        self.headers = {
            "Content-Length": str(
                len(data) if reported_length is None else reported_length
            )
        }
        self.url = "https://example.test/resource"


class AcquisitionTests(unittest.TestCase):
    def test_first_download_is_unverified_and_pinned_repeat_does_not_replace_receipt(
        self,
    ):
        data = b"official fixture"
        sha = hashlib.sha256(data).hexdigest()
        source = {
            "id": "fixture",
            "url": "https://example.test/resource",
            "sha256": None,
            "bytes": None,
        }
        with tempfile.TemporaryDirectory() as root:
            with patch(
                "madrid_demography.acquisition.urlopen", return_value=Response(data)
            ):
                receipt = acquire(source, root)
            self.assertFalse(receipt["verified"])
            stored = Path(root) / "fixture" / (sha + ".receipt.json")
            original = stored.read_bytes()
            source.update(sha256=sha, bytes=len(data))
            with patch(
                "madrid_demography.acquisition.urlopen", return_value=Response(data)
            ):
                self.assertTrue(acquire(source, root)["verified"])
            self.assertEqual(stored.read_bytes(), original)

    def test_changed_source_is_staged_without_replacing_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            original = b"old"
            oldsha = hashlib.sha256(original).hexdigest()
            location = Path(root) / "fixture"
            location.mkdir()
            (location / oldsha).write_bytes(original)
            source = {
                "id": "fixture",
                "url": "https://example.test/resource",
                "sha256": oldsha,
                "bytes": len(original),
            }
            with patch(
                "madrid_demography.acquisition.urlopen", return_value=Response(b"new")
            ):
                with self.assertRaisesRegex(ContractError, "staged"):
                    acquire(source, root)
            self.assertEqual((location / oldsha).read_bytes(), original)
            newsha = hashlib.sha256(b"new").hexdigest()
            self.assertFalse(
                json.loads((location / (newsha + ".receipt.json")).read_text())[
                    "verified"
                ]
            )

    def test_truncated_download_never_becomes_content_addressed_source(self):
        with tempfile.TemporaryDirectory() as root:
            with patch(
                "madrid_demography.acquisition.urlopen",
                return_value=Response(b"short", 100),
            ):
                with self.assertRaisesRegex(ContractError, "truncated"):
                    acquire(
                        {"id": "fixture", "url": "https://example.test/resource"}, root
                    )
            self.assertEqual(list((Path(root) / "fixture").iterdir()), [])
