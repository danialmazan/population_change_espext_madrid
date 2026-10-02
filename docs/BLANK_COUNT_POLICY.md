# Conditional monthly blank-count policy

The eligible 2015 baseline cohorts now have a reproducible research candidate with inferred zeros. Raw blanks remain null, and official publication remains blocked. This is an inference under stated assumptions, not a recovered source definition or a release approval.

## Evidence and scope

The public municipal bank was queried for January 2015, each of 21 districts and each single age 0–89. Both sex and nationality counts are returned as four integer fields. Two batches contain 900 and 990 district/age rows. Each response has full requested coverage and no truncation warning. All **7,560 district × age × sex × nationality totals match the sum of known CSV cells**, with zero residual in every group.

The proof is conditional: if the controls exhaust the same population universe, known cells are correct, and missing population counts are nonnegative, the sum of the missing cells is zero. Every missing cell in the group must therefore be zero. The bank and CSV may share an underlying extraction; matching them does not exclude correlated or compensating source errors.

This policy covers **261,837 blank cells** in eligible baseline ages 0–89, representing the cohorts aged 10–99 in 2025. The known eligible population remains **3,109,701**. The other **42,820 baseline blanks**, outside the paired cohort scope, remain null. No other January vintage inherits this rule.

The locked policy is [config/blank-count-policy.json](../config/blank-count-policy.json). It binds the source hash, reference date, exact age range and both response hashes. Compressed original responses and request receipts are retained in [audit/monthly-age-controls](audit/monthly-age-controls). Results and candidate output hash are in [audit/blank-count-policy.json](audit/blank-count-policy.json).

## Reproduce

After acquiring pinned inputs and generating the normal audit export:

```bash
python -m madrid_demography.normalise
python scripts/apply_blank_count_policy.py
```

The script verifies raw source and control hashes, reference dates, complete group coverage, nonnegative integers, matching totals and the normal audit export hash. It writes the candidate to ignored `data/normalised/padron_2015_monthly_candidate.csv`. Inferred cells carry `population_status=inferred_zero_monthly_control`, their original `raw_population_status=unknown_blank`, and a policy ID. All observed counts and excluded rows are preserved. A failed export cannot replace a previously completed candidate.

`python scripts/fetch_monthly_age_controls.py` refreshes the public controls with recorded POST bodies and response encodings. A changed response hash requires explicit policy revision; fetching alone cannot approve new evidence.

The normal audit exports and strict model-facing normaliser retain their existing policies. The research candidate preserves raw geography and excluded/null cells; it is not an official model input.

## Validation and next work

53 tests pass, including rejection of truncated, missing, duplicated, wrong-date and mismatched controls; noninteger and negative values; changed audit hashes; and incomplete candidate exports. Ruff lint and formatting pass.

Next, review the provisional changed boundary components and historical barrio/district parents. The source-universe assumptions and count policy still need analytical review before an official release, alongside monthly versus revised annual source policy, independent survival reproduction, mortality sensitivity and licensing.
