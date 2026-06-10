from app.schemas.events import WorkEvent


def normalize(payload: dict) -> WorkEvent:
    raise NotImplementedError("Figma webhook normalizer not implemented")
