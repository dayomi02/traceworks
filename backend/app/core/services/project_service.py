from datetime import date


def derive_status(stored: str | None, start_date: str | None, today: date | None = None) -> str:
    """저장된 projectStatus와 시작일로 표시용 상태를 결정한다.

    - 저장값이 'COMPLETED'면 그대로 COMPLETED
    - 그 외(ACTIVE/PLANNING/None)는 시작일 기준 PLANNING/ACTIVE 파생
    - 시작일 없거나 파싱 불가 → ACTIVE
    """
    if stored == "COMPLETED":
        return "COMPLETED"
    today = today or date.today()
    if not start_date:
        return "ACTIVE"
    try:
        sd = date.fromisoformat(start_date)
    except ValueError:
        return "ACTIVE"
    return "PLANNING" if today < sd else "ACTIVE"
