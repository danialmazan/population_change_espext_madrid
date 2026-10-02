"""Machine-readable evidence and fail-closed official release checks."""

import math
from collections import defaultdict
from .io import ContractError


def validate_analysis(analysis, geographies):
    checks = []

    def check(name, passed, details=None):
        checks.append({"name": name, "passed": bool(passed), "details": details})

    areas = {a["id"]: a for a in analysis["areas"]}
    detail = defaultdict(list)
    for row in analysis["cohort_detail"]:
        detail[row["area_id"]].append(row)
    for gid, area in areas.items():
        rows = [r for r in detail[gid] if r["cohort_eligible"]]
        check(
            f"{gid}:sex-nationality-sums",
            all(
                math.isclose(sum(r[field] for r in rows), area[field], abs_tol=1e-6)
                for field in ["baseline", "expected", "actual", "residual"]
            ),
        )
        check(
            f"{gid}:survival-bounds",
            all(0 <= r["expected"] <= r["baseline"] + 1e-9 for r in rows),
        )
        check(
            f"{gid}:stock-accounting",
            math.isclose(
                area["residual"],
                area["observed_change"] + area["modelled_deaths"],
                abs_tol=1e-6,
            ),
        )
        children = [a for a in areas.values() if a["parent_id"] == gid]
        if children:
            check(
                f"{gid}:hierarchy",
                all(
                    math.isclose(
                        sum(c[field] for c in children), area[field], abs_tol=1e-6
                    )
                    for field in [
                        "baseline",
                        "expected",
                        "actual",
                        "residual",
                        "observed_under_interval",
                        "observed_terminal",
                    ]
                ),
            )
    return {"passed": all(c["passed"] for c in checks), "checks": checks}


def reconcile(analysis, published, endpoint):
    """Published totals are independent full-population controls, by requested area."""
    areas = {a["id"]: a for a in analysis["areas"]}
    discrepancies = []
    for control in published:
        gid = control["area_id"]
        if gid not in areas:
            raise ContractError(f"unknown published control {gid}")
        actual = sum(
            r["population"]
            for r in areas[gid]["composition"]
            if r["year"] == endpoint
            and (control.get("age") is None or r["age"] == control["age"])
            and (
                not control.get("nationality")
                or r["nationality"] == control["nationality"]
            )
        )
        difference = actual - control["population"]
        tolerance = control.get("tolerance", 0)
        discrepancies.append(
            dict(
                control,
                calculated=actual,
                difference=difference,
                passed=abs(difference) <= tolerance,
            )
        )
    return discrepancies


def feasibility(start, end, crosswalk, components, threshold=0.95):
    by_vintage = {
        v: {r["source_id"]: r["quality_status"] for r in crosswalk if r["vintage"] == v}
        for v in ["old", "new"]
    }
    shares = {}
    counts = {}
    for vintage, population in [("old", start), ("new", end)]:
        distribution = defaultdict(float)
        for (gid, *_), value in population.items():
            distribution[by_vintage[vintage].get(gid, "unreliable")] += value
        total = sum(distribution.values())
        shares[vintage] = {
            status: value / total if total else 0
            for status, value in distribution.items()
        }
        counts[vintage] = {
            status: sum(s == status for s in by_vintage[vintage].values())
            for status in set(by_vintage[vintage].values())
        }
    exact = min(
        sum(shares[v].get(s, 0) for s in ["unchanged", "exact_harmonisation"])
        for v in shares
    )
    return {
        "population_shares": shares,
        "section_counts": counts,
        "exact_population_share": exact,
        "section_gate_passed": exact >= threshold,
        "recommended_level": "section" if exact >= threshold else "barrio",
        "changed_components_pending_review": [
            c["zone_id"] for c in components if c["requires_review"]
        ],
    }


def official_release_gate(config, evidence, qa):
    """Every empirical gate must include review evidence, not just a boolean assertion."""
    checks = [{"name": "arithmetic", "passed": qa["passed"]}]
    required = [
        "source_checksums",
        "reference_dates",
        "annual_profiles",
        "published_totals",
        "mortality_coverage",
        "boundary_audit",
        "historical_parents",
        "independent_survival",
        "sensitivity_review",
        "licensing",
    ]
    for name in required:
        item = evidence.get(name, {})
        checks.append(
            {
                "name": name,
                "passed": item.get("passed") is True
                and bool(item.get("reviewed_by"))
                and bool(item.get("artifact")),
            }
        )
    warnings = evidence.get("warnings", [])
    checks.append(
        {
            "name": "warning_signoffs",
            "passed": all(w.get("reviewed_by") and w.get("note") for w in warnings),
        }
    )
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "warnings": warnings,
        "dataset_kind": config.dataset_kind,
    }
