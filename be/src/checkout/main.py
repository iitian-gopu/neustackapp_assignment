import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from checkout.api import router
from checkout.config import Settings
from checkout.database import Database
from checkout.errors import DomainError
from checkout.schemas import ErrorResponse
from checkout.service import Store

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None):
    database = Database(settings or Settings.from_env())

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        yield

    app = FastAPI(
        title="Checkout and Rewards",
        version="0.1.0",
        lifespan=lifespan,
        responses={status: {"model": ErrorResponse} for status in (404, 409, 422, 500, 503)},
    )
    app.state.store = Store(database)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        return JSONResponse(
            status_code=error.status,
            content={
                "error": {"code": error.code, "message": error.message, "details": error.details}
            },
            headers={"Retry-After": "1"} if error.status == 503 else None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        issues = [
            {"location": list(item["loc"]), "message": item["msg"]} for item in error.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"issues": issues},
                }
            },
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception):
        logger.error("Unhandled request failure", exc_info=error)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Request could not be completed",
                    "details": {},
                }
            },
        )

    app.include_router(router)
    return app


app = create_app()
