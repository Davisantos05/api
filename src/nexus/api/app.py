"""FastAPI application factory for NEXUS."""

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader

from nexus.api.schemas import (
    ErrorDetail,
    ErrorResponse,
    OperationResponse,
    OperationResult,
)
from nexus.domain.authorization import AgentPolicy, OperationRequest, evaluate_operation
from nexus.security.dev_agents import (
    DevelopmentAgentRegistry,
    registry_from_environment,
)

agent_token_header = APIKeyHeader(
    name="X-Nexus-Agent-Token",
    scheme_name="DevelopmentAgentToken",
    description=(
        "Temporary local-development agent token. This mechanism is not suitable "
        "for production."
    ),
    auto_error=False,
)


def create_app(registry: DevelopmentAgentRegistry | None = None) -> FastAPI:
    """Create an application, optionally injecting a registry for tests."""

    app = FastAPI(
        title="NEXUS Authorization API",
        version="0.2.0",
        description=(
            "Development API for simulated authorization decisions. It does not "
            "execute payments or other real financial operations."
        ),
    )
    app.state.agent_registry = registry

    def get_registry() -> DevelopmentAgentRegistry:
        if app.state.agent_registry is None:
            try:
                app.state.agent_registry = registry_from_environment()
            except (RuntimeError, ValueError) as error:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail={
                        "code": "development_agent_not_configured",
                        "message": str(error),
                    },
                ) from error
        return app.state.agent_registry

    def authenticated_agent(
        token: Annotated[str | None, Depends(agent_token_header)],
        agent_registry: Annotated[DevelopmentAgentRegistry, Depends(get_registry)],
    ) -> AgentPolicy:
        if token is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "missing_agent_token",
                    "message": "X-Nexus-Agent-Token header is required",
                },
            )
        policy = agent_registry.identify(token)
        if policy is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "invalid_agent_token",
                    "message": "agent token is invalid",
                },
            )
        return policy

    @app.exception_handler(HTTPException)
    async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        error = ErrorResponse(
            error=ErrorDetail(
                code=str(detail.get("code", "http_error")),
                message=str(detail.get("message", exc.detail)),
            )
        )
        return JSONResponse(status_code=exc.status_code, content=error.model_dump())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        error = ErrorResponse(
            error=ErrorDetail(
                code="request_validation_error",
                message="request body is invalid",
                details=list(exc.errors()),
            )
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error.model_dump(mode="json"),
        )

    @app.post(
        "/api/v1/operations",
        response_model=OperationResponse,
        summary="Evaluate a simulated agent operation",
        description=(
            "Evaluates an operation against the authenticated agent's server-owned "
            "policy. No payment or real-world action is executed."
        ),
        responses={
            401: {"model": ErrorResponse, "description": "Missing or invalid token"},
            422: {"model": ErrorResponse, "description": "Invalid request body"},
            503: {"model": ErrorResponse, "description": "Local agent not configured"},
        },
        tags=["Authorization"],
    )
    def submit_operation(
        operation: OperationRequest,
        policy: Annotated[AgentPolicy, Depends(authenticated_agent)],
    ) -> OperationResponse:
        decision = evaluate_operation(policy, operation)
        return OperationResponse(
            data=OperationResult(
                request_id=decision.request_id,
                agent_id=decision.agent_id,
                operation=decision.operation,
                amount_cents=decision.amount_cents,
                outcome=decision.outcome,
                reason=decision.reason,
            )
        )

    return app


app = create_app()
