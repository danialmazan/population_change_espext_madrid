# Madrid demographic residual

An analytical pipeline and static explorer for the question: **what would Madrid's areas look like if their 2015 residents had aged in place under natural mortality?**

This implementation follows [`PLAN.md`](PLAN.md). It does not bundle or invent official results. The checked-in web payload is an explicitly labelled deterministic demonstration dataset so the interface can be reviewed before official source acquisition and GIS harmonisation are signed off.

## Run the demonstration

```bash
python scripts/build_demo.py
python -m http.server 8000 -d web
```

Open <http://localhost:8000>. The app has no build-time JavaScript dependencies.

## Run the analytical pipeline

Input padrón files must be normalised to long form:

```csv
geography_id,age,sex,nationality,population
2807901001,25,male,ESP,42
2807901001,25,female,EXT,17
```

The two endpoint files use the same schema. `sex` is `male` or `female`; `nationality` is `ESP` or `EXT`. The mortality file contains annual single-age probabilities:

```csv
year,age,sex,qx
2015,25,male,0.0008
```

The geography file defines the leaf areas and aggregation hierarchy:

```csv
area_id,name,level,parent_id,boundary_status,boundary_method
2807901001,Section 001,section,B01,unchanged,direct
B01,Example barrio,barrio,D01,unchanged,aggregate
D01,Example distrito,distrito,MAD,unchanged,aggregate
MAD,Madrid,city,,unchanged,aggregate
```

Run:

```bash
python -m madrid_demography.cli \
  --start data/normalised/padron_2015-01-01.csv \
  --end data/normalised/padron_2025-01-01.csv \
  --mortality data/normalised/mortality_2015_2024.csv \
  --geographies data/normalised/geographies.csv \
  --start-year 2015 --end-year 2025 \
  --output web/data/analysis.json
```

The command fails on duplicate cells, invalid categories, missing annual mortality probabilities, hierarchy cycles, and arithmetic invariant violations. Ages below the interval length are retained as observed-only endpoint cells and are not assigned a cohort residual.

## Test

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Production-data gate

Before publishing real results, complete Phase 0 in [`PLAN.md`](PLAN.md): pin official downloads and checksums, verify endpoint semantics, reconcile city totals, build the reviewed 2015/2025 geographic crosswalk, and replace the demo payload. `web/data/analysis.json` carries `dataset_kind`; the UI displays a blocking demo banner unless it equals `official`.

