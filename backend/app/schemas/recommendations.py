from pydantic import BaseModel, Field


class RecommendStaffRequest(BaseModel):
    persist: bool = False
    top_k: int | None = Field(default=None, ge=1, le=20)


class RoleHeadcount(BaseModel):
    role: str
    count: int = Field(ge=1)


class RecommendStaffRefreshRequest(BaseModel):
    role_headcounts: list[RoleHeadcount]
    top_k: int | None = Field(default=None, ge=1, le=20)
    persist: bool = False


class RoleRecommendation(BaseModel):
    role: str
    required_count: int
    candidates: list["RecommendationItem"]


class RecommendStaffRefreshResponse(BaseModel):
    by_role: list[RoleRecommendation]
    total_required: int


class StaffAssignment(BaseModel):
    person_id: str
    role: str


class AssignStaffRequest(BaseModel):
    assignments: list[StaffAssignment]


class AssignStaffResponse(BaseModel):
    project_id: str
    assigned_count: int
    wbs_tasks_assigned: int = 0


class MatchedSkill(BaseModel):
    skill: str
    proficiency: float


class RecommendationItem(BaseModel):
    rank: int
    person_id: str
    person_name: str
    role: str | None = None
    grade: str | None = None
    similarity_score: float
    availability_score: float | None = None
    matched_skills: list[MatchedSkill] = []
    reason: str
    is_sample: bool = False


class AvailabilityItem(BaseModel):
    person_id: str
    person_name: str
    role: str | None = None
    active_tasks: int
    availability_score: float | None = None
    computed_availability: float | None = None
