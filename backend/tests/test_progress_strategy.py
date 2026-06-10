from app.core.services.progress_strategy import (
    DoneRatio,
    SimpleAverage,
    WeightedByPlannedHours,
)

PRJ001_ROWS = [
    {"progress": 55, "planned": 40, "status": "IN_PROGRESS"},
    {"progress": 10, "planned": 56, "status": "TODO"},
    {"progress": 70, "planned": 64, "status": "IN_PROGRESS"},
    {"progress": 80, "planned": 32, "status": "REVIEW"},
    {"progress": 0,  "planned": 24, "status": "TODO"},
]


def test_simple_average():
    assert SimpleAverage().compute(PRJ001_ROWS) == 43.0


def test_simple_average_empty():
    assert SimpleAverage().compute([]) == 0.0


def test_weighted_by_planned_hours():
    # (55*40 + 10*56 + 70*64 + 80*32 + 0*24) / (40+56+64+32+24)
    # = 9800 / 216 ≈ 45.4
    assert WeightedByPlannedHours().compute(PRJ001_ROWS) == 45.4


def test_weighted_falls_back_to_simple_when_no_hours():
    rows = [{"progress": p, "planned": None, "status": "TODO"} for p in [20, 40, 60]]
    assert WeightedByPlannedHours().compute(rows) == 40.0


def test_done_ratio():
    rows = [
        {"progress": 100, "status": "DONE"},
        {"progress": 100, "status": "DONE"},
        {"progress": 50, "status": "IN_PROGRESS"},
        {"progress": 0, "status": "TODO"},
    ]
    assert DoneRatio().compute(rows) == 50.0
