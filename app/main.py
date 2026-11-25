"""Application factory and backend entry point."""

from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.chat import router
from app.config import Settings
from app.providers.base import ProviderError


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


class ServiceResponse(BaseModel):
    name: str
    version: str
    docs: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    application = FastAPI(
        title=settings.app_name,
        version="0.2.0",
        description="Self-hosted LLM backend. Phase 2: Gemini text chat and streaming.",
    )
    application.state.settings = settings
    application.include_router(router)

    @application.exception_handler(ProviderError)
    async def provider_error_handler(request: Request, exc: ProviderError):
        return JSONResponse(status_code=exc.status, content={"error": exc.payload()})

    @application.get("/", response_model=ServiceResponse, tags=["service"])
    async def service_info() -> ServiceResponse:
        return ServiceResponse(name=settings.app_name, version=application.version, docs="/docs")

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Process liveness only; does not check model providers or a database."""
        return HealthResponse()

    return application


app = create_app()
