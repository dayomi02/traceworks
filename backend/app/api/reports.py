from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/generate", status_code=501, include_in_schema=False)
def generate_report() -> dict:
    raise HTTPException(status_code=501, detail="generate_report not implemented")
