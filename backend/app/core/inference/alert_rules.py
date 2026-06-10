from app.schemas.events import SemanticUnit


async def derive_alerts(unit: SemanticUnit) -> list[dict]:
    raise NotImplementedError("derive_alerts not implemented")
