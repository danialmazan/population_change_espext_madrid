"""Date-based, versioned analytical configuration."""

from dataclasses import asdict, dataclass
from datetime import date
import json
import math
from pathlib import Path

from .io import ContractError


@dataclass(frozen=True)
class ModelConfig:
    start_date: str = "2015-01-01"
    end_date: str = "2025-01-01"
    mortality_region: str = "Comunidad de Madrid"
    zone_version: str = "2015-2025-v1"
    terminal_age: int = 100
    min_expected: float = 20
    exact_coverage_gate: float = 0.95
    overlap_tolerance: float = 0.001
    material_overlap: float = 0.000001
    discontinuity_threshold: float = 0.05
    timing_materiality: float = 0.005
    dataset_kind: str = "demonstration"

    def __post_init__(self):
        start, end = (
            date.fromisoformat(self.start_date),
            date.fromisoformat(self.end_date),
        )
        if (
            (start.month, start.day) != (1, 1)
            or (end.month, end.day) != (1, 1)
            or end <= start
        ):
            raise ContractError("V1 requires increasing 1 January dates")
        if not 1 <= self.terminal_age <= 130 or self.terminal_age < self.interval:
            raise ContractError("invalid terminal age")
        if (
            not math.isfinite(self.min_expected)
            or self.min_expected < 0
            or not 0 <= self.exact_coverage_gate <= 1
        ):
            raise ContractError("invalid suppression/coverage threshold")
        if (
            not 0 < self.overlap_tolerance < 1
            or not 0 <= self.material_overlap < self.overlap_tolerance
        ):
            raise ContractError("invalid geometry tolerances")
        if self.discontinuity_threshold < 0 or self.timing_materiality < 0:
            raise ContractError("invalid diagnostic thresholds")
        if self.dataset_kind not in {"official", "demonstration", "research"}:
            raise ContractError("invalid dataset kind")

    @property
    def start_year(self):
        return date.fromisoformat(self.start_date).year

    @property
    def end_year(self):
        return date.fromisoformat(self.end_date).year

    @property
    def interval(self):
        return self.end_year - self.start_year

    def to_dict(self):
        return asdict(self)

    @classmethod
    def read(cls, path):
        return cls(**json.loads(Path(path).read_text()))

    def presets(self):
        items = [
            {
                "id": "cohorts",
                "label": f"{self.interval}+",
                "min": self.interval,
                "max": self.terminal_age - 1,
            }
        ]
        for low, high in [
            (10, 17),
            (18, 24),
            (25, 34),
            (35, 44),
            (45, 54),
            (55, 64),
            (65, 74),
            (75, 130),
        ]:
            low = max(low, self.interval)
            upper = min(high, self.terminal_age - 1)
            if low <= upper:
                items.append(
                    {
                        "id": f"{low}-{high}",
                        "label": f"{low}–{high}" if high < 130 else f"{low}+",
                        "min": low,
                        "max": upper,
                    }
                )
        items.append(
            {
                "id": "born",
                "label": f"0–{self.interval - 1} · solo observada",
                "min": 0,
                "max": self.interval - 1,
            }
        )
        return items
