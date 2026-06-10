from statistics import mean
from typing import Protocol


class OverallProgressStrategy(Protocol):
    def compute(self, rows: list[dict]) -> float: ...


class SimpleAverage:
    def compute(self, rows: list[dict]) -> float:
        if not rows:
            return 0.0
        return round(mean(r["progress"] for r in rows), 1)


class WeightedByPlannedHours:
    def compute(self, rows: list[dict]) -> float:
        if not rows:
            return 0.0
        num = sum(r["progress"] * (r.get("planned") or 0) for r in rows)
        den = sum((r.get("planned") or 0) for r in rows)
        if den == 0:
            return SimpleAverage().compute(rows)
        return round(num / den, 1)


class DoneRatio:
    def compute(self, rows: list[dict]) -> float:
        if not rows:
            return 0.0
        done = sum(1 for r in rows if r.get("status") == "DONE")
        return round(100 * done / len(rows), 1)


DEFAULT_STRATEGY: OverallProgressStrategy = SimpleAverage()
