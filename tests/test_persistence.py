from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from nexus.api.app import create_app
from nexus.database.base import Base
from nexus.database.models import Agent, Company, OperationRequestRecord, UserRole
from nexus.database.session import create_database_engine, create_session_factory
from nexus.domain.authorization import DecisionOutcome, OperationRequest
from nexus.repositories.agents import AgentRepository
from nexus.repositories.companies import CompanyRepository
from nexus.repositories.operations import OperationRepository
from nexus.repositories.users import UserRepository
from nexus.security.tokens import fingerprint_agent_token
from nexus.services.authorization import (
    IdempotencyConflictError,
    PersistentAuthorizationService,
    UnknownAgentError,
)

AGENT_TOKEN = "persistent-agent-token-1234567890abcdef"
SECOND_TOKEN = "second-company-agent-token-1234567890abcd"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    database_path = tmp_path / "test.db"
    test_engine = create_database_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


def create_company_and_agent(
    session: Session,
    *,
    company_name: str = "Company A",
    token: str = AGENT_TOKEN,
    active: bool = True,
    automatic_limit_cents: int = 50_000,
    maximum_limit_cents: int = 200_000,
) -> tuple[Company, Agent]:
    company = CompanyRepository(session).create(name=company_name)
    agent = AgentRepository(session).create(
        company_id=company.id,
        name="Purchasing Agent",
        description="Test agent",
        token=token,
        allowed_operations={"purchase", "read_inventory"},
        automatic_limit_cents=automatic_limit_cents,
        maximum_limit_cents=maximum_limit_cents,
        active=active,
    )
    session.commit()
    return company, agent


def operation(amount_cents: int, *, request_id: UUID | None = None) -> OperationRequest:
    return OperationRequest(
        request_id=request_id or uuid4(),
        operation="purchase",
        amount_cents=amount_cents,
    )


