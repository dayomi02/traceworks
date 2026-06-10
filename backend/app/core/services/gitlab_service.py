import logging
import re

import gitlab

from app.config import get_settings

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    import unicodedata
    # 유니코드 정규화 후 ASCII로 변환 (한글 등 비ASCII 제거)
    slug = unicodedata.normalize("NFKD", name)
    slug = slug.encode("ascii", "ignore").decode("ascii")
    slug = slug.lower()
    slug = re.sub(r"[^a-z0-9._-]", "-", slug)   # 허용 문자 외 → 하이픈
    slug = re.sub(r"-{2,}", "-", slug)            # 연속 하이픈 축소
    slug = slug.strip("-_.")                      # 앞뒤 금지 문자 제거
    slug = re.sub(r"\.(git|atom)$", "", slug)     # .git/.atom 접미사 제거
    return slug or "project"


def create_repository(project_name: str, project_id: str) -> dict:
    """
    GitLab 저장소를 생성하고 {"id": str, "url": str}을 반환합니다.
    GITLAB_NAMESPACE에 해당하는 그룹/유저 아래에 저장소가 생성됩니다.
    """
    settings = get_settings()
    if not settings.GITLAB_TOKEN:
        raise RuntimeError("GITLAB_TOKEN 환경변수가 설정되지 않았습니다.")
    if not settings.GITLAB_NAMESPACE:
        raise RuntimeError("GITLAB_NAMESPACE 환경변수가 설정되지 않았습니다.")

    logger.info(
        "[GITLAB] create_repository 시작: url=%s namespace=%s project_name=%s project_id=%s",
        settings.GITLAB_URL, settings.GITLAB_NAMESPACE, project_name, project_id,
    )

    try:
        gl = gitlab.Gitlab(settings.GITLAB_URL, private_token=settings.GITLAB_TOKEN, keep_base_url=True)
        gl.auth()
        logger.info("[GITLAB] 인증 성공: user=%s", getattr(gl.user, "username", "?"))
    except Exception as e:
        logger.exception("[GITLAB] 인증 실패")
        raise RuntimeError(f"GitLab 인증 실패 ({type(e).__name__}): {e}") from e

    # namespace_id 조회: /api/v4/namespaces 직접 검색
    try:
        namespace_id: int | None = None
        namespaces = gl.namespaces.list(search=settings.GITLAB_NAMESPACE, iterator=False)
        for ns in namespaces:
            if ns.path == settings.GITLAB_NAMESPACE or ns.full_path == settings.GITLAB_NAMESPACE:
                namespace_id = ns.id
                break
    except Exception as e:
        logger.exception("[GITLAB] namespace 조회 실패")
        raise RuntimeError(f"GitLab namespace 조회 실패 ({type(e).__name__}): {e}") from e

    if namespace_id is None:
        logger.error("[GITLAB] namespace '%s' 없음 (검색 결과 %d개)",
                     settings.GITLAB_NAMESPACE, len(namespaces) if namespaces else 0)
        raise RuntimeError(f"GitLab namespace '{settings.GITLAB_NAMESPACE}'를 찾을 수 없습니다.")

    repo_name = _slugify(project_name) or _slugify(project_id)
    logger.info("[GITLAB] 프로젝트 생성 시도: namespace_id=%d path=%s", namespace_id, repo_name)
    try:
        repo = gl.projects.create(
            {
                "name": project_name,
                "path": repo_name,
                "namespace_id": namespace_id,
                "initialize_with_readme": True,
                "description": f"Traceworks 자동 생성 저장소 ({project_id})",
                "visibility": "internal",
            }
        )
    except Exception as e:
        # GitlabCreateError는 response_code/response_body 속성을 가짐
        code = getattr(e, "response_code", None)
        body = getattr(e, "response_body", None)
        error_msg = getattr(e, "error_message", None)
        logger.exception(
            "[GITLAB] 프로젝트 생성 실패: code=%s error_message=%s body=%s",
            code, error_msg, body,
        )
        raise RuntimeError(
            f"GitLab 프로젝트 생성 실패 ({type(e).__name__}, code={code}): "
            f"{error_msg or body or e}"
        ) from e

    logger.info("[GITLAB] 저장소 생성 완료: id=%s url=%s", repo.id, repo.http_url_to_repo)
    return {"id": str(repo.id), "url": repo.http_url_to_repo}
