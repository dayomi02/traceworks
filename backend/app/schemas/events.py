from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

EventSource = Literal["github", "figma", "slack", "notion"]
SignalType = Literal["ProgressSignal", "IssueSignal", "CompetencySignal", "CollaborationSignal"]


class WorkEvent(BaseModel):
    source: EventSource
    external_id: str
    actor_id: str
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)


class Signal(BaseModel):
    type: SignalType
    confidence: float = 0.0
    attributes: dict = Field(default_factory=dict)


class SemanticUnit(BaseModel):
    event: WorkEvent
    signals: list[Signal] = Field(default_factory=list)
