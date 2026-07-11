"""
Centralised error handling for the FastAPI app.

The previous version of every route did:

    try:
        ...
    except Exception as e:
        raise HTTPException(500, detail=str(e))

That swallowed legitimate 4xx responses raised inside the try (e.g. 404
after a DB lookup returned None) and re-raised them as 500s. It also
leaked raw exception messages to the client.

This module provides:
  * an `error_response(status_code, detail, error_id=None)` helper, and
  * an `install_error_handlers(app)` that registers global handlers
    which preserve HTTPException, log with a traceback, and return a
    sanitised body to the client.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from . import new_error_id

logger = logging.getLogger(__name__)


def _error_body(detail: Any, error_id: str | None = None) -> dict:
    return {
        "success": False,
        "error": {"detail": detail, "error_id": error_id},
    }


def error_response(
    status_code: int,
    detail: Any,
    error_id: str | None = None,
) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=_error_body(detail, error_id))


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # Preserve the status code and detail. Pass through 401/403/404/409 etc.
        return error_response(exc.status_code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return error_response(422, {"message": "Invalid request", "errors": exc.errors()})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        error_id = new_error_id()
        logger.error(
            "Unhandled error id=%s on %s %s: %s\n%s",
            error_id,
            request.method,
            request.url.path,
            exc,
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        )
        return error_response(
            500,
            "Internal server error",
            error_id=error_id,
        )
