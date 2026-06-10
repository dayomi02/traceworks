from typing import Literal

from pydantic import BaseModel


class InsightItem(BaseModel):
    type: str
    severity: Literal["critical", "warning", "info"]
    title: str
    message: str
    affected_entities: list[str] = []


class InsightsResponse(BaseModel):
    project_id: str
    insights: list[InsightItem]
    generated_at: str
