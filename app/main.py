"""Application factory and backend entry point."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

from app.config import Settings


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
        version="0.1.0",
        description="Self-hosted multi-provider LLM backend. Phase 1: foundation.",
    )
    application.state.settings = settings
    @application.get("/", response_model=ServiceResponse, tags=["service"])
    async def service_info() -> ServiceResponse:
        return ServiceResponse(name=settings.app_name, version=application.version, docs="/docs")

    @application.get("/api/v1/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        """Process liveness only; does not check model providers or a database."""
        return HealthResponse()

    return application


app = create_app()
