"""Compare raw municipal sums with independently published legal INE totals."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import posixpath
import re
import zipfile
from xml.etree import ElementTree as ET
from pathlib import Path

from .acquire import load_manifest
from .profile import latest_receipt


def verified_path(source: dict, root: Path) -> Path:
    receipt = latest_receipt(root, source)
    if not receipt or receipt["status"] == "failed" or not source.get("sha256"):
        raise ValueError(f"missing pinned successful acquisition: {source['id']}")
    path = Path(receipt["path"])
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()
    if checksum != receipt["sha256"] or checksum != source["sha256"]:
        raise ValueError(f"checksum mismatch: {source['id']}")
    return path


def published_totals(path: Path, years: set[int]) -> dict[int, dict[str, int]]:
    totals = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter=";"):
            if row["Municipios"] != "28079 Madrid" or int(row["Periodo"]) not in years:
                continue
            year, sex = int(row["Periodo"]), row["Sexo"]
            if sex in totals.setdefault(year, {}):
                raise ValueError("duplicate published total")
            totals[year][sex] = int(row["Total"].replace(".", ""))
    for year in years:
        if set(totals.get(year, {})) != {"Total", "Hombres", "Mujeres"}:
            raise ValueError(f"missing published dimensions for {year}")
        if totals[year]["Total"] != totals[year]["Hombres"] + totals[year]["Mujeres"]:
            raise ValueError(f"published sex totals do not reconcile for {year}")
    return totals


def comparisons(profiles: list[dict], published: dict) -> list[dict]:
    output = []
    for profile in profiles:
        year = int(profile["reference_date"][:4])
        if year not in published:
            continue
        c = profile["known_population_by_column"]
        known = {
            "Hombres": c["ESPANOLESHOMBRES"] + c["EXTRANJEROSHOMBRES"],
            "Mujeres": c["ESPANOLESMUJERES"] + c["EXTRANJEROSMUJERES"],
            "Total": profile["known_population_sum"],
        }
        differences = {sex: known[sex] - published[year][sex] for sex in known}
        output.append(
            {
                "reference_date": profile["reference_date"],
                "source_id": profile["source_id"],
                "source_sha256": profile["sha256"],
                "raw_known_counts": known,
                "ine_legal_totals": published[year],
                "differences": differences,
                "difference_percent_total": 100
                * differences["Total"]
                / published[year]["Total"],
                "blank_count_cells": sum(profile["blank_count_cells"].values()),
                "status": "exact_match"
                if not any(differences.values())
                else "different_series_unresolved",
                "counts_adjusted": False,
            }
        )
    return sorted(output, key=lambda x: x["reference_date"])


def workbook_rows(path: Path, sheet_name: str) -> list[tuple[int, dict[str, str]]]:
    """Read XLSX cell values without a spreadsheet runtime dependency."""
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    relation_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    with zipfile.ZipFile(path) as archive:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        matches = [
            s
            for s in workbook.findall("m:sheets/m:sheet", ns)
            if s.get("name") == sheet_name
        ]
        if len(matches) != 1:
            raise ValueError(f"missing or duplicate workbook year {sheet_name}")
        relation = matches[0].get(f"{{{relation_ns}}}id")
        relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        target = next(r.get("Target") for r in relationships if r.get("Id") == relation)
        sheet_path = (
            target.lstrip("/")
            if target.startswith("/")
            else posixpath.normpath("xl/" + target)
        )
        shared = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = [
                "".join(t.itertext())
                for t in ET.fromstring(archive.read("xl/sharedStrings.xml"))
            ]
        sheet = ET.fromstring(archive.read(sheet_path))
        rows = []
        for row in sheet.findall("m:sheetData/m:row", ns):
            values = {}
            for cell in row.findall("m:c", ns):
                column = re.match(r"[A-Z]+", cell.get("r", ""))[0]
                value = cell.findtext("m:v", "", ns)
                if cell.get("t") == "s":
                    value = shared[int(value)]
                elif cell.get("t") == "inlineStr":
                    value = "".join(cell.find("m:is", ns).itertext())
                values[column] = value
            rows.append((int(row.get("r")), values))
        return rows


def municipal_totals(path: Path, year: int) -> dict:
    rows = workbook_rows(path, str(year))
    if not any(f"1 de enero de {year}" in r.get("A", "") for _, r in rows):
        raise ValueError("municipal workbook reference date unverified")
    matches = [
        (line, row)
        for line, row in rows
        if row.get("A") == "Ciudad de Madrid" and row.get("C", "").isdigit()
    ]
    if len(matches) != 1:
        raise ValueError("missing or duplicate municipal city total")
    line, city = matches[0]
    columns = {
        "Total": "C",
        "Hombres": "D",
        "Mujeres": "E",
        "ESP_total": "G",
        "ESP_male": "H",
        "ESP_female": "I",
        "EXT_total": "K",
        "EXT_male": "L",
        "EXT_female": "M",
        "no_consta_total": "O",
        "no_consta_male": "P",
        "no_consta_female": "Q",
    }
    if not any(row.get("O") == "No consta" for _, row in rows):
        raise ValueError("missing explicit No consta nationality header")
    counts = {key: int(city[col]) for key, col in columns.items()}
    for total, male, female in (
        ("Total", "Hombres", "Mujeres"),
        ("ESP_total", "ESP_male", "ESP_female"),
        ("EXT_total", "EXT_male", "EXT_female"),
        ("no_consta_total", "no_consta_male", "no_consta_female"),
    ):
        if counts[total] != counts[male] + counts[female]:
            raise ValueError("municipal workbook sex identity failed")
    if (
        counts["Total"]
        != counts["ESP_total"] + counts["EXT_total"] + counts["no_consta_total"]
    ):
        raise ValueError("municipal nationality total identity failed")
    sections = {}
    for _, row in rows:
        if re.fullmatch(r"\d{5}", row.get("B", "")) and row.get("C", "").isdigit():
            code = "28079" + row["B"]
            if code in sections:
                raise ValueError("duplicate municipal section")
            sections[code] = {name: int(row[col]) for name, col in columns.items()}
    return {
        "sheet": str(year),
        "city_row": line,
        "city_counts": counts,
        "nationality_groups_gap": counts["Total"]
        - counts["ESP_total"]
        - counts["EXT_total"],
        "section_rows": len(sections),
        "sections": sections,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("sources.lock.yml"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument(
        "--profiles", type=Path, default=Path("docs/audit/padron_profiles.json")
    )
    parser.add_argument(
        "--report", type=Path, default=Path("docs/audit/reconciliation.json")
    )
    args = parser.parse_args()
    sources = {s["id"]: s for s in load_manifest(args.manifest)["sources"]}
    profiles = json.loads(args.profiles.read_text())["profiles"]
    for profile in profiles:
        source = sources[profile["source_id"]]
        if profile.get("sha256") != source["sha256"]:
            raise ValueError("profile and source manifest differ")
    totals = published_totals(
        verified_path(sources["ine_approved_population"], args.raw_dir), {2015, 2025}
    )
    rows = comparisons(profiles, totals)
    if len(rows) != 2:
        raise ValueError("both endpoint comparisons are required")
    municipal_comparisons = []
    for year, id in (
        (2015, "municipal_section_totals_2009_2019"),
        (2025, "municipal_section_totals_2020_2026"),
    ):
        source = sources[id]
        municipal = municipal_totals(verified_path(source, args.raw_dir), year)
        profile = next(
            p for p in profiles if p["source_id"] == f"padron_january_{year}"
        )
        raw_sections = {
            f"28079{int(code) // 1000:02d}{int(code) % 1000:03d}": count
            for code, count in profile["known_population_by_section"].items()
        }
        differences = {
            code: raw_sections.get(code, 0) - counts["Total"]
            for code, counts in municipal["sections"].items()
        }
        summary = next(r for r in rows if r["reference_date"].startswith(str(year)))
        revised = municipal["city_counts"]
        c = profile["known_population_by_column"]
        canonical = {
            "ESPANOLESHOMBRES": revised["ESP_male"],
            "ESPANOLESMUJERES": revised["ESP_female"],
            "EXTRANJEROSHOMBRES": revised["EXT_male"] + revised["no_consta_male"],
            "EXTRANJEROSMUJERES": revised["EXT_female"] + revised["no_consta_female"],
        }
        accounting = (
            sum(differences.values())
            + sum(
                count
                for code, count in raw_sections.items()
                if code not in municipal["sections"]
            )
            + profile.get("invalid_geography_known_population", 0)
        )
        if accounting != summary["raw_known_counts"]["Total"] - revised["Total"]:
            raise ValueError(
                "section discrepancy accounting did not reconcile to city difference"
            )
        municipal_comparisons.append(
            {
                "reference_date": profile["reference_date"],
                "source_id": id,
                "source_sha256": source["sha256"],
                "sheet": municipal["sheet"],
                "city_row": municipal["city_row"],
                "published_city_counts": municipal["city_counts"],
                "raw_minus_published": {
                    k: summary["raw_known_counts"][k] - municipal["city_counts"][k]
                    for k in ("Total", "Hombres", "Mujeres")
                },
                "nationality_groups_gap": municipal["nationality_groups_gap"],
                "nationality_groups_gap_explained_by_no_consta": municipal[
                    "nationality_groups_gap"
                ]
                == revised["no_consta_total"],
                "canonical_EXT_definition": "Published foreign plus No consta, matching the raw source's inclusion of unknown nationality in EXT",
                "raw_minus_revised_by_count_column": {
                    k: c[k] - canonical[k] for k in canonical
                },
                "section_discrepancy_accounting_verified": True,
                "published_section_rows": municipal["section_rows"],
                "published_section_total_sum": sum(
                    v["Total"] for v in municipal["sections"].values()
                ),
                "raw_ids_not_in_published_sections": sorted(
                    set(raw_sections) - set(municipal["sections"])
                ),
                "published_ids_not_in_raw_sections": sorted(
                    set(municipal["sections"]) - set(raw_sections)
                ),
                "matching_section_total_count": sum(
                    d == 0 for d in differences.values()
                ),
                "differing_section_totals": {k: d for k, d in differences.items() if d},
                "status": "exact_match"
                if summary["raw_known_counts"]["Total"]
                == municipal["city_counts"]["Total"]
                else "monthly_vs_revised_unresolved",
            }
        )
    report = {
        "production_ready": False,
        "independent_comparison_completed": True,
        "endpoint_totals_reconciled": all(r["status"] == "exact_match" for r in rows),
        "comparison_source_id": "ine_approved_population",
        "comparison_sha256": sources["ine_approved_population"]["sha256"],
        "methodology_source_id": "municipal_methodology",
        "methodology_sha256": sources["municipal_methodology"]["sha256"],
        "interpretation": "Municipal statistical extraction and legal INE population are different published series, explicitly distinguished in Madrid methodology. This does not account for the exact differences. Do not rescale or fill blanks to force agreement.",
        "municipal_revised_comparisons": municipal_comparisons,
        "remaining_requirement": "Choose a compatible monthly/revised source policy and explain remaining revision differences. Blank counts remain unresolved; No consta category is explicitly reconciled into non-Spanish for comparison.",
        "comparisons": rows,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
