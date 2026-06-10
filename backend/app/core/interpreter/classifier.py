from app.schemas.events import SemanticUnit, WorkEvent


async def classify(event: WorkEvent) -> SemanticUnit:
    raise NotImplementedError("classify not implemented")
