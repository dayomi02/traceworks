from app.schemas.events import WorkEvent


def normalize(payload: dict) -> WorkEvent:
    raise NotImplementedError("GitHub webhook normalizer not implemented")
