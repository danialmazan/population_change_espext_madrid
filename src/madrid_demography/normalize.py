"""Source profiling, versioned unpivoting, and annual-series diagnostics."""

import csv
import hashlib
from collections import Counter
from pathlib import Path
from .io import ContractError


def canonical_section(district, section):
    d, s = str(district).strip(), str(section).strip()
    if not d.isdigit() or not s.isdigit():
        raise ContractError("section/district codes must be numeric")
    d = d.zfill(2)
    if len(s) == 10:
        if not s.startswith("28079" + d):
            raise ContractError("full section code disagrees with district")
        return s
    if len(s) == 4:
        s = s.zfill(5)
    if len(s) == 5:
        if s[:2] != d:
            raise ContractError("local section code disagrees with district")
        s = s[2:]
    if len(d) != 2 or len(s) > 3:
        raise ContractError("invalid Madrid section code width")
    return "28079" + d + s.zfill(3)


def canonical_barrio(district, barrio, code_format="district_times_10"):
    """Interpret the code only according to the versioned source schema."""
    widths = {"district_times_10": 3, "district_times_100": 4}
    if code_format not in widths:
        raise ContractError("unreviewed barrio code format")
    width = widths[code_format]
    district, barrio = str(district).strip().zfill(2), str(barrio).strip().zfill(width)
    if (
        len(barrio) != width
        or not barrio.isdigit()
        or barrio[:2] != district
        or int(barrio[2:]) == 0
    ):
        raise ContractError("barrio code disagrees with district")
    return barrio


def normalize_padron(path, schema, reference_date, source_id):
    if not schema["valid_from"] <= reference_date <= schema["valid_to"]:
        raise ContractError("schema not valid for reference date")
    raw = Path(path).read_bytes()
    decoded = raw.decode(schema["encoding"])
    reader = csv.DictReader(decoded.splitlines(), delimiter=schema["delimiter"])
    aliases = schema["aliases"]
    headers = reader.fieldnames or []
    unknown = (
        set(headers)
        - set(aliases)
        - set(schema.get("ignored_columns", []))
        - ({schema["total_column"]} if schema.get("total_column") else set())
    )
    missing = set(aliases) - set(headers)
    if unknown or missing:
        raise ContractError(
            f"unreviewed schema: unknown={sorted(unknown)}, missing={sorted(missing)}"
        )
    required = {
        "district",
        "barrio",
        "section",
        "age",
        "male_ESP",
        "female_ESP",
        "male_EXT",
        "female_EXT",
    }
    if not required <= set(aliases.values()):
        raise ContractError("alias schema incomplete")
    facts, excluded, seen, ages, parents = [], [], set(), Counter(), {}
    for line, source in enumerate(reader, 2):
        row = {
            canonical: source[original].strip()
            for original, canonical in aliases.items()
        }
        age_text = row["age"]
        is_open = age_text in schema.get(
            "open_age_labels", [f"{schema.get('open_age', 100)}+"]
        )
        if not age_text.isdigit() and not is_open:
            if age_text not in {
                "",
                "TOTAL",
                "Total",
                "DESCONOCIDA",
                "Unknown",
                f"{schema.get('open_age', 100)}+",
            }:
                raise ContractError(f"line {line}: unrecognised age {age_text}")
            excluded.append(
                {
                    "raw_row_number": line,
                    "age_label": age_text,
                    "row": row,
                    "reason": "terminal_open"
                    if age_text.endswith("+")
                    else "total_or_unknown",
                }
            )
            continue
        age = schema["open_age"] if is_open else int(age_text)
        if not 0 <= age <= schema.get("max_exact_age", 130):
            raise ContractError("impossible age")
        gid = canonical_section(row["district"], row["section"])
        district = row["district"].zfill(2)
        barrio = canonical_barrio(
            district,
            row["barrio"],
            schema.get("barrio_code_format", "district_times_10"),
        )
        if gid in parents and parents[gid] != (district, barrio):
            raise ContractError("ambiguous vintage parent")
        parents[gid] = (district, barrio)
        counts = []
        for sex in ("male", "female"):
            for nationality in ("ESP", "EXT"):
                value = row[f"{sex}_{nationality}"]
                if not value.isdigit():
                    raise ContractError(f"line {line}: invalid/suppressed count")
                count = int(value)
                key = (gid, age, sex, nationality)
                if key in seen:
                    raise ContractError(f"duplicate source cell {key}")
                seen.add(key)
                counts.append(count)
                facts.append(
                    dict(
                        geography_id=gid,
                        age=age,
                        sex=sex,
                        nationality=nationality,
                        population=count,
                        reference_date=reference_date,
                        source_file_id=source_id,
                        schema_version=schema["schema_version"],
                        raw_row_number=line,
                        district_code=district,
                        barrio_code=barrio,
                        section_code=gid[-3:],
                        age_kind="open" if is_open else "exact",
                    )
                )
        total_col = schema.get("total_column")
        if total_col and int(source[total_col]) != sum(counts):
            raise ContractError("raw row total differs from four cells")
        ages[age] += 1
    profile = dict(
        source_file_id=source_id,
        reference_date=reference_date,
        sha256=hashlib.sha256(raw).hexdigest(),
        bytes=len(raw),
        encoding=schema["encoding"],
        delimiter=schema["delimiter"],
        decimal_convention="integer",
        header_text=headers,
        raw_header_hex=raw.splitlines()[0].hex(),
        row_count=sum(ages.values()) + len(excluded),
        fact_count=len(facts),
        ages=sorted(ages),
        minimum_age=min(ages, default=None),
        maximum_age=max(ages, default=None),
        excluded_rows=len(excluded),
        section_count=len(parents),
        total=sum(f["population"] for f in facts),
        schema_reviewed=schema.get("reviewed", False),
        parents=parents,
    )
    return facts, excluded, profile


