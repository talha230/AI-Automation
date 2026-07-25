"""FastAPI application exposing the AI Requirements Assistant.

Endpoints:
    GET  /health        — liveness/readiness probe.
    POST /requirements  — turn a product idea into a structured requirements doc.

Run locally with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .assistant import AssistantError, RequirementsAssistant
from .config import get_settings
from .logging_config import configure_logging, request_id_var
from .schemas import RequirementsRequest, RequirementsResponse

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Configure logging and build the assistant once at startup."""
    settings = get_settings()
    configure_logging(level=settings.log_level, as_json=settings.log_json)
    logger.info(
        "Starting %s (model=%s, api_key=%s)",
        settings.app_name,
        settings.model,
        settings.redacted_api_key,
    )
    if not settings.has_api_key:
        logger.warning(
            "No ANTHROPIC_API_KEY set. The SDK will fall back to an "
            "`ant auth login` profile if one exists; otherwise /requirements "
            "will fail until a key is provided."
        )
    app.state.assistant = RequirementsAssistant(settings)
    yield
    logger.info("Shutting down %s", settings.app_name)


app = FastAPI(
    title="AI Requirements Assistant",
    description="Turns a plain-language product idea into a structured software "
    "requirements document using Claude.",
    version="1.0.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """Assign a request id, expose it on the response, and log the round trip."""
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    token = request_id_var.set(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> handled in %.1f ms",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        request_id_var.reset(token)
    response.headers["x-request-id"] = request_id
    return response


@app.get("/health", tags=["ops"])
async def health() -> dict[str, object]:
    """Basic liveness probe with a hint about credential availability."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "model": settings.model,
        "api_key_configured": settings.has_api_key,
    }


@app.post("/requirements", response_model=RequirementsResponse, tags=["assistant"])
async def create_requirements(payload: RequirementsRequest, request: Request):
    """Generate a structured requirements document from a product idea."""
    assistant: RequirementsAssistant = request.app.state.assistant
    settings = get_settings()
    request_id = request_id_var.get()

    try:
        document = assistant.generate(payload)
    except AssistantError as exc:
        # Upstream/model failure — 502 signals "the dependency failed", not a
        # client mistake (invalid input is already rejected as 422 by FastAPI).
        return JSONResponse(
            status_code=502,
            content={"error": str(exc), "request_id": request_id},
        )

    return RequirementsResponse(
        request_id=request_id,
        model=settings.model,
        document=document,
    )
