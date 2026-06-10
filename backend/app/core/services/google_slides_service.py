import logging
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import get_settings

logger = logging.getLogger(__name__)

_SCOPES = [
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/drive.file",
]


def _credentials() -> Credentials:
    settings = get_settings()
    if not settings.GOOGLE_CLIENT_SECRET_FILE:
        raise RuntimeError("GOOGLE_CLIENT_SECRET_FILE 환경변수가 설정되지 않았습니다.")

    token_file = settings.GOOGLE_TOKEN_FILE
    creds: Credentials | None = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            # 최초 인증: 브라우저 로그인 필요
            flow = InstalledAppFlow.from_client_secrets_file(
                settings.GOOGLE_CLIENT_SECRET_FILE, _SCOPES
            )
            creds = flow.run_local_server(port=0)

        os.makedirs(os.path.dirname(token_file) or ".", exist_ok=True)
        with open(token_file, "w") as f:
            f.write(creds.to_json())
        logger.info("Google OAuth2 토큰 저장: %s", token_file)

    return creds


def create_presentation(project_name: str) -> str:
    """
    Google Slides 프레젠테이션을 생성하고 presentationId를 반환합니다.
    GOOGLE_SLIDES_FOLDER_ID가 설정된 경우 해당 Drive 폴더로 이동합니다.
    """
    settings = get_settings()
    creds = _credentials()

    slides = build("slides", "v1", credentials=creds, cache_discovery=False)
    presentation = slides.presentations().create(body={"title": project_name}).execute()
    presentation_id: str = presentation["presentationId"]
    logger.info("Google Slides 생성 완료: id=%s title=%s", presentation_id, project_name)

    if settings.GOOGLE_SLIDES_FOLDER_ID:
        drive = build("drive", "v3", credentials=creds, cache_discovery=False)
        drive.files().update(
            fileId=presentation_id,
            addParents=settings.GOOGLE_SLIDES_FOLDER_ID,
            removeParents="root",
            fields="id, parents",
        ).execute()
        logger.info("Google Slides 폴더 이동 완료: folder=%s", settings.GOOGLE_SLIDES_FOLDER_ID)

    return presentation_id
