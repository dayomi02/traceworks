class NotFoundError(Exception):
    resource: str = "resource"

    def __init__(self, identifier: str):
        self.identifier = identifier
        super().__init__(f"{self.resource} not found: {identifier}")


class ProjectNotFound(NotFoundError):
    resource = "project"


class TaskNotFound(NotFoundError):
    resource = "task"


class PersonNotFound(NotFoundError):
    resource = "person"


class RfpNotFound(NotFoundError):
    resource = "rfp"


class RfpStateError(Exception):
    """RFP 상태 전이 불가 (예: analyze 전 confirm 시도)."""
    def __init__(self, rfp_id: str, current_status: str, required: str):
        self.rfp_id = rfp_id
        self.current_status = current_status
        self.required = required
        super().__init__(
            f"RFP {rfp_id}: 상태가 '{current_status}'이므로 '{required}' 작업 불가"
        )


class IntegrationError(Exception):
    """외부 서비스(Google Slides, GitLab 등) 연동 실패."""
    def __init__(self, message: str):
        super().__init__(message)
