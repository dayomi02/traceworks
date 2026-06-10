from pydantic import BaseModel

from app.schemas.projects import ProjectRef


class SkillRef(BaseModel):
    name: str
    proficiency: float | None = None


class PersonRef(BaseModel):
    person_id: str
    person_name: str


class PersonSummary(BaseModel):
    person_id: str
    person_name: str
    role: str | None = None
    rank: str | None = None
    skills: list[SkillRef] = []


class PersonDetail(PersonSummary):
    participates_in: list[ProjectRef] = []
