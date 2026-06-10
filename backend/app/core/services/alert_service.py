import logging
from datetime import datetime

import httpx

from app.config import get_settings
from app.db import sparql_repo

logger = logging.getLogger(__name__)

_STATUS_MAP: dict[str, str] = {
    "미진행": "TODO",
    "진행": "IN_PROGRESS",
    "완료": "COMPLETED",
}

# 알림 API의 assignee_user_role enum 매핑 — 내부 한글/약어 → 코드값
_ROLE_CODE_MAP: dict[str, str] = {
    "PM": "pm",
    "pm": "pm",
    "기획자": "planner",
    "기획": "planner",
    "개발자": "developer",
    "개발": "developer",
}

DESIGN_ROLES: set[str] = {"기획", "기획자", "디자인", "디자이너", "UI", "UX", "UI/UX"}


def _to_role_code(role: str | None) -> str | None:
    """내부 역할명을 알림 API의 enum 코드값으로 변환."""
    if not role:
        return None
    return _ROLE_CODE_MAP.get(role.strip(), role)


def _build_title_message(
    task_name: str,
    old_status: str,
    new_status: str,
    actor_name: str,
    actor_role: str | None,
    req_name: str | None,
) -> tuple[str, str]:
    role_label = actor_role or "담당자"
    req_label = f" '{req_name}' 요구사항의" if req_name else ""
    if new_status == "진행":
        title = f"'{task_name}' 작업이 진행 시작되었습니다."
        message = f"{role_label} {actor_name}님이{req_label} '{task_name}' 작업을 진행 시작하였습니다."
    elif old_status == "완료":
        title = f"'{task_name}' 작업 상태 변경이 요청되었습니다."
        message = f"{role_label} {actor_name}님이{req_label} '{task_name}' 작업을 추가 요청하였습니다. (완료 → 새 작업 추가)"
    elif new_status == "완료":
        title = f"'{task_name}' 작업이 완료되었습니다."
        message = f"{role_label} {actor_name}님이{req_label} '{task_name}' 작업을 완료 처리하였습니다."
    else:
        title = f"'{task_name}' 작업 상태가 변경되었습니다."
        message = f"{role_label} {actor_name}님이{req_label} '{task_name}' 작업의 상태를 '{old_status}'에서 '{new_status}'(으)로 변경하였습니다."
    return title, message


async def send_status_change_notification(
    task_data: dict,
    old_status: str,
    new_status: str,
    changed_by_name: str,
    changed_by_role: str | None,
    change_reason: str | None,
    slide_change_summary: str | None = None,
) -> int | None:
    """알림 이벤트를 생성하고 notification_event_id를 반환합니다."""
    settings = get_settings()
    task_name = task_data.get("task_name", "")
    assignee_role = task_data.get("assignee_role")
    actor_role = changed_by_role or assignee_role

    title, message = _build_title_message(
        task_name, old_status, new_status, changed_by_name, actor_role, task_data.get("req_name")
    )

    project_id = task_data.get("project_id")
    slide_id: str | None = None
    gitlab_id_int: int | None = None
    if project_id:
        integration = sparql_repo.get_project_integration_ids(project_id)
        slide_id = integration.get("google_slide_id")
        gitlab_raw = integration.get("gitlab_project_id")
        if gitlab_raw:
            try:
                gitlab_id_int = int(gitlab_raw)
            except (TypeError, ValueError):
                gitlab_id_int = None

    content: dict = {
        "common": {
            "req_id": task_data.get("req_id"),
            "req_name": task_data.get("req_name"),
            "task_id": task_data.get("task_id"),
            "task_name": task_name,
            "assignee_user_name": changed_by_name,
            "assignee_user_role": _to_role_code(actor_role),
            "noti_type": "PM_APPROVAL_REQUESTED",
        },
    }
    # status_change는 수신 서버가 IN_PROGRESS / COMPLETED 전환만 허용함
    # 미진행(TODO)이 prev나 new에 끼면 422가 떨어지므로 블록 자체를 제외한다
    if old_status != "미진행" and new_status != "미진행":
        content["status_change"] = {
            "prev_status": _STATUS_MAP.get(old_status, old_status),
            "new_status": _STATUS_MAP.get(new_status, new_status),
            "change_reason": change_reason,
            "slide_change_summary": slide_change_summary,
        }

    payload: dict = {
        "title": title,
        "message": message,
        "project_id": project_id,
        "presentation_id": slide_id,
        "gitlab_project_id": gitlab_id_int,
        "content": content,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ALERT_API_URL}/api/notifications",
                json=payload,
                headers={"X-Internal-Token": settings.ALERT_API_INTERNAL_TOKEN},
            )
            resp.raise_for_status()
            event_id: int = resp.json()["id"]
            logger.info("알림 생성 완료: task=%s %s→%s event_id=%s", task_data.get("task_id"), old_status, new_status, event_id)
            return event_id
    except Exception as e:
        logger.warning("알림 생성 실패 (무시): %s", e)
        return None


