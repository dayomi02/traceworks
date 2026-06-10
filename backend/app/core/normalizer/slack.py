from app.schemas.events import WorkEvent


def normalize(payload: dict) -> WorkEvent:
    raise NotImplementedError("Slack webhook normalizer not implemented")
