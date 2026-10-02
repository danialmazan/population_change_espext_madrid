"""Audit raw-vintage parent membership without approving independent boundaries."""

import csv
from collections import Counter, defaultdict
from .io import ContractError
from .profile import COUNTS


def read_membership(path, source):
    parents, population, by_parent = defaultdict(set), Counter(), Counter()
    missing = 0
    with path.open(encoding=source["encoding"], newline="") as handle:
        for raw in csv.DictReader(handle, delimiter=source["delimiter"]):
            row = {k.strip().upper(): v.strip() for k, v in raw.items()}
            district = int(row["COD_DISTRITO"])
            barrio = int(row["COD_DIST_BARRIO"])
            if not 1 <= district <= 21 or (barrio != 0 and barrio // 100 != district):
                raise ContractError("Raw barrio/district codes disagree")
            values = [row[c] for c in COUNTS]
            if any(value and not value.isdigit() for value in values):
                raise ContractError("Invalid population count in parent audit")
            count = sum(int(value) if value else 0 for value in values)
            section = row["COD_DIST_SECCION"]
            if not section:
                missing += count
                continue
            section = int(section)
            if section // 1000 != district:
                raise ContractError("Raw section/district codes disagree")
            gid = f"28079{district:02d}{section % 1000:03d}"
            parent = (f"{district:02d}", f"{barrio:04d}")
            # Zero and blank rows also establish raw membership; never pick the largest group.
            parents[gid].add(parent)
            population[gid] += count
            by_parent[(gid, parent)] += count
    return parents, population, by_parent, missing


def assess_parents(before, after, old_membership, new_membership):
    old = set().union(*(old_membership.get(g, set()) for g in before))
    new = set().union(*(new_membership.get(g, set()) for g in after))
    missing = [g for g in before if not old_membership.get(g)] + [
        g for g in after if not new_membership.get(g)
    ]
    ambiguous_old = [g for g in before if len(old_membership.get(g, set())) > 1]
    ambiguous_new = [g for g in after if len(new_membership.get(g, set())) > 1]
    unknown_barrio = any(b == "0000" for d, b in old | new)
    stable = (
        len(old) == len(new) == 1 and old == new and not missing and not unknown_barrio
    )
    if missing:
        status = "missing_raw_membership"
    elif unknown_barrio:
        status = "unknown_raw_barrio"
    elif ambiguous_old or ambiguous_new:
        status = "ambiguous_section_membership"
    elif stable:
        status = "stable_raw_parent_code_only"
    elif len(old) == len(new) == 1:
        status = "raw_parent_reassignment"
    else:
        status = "multi_parent_zone"
    districts_old = {d for d, b in old}
    districts_new = {d for d, b in new}
    return dict(
        raw_parent_status=status,
        old_parents=[list(p) for p in sorted(old)],
        new_parents=[list(p) for p in sorted(new)],
        ambiguous_old_sections=ambiguous_old,
        ambiguous_new_sections=ambiguous_new,
        missing_raw_membership=missing,
        stable_raw_parent_code=stable,
        stable_raw_district_code=len(districts_old) == len(districts_new) == 1
        and districts_old == districts_new
        and not missing,
        independent_historical_parent_boundaries_verified=False,
    )
