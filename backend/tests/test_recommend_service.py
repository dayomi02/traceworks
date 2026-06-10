from app.core.services.recommend_service import (
    _build_reason,
    _rank_candidates,
    _similarity,
    compute_load_availability,
)


P005 = {
    "person_id": "P005",
    "person_name": "최민준",
    "availability_score": 0.80,
    "synergy_score": 0.70,
    "skills": [
        {"name": "React", "proficiency": 0.91},
        {"name": "TypeScript", "proficiency": 0.87},
        {"name": "Python", "proficiency": 0.74},
        {"name": "데이터 애널리틱스", "proficiency": 0.76},
    ],
}

P003 = {
    "person_id": "P003",
    "person_name": "김태양",
    "availability_score": 0.35,
    "synergy_score": 0.88,
    "skills": [
        {"name": "React", "proficiency": 0.91},
        {"name": "TypeScript", "proficiency": 0.87},
    ],
}

REQUIRED = ["React", "TypeScript", "Python", "데이터 애널리틱스"]


def test_similarity_full_match():
    score, matched = _similarity(P005["skills"], REQUIRED)
    assert score == 0.82  # (0.91+0.87+0.74+0.76)/4 = 0.82
    assert len(matched) == 4


def test_similarity_partial_match():
    score, matched = _similarity(P003["skills"], REQUIRED)
    # (0.91+0.87)/4 = 0.445 → round 0.45
    assert score == 0.45
    assert len(matched) == 2


def test_similarity_no_match():
    score, matched = _similarity(
        [{"name": "Go", "proficiency": 0.9}],
        REQUIRED,
    )
    assert score == 0.0
    assert matched == []


def test_similarity_case_insensitive():
    score, _ = _similarity(
        [{"name": "react", "proficiency": 1.0}],
        ["React"],
    )
    assert score == 1.0


def test_ranking_orders_by_similarity_then_availability():
    ranked = _rank_candidates([P003, P005], REQUIRED)
    assert [r["person_id"] for r in ranked] == ["P005", "P003"]
    assert ranked[0]["rank"] == 1
    assert ranked[0]["similarity_score"] == 0.82


def test_ranking_ties_break_by_availability():
    alt_p003 = {**P003, "skills": P005["skills"]}  # 같은 skills → 동일 similarity
    ranked = _rank_candidates([alt_p003, P005], REQUIRED)
    # 둘 다 similarity 0.82, P005 availability 0.80 > P003 0.35
    assert ranked[0]["person_id"] == "P005"


def test_ranking_excludes_zero_similarity():
    outsider = {
        "person_id": "P999", "person_name": "외부인",
        "availability_score": 1.0, "synergy_score": 0.0,
        "skills": [{"name": "Go", "proficiency": 0.95}],
    }
    ranked = _rank_candidates([outsider, P005], REQUIRED)
    assert [r["person_id"] for r in ranked] == ["P005"]


def test_build_reason_includes_top_skills_and_availability():
    _, matched = _similarity(P005["skills"], REQUIRED)
    reason = _build_reason(P005, matched)
    assert "React" in reason
    assert "0.91" in reason
    assert "가용성 0.80" in reason
    # 3개 이상이면 "외 N건" 접미
    assert "외 1건" in reason


def test_compute_load_availability_no_active_tasks():
    assert compute_load_availability(0, 0) == 1.0
    assert compute_load_availability(0, None) == 1.0


def test_compute_load_availability_high_load():
    # 3 tasks at 0% progress → load=3 → availability=0
    assert compute_load_availability(3, 0.0) == 0.0


def test_compute_load_availability_partial_progress():
    # 2 tasks at 50% progress → load=2*0.5=1 → 1 - 1/3 = 0.67
    assert compute_load_availability(2, 50.0) == 0.67
