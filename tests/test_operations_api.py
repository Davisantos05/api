from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session, sessionmaker

from nexus.api.app import create_app
from nexus.database.base import Base
from nexus.database.session import create_database_engine, create_session_factory
from nexus.repositories.agents import AgentRepository
from nexus.repositories.companies import CompanyRepository

TEST_TOKEN = "test-agent-token-with-at-least-32-characters"


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'api.db'}")
    Base.metadata.create_all(engine)
    sessions: sessionmaker[Session] = create_session_factory(engine)
    with sessions() as session:
        company = CompanyRepository(session).create(name="API Test", slug="api-test")
        AgentRepository(session).create(
            company_id=company.id,
            name="Test Agent",
            description="",
            token=TEST_TOKEN,
            allowed_operations={"purchase"},
            automatic_limit_cents=50_000,
            maximum_limit_cents=200_000,
        )
        session.commit()
    with TestClient(create_app(session_factory=sessions)) as test_client:
        yield test_client
    engine.dispose()


def submit(
    client: TestClient,
    *,
    amount_cents: object,
    operation: str = "purchase",
    token: str = TEST_TOKEN,
) -> Response:
    return client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": token},
        json={
            "request_id": str(uuid4()),
            "operation": operation,
            "amount_cents": amount_cents,
        },
    )


@pytest.mark.parametrize("amount_cents", [0, 50_000])
def test_api_authorizes_zero_and_automatic_boundary(
    client: TestClient, amount_cents: int
) -> None:
    response = submit(client, amount_cents=amount_cents)

    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == "authorized"
    assert response.json()["data"]["reason"] == "within_automatic_limit"


@pytest.mark.parametrize("amount_cents", [50_001, 200_000])
def test_api_returns_pending_for_human_approval_range(
    client: TestClient, amount_cents: int
) -> None:
    response = submit(client, amount_cents=amount_cents)

    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == "pending_approval"
    assert response.json()["data"]["reason"] == "human_approval_required"


def test_api_blocks_above_maximum(client: TestClient) -> None:
    response = submit(client, amount_cents=200_001)

    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == "blocked"
    assert response.json()["data"]["reason"] == "maximum_limit_exceeded"


def test_api_blocks_operation_not_in_server_policy(client: TestClient) -> None:
    response = submit(client, amount_cents=100, operation="transfer")

    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == "blocked"
    assert response.json()["data"]["reason"] == "operation_not_allowed"


@pytest.mark.parametrize("amount_cents", [-1, 1.5, "100"])
def test_api_rejects_invalid_money_values(
    client: TestClient, amount_cents: object
) -> None:
    response = submit(client, amount_cents=amount_cents)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_api_rejects_unknown_agent(client: TestClient) -> None:
    response = submit(
        client,
        amount_cents=100,
        token="unknown-agent-token-with-at-least-32-chars",
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "invalid_agent_token",
            "message": "agent token is invalid",
            "details": None,
        }
    }


def test_api_requires_agent_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/operations",
        json={
            "request_id": str(uuid4()),
            "operation": "purchase",
            "amount_cents": 100,
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_agent_token"


def test_api_rejects_policy_fields_in_request(client: TestClient) -> None:
    response = client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": TEST_TOKEN},
        json={
            "request_id": str(uuid4()),
            "operation": "purchase",
            "amount_cents": 100,
            "maximum_limit_cents": 999_999_999,
            "company_id": str(uuid4()),
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"


def test_openapi_documents_endpoint_and_security_scheme(client: TestClient) -> None:
    document = client.get("/openapi.json").json()

    assert "/api/v1/operations" in document["paths"]
    assert "AgentApiKey" in document["components"]["securitySchemes"]
