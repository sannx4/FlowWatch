"""FlowWatch V7 analyst API: auth, country/project/credit drill-down, rule flags.

Run using: uvicorn src.api.day2.app:app --host 127.0.0.1 --port 8000
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import SQLAlchemyError

from src.api.day2 import queries
from src.api.day2.config import Settings, get_settings
from src.api.day2.db import check_warehouse, make_engine, read_connection
from src.api.day2.security import authenticate, issue_token, load_users, verify_token

logger = logging.getLogger("flowwatch.day2")
BEARER = HTTPBearer(auto_error=False)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=500)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int = 1800


def create_app(settings: Settings | None = None, engine: Engine | None = None) -> FastAPI:
    config = settings or get_settings()
    config.database_url()  # Reject unsafe identity before startup.
    pool = engine or make_engine(config)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        load_users(config.users_file)  # Fail startup if identity configuration is invalid.
        try:
            yield
        finally:
            if engine is None:
                pool.dispose()

    api = FastAPI(title="FlowWatch Financial Intelligence", version="0.1.0", lifespan=lifespan,
                  description="Isolated read-only financial stock observations; no ML predictions.")
    api.add_middleware(CORSMiddleware, allow_origins=[config.ui_origin], allow_credentials=False,
                       allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])

    @api.middleware("http")
    async def correlate(request: Request, call_next: Any):
        request_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_failure id=%s path=%s", request_id, request.url.path)
            raise
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        logger.info("request id=%s path=%s status=%s elapsed_ms=%.1f", request_id,
                    request.url.path, response.status_code, (time.monotonic()-started)*1000)
        return response

    @api.exception_handler(SQLAlchemyError)
    async def db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("database_error path=%s", request.url.path)
        return JSONResponse(status_code=503, content={"detail": "Financial warehouse temporarily unavailable"})

    def principal(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(BEARER)]) -> dict[str, str]:
        if credentials is None or credentials.scheme.lower() != "bearer":
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bearer token required")
        return verify_token(credentials.credentials, config.jwt_secret, load_users(config.users_file))

    def operator(user: Annotated[dict[str, str], Depends(principal)]) -> dict[str, str]:
        if user["role"] not in ("operator", "administrator"):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Operator role required")
        return user

    def get_conn(_: Annotated[dict[str, str], Depends(principal)]):
        with read_connection(pool) as conn:
            yield conn

    @api.get("/api/v1/health/live", tags=["Health"])
    def live() -> dict[str, str]:
        return {"status": "alive"}

    @api.get("/api/v1/health/ready", tags=["Health"])
    def ready(_: Annotated[dict[str, str], Depends(principal)]) -> dict[str, Any]:
        try:
            with read_connection(pool) as conn:
                return {"status": "ready", **check_warehouse(conn)}
        except Exception as exc:
            logger.warning("readiness_failed error_type=%s", type(exc).__name__)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Warehouse unavailable") from exc

    @api.get("/api/v1/operations/warehouse", tags=["Operations"])
    def operator_warehouse(_: Annotated[dict[str, str], Depends(operator)]) -> dict[str, Any]:
        try:
            with read_connection(pool) as conn:
                return {"status": "ready", **check_warehouse(conn)}
        except Exception as exc:
            logger.warning("operator_warehouse_failed type=%s", type(exc).__name__)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Warehouse unavailable") from exc

    @api.post("/api/v1/auth/token", response_model=TokenResponse, tags=["Authentication"])
    def token(payload: LoginRequest, request: Request) -> TokenResponse:
        ip = request.client.host if request.client else "unknown"
        auth = authenticate(load_users(config.users_file), payload.username, payload.password, ip)
        return TokenResponse(access_token=issue_token(auth, config.jwt_secret))

    @api.get("/api/v1/auth/me", tags=["Authentication"])
    def me(user: Annotated[dict[str, str], Depends(principal)]) -> dict[str, str]:
        return user

    @api.get("/api/v1/portfolio/summary", tags=["Portfolio"])
    def summary(conn: Annotated[Connection, Depends(get_conn)]) -> dict[str, Any]:
        return {"grain": "latest_observation_per_credit", "currency": "USD",
                "warning": "Period-end reported balances; not verified cash flows. Latest dates may differ across credits.",
                **queries.portfolio(conn)}

    @api.get("/api/v1/countries", tags=["Explore"])
    def list_countries(conn: Annotated[Connection, Depends(get_conn)],
                       q: str = Query(default="", max_length=80),
                       limit: int = Query(default=50, ge=1, le=100),
                       offset: int = Query(default=0, ge=0, le=100000)) -> dict[str, Any]:
        return {"items": queries.countries(conn, q, limit, offset), "limit": limit, "offset": offset}

    @api.get("/api/v1/projects", tags=["Explore"])
    def list_projects(conn: Annotated[Connection, Depends(get_conn)],
                      q: str = Query(default="", max_length=80),
                      country_id: int | None = Query(default=None, ge=1),
                      limit: int = Query(default=50, ge=1, le=100),
                      offset: int = Query(default=0, ge=0, le=100000)) -> dict[str, Any]:
        return {"items": queries.projects(conn, q, country_id, limit, offset), "limit": limit, "offset": offset}

    @api.get("/api/v1/credits", tags=["Explore"])
    def list_credits(conn: Annotated[Connection, Depends(get_conn)],
                     q: str = Query(default="", max_length=80),
                     project_pk: int | None = Query(default=None, ge=1),
                     limit: int = Query(default=50, ge=1, le=100),
                     offset: int = Query(default=0, ge=0, le=100000)) -> dict[str, Any]:
        return {"items": queries.credits(conn, q, project_pk, limit, offset), "limit": limit, "offset": offset}

    @api.get("/api/v1/credits/{credit_id}/timeline", tags=["Credit Intelligence"])
    def credit_timeline(credit_id: int, conn: Annotated[Connection, Depends(get_conn)],
                        limit: int = Query(default=250, ge=1, le=500)) -> dict[str, Any]:
        if credit_id < 1:
            raise HTTPException(422, "Invalid credit ID")
        values = queries.timeline(conn, credit_id, limit)
        if not values:
            raise HTTPException(404, "Credit has no financial observations")
        return {"credit_id": credit_id, "items": values,
                "order": "newest_first", "limit": limit,
                "warning": "Reported balance changes are not validated disbursement cash flows."}

    @api.get("/api/v1/credits/{credit_id}/lineage", tags=["Credit Intelligence"])
    def credit_lineage(credit_id: int, period: date,
                       conn: Annotated[Connection, Depends(get_conn)]) -> dict[str, Any]:
        if credit_id < 1:
            raise HTTPException(422, "Invalid credit ID")
        item = queries.lineage(conn, credit_id, period)
        if item is None:
            raise HTTPException(404, "No matching financial snapshot")
        return {"item": item, "scope": "warehouse_to_canonical_source_locator",
                "warning": "Raw MongoDB page verification is a separate operator workflow."}

    @api.get("/api/v1/risk/watchlist", tags=["Risk Watchlist"])
    def risk_watchlist(conn: Annotated[Connection, Depends(get_conn)],
                       limit: int = Query(default=50, ge=1, le=100)) -> dict[str, Any]:
        return {"items": queries.watchlist(conn, limit), "label": "descriptive_rules_only",
                "warning": "Flags are not predictive risk scores or confirmed financial anomalies."}

    return api


# Lazy ASGI instantiation: imports and offline test discovery do not need secrets.
class LazyASGI:
    _app: FastAPI | None = None

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if self._app is None:
            self._app = create_app()
        await self._app(scope, receive, send)


app = LazyASGI()
