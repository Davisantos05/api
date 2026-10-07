"""Exercise the demo CLI and its server-owned policies through the real API."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from nexus.api.app import WEB_REQUEST_HEADER, create_app
from nexus.cli import seed_dashboard
from nexus.database.base import Base
from nexus.database.models import (
    Agent,
    AgentCredential,
    ApprovalDecision,
    AuditActorType,
    AuditEvent,
    Company,
    OperationRequestRecord,
    User,
    UserRole,
)
from nexus.database.session import create_database_engine, create_session_factory
from nexus.repositories.agents import AgentRepository
from nexus.repositories.companies import CompanyRepository
from nexus.repositories.identity import AgentCredentialRepository
from nexus.repositories.operations import OperationRepository
from nexus.repositories.users import UserRepository
from nexus.security.passwords import hash_password
from nexus.security.tokens import fingerprint_agent_token

DEMO_PASSWORD = "DemoSeedPassword9!"
WEB_HEADERS = {WEB_REQUEST_HEADER: "1"}


@dataclass(frozen=True)
class Demo:
    company_id: UUID
    admin_id: UUID
    agents: dict[str, UUID]
    keys: dict[str, str]


@pytest.fixture
def sessions(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'demo.db'}")
    Base.metadata.create_all(engine)
    yield create_session_factory(engine)
    engine.dispose()


@pytest.fixture
def configured_seed(sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NEXUS_DEMO_ADMIN_PASSWORD", DEMO_PASSWORD)
    monkeypatch.setattr(seed_dashboard, "get_session_factory", lambda: sessions)
    return seed_dashboard.main


@pytest.fixture
def demo(
    sessions: sessionmaker[Session], configured_seed, capsys: pytest.CaptureFixture[str]
) -> Demo:
    configured_seed()
    output = capsys.readouterr().out
    lines = output.splitlines()
    keys = {}
    for name in ("Purchasing Agent", "Finance Agent"):
        label = f"{name} API key (shown once):"
        assert lines.count(label) == 1
        key = lines[lines.index(label) + 1]
        assert key.startswith("nxs_ag_")
        assert output.count(key) == 1
        keys[name] = key
    assert keys["Purchasing Agent"] != keys["Finance Agent"]
    with sessions() as session:
        company = session.scalar(select(Company).where(Company.slug == "nexus-demo"))
        admin = session.scalar(select(User).where(User.email == "admin@nexus.demo"))
        assert company is not None and admin is not None
        agents = {
            agent.name: agent.id
            for agent in AgentRepository(session).list_for_company(company.id)
        }
        return Demo(company.id, admin.id, agents, keys)


@pytest.fixture
def client(sessions: sessionmaker[Session], demo: Demo) -> Iterator[TestClient]:
    with TestClient(create_app(session_factory=sessions)) as value:
        yield value


def login(
    client: TestClient, *, email: str = "admin@nexus.demo", slug: str = "nexus-demo"
) -> None:
    response = client.post(
        "/api/v1/auth/browser-login",
        headers=WEB_HEADERS,
        json={"company_slug": slug, "email": email, "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200
    assert "token" not in response.json()


def submit(
    client: TestClient,
    demo: Demo,
    *,
    agent: str,
    operation: str,
    amount: int,
    request_id: UUID | None = None,
):
    return client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": demo.keys[agent]},
        json={
            "request_id": str(request_id or uuid4()),
            "operation": operation,
            "amount_cents": amount,
        },
    )


def test_seed_creates_exact_multi_agent_dataset_and_dashboard(
    sessions: sessionmaker[Session], demo: Demo, client: TestClient
) -> None:
    expected = {
        "Purchasing Agent": (
            "Agente responsável por solicitações de compras na demonstração.",
            "purchase",
            50_000,
            200_000,
            {
                30_000: ("authorized", None),
                100_000: ("pending_approval", None),
                125_000: ("pending_approval", "rejected"),
                150_000: ("pending_approval", "approved"),
                300_000: ("blocked", None),
            },
        ),
        "Finance Agent": (
            "Agente financeiro para demonstração de operações simuladas.",
            "pix",
            10_000,
            100_000,
            {
                5_000: ("authorized", None),
                50_000: ("pending_approval", None),
                70_000: ("pending_approval", "approved"),
                80_000: ("pending_approval", "rejected"),
                200_000: ("blocked", None),
            },
        ),
    }
    with sessions() as session:
        agents = AgentRepository(session).list_for_company(demo.company_id)
        assert {agent.name for agent in agents} == set(expected)
        admin = session.get(User, demo.admin_id)
        assert admin is not None
        assert admin.name == "Administrador Demo" and admin.role == UserRole.ADMIN
        for agent in agents:
            description, operation, automatic, maximum, cases = expected[agent.name]
            assert agent.active
            assert agent.description == description
            assert {permission.operation for permission in agent.permissions} == {
                operation
            }
            assert (agent.automatic_limit_cents, agent.maximum_limit_cents) == (
                automatic,
                maximum,
            )
            records = OperationRepository(session).list_detailed(
                company_id=demo.company_id, agent_id=agent.id
            )
            assert len(records) == 5
            assert {
                record.amount_cents: (
                    record.outcome,
                    record.approval_decision.decision.value
                    if record.approval_decision
                    else None,
                )
                for record in records
            } == cases
            assert all(record.operation == operation for record in records)
    login(client)
    assert client.get("/api/v1/dashboard/summary").json() == {
        "agents_active": 2,
        "operations_total": 10,
        "authorized": 2,
        "pending_approval": 2,
        "blocked": 2,
        "human_approved": 2,
        "human_rejected": 2,
    }
    assert {agent["name"] for agent in client.get("/api/v1/agents").json()} == set(
        expected
    )
    recent = client.get("/api/v1/operations?limit=6").json()
    assert {item["agent_name"] for item in recent} == set(expected)
    pending = client.get("/api/v1/approvals").json()
    assert {(item["agent_name"], item["amount_cents"]) for item in pending} == {
        ("Purchasing Agent", 100_000),
        ("Finance Agent", 50_000),
    }
    assert {
        item["agent_name"] for item in client.get("/api/v1/dashboard/attention").json()
    } == set(expected)


def test_seed_keys_are_shown_once_and_only_hash_and_prefix_are_stored(
    sessions: sessionmaker[Session], demo: Demo, client: TestClient
) -> None:
    login(client)
    with sessions() as session:
        credentials = list(session.scalars(select(AgentCredential)))
        assert len(credentials) == 2
        assert len({record.token_hash for record in credentials}) == 2
        assert set(AgentCredential.__table__.columns.keys()) == {
            "id",
            "agent_id",
            "token_hash",
            "token_prefix",
            "created_at",
            "expires_at",
            "revoked_at",
            "last_used_at",
        }
        for name, key in demo.keys.items():
            credential = next(
                record for record in credentials if record.agent_id == demo.agents[name]
            )
            assert credential.token_hash == fingerprint_agent_token(key)
            assert credential.token_prefix == key[:12]
            assert credential.last_used_at is not None
            response = client.get(f"/api/v1/agents/{demo.agents[name]}/credentials")
            assert response.status_code == 200 and len(response.json()) == 1
            assert key not in response.text
            assert "token_hash" not in response.text
        # Includes every persisted row, not just the credential table.
        raw_connection = session.connection().connection.driver_connection
        assert raw_connection is not None
        dump = "\n".join(raw_connection.iterdump())
        assert all(key not in dump for key in demo.keys.values())


@pytest.mark.parametrize(
    ("agent", "operation", "amount", "outcome", "reason"),
    [
        (
            "Purchasing Agent",
            "purchase",
            30_000,
            "authorized",
            "within_automatic_limit",
        ),
        (
            "Purchasing Agent",
            "purchase",
            100_000,
            "pending_approval",
            "human_approval_required",
        ),
        ("Purchasing Agent", "purchase", 300_000, "blocked", "maximum_limit_exceeded"),
        ("Purchasing Agent", "pix", 5_000, "blocked", "operation_not_allowed"),
        ("Finance Agent", "pix", 5_000, "authorized", "within_automatic_limit"),
        ("Finance Agent", "pix", 50_000, "pending_approval", "human_approval_required"),
        ("Finance Agent", "pix", 200_000, "blocked", "maximum_limit_exceeded"),
        ("Finance Agent", "purchase", 5_000, "blocked", "operation_not_allowed"),
    ],
)
def test_demo_agent_policies_and_cross_agent_permission_isolation(
    client: TestClient,
    demo: Demo,
    agent: str,
    operation: str,
    amount: int,
    outcome: str,
    reason: str,
) -> None:
    response = submit(client, demo, agent=agent, operation=operation, amount=amount)
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["agent_id"] == str(demo.agents[agent])
    assert result["outcome"] == outcome
    assert result["reason"] == reason


@pytest.mark.parametrize(
    ("amount", "outcome", "reason"),
    [
        (10_000, "authorized", "within_automatic_limit"),
        (10_001, "pending_approval", "human_approval_required"),
        (100_000, "pending_approval", "human_approval_required"),
        (100_001, "blocked", "maximum_limit_exceeded"),
    ],
)
def test_finance_automatic_and_maximum_boundaries(
    client: TestClient, demo: Demo, amount: int, outcome: str, reason: str
) -> None:
    response = submit(
        client, demo, agent="Finance Agent", operation="pix", amount=amount
    )
    assert response.status_code == 200
    assert response.json()["data"]["outcome"] == outcome
    assert response.json()["data"]["reason"] == reason


@pytest.mark.parametrize(
    "extra",
    [
        {"automatic_limit_cents": 999_999},
        {"maximum_limit_cents": 999_999},
        {"allowed_operations": ["purchase"]},
        {"agent_id": str(uuid4())},
        {"company_id": str(uuid4())},
    ],
)
def test_finance_cannot_supply_server_owned_policy_or_identity(
    client: TestClient,
    demo: Demo,
    sessions: sessionmaker[Session],
    extra: dict[str, object],
) -> None:
    response = client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": demo.keys["Finance Agent"]},
        json={
            "request_id": str(uuid4()),
            "operation": "pix",
            "amount_cents": 100_001,
            **extra,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "request_validation_error"
    with sessions() as session:
        assert (
            session.scalar(select(func.count()).select_from(OperationRequestRecord))
            == 10
        )
        agent = session.get(Agent, demo.agents["Finance Agent"])
        assert agent is not None
        assert (agent.automatic_limit_cents, agent.maximum_limit_cents) == (
            10_000,
            100_000,
        )


def test_finance_idempotent_replay_and_conflict_do_not_duplicate_operations_or_audit(
    client: TestClient, demo: Demo, sessions: sessionmaker[Session]
) -> None:
    request_id = uuid4()
    first = submit(
        client,
        demo,
        agent="Finance Agent",
        operation="pix",
        amount=50_000,
        request_id=request_id,
    )
    replay = submit(
        client,
        demo,
        agent="Finance Agent",
        operation="pix",
        amount=50_000,
        request_id=request_id,
    )
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    conflict = submit(
        client,
        demo,
        agent="Finance Agent",
        operation="pix",
        amount=50_001,
        request_id=request_id,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_conflict"
    with sessions() as session:
        operations = list(
            session.scalars(
                select(OperationRequestRecord).where(
                    OperationRequestRecord.request_id == request_id
                )
            )
        )
        assert len(operations) == 1
        events = list(
            session.scalars(
                select(AuditEvent).where(AuditEvent.target_id == operations[0].id)
            )
        )
        assert {event.action for event in events} == {
            "operation.requested",
            "operation.pending_approval",
        }
        assert len(events) == 2


def test_both_demo_agents_can_reuse_the_same_request_id(
    client: TestClient, demo: Demo, sessions: sessionmaker[Session]
) -> None:
    request_id = uuid4()
    for agent, operation, amount in [
        ("Purchasing Agent", "purchase", 30_000),
        ("Finance Agent", "pix", 5_000),
    ]:
        response = submit(
            client,
            demo,
            agent=agent,
            operation=operation,
            amount=amount,
            request_id=request_id,
        )
        assert response.status_code == 200
        assert response.json()["data"]["outcome"] == "authorized"
        assert response.json()["data"]["agent_id"] == str(demo.agents[agent])
    with sessions() as session:
        records = list(
            session.scalars(
                select(OperationRequestRecord).where(
                    OperationRequestRecord.request_id == request_id
                )
            )
        )
        assert len(records) == 2
        assert {record.agent_id for record in records} == set(demo.agents.values())


def test_finance_snapshot_survives_later_server_policy_changes(
    client: TestClient, demo: Demo, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session:
        historical = next(
            record
            for record in OperationRepository(session).list_detailed(
                company_id=demo.company_id, agent_id=demo.agents["Finance Agent"]
            )
            if record.amount_cents == 5_000
        )
        operation_id, request_id = historical.id, historical.request_id
        expected = {
            "schema_version": 1,
            "active": True,
            "allowed_operations": ["pix"],
            "automatic_limit_cents": 10_000,
            "maximum_limit_cents": 100_000,
        }
        assert historical.policy_snapshot == expected
        agent = session.get(Agent, demo.agents["Finance Agent"])
        assert agent is not None
        agent.automatic_limit_cents = 1
        agent.maximum_limit_cents = 2
        session.commit()
    login(client)
    assert (
        client.get(f"/api/v1/operations/{operation_id}").json()["policy_snapshot"]
        == expected
    )
    replay = submit(
        client,
        demo,
        agent="Finance Agent",
        operation="pix",
        amount=5_000,
        request_id=request_id,
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["outcome"] == "authorized"
    new = submit(client, demo, agent="Finance Agent", operation="pix", amount=5_000)
    assert new.status_code == 200
    assert new.json()["data"]["reason"] == "maximum_limit_exceeded"


def test_demo_audit_preserves_both_agent_actors_and_human_administrator(
    demo: Demo, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session:
        operations = {
            record.id: record
            for record in session.scalars(select(OperationRequestRecord))
        }
        events = list(
            session.scalars(
                select(AuditEvent).where(AuditEvent.target_type == "operation_request")
            )
        )
        assert len(events) == 24
        for agent_id in demo.agents.values():
            agent_events = [
                event
                for event in events
                if operations[event.target_id].agent_id == agent_id
            ]
            assert {event.action for event in agent_events} == {
                "operation.requested",
                "operation.authorized",
                "operation.pending_approval",
                "operation.blocked",
                "approval.approved",
                "approval.rejected",
            }
            requested = [
                event for event in agent_events if event.action == "operation.requested"
            ]
            assert len(requested) == 5
            assert all(
                event.actor_type == AuditActorType.AGENT
                and event.actor_agent_id == agent_id
                and event.actor_user_id is None
                for event in requested
            )
            human = [
                event for event in agent_events if event.action.startswith("approval.")
            ]
            assert len(human) == 2
            assert all(
                event.actor_type == AuditActorType.HUMAN
                and event.actor_user_id == demo.admin_id
                and event.actor_agent_id is None
                and event.actor_user is not None
                and event.actor_user.name == "Administrador Demo"
                for event in human
            )
            outcomes = [
                event
                for event in agent_events
                if event.action != "operation.requested"
                and event.action.startswith("operation.")
            ]
            assert all(
                event.actor_type == AuditActorType.SYSTEM
                and event.actor_agent_id is None
                and event.actor_user_id is None
                for event in outcomes
            )


def test_seed_repeat_refuses_existing_demo_without_changes_or_reprinting_keys(
    demo: Demo,
    configured_seed,
    sessions: sessionmaker[Session],
    capsys: pytest.CaptureFixture[str],
) -> None:
    tables = (
        Company,
        User,
        Agent,
        AgentCredential,
        OperationRequestRecord,
        ApprovalDecision,
        AuditEvent,
    )
    with sessions() as session:
        before = [
            session.scalar(select(func.count()).select_from(table)) for table in tables
        ]
    with pytest.raises(SystemExit, match="already exists; no data was changed"):
        configured_seed()
    assert capsys.readouterr().out == ""
    with sessions() as session:
        assert [
            session.scalar(select(func.count()).select_from(table)) for table in tables
        ] == before


def test_seed_requires_explicit_password_and_leaves_database_empty(
    configured_seed, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("NEXUS_DEMO_ADMIN_PASSWORD")
    with pytest.raises(SystemExit, match="Set NEXUS_DEMO_ADMIN_PASSWORD"):
        configured_seed()
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0


def test_seed_rejects_weak_password_without_partial_company(
    configured_seed, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_DEMO_ADMIN_PASSWORD", "weak")
    with pytest.raises(ValueError, match="at least 12 characters"):
        configured_seed()
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 0


def test_demo_tenant_isolation_protects_operations_approvals_credentials_and_audit(
    client: TestClient, demo: Demo, sessions: sessionmaker[Session]
) -> None:
    with sessions() as session:
        other = CompanyRepository(session).create(name="Other Company", slug="other")
        UserRepository(session).create(
            company_id=other.id,
            name="Other Admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            password_hash=hash_password(DEMO_PASSWORD),
        )
        session.commit()
        operation_id = session.scalar(
            select(OperationRequestRecord.id).where(
                OperationRequestRecord.outcome == "pending_approval"
            )
        )
        credential = session.scalar(
            select(AgentCredential).where(
                AgentCredential.agent_id == demo.agents["Finance Agent"]
            )
        )
        assert operation_id is not None and credential is not None
        credential_id = credential.id
    login(client, email="admin@example.com", slug="other")
    assert client.get("/api/v1/dashboard/summary").json()["operations_total"] == 0
    assert client.get("/api/v1/dashboard/attention").json() == []
    assert client.get("/api/v1/agents").json() == []
    assert client.get("/api/v1/approvals").json() == []
    assert client.get(f"/api/v1/operations/{operation_id}").status_code == 404
    assert client.get(f"/api/v1/approvals/{operation_id}").status_code == 404
    assert (
        client.post(
            f"/api/v1/approvals/{operation_id}/decision",
            headers=WEB_HEADERS,
            json={"decision": "approved"},
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/agents/{demo.agents['Finance Agent']}/credentials").json()
        == []
    )
    assert (
        client.post(
            f"/api/v1/agents/{demo.agents['Finance Agent']}/credentials/{credential_id}/revoke",
            headers=WEB_HEADERS,
        ).status_code
        == 404
    )
    assert not any(
        event["target_type"] == "operation_request"
        for event in client.get("/api/v1/audit-events").json()
    )


@pytest.mark.parametrize("role", [UserRole.APPROVER, UserRole.VIEWER])
def test_multi_agent_demo_preserves_rbac_and_credential_separation(
    client: TestClient, demo: Demo, sessions: sessionmaker[Session], role: UserRole
) -> None:
    with sessions() as session:
        user = UserRepository(session).create(
            company_id=demo.company_id,
            name=role.value,
            email=f"{role.value}@example.com",
            role=role,
            password_hash=hash_password(DEMO_PASSWORD),
        )
        session.commit()
        email = user.email
    login(client, email=email)
    assert client.get("/api/v1/dashboard/summary").json()["agents_active"] == 2
    approvals = client.get("/api/v1/approvals")
    assert approvals.status_code == (200 if role == UserRole.APPROVER else 403)
    for agent_id in demo.agents.values():
        assert client.get(f"/api/v1/agents/{agent_id}/credentials").status_code == 403
        assert (
            client.post(
                f"/api/v1/agents/{agent_id}/credentials", headers=WEB_HEADERS, json={}
            ).status_code
            == 403
        )


def test_finance_credential_revocation_does_not_revoke_purchasing_access(
    client: TestClient, demo: Demo, sessions: sessionmaker[Session]
) -> None:
    login(client)
    agent_id = demo.agents["Finance Agent"]
    credential = client.get(f"/api/v1/agents/{agent_id}/credentials").json()[0]
    assert (
        client.post(
            f"/api/v1/agents/{agent_id}/credentials/{credential['id']}/revoke",
            headers=WEB_HEADERS,
        ).status_code
        == 204
    )
    assert (
        submit(
            client, demo, agent="Finance Agent", operation="pix", amount=5_000
        ).status_code
        == 401
    )
    assert (
        submit(
            client, demo, agent="Purchasing Agent", operation="purchase", amount=30_000
        ).status_code
        == 200
    )
    with sessions() as session:
        other = AgentCredentialRepository(session).authenticate(
            demo.keys["Purchasing Agent"]
        )
        assert other is not None and other.revoked_at is None
