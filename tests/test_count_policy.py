import csv
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from madrid_demography.count_policy import (
    validate_policy,
    verify_group_counts,
    load_controls,
    export_candidate,
)
from madrid_demography.io import ContractError


class CountPolicyTests(unittest.TestCase):
    def test_matching_totals_do_not_allow_missing_controls_or_negative_values(self):
        key = (1, 0, "ESPANOLESHOMBRES")
        self.assertEqual(verify_group_counts({key: 5}, {key: 5}, {key}), 1)
        for known, controls in [
            ({key: 5}, {}),
            ({key: 5}, {key: 6}),
            ({key: -1}, {key: -1}),
            ({key: True}, {key: True}),
        ]:
            with self.assertRaises(ContractError):
                verify_group_counts(known, controls, {key})

    def test_truncated_wrong_date_and_duplicate_responses_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            policy = json.loads(Path("config/blank-count-policy.json").read_text())
            original = policy["controls"][0]
            receipt = json.loads(Path(original["receipt"]).read_text())
            response = json.loads(
                gzip.decompress(Path(original["path"]).read_bytes()).decode(
                    receipt["response_encoding"]
                )
            )
            for kind in ("truncated", "wrong_date", "duplicate", "missing"):
                candidate = json.loads(json.dumps(response))
                if kind == "truncated":
                    candidate["errorTitulo"] = "Only first 1000 rows"
                elif kind == "wrong_date":
                    candidate["mapaEpigrafesFiltros"]["Año: "] = "2025"
                elif kind == "duplicate":
                    candidate["listaConsulta"].append(candidate["listaConsulta"][0])
                else:
                    candidate["listaConsulta"].pop()
                raw = json.dumps(candidate).encode("utf-8")
                path = folder / "response.json.gz"
                path.write_bytes(gzip.compress(raw))
                receipt.update(
                    sha256=hashlib.sha256(raw).hexdigest(), response_encoding="utf-8"
                )
                receipt_path = folder / "receipt.json"
                receipt_path.write_text(json.dumps(receipt))
                policy["controls"] = [
                    dict(
                        path=str(path),
                        receipt=str(receipt_path),
                        sha256=receipt["sha256"],
                    )
                ]
                with self.assertRaises(ContractError):
                    load_controls(policy)

    def test_policy_cannot_transfer_to_another_vintage_or_changed_source(self):
        policy = json.loads(Path("config/blank-count-policy.json").read_text())
        source = dict(
            id=policy["source_id"],
            reference_date="2015-01-01",
            sha256=policy["source_sha256"],
        )
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "changed.csv"
            raw.write_text("changed source")
            with self.assertRaisesRegex(ContractError, "checksum changed"):
                validate_policy(policy, source, raw)
            source["reference_date"] = "2014-01-01"
            with self.assertRaisesRegex(ContractError, "source scope"):
                validate_policy(policy, source, raw)

    def test_candidate_preserves_raw_status_and_out_of_scope_blanks(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "audit.csv"
            output = Path(directory) / "candidate.csv"
            header = [
                "source_sha256",
                "reference_date",
                "population_status",
                "cohort_status",
                "age",
                "population",
            ]
            with source.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(header)
                writer.writerows(
                    [
                        ["sha", "2015-01-01", "unknown_blank", "eligible", "5", ""],
                        [
                            "sha",
                            "2015-01-01",
                            "unknown_blank",
                            "excluded_terminal",
                            "95",
                            "",
                        ],
                        ["sha", "2015-01-01", "observed", "eligible", "5", "7"],
                    ]
                )
            policy = dict(
                id="test-policy", source_sha256="sha", reference_date="2015-01-01"
            )
            sha = hashlib.sha256(source.read_bytes()).hexdigest()
            report = export_candidate(source, sha, output, policy, 1)
            self.assertEqual(report["inferred_zero_cells"], 1)
            with output.open() as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(
                (rows[0]["population"], rows[0]["raw_population_status"]),
                ("0", "unknown_blank"),
            )
            self.assertEqual(rows[1]["population"], "")
            self.assertEqual(rows[2]["population"], "7")
            previous = output.read_bytes()
            with self.assertRaises(ContractError):
                export_candidate(source, sha, output, policy, 2)
            self.assertEqual(output.read_bytes(), previous)
            with self.assertRaises(ContractError):
                export_candidate(source, "changed-hash", output, policy, 1)