def test_creates_company_and_user_with_tenant_relationship(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        company = CompanyRepository(session).create(name="NEXUS Test")
        user = UserRepository(session).create(
            company_id=company.id,
            name="Test Admin",
            email="admin@example.test",
            role=UserRole.ADMIN,
        )
        session.commit()

        assert company.id is not None
        assert user.company_id == company.id
        assert (
            UserRepository(session).get(company_id=company.id, user_id=user.id) == user
        )


def test_creates_agent_for_company_without_storing_plaintext_token(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        company, agent = create_company_and_agent(session)

        assert agent.company_id == company.id
        assert agent.token_hash == fingerprint_agent_token(AGENT_TOKEN)
        assert agent.token_hash != AGENT_TOKEN.encode()


def test_loads_permissions_and_builds_policy_from_database(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        company, agent = create_company_and_agent(session)
        loaded = AgentRepository(session).get(company_id=company.id, agent_id=agent.id)

        assert loaded is not None
        assert {permission.operation for permission in loaded.permissions} == {
            "purchase",
            "read_inventory",
        }
        policy = AgentRepository.to_policy(loaded)
        assert policy.company_id == company.id
        assert policy.allowed_operations == frozenset({"purchase", "read_inventory"})
        assert policy.automatic_limit_cents == 50_000
        assert policy.maximum_limit_cents == 200_000


@pytest.mark.parametrize(
    ("amount_cents", "expected"),
    [
        (30_000, DecisionOutcome.AUTHORIZED),
        (100_000, DecisionOutcome.PENDING_APPROVAL),
        (300_000, DecisionOutcome.BLOCKED),
    ],
)
def test_persists_every_decision_outcome(
    sessions: sessionmaker[Session], amount_cents: int, expected: DecisionOutcome
) -> None:
    with sessions() as session:
        company, agent = create_company_and_agent(session)
        request = operation(amount_cents)

        decision = PersistentAuthorizationService(session).evaluate(
            token=AGENT_TOKEN, request=request
        )
        record = OperationRepository(session).get(
            company_id=company.id,
            agent_id=agent.id,
            request_id=request.request_id,
        )

        assert decision.outcome is expected
        assert record is not None
        assert record.outcome == expected.value


def test_repositories_isolate_two_companies(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        company_a, agent_a = create_company_and_agent(session)
        company_b, _agent_b = create_company_and_agent(
            session, company_name="Company B", token=SECOND_TOKEN
        )
        request = operation(100)
        PersistentAuthorizationService(session).evaluate(
            token=AGENT_TOKEN, request=request
        )

        assert (
            AgentRepository(session).get(company_id=company_b.id, agent_id=agent_a.id)
            is None
        )
        assert OperationRepository(session).list_for_company(company_b.id) == []
        assert len(OperationRepository(session).list_for_company(company_a.id)) == 1


def test_identical_request_id_replays_one_persisted_decision(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        create_company_and_agent(session)
        request = operation(30_000)
        service = PersistentAuthorizationService(session)

        first = service.evaluate(token=AGENT_TOKEN, request=request)
        replay = service.evaluate(token=AGENT_TOKEN, request=request)
        count = session.scalar(select(func.count()).select_from(OperationRequestRecord))

        assert replay == first
        assert count == 1


def test_reused_request_id_with_different_payload_is_rejected(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        create_company_and_agent(session)
        request_id = uuid4()
        service = PersistentAuthorizationService(session)
        service.evaluate(
            token=AGENT_TOKEN, request=operation(100, request_id=request_id)
        )

        with pytest.raises(IdempotencyConflictError):
            service.evaluate(
                token=AGENT_TOKEN, request=operation(101, request_id=request_id)
            )


def test_two_agents_in_same_company_can_reuse_request_id(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        company, first_agent = create_company_and_agent(session)
        second_agent = AgentRepository(session).create(
            company_id=company.id,
            name="Second Purchasing Agent",
            description="Another agent in the same tenant",
            token=SECOND_TOKEN,
            allowed_operations={"purchase"},
            automatic_limit_cents=50_000,
            maximum_limit_cents=200_000,
        )
        session.commit()
        request_id = uuid4()
        service = PersistentAuthorizationService(session)

        first = service.evaluate(
            token=AGENT_TOKEN, request=operation(100, request_id=request_id)
        )
        second = service.evaluate(
            token=SECOND_TOKEN, request=operation(101, request_id=request_id)
        )

        assert first.agent_id == first_agent.id
        assert second.agent_id == second_agent.id
        assert first.request_id == second.request_id == request_id
        assert (
            session.scalar(select(func.count()).select_from(OperationRequestRecord))
            == 2
        )


def test_agents_in_different_companies_can_reuse_request_id(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        first_company, first_agent = create_company_and_agent(session)
        second_company, second_agent = create_company_and_agent(
            session, company_name="Company B", token=SECOND_TOKEN
        )
        request_id = uuid4()
        service = PersistentAuthorizationService(session)

        first = service.evaluate(
            token=AGENT_TOKEN, request=operation(100, request_id=request_id)
        )
        second = service.evaluate(
            token=SECOND_TOKEN, request=operation(101, request_id=request_id)
        )

        assert first.agent_id == first_agent.id
        assert second.agent_id == second_agent.id
        assert first.company_id == first_company.id
        assert second.company_id == second_company.id
        assert first.request_id == second.request_id == request_id
        assert (
            session.scalar(select(func.count()).select_from(OperationRequestRecord))
            == 2
        )


def test_unknown_agent_is_rejected(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        with pytest.raises(UnknownAgentError):
            PersistentAuthorizationService(session).evaluate(
                token="unknown-token-with-more-than-32-characters",
                request=operation(100),
            )


def test_inactive_agent_is_blocked_and_persisted(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        company, agent = create_company_and_agent(session, active=False)
        request = operation(100)

        decision = PersistentAuthorizationService(session).evaluate(
            token=AGENT_TOKEN, request=request
        )
        record = OperationRepository(session).get(
            company_id=company.id,
            agent_id=agent.id,
            request_id=request.request_id,
        )

        assert decision.outcome is DecisionOutcome.BLOCKED
        assert record is not None
        assert record.reason == "agent_inactive"


def test_api_uses_database_limits_and_persists_result(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        create_company_and_agent(
            session, automatic_limit_cents=100, maximum_limit_cents=200
        )

    with TestClient(create_app(session_factory=sessions)) as client:
        response = client.post(
            "/api/v1/operations",
            headers={"X-Nexus-Agent-Token": AGENT_TOKEN},
            json={
                "request_id": str(uuid4()),
                "operation": "purchase",
                "amount_cents": 101,
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == "pending_approval"
    with sessions() as session:
        assert (
            session.scalar(select(func.count()).select_from(OperationRequestRecord))
            == 1
        )


def test_api_returns_conflict_for_changed_idempotent_payload(
    sessions: sessionmaker[Session],
) -> None:
    with sessions() as session:
        create_company_and_agent(session)
    request_id = str(uuid4())
    headers = {"X-Nexus-Agent-Token": AGENT_TOKEN}

    with TestClient(create_app(session_factory=sessions)) as client:
        first = client.post(
            "/api/v1/operations",
            headers=headers,
            json={"request_id": request_id, "operation": "purchase", "amount_cents": 1},
        )
        conflict = client.post(
            "/api/v1/operations",
            headers=headers,
            json={"request_id": request_id, "operation": "purchase", "amount_cents": 2},
        )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
