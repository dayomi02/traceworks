from app.workers.celery_app import celery_app


@celery_app.task(name="reports.generate_weekly")
def generate_weekly_report(project_id: str) -> dict:
    raise NotImplementedError("generate_weekly_report not implemented")