async def send_notification_to_pm(event_id: int, pm_user_ids: list[str], noti_type: str | None = None) -> None:
    """생성된 알림 이벤트를 PM에게 전달합니다."""
    if not pm_user_ids:
        logger.warning("PM user_id 없음 — 알림 전달 skip")
        return

    settings = get_settings()
    payload: dict = {"notification_event_id": event_id, "user_ids": pm_user_ids}
    if noti_type:
        payload["noti_type"] = noti_type
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ALERT_API_URL}/api/notifications/send",
                json=payload,
            )
            resp.raise_for_status()
            logger.info("알림 전달 완료: event_id=%s pm_users=%s", event_id, pm_user_ids)
    except Exception as e:
        logger.warning("알림 전달 실패 (무시): %s", e)


async def send_notification_to_users(
    event_id: int,
    user_ids: list[str],
    noti_type: str | None = None,
) -> None:
    """임의 사용자 그룹에 알림 이벤트를 전달합니다 (PM/담당자 구분 없음)."""
    if not user_ids:
        logger.warning("user_ids 없음 — 알림 전달 skip")
        return

    settings = get_settings()
    payload: dict = {"notification_event_id": event_id, "user_ids": user_ids}
    if noti_type:
        payload["noti_type"] = noti_type

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ALERT_API_URL}/api/notifications/send",
                json=payload,
            )
            resp.raise_for_status()
            logger.info(
                "알림 전달 완료: event_id=%s users=%d noti_type=%s",
                event_id, len(user_ids), noti_type,
            )
    except Exception as e:
        logger.warning("알림 전달 실패 (무시): %s", e)


async def send_notification_to_assignee(
    event_id: int,
    assignee_user_ids: list[str],
    is_approved: bool,
    rejection_reason: str | None = None,
) -> None:
    """승인/반려 결과를 담당 작업자에게 전달합니다."""
    if not assignee_user_ids:
        logger.warning("assignee user_id 없음 — 작업자 알림 skip")
        return

    settings = get_settings()
    noti_type = "PM_APPROVED" if is_approved else "PM_REJECTED"
    approval_result: dict = {
        "is_approved": is_approved,
        "approved_at": datetime.utcnow().isoformat(),
        "noti_type": noti_type,
    }
    if not is_approved and rejection_reason:
        approval_result["rejection_reason"] = rejection_reason

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ALERT_API_URL}/api/notifications/send",
                json={"notification_event_id": event_id, "user_ids": assignee_user_ids, "approval_result": approval_result, "noti_type": noti_type},
            )
            resp.raise_for_status()
            logger.info("작업자 알림 전달 완료: event_id=%s noti_type=%s", event_id, noti_type)
    except Exception as e:
        logger.warning("작업자 알림 전달 실패 (무시): %s", e)


async def call_slides_webhook(project_id: str, req_id: str) -> str | None:
    settings = get_settings()
    integration = sparql_repo.get_project_integration_ids(project_id)
    slide_id = integration.get("google_slide_id")
    gitlab_id = integration.get("gitlab_project_id")

    if not slide_id or not gitlab_id:
        logger.warning("Slides 웹훅 skip: project=%s slide_id=%s gitlab_id=%s", project_id, slide_id, gitlab_id)
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.ALERT_API_URL}/webhook/slides",
                json={
                    "git_lab_project_id": int(gitlab_id),
                    "presentation_id": slide_id,
                    "req_id": req_id,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            llm_summary = data.get("llm_summary")
            logger.info("Slides 웹훅 호출 완료: project=%s req=%s", project_id, req_id)
            return llm_summary
    except Exception as e:
        logger.warning("Slides 웹훅 실패 (무시): %s", e)
        return None
