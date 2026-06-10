from typing import Literal

from pydantic import BaseModel

ProjectStatus = Literal["PLANNING", "ACTIVE", "COMPLETED"]


class RequirementDetail(BaseModel):
    req_id: str
    req_name: str | None = None
    req_description: str | None = None
    req_type: str | None = None             # 기능/비기능 (= requirement_type)
    user_type: list[str] = []               # 사용자 유형: ["사용자", "관리자"] 등
    req_priority: str | None = None
    req_status: str | None = None


class RequirementGroup(RequirementDetail):
    """대분류(Large) 요구사항 — children에 중분류(Mid) 배열을 가진다."""
    children: list[RequirementDetail] = []


class ProjectDetail(BaseModel):
    project_id: str
    project_name: str
    project_amount: int | None = None
    client_name: str | None = None
    project_theme: str | None = None
    project_domain: str | None = None
    project_status: str
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    contract_type: str | None = None
    business_type: str | None = None
    budget: str | None = None
    lead_company: str | None = None
    partner_companies: list[str] = []
    google_slide_id: str | None = None
    gitlab_project_id: str | None = None
    gitlab_repo_url: str | None = None
    requirements: list[RequirementGroup] = []


class ProjectSummary(BaseModel):
    project_id: str
    project_name: str
    domain: str | None = None
    status: ProjectStatus
    start_date: str | None = None
    end_date: str | None = None
    overall_progress: float


class ProjectRef(BaseModel):
    project_id: str
    project_name: str