def discontinuities(profiles, threshold=0.05):
    output = []
    ordered = sorted(profiles, key=lambda p: p["reference_date"])
    for previous, current in zip(ordered, ordered[1:]):
        change = current["total"] / previous["total"] - 1 if previous["total"] else None
        output.append(
            {
                "from": previous["reference_date"],
                "to": current["reference_date"],
                "relative_change": change,
                "flagged": change is None or abs(change) > threshold,
                "schema_changed": previous.get("header_text")
                != current.get("header_text"),
                "section_count_change": current.get("section_count", 0)
                - previous.get("section_count", 0),
            }
        )
    return output


def extract_mortality(rows, measure="qx", units="probability"):
    """Explicit dimension-selected rows. Never interpret m_x as q_x."""
    if measure not in {"qx", "px", "lx"}:
        raise ContractError(
            "life-table conversion for mx is not implemented; use official qx/px/lx"
        )
    if units not in {"probability", "per_1000", "survivors"}:
        raise ContractError("unsupported mortality units")
    indexed = {}
    for row in rows:
        key = (int(row["year"]), int(row["age"]), row["sex"])
        if key in indexed:
            raise ContractError("duplicate selected mortality dimension")
        value = float(row[measure])
        if not __import__("math").isfinite(value) or value < 0:
            raise ContractError("invalid life-table value")
        indexed[key] = value
    output = {}
    for (year, age, sex), value in indexed.items():
        if measure == "lx":
            if (year, age + 1, sex) not in indexed:
                continue  # open last age has no defensible ratio
            if value <= 0:
                raise ContractError("zero lx denominator")
            qx = 1 - indexed[(year, age + 1, sex)] / value
        else:
            if units == "per_1000":
                value /= 1000
            qx = value if measure == "qx" else 1 - value
        if sex not in {"male", "female"} or not 0 <= qx <= 1:
            raise ContractError("invalid selected life-table probability")
        output[(year, age, sex)] = qx
    return output


def extract_ine_series(payload, selection):
    """Decode selected INE metadata codes, never select by series order or substring."""
    dimensions = selection["dimensions"]
    age_variable = str(selection["age_variable"])
    sex_variable = str(selection["sex_variable"])
    rows = []
    for series in payload:
        metadata = {
            str(m["Variable"]["Codigo"]): str(m["Codigo"]) for m in series["MetaData"]
        }
        if not all(
            metadata.get(str(variable)) == str(code)
            for variable, code in dimensions.items()
        ):
            continue
        if (
            metadata.get(age_variable) not in selection["age_codes"]
            or metadata.get(sex_variable) not in selection["sex_codes"]
        ):
            raise ContractError(
                "selected INE series contains unmapped age/sex; audit metadata"
            )
        age = selection["age_codes"][metadata[age_variable]]
        sex = selection["sex_codes"][metadata[sex_variable]]
        for value in series["Data"]:
            if value.get("Valor") is None:
                raise ContractError("missing selected INE observation")
            year = int(value["Anyo"])
            if int(selection["start_year"]) <= year < int(selection["end_year"]):
                rows.append(
                    {
                        "year": year,
                        "age": age,
                        "sex": sex,
                        selection["measure"]: value["Valor"],
                    }
                )
    if not rows:
        raise ContractError("no INE series match explicit dimension selection")
    return extract_mortality(rows, selection["measure"], selection["units"])
