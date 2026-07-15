"""
Standardized HTTP error helpers.

Migration target from raw integer status codes:
  Before: HTTPException(status_code=404, detail="not found")
  After:  raise not_found("not found")

All status code → detail mappings are centralized here.
New code MUST use these helpers; existing code can be migrated incrementally.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Optional

from fastapi import HTTPException


def not_found(detail: str = "Not found") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.NOT_FOUND, detail=detail)

def bad_request(detail: str = "Bad request") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=detail)

def unauthorized(detail: str = "Unauthorized") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=detail)

def forbidden(detail: str = "Forbidden") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.FORBIDDEN, detail=detail)

def conflict(detail: str = "Conflict") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.CONFLICT, detail=detail)

def service_unavailable(detail: str = "Service unavailable") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.SERVICE_UNAVAILABLE, detail=detail)

def internal_error(detail: str = "Internal server error") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.INTERNAL_SERVER_ERROR, detail=detail)

def unprocessable(detail: str = "Unprocessable entity") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=detail)

def too_many_requests(detail: str = "Too many requests") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.TOO_MANY_REQUESTS, detail=detail)

def not_implemented(detail: str = "Not implemented") -> HTTPException:
    return HTTPException(status_code=HTTPStatus.NOT_IMPLEMENTED, detail=detail)


__all__ = [
    "not_found", "bad_request", "unauthorized", "forbidden",
    "conflict", "service_unavailable", "internal_error",
    "unprocessable", "too_many_requests", "not_implemented",
]
