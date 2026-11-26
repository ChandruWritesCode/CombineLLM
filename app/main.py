"""Application factory and backend entry point."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.chat import router
from app.config import Settings
from app.conversations import Generations
from app.conversations import router as conversations_router
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
        application.state.generations = Generations(application.state.store)
        yield
        await application.state.generations.close()

    application = FastAPI(
        title=settings.app_name,
        version="0.3.0",
        description="Self-hosted LLM backend. Phase 3: saved conversations and local chat UI.",
        lifespan=lifespan,
    )
    application.state.settings = settings
    application.include_router(router)
    application.include_router(conversations_router)
    static = Path(__file__).parent / "static"
    application.mount("/static", StaticFiles(directory=static), name="static")

    @application.get("/", include_in_schema=False)
    async def frontend():
        return FileResponse(static / "index.html")

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
