from __future__ import annotations

import argparse
import json
from pathlib import Path

from .io import read_geographies, read_mortality, read_population
from .model import build_analysis


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Build Madrid demographic residual data")
    result.add_argument("--start", required=True)
    result.add_argument("--end", required=True)
    result.add_argument("--mortality", required=True)
    result.add_argument("--geographies", required=True)
    result.add_argument("--start-year", type=int, required=True)
    result.add_argument("--end-year", type=int, required=True)
    result.add_argument("--output", required=True)
    result.add_argument("--dataset-kind", choices=("official", "demonstration"), default="official")
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    analysis = build_analysis(
        read_population(args.start),
        read_population(args.end),
        read_mortality(args.mortality),
        read_geographies(args.geographies),
        args.start_year,
        args.end_year,
        dataset_kind=args.dataset_kind,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(analysis, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {len(analysis['areas'])} areas to {output}")


if __name__ == "__main__":
    main()

