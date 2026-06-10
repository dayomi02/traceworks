from app.workers.celery_app import celery_app


@celery_app.task(name="events.process_work_event")
def process_work_event(event: dict) -> dict:
    raise NotImplementedError("process_work_event not implemented")
