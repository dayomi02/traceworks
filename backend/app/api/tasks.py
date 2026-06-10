import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.exceptions import TaskNotFound
from app.core.services import alert_service, rfp_service
from app.db import sparql_repo
from app.db.models import User, WbsIssue, WbsTaskHistory
from app.db.postgres import get_db
from app.schemas.tasks import (
    TaskApprovalRequest,
    TaskApprovalResponse,
    TaskDetail,
    TaskHistoryEntry,
    TaskIssue,
    TaskStatusUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["WBS 태스크"])

ID_PATTERN = r"^[A-Za-z0-9_-]+$"

WBS_STATUS_ORDER = ["미진행", "진행", "완료"]

# 이 전환은 PM 승인 없이 즉시 반영
_IMMEDIATE_TRANSITIONS: set[tuple[str, str]] = {
    ("미진행", "진행"),
}


@router.get("/{task_id}", response_model=TaskDetail)
async def get_task(
    task_id: str = Path(..., pattern=ID_PATTERN),
    db: AsyncSession = Depends(get_db),
) -> TaskDetail:
    """
    **[화면 3 - WBS 일정 / 태스크 상세]** 특정 태스크의 상세 정보, 상태 변경 이력, 이슈 목록을 반환합니다.

    - `task_id`는 `GET /projects/{project_id}/wbs` 응답의 `task_id` 값을 사용합니다.
    - `history`: MariaDB에 저장된 상태 변경 이력 (변경자·변경 사유·추가 작업 기간 포함)
    - `issues`: 해당 태스크에 등록된 이슈 목록 (상태: `open` / `monitoring` / `resolved`)
    - `planned_start` / `planned_end`: AI 분석 시 산정된 계획 시작·종료일
    - 인증 불필요 (공개 조회)
    """
    data = sparql_repo.get_task_by_id(task_id)
    if data is None:
        raise TaskNotFound(task_id)

    hist_rows = await db.execute(
        select(WbsTaskHistory, User.name)
        .join(User, WbsTaskHistory.changed_by == User.id)
        .where(WbsTaskHistory.task_id == task_id)
        .order_by(WbsTaskHistory.created_at.asc())
    )
    history = [
        TaskHistoryEntry(
            history_id=h.WbsTaskHistory.id,
            old_status=h.WbsTaskHistory.old_status,
            new_status=(
                "변경 요청"
                if h.WbsTaskHistory.old_status == "완료" and h.WbsTaskHistory.new_status == "완료"
                else h.WbsTaskHistory.new_status
            ),
            change_reason=h.WbsTaskHistory.change_reason,
            extra_work_start=str(h.WbsTaskHistory.extra_work_start) if h.WbsTaskHistory.extra_work_start else None,
            extra_work_end=str(h.WbsTaskHistory.extra_work_end) if h.WbsTaskHistory.extra_work_end else None,
            changed_by_name=h.name,
            created_at=h.WbsTaskHistory.created_at.isoformat(),
        )
        for h in hist_rows.all()
    ]

    # TODO: issues 목록은 추후에 issues 목록 API 와 연동 필요
    # issue_rows =
    # issues = [    ]

    logger.info("태스크 조회: task_id=%s status=%s", task_id, data.get("status"))
    return TaskDetail(**data, history=history, issues=[])


