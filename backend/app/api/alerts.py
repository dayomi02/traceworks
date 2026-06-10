from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", status_code=501, include_in_schema=False)
def list_alerts() -> list[dict]:
    raise HTTPException(status_code=501, detail="list_alerts not implemented")


@router.post("/{alert_id}/ack", status_code=501, include_in_schema=False)
def ack_alert(alert_id: str) -> dict:
    raise HTTPException(status_code=501, detail="ack_alert not implemented")
