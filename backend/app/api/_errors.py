from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import IntegrationError, NotFoundError, RfpStateError
from app.core.interpreter.llm_client import LLMUnavailable
from app.db.fuseki import FusekiUnavailable


def install(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "detail": str(exc),
                "code": type(exc).__name__,
                "resource": exc.resource,
                "identifier": exc.identifier,
            },
        )

    @app.exception_handler(FusekiUnavailable)
    async def _fuseki_down(request: Request, exc: FusekiUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "triple store unavailable", "message": str(exc)},
        )

    @app.exception_handler(LLMUnavailable)
    async def _llm_down(request: Request, exc: LLMUnavailable) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"detail": "llm unavailable", "message": str(exc)},
        )

    @app.exception_handler(RfpStateError)
    async def _rfp_state(request: Request, exc: RfpStateError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": str(exc),
                "code": "RfpStateError",
                "rfp_id": exc.rfp_id,
                "current_status": exc.current_status,
                "required": exc.required,
            },
        )

    @app.exception_handler(IntegrationError)
    async def _integration_error(request: Request, exc: IntegrationError) -> JSONResponse:
        return JSONResponse(
            status_code=502,
            content={"detail": str(exc), "code": "IntegrationError"},
        )