@router.patch("/{task_id}/status", response_model=dict)
async def update_task_status(
    body: TaskStatusUpdate,
    task_id: str = Path(..., pattern=ID_PATTERN),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    **[화면 3 - WBS 일정 / 태스크 상태 변경]** 태스크의 진행 상태를 변경하고 이력을 기록합니다.

    - 상태 흐름: `미진행` → `진행` → `완료`
    - **권한 규칙:**
        - **PM (해당 프로젝트의 PM)**: 어떤 task든 상태 변경 가능. 모든 전환이 **즉시 반영**되고
          본인을 제외한 프로젝트 인원 전체에게 알림이 발송됩니다 (승인/반려 불필요).
        - **그 외 사용자**: **본인이 담당자(assignee)인 task만** 변경 가능. 그 외에는 403 응답.
    - 일반 사용자 기준 흐름:
        - `미진행 → 진행`: 즉시 반영
        - 그 외 전환: PM 승인 필요 (`"pending_approval"` 응답)
    - **완료 → 다른 상태로 되돌릴 때 필수 필드:**
        - `change_reason`: 완료 취소 사유 (필수)
        - `extra_work_start`: 추가 작업 시작일 YYYY-MM-DD (필수)
        - `extra_work_end`: 추가 작업 종료일 YYYY-MM-DD (필수)
    - **인증 필요** (`Authorization: Bearer <token>`)
    """
    data = sparql_repo.get_task_by_id(task_id)
    if data is None:
        raise TaskNotFound(task_id)

    old_status = data["status"]
    project_id = data.get("project_id")
    assignee_name = (
        data.get("assignee", {}).get("person_name")
        if data.get("assignee") else None
    )

    # ── 권한 체크: PM(해당 프로젝트) or 본인 담당 task ──
    pm_names = sparql_repo.get_project_pm_names(project_id) if project_id else []
    is_pm = bool(current_user.name) and current_user.name in pm_names

    if not is_pm:
        if not assignee_name or assignee_name != current_user.name:
            logger.warning(
                "[STATUS-UPDATE] 권한 거부: task_id=%s user=%s assignee=%s is_pm=False",
                task_id, current_user.name, assignee_name,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="본인이 담당자인 태스크만 수정할 수 있습니다.",
            )

    if old_status == "완료":
        if not body.change_reason:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="완료 상태에서 변경 시 변경 사유(change_reason)를 입력해야 합니다.",
            )
        if not body.extra_work_start or not body.extra_work_end:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="완료 상태에서 변경 시 추가 작업 시작일(extra_work_start)과 종료일(extra_work_end)을 입력해야 합니다.",
            )

    # PM은 모든 전환을 즉시 반영. 일반 사용자는 _IMMEDIATE_TRANSITIONS 룰 적용
    if is_pm:
        is_immediate = True
    else:
        is_immediate = body.status != "완료" and (old_status, body.status) in _IMMEDIATE_TRANSITIONS

    if is_immediate:
        sparql_repo.update_task_status(task_id, body.status)

    history_entry = WbsTaskHistory(
        id=str(uuid.uuid4()),
        task_id=task_id,
        changed_by=current_user.id,
        old_status=old_status,
        new_status=body.status,
        change_reason=body.change_reason,
        extra_work_start=str(body.extra_work_start) if body.extra_work_start else None,
        extra_work_end=str(body.extra_work_end) if body.extra_work_end else None,
        approval_status=None if is_immediate else "pending",
    )
    db.add(history_entry)
    await db.commit()

    logger.info(
        "[STATUS-UPDATE] task_id=%s %s→%s by %s is_pm=%s immediate=%s assignee=%s",
        task_id, old_status, body.status, current_user.email,
        is_pm, is_immediate, assignee_name,
    )

    # `미진행 → 진행` 은 알림/웹훅 없이 즉시 반영만 하고 종료
    if old_status == "미진행" and body.status == "진행":
        result: dict = {"task_id": task_id, "old_status": old_status, "new_status": body.status}
        if is_pm:
            result["status"] = "applied_by_pm"
        return result

    # Slides 웹훅 (기획/디자인 역할)
    assignee_role = data.get("assignee_role") or ""
    llm_summary = ""
    if any(r in assignee_role for r in alert_service.DESIGN_ROLES):
        project_id = data.get("project_id")
        req_id = data.get("req_id")
        if project_id and req_id:
            llm_summary = await alert_service.call_slides_webhook(project_id, req_id)

    # 알림 생성
    event_id = await alert_service.send_status_change_notification(
        task_data={**data, "task_id": task_id},
        old_status=old_status,
        new_status=body.status,
        changed_by_name=current_user.name,
        changed_by_role="PM" if is_pm else None,
        change_reason=body.change_reason,
        slide_change_summary=llm_summary,
    )

    # event_id를 이력에 저장 (승인 API에서 조회용)
    if event_id and not is_immediate:
        history_entry.notification_event_id = event_id
        await db.commit()

    # ── 알림 전송 분기 ──────────────────────────────
    if event_id and project_id:
        if is_pm:
            # PM이 변경한 경우: 프로젝트 멤버 전체(본인 제외)에게 알림
            member_names = sparql_repo.get_project_member_names(project_id)
            target_names = [n for n in member_names if n != current_user.name]
            if target_names:
                member_rows = await db.execute(
                    select(User.id).where(User.name.in_(target_names))
                )
                target_user_ids = [str(row[0]) for row in member_rows.all()]
                # await alert_service.send_notification_to_users(
                #     event_id, target_user_ids, noti_type="PM_APPROVED",
                # )
                await alert_service.send_notification_to_assignee(
                    event_id, target_user_ids, is_approved=True
                )
        else:
            # 일반 사용자가 변경: 기존 동작 (PM 승인 요청 / 즉시 반영 통지) — PM에게 알림
            if pm_names:
                pm_rows = await db.execute(
                    select(User.id).where(User.name.in_(pm_names))
                )
                pm_user_ids = [str(row[0]) for row in pm_rows.all()]
                await alert_service.send_notification_to_pm(event_id, pm_user_ids, noti_type="PM_APPROVED_REQUEST")

    # 기획/디자인 역할 즉시 반영 케이스에서 Slides 웹훅 호출
    if is_immediate:
        assignee_role = data.get("assignee_role") or ""
        if any(r in assignee_role for r in alert_service.DESIGN_ROLES):
            req_id = data.get("req_id")
            if project_id and req_id:
                await alert_service.call_slides_webhook(project_id, req_id)

    result: dict = {"task_id": task_id, "old_status": old_status, "new_status": body.status}
    if not is_immediate:
        result["status"] = "pending_approval"
    if is_pm:
        result["status"] = "applied_by_pm"
    return result


@router.post("/{task_id}/approve", response_model=TaskApprovalResponse)
async def approve_task_status(
    body: TaskApprovalRequest,
    task_id: str = Path(..., pattern=ID_PATTERN),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskApprovalResponse:
    """
    **[PM 승인/반려]** 태스크 상태 변경 요청을 승인하거나 반려합니다.

    - `notification_event_id`: 알림 목록에서 확인한 이벤트 ID
    - `is_approved`: `true`=승인, `false`=반려
    - `rejection_reason`: 반려 시 사유 (반려 시 필수)
    - **인증 필요** (`Authorization: Bearer <token>`)
    """
    # 1. pending 이력 조회
    hist_row = await db.execute(
        select(WbsTaskHistory).where(
            WbsTaskHistory.task_id == task_id,
            WbsTaskHistory.notification_event_id == body.notification_event_id,
            WbsTaskHistory.approval_status == "pending",
        )
    )
    history_entry = hist_row.scalar_one_or_none()
    if history_entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"task_id={task_id}, notification_event_id={body.notification_event_id} 에 해당하는 승인 대기 이력이 없습니다.",
        )

    old_status = history_entry.old_status
    new_status = history_entry.new_status

    # 2. Fuseki 태스크 데이터 조회 (담당자 정보 등)
    data = sparql_repo.get_task_by_id(task_id)
    if data is None:
        raise TaskNotFound(task_id)

    new_task_id: str | None = None

    if body.is_approved:
        # 3-A. 승인: Fuseki 상태 업데이트
        sparql_repo.update_task_status(task_id, new_status)

        # 완료 → 다른 상태 전환이면 추가 태스크 생성
        if old_status == "완료":
            project_id = data.get("project_id")
            extra_start_str = history_entry.extra_work_start
            extra_end_str = history_entry.extra_work_end

            if project_id and extra_start_str and extra_end_str:
                extra_start = date.fromisoformat(extra_start_str)
                extra_end = date.fromisoformat(extra_end_str)

                base_name = data["task_name"]
                if " - " in base_name and base_name.rsplit(" - ", 1)[-1].isdigit():
                    root_name = base_name.rsplit(" - ", 1)[0]
                    next_num = int(base_name.rsplit(" - ", 1)[-1]) + 1
                else:
                    root_name = base_name
                    next_num = 1
                new_task_name = f"{root_name} - {next_num}"

                base_wbs = data["wbs_code"]
                if base_wbs.endswith(f"-{next_num - 1}"):
                    new_wbs_code = base_wbs.rsplit("-", 1)[0] + f"-{next_num}"
                else:
                    new_wbs_code = f"{base_wbs}-{next_num}"

                new_task_id = f"{project_id}-R{str(uuid.uuid4())[:8].upper()}"
                delta = (extra_end - extra_start).days + 1
                planned_hours = round(delta * 8.0, 1) if data.get("planned_hours") is None else data["planned_hours"]
                assignee_person_id = data["assignee"]["person_id"] if data.get("assignee") else None

                sparql_repo.insert_single_task(
                    project_id=project_id,
                    task_id=new_task_id,
                    wbs_code=new_wbs_code,
                    task_name=new_task_name,
                    planned_start=extra_start_str,
                    planned_end=extra_end_str,
                    planned_hours=planned_hours,
                    description=history_entry.change_reason,
                    assignee_role=data.get("assignee_role"),
                    assignee_person_id=assignee_person_id,
                    estimated_days=float(delta),
                    depends_on_codes=data.get("depends_on") or [],
                    req_id=data.get("req_id"),
                )
                logger.info("승인 후 추가 태스크 생성: new_task_id=%s wbs_code=%s", new_task_id, new_wbs_code)

                # 옵션: 후속/충돌 태스크 일정 자동 재산출
                if body.reschedule_wbs:
                    try:
                        rs = rfp_service.reschedule_wbs_after_extra_task(
                            project_id=project_id,
                            new_task_id=new_task_id,
                        )
                        logger.info(
                            "[APPROVE-RESCHEDULE] project=%s new_task=%s affected=%d skipped_completed=%d overflow=%d total=%d",
                            project_id, new_task_id,
                            rs["affected"], rs["skipped_completed"], rs["overflow"], rs["total"],
                        )
                    except Exception as e:
                        # 재산출 실패해도 승인 자체는 성공 — 경고 로그만
                        logger.warning(
                            "[APPROVE-RESCHEDULE] 재산출 실패 (무시): project=%s new_task=%s err=%s",
                            project_id, new_task_id, e,
                        )

        # # Slides 웹훅 (기획/디자인 역할)
        # assignee_role = data.get("assignee_role") or ""
        # if any(r in assignee_role for r in alert_service.DESIGN_ROLES):
        #     project_id = data.get("project_id")
        #     req_id = data.get("req_id")
        #     if project_id and req_id:
        #         await alert_service.call_slides_webhook(project_id, req_id)

        history_entry.approval_status = "approved"
    else:
        # 3-B. 반려: Fuseki 변경 없음
        history_entry.approval_status = "rejected"

    # PM 승인/반려 행위를 별도 이력으로 저장
    pm_history = WbsTaskHistory(
        id=str(uuid.uuid4()),
        task_id=task_id,
        changed_by=current_user.id,
        old_status=old_status,
        new_status=new_status if body.is_approved else old_status,
        change_reason=body.rejection_reason if not body.is_approved else None,
        approval_status="approved" if body.is_approved else "rejected",
    )
    db.add(pm_history)

    await db.commit()

    # 4. 담당자에게 알림 전달 (승인/반려 결과 포함 — 풍부한 페이로드)
    assignee_name = data.get("assignee", {}).get("person_name") if data.get("assignee") else None
    assignee_user_ids: list[str] = []
    if assignee_name:
        assignee_rows = await db.execute(select(User.id).where(User.name == assignee_name))
        assignee_user_ids = [str(row[0]) for row in assignee_rows.all()]

    await alert_service.send_notification_to_assignee(
        event_id=body.notification_event_id,
        assignee_user_ids=assignee_user_ids,
        is_approved=body.is_approved,
        rejection_reason=body.rejection_reason,
    )

    # 4-2. 프로젝트 전체 멤버에게도 알림 전달 (담당자 + 승인자 본인 제외)
    project_id = data.get("project_id")
    if project_id:
        member_names = sparql_repo.get_project_member_names(project_id)
        if member_names:
            member_rows = await db.execute(
                select(User.id, User.name).where(User.name.in_(member_names))
            )
            exclude_ids = set(assignee_user_ids) | {str(current_user.id)}
            other_user_ids = [
                str(row[0]) for row in member_rows.all()
                if str(row[0]) not in exclude_ids
            ]
            if other_user_ids:
                await alert_service.send_notification_to_users(
                    event_id=body.notification_event_id,
                    user_ids=other_user_ids,
                    noti_type="PM_APPROVED" if body.is_approved else "PM_REJECTED",
                )

    logger.info(
        "PM 승인 처리: task_id=%s event_id=%s result=%s by %s",
        task_id, body.notification_event_id, "approved" if body.is_approved else "rejected", current_user.email,
    )

    return TaskApprovalResponse(
        task_id=task_id,
        result="approved" if body.is_approved else "rejected",
        new_task_id=new_task_id,
    )
