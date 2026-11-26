"""Application factory and backend entry point."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.chat import router
from app.config import Settings
from app.connections import Connections
from app.conversations import Generations
from app.conversations import router as conversations_router
from app.model_api import router as model_router
from app.oauth import router as oauth_router
from app.providers.base import ProviderError
from app.storage import Store


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ServiceResponse(BaseModel):
    name: str
    version: str
    docs: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(application):
        application.state.store = Store(settings.database_path)
        application.state.connections = Connections(application.state.store)
        application.state.connections.import_environment(settings)
        application.state.oauth_pending = {}
        application.state.generations = Generations(application.state.store)
        yield
        await application.state.generations.close()

    application = FastAPI(
        title=settings.app_name,
        version="0.5.0",
        description="Self-hosted LLM backend. Phase 5: manual budgets and cost estimates.",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.include_router(router)
    application.include_router(conversations_router)
    application.include_router(model_router)
    application.include_router(oauth_router)
    static = Path(__file__).parent / "static"
    application.mount("/static", StaticFiles(directory=static), name="static")

    @application.get("/", include_in_schema=False)
    async def frontend():
        return FileResponse(static / "index.html")

    @application.get("/settings", include_in_schema=False)
    async def settings_page():
        return FileResponse(static / "settings.html")

    @application.get("/usage", include_in_schema=False)
    async def usage_page():
        return FileResponse(static / "usage.html")

    @application.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Validation errors must not echo submitted API keys or the complete request body.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": error["loc"], "msg": error["msg"], "type": error["type"]}
                    for error in exc.errors()
                ]
            },
        )

    @application.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"} and origin:
            if origin.rstrip("/") != str(request.base_url).rstrip("/"):
                return JSONResponse(
                    status_code=403, content={"detail": "Cross-origin writes are not allowed"}
                )
        response = await call_next(request)
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @application.exception_handler(ProviderError)
    async def provider_error_handler(request: Request, exc: ProviderError):
        return JSONResponse(status_code=exc.status, content={"error": exc.payload()})

    @application.get("/api/v1", response_model=ServiceResponse, tags=["service"])
    async def service_info() -> ServiceResponse:
        return ServiceResponse(name=settings.app_name, version=application.version, docs="/docs")

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Process liveness only; does not check model providers or a database."""
        return HealthResponse()

    return application


app = create_app()
