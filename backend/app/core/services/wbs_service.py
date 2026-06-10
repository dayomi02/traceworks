from app.core.exceptions import ProjectNotFound
from app.core.services.progress_strategy import DEFAULT_STRATEGY, OverallProgressStrategy
from app.core.services.project_service import derive_status
from app.db import sparql_repo


def list_projects_with_progress(
    strategy: OverallProgressStrategy = DEFAULT_STRATEGY,
    status: str | None = None,
) -> list[dict]:
    base = sparql_repo.list_projects()
    aggregate = sparql_repo.all_projects_task_aggregate()
    for project in base:
        rows = aggregate.get(project["project_id"], [])
        project["overall_progress"] = strategy.compute(rows)
        project["status"] = derive_status(project.get("status"), project.get("start_date"))
    if status:
        base = [p for p in base if p["status"] == status]
    return base


def get_wbs(project_id: str) -> list[dict]:
    if not sparql_repo.project_exists(project_id):
        raise ProjectNotFound(project_id)
    return sparql_repo.list_tasks_by_project(project_id)


async def create_snapshot(project_id: str) -> dict:
    raise NotImplementedError("create_snapshot not implemented")
