from fastapi import APIRouter, HTTPException, Request

router = APIRouter(prefix="/webhook", tags=["webhooks"])


@router.post("/github", status_code=501)
async def github_webhook(request: Request) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="GitHub webhook handler not implemented")


@router.post("/figma", status_code=501)
async def figma_webhook(request: Request) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Figma webhook handler not implemented")


@router.post("/slack", status_code=501)
async def slack_webhook(request: Request) -> dict[str, str]:
    raise HTTPException(status_code=501, detail="Slack webhook handler not implemented")
