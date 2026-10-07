from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from nexus.api.app import create_app
from nexus.database.base import Base
from nexus.database.models import (
    Agent,
    AgentPermission,
    ApprovalChoice,
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
from nexus.repositories.audit import AuditAction, AuditRepository, sanitize_metadata
from nexus.repositories.companies import CompanyRepository
from nexus.repositories.identity import AgentCredentialRepository
from nexus.repositories.users import UserRepository
from nexus.security.passwords import hash_password
from nexus.services.approvals import ApprovalConflictError, ApprovalService

PASSWORD = "ApprovalPassword9"


@pytest.mark.parametrize(
    "key", ["password", "password_hash", "token", "authorization", "secret"]
)
def test_audit_metadata_rejects_sensitive_keys(key: str) -> None:
    with pytest.raises(ValueError, match="sensitive audit metadata key"):
        sanitize_metadata({key: "must-not-be-recorded"})


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    value = create_database_engine(f"sqlite:///{tmp_path / 'approvals.db'}")
    Base.metadata.create_all(value)
    yield value
    value.dispose()


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def approval_data(sessions: sessionmaker[Session]) -> dict[str, object]:
    with sessions() as session:
        company = CompanyRepository(session).create(name="Alpha", slug="alpha")
        users = {
            role.value: UserRepository(session).create(
                company_id=company.id,
                name=role.value.title(),
                email=f"{role.value}@example.com",
                role=role,
                password_hash=hash_password(PASSWORD),
            )
            for role in UserRole
        }
        agent = AgentRepository(session).create(
            company_id=company.id,
            name="Buyer",
            description="Approval test agent",
            token=None,
            allowed_operations={"purchase"},
            automatic_limit_cents=500,
            maximum_limit_cents=2_000,
        )
        _credential, api_key = AgentCredentialRepository(session).create(agent)
        other_company = CompanyRepository(session).create(name="Beta", slug="beta")
        other_admin = UserRepository(session).create(
            company_id=other_company.id,
            name="Beta Admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            password_hash=hash_password(PASSWORD),
        )
        session.commit()
        return {
            "company": company,
            "users": users,
            "agent": agent,
            "api_key": api_key,
            "other_company": other_company,
            "other_admin": other_admin,
        }


@pytest.fixture
def client(
    sessions: sessionmaker[Session], approval_data: dict[str, object]
) -> Iterator[TestClient]:
    with TestClient(create_app(session_factory=sessions)) as value:
        yield value


def login(
    client: TestClient,
    *,
    role: str = "admin",
    slug: str = "alpha",
    password: str = PASSWORD,
) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "company_slug": slug,
            "email": f"{role}@example.com",
            "password": password,
        },
    )
    assert response.status_code == 200
    return response.json()["token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def create_operation(
    client: TestClient,
    sessions: sessionmaker[Session],
    api_key: str,
    amount_cents: int,
    *,
    request_id: UUID | None = None,
) -> OperationRequestRecord:
    identifier = request_id or uuid4()
    response = client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": api_key},
        json={
            "request_id": str(identifier),
            "operation": "purchase",
            "amount_cents": amount_cents,
        },
    )
    assert response.status_code == 200
    with sessions() as session:
        record = session.scalar(
            select(OperationRequestRecord).where(
                OperationRequestRecord.request_id == identifier
            )
        )
        assert record is not None
        session.expunge(record)
        return record


def test_policy_snapshot_survives_policy_change_and_idempotent_replay(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
) -> None:
    request_id = uuid4()
    api_key = str(approval_data["api_key"])
    original = create_operation(client, sessions, api_key, 1_000, request_id=request_id)
    expected_snapshot = {
        "schema_version": 1,
        "active": True,
        "allowed_operations": ["purchase"],
        "automatic_limit_cents": 500,
        "maximum_limit_cents": 2_000,
    }
    assert original.outcome == "pending_approval"
    assert original.policy_snapshot == expected_snapshot
    assert set(original.policy_snapshot) == set(expected_snapshot)
    assert not any(
        fragment in str(original.policy_snapshot).lower()
        for fragment in ("password", "token", "secret", "hash", "credential")
    )

    agent = approval_data["agent"]
    with sessions() as session:
        stored_agent = session.get(Agent, agent.id)  # type: ignore[attr-defined]
        assert stored_agent is not None
        stored_agent.automatic_limit_cents = 1_500
        stored_agent.maximum_limit_cents = 4_000
        stored_agent.permissions.clear()
        stored_agent.permissions.append(AgentPermission(operation="refund"))
        session.commit()

    replay = client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": api_key},
        json={
            "request_id": str(request_id),
            "operation": "purchase",
            "amount_cents": 1_000,
        },
    )
    assert replay.status_code == 200
    assert replay.json()["data"]["outcome"] == "pending_approval"

    with sessions() as session:
        records = list(
            session.scalars(
                select(OperationRequestRecord).where(
                    OperationRequestRecord.request_id == request_id
                )
            )
        )
        assert len(records) == 1
        assert records[0].policy_snapshot == expected_snapshot
        audit_count = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.target_id == records[0].id)
        )
        assert audit_count == 2


@pytest.mark.parametrize(
    ("actor_type", "has_user", "has_agent"),
    [
        (AuditActorType.HUMAN, False, False),
        (AuditActorType.HUMAN, True, True),
        (AuditActorType.AGENT, False, False),
        (AuditActorType.AGENT, True, True),
        (AuditActorType.SYSTEM, True, False),
        (AuditActorType.SYSTEM, False, True),
    ],
)
def test_database_rejects_incoherent_audit_actors(
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
    actor_type: AuditActorType,
    has_user: bool,
    has_agent: bool,
) -> None:
    company = approval_data["company"]
    user = approval_data["users"]["admin"]  # type: ignore[index]
    agent = approval_data["agent"]
    with sessions() as session:
        session.add(
            AuditEvent(
                company_id=company.id,  # type: ignore[attr-defined]
                actor_type=actor_type,
                actor_user_id=user.id if has_user else None,  # type: ignore[attr-defined]
                actor_agent_id=agent.id if has_agent else None,  # type: ignore[attr-defined]
                action="integrity.test",
                target_type="test",
                target_id=uuid4(),
                metadata_json={},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_repository_rejects_incoherent_audit_actor_before_database(
    sessions: sessionmaker[Session], approval_data: dict[str, object]
) -> None:
    company = approval_data["company"]
    with (
        sessions() as session,
        pytest.raises(ValueError, match="identifiers do not match"),
    ):
        AuditRepository(session).add(
            company_id=company.id,  # type: ignore[attr-defined]
            actor_type=AuditActorType.HUMAN,
            action=AuditAction.HUMAN_LOGIN,
            target_type="user",
            target_id=uuid4(),
        )


def test_historical_foreign_keys_restrict_parent_deletion(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
) -> None:
    operation = create_operation(client, sessions, str(approval_data["api_key"]), 1_000)
    approver = approval_data["users"]["approver"]  # type: ignore[index]
    company = approval_data["company"]
    agent = approval_data["agent"]
    with sessions() as session:
        ApprovalService(session).decide(
            company_id=company.id,  # type: ignore[attr-defined]
            operation_id=operation.id,
            user_id=approver.id,  # type: ignore[attr-defined]
            decision=ApprovalChoice.APPROVED,
            reason=None,
        )

    deletions = (
        delete(User).where(User.id == approver.id),  # type: ignore[attr-defined]
        delete(Agent).where(Agent.id == agent.id),  # type: ignore[attr-defined]
        delete(Company).where(Company.id == company.id),  # type: ignore[attr-defined]
    )
    for statement in deletions:
        with sessions() as session, pytest.raises(IntegrityError):
            session.execute(statement)
            session.commit()


def test_only_pending_policy_operations_appear_in_default_list(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
) -> None:
    key = str(approval_data["api_key"])
    authorized = create_operation(client, sessions, key, 100)
    pending = create_operation(client, sessions, key, 1_000)
    blocked = create_operation(client, sessions, key, 3_000)
    token = login(client)

    response = client.get("/api/v1/approvals", headers=bearer(token))

    assert response.status_code == 200
    ids = {item["operation_id"] for item in response.json()}
    assert str(pending.id) in ids
    assert str(authorized.id) not in ids
    assert str(blocked.id) not in ids


@pytest.mark.parametrize("role", ["admin", "approver"])
def test_admin_and_approver_can_view_pending(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
    role: str,
) -> None:
    create_operation(client, sessions, str(approval_data["api_key"]), 1_000)
    assert (
        client.get(
            "/api/v1/approvals", headers=bearer(login(client, role=role))
        ).status_code
        == 200
    )


def test_viewer_cannot_view_or_decide_pending(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
) -> None:
    operation = create_operation(client, sessions, str(approval_data["api_key"]), 1_000)
    headers = bearer(login(client, role="viewer"))
    assert client.get("/api/v1/approvals", headers=headers).status_code == 403
    assert (
        client.post(
            f"/api/v1/approvals/{operation.id}/decision",
            headers=headers,
            json={"decision": "approved"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    ("role", "decision", "reason"),
    [
        ("admin", "approved", "Validated by finance"),
        ("approver", "approved", None),
        ("approver", "rejected", "Supplier is not authorized"),
    ],
)
def test_authorized_humans_decide_once_and_reason_is_persisted(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
    role: str,
    decision: str,
    reason: str | None,
) -> None:
    operation = create_operation(client, sessions, str(approval_data["api_key"]), 1_000)
    response = client.post(
        f"/api/v1/approvals/{operation.id}/decision",
        headers=bearer(login(client, role=role)),
        json={"decision": decision, "reason": reason},
    )
    assert response.status_code == 200
    assert response.json()["decision"] == decision
    assert response.json()["reason"] == reason
    with sessions() as session:
        stored = session.scalar(
            select(ApprovalDecision).where(
                ApprovalDecision.operation_request_id == operation.id
            )
        )
        assert stored is not None and stored.reason == reason
        expected_action = f"approval.{decision}"
        audit_count = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.target_id == operation.id,
                AuditEvent.action == expected_action,
            )
        )
        assert audit_count == 1


def test_already_decided_operation_returns_conflict(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
) -> None:
    operation = create_operation(client, sessions, str(approval_data["api_key"]), 1_000)
    url = f"/api/v1/approvals/{operation.id}/decision"
    headers = bearer(login(client, role="approver"))
    assert (
        client.post(url, headers=headers, json={"decision": "approved"}).status_code
        == 200
    )
    conflict = client.post(url, headers=headers, json={"decision": "rejected"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "approval_already_decided"


def test_cross_tenant_and_missing_approvals_are_not_disclosed(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
) -> None:
    operation = create_operation(client, sessions, str(approval_data["api_key"]), 1_000)
    other = bearer(login(client, slug="beta"))
    for operation_id in (operation.id, uuid4()):
        assert (
            client.get(f"/api/v1/approvals/{operation_id}", headers=other).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/approvals/{operation_id}/decision",
                headers=other,
                json={"decision": "approved"},
            ).status_code
            == 404
        )


@pytest.mark.parametrize("amount_cents", [100, 3_000])
def test_authorized_and_blocked_operations_cannot_receive_human_decision(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
    amount_cents: int,
) -> None:
    operation = create_operation(
        client, sessions, str(approval_data["api_key"]), amount_cents
    )
    response = client.post(
        f"/api/v1/approvals/{operation.id}/decision",
        headers=bearer(login(client, role="approver")),
        json={"decision": "approved"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "operation_not_approvable"


def test_concurrent_decisions_persist_exactly_one_decision_and_event(
    sessions: sessionmaker[Session], approval_data: dict[str, object]
) -> None:
    agent = approval_data["agent"]
    approver = approval_data["users"]["approver"]  # type: ignore[index]
    with sessions() as session:
        operation = OperationRequestRecord(
            request_id=uuid4(),
            company_id=agent.company_id,  # type: ignore[attr-defined]
            agent_id=agent.id,  # type: ignore[attr-defined]
            operation="purchase",
            amount_cents=1_000,
            outcome="pending_approval",
            reason="human_approval_required",
            policy_snapshot={
                "schema_version": 1,
                "active": True,
                "allowed_operations": ["purchase"],
                "automatic_limit_cents": 500,
                "maximum_limit_cents": 2_000,
            },
        )
        session.add(operation)
        session.commit()
        operation_id = operation.id
        company_id = operation.company_id
        user_id = approver.id  # type: ignore[attr-defined]

    barrier = Barrier(2)

    def decide(choice: ApprovalChoice) -> str:
        barrier.wait()
        with sessions() as session:
            try:
                ApprovalService(session).decide(
                    company_id=company_id,
                    operation_id=operation_id,
                    user_id=user_id,
                    decision=choice,
                    reason=None,
                )
                return "won"
            except ApprovalConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(decide, [ApprovalChoice.APPROVED, ApprovalChoice.REJECTED])
        )

    assert sorted(results) == ["conflict", "won"]
    with sessions() as session:
        decisions = session.scalar(select(func.count()).select_from(ApprovalDecision))
        events = session.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.action.in_(["approval.approved", "approval.rejected"]))
        )
        assert decisions == 1
        assert events == 1


def test_operation_audit_outcomes_and_idempotent_replay(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
) -> None:
    key = str(approval_data["api_key"])
    request_id = uuid4()
    create_operation(client, sessions, key, 100, request_id=request_id)
    create_operation(client, sessions, key, 100, request_id=request_id)
    create_operation(client, sessions, key, 1_000)
    create_operation(client, sessions, key, 3_000)
    with sessions() as session:
        actions = list(session.scalars(select(AuditEvent.action)))
    assert actions.count("operation.requested") == 3
    assert actions.count("operation.authorized") == 1
    assert actions.count("operation.pending_approval") == 1
    assert actions.count("operation.blocked") == 1


def test_identity_and_credential_actions_are_audited_without_secrets(
    client: TestClient,
    sessions: sessionmaker[Session],
    approval_data: dict[str, object],
) -> None:
    token = login(client)
    agent = approval_data["agent"]
    client.post(
        "/api/v1/agents",
        headers=bearer(token),
        json={
            "name": "Audited Agent",
            "allowed_operations": ["purchase"],
            "automatic_limit_cents": 100,
            "maximum_limit_cents": 200,
        },
    )
    created = client.post(
        f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
        headers=bearer(token),
        json={},
    ).json()
    client.post(
        f"/api/v1/agents/{agent.id}/credentials/{created['credential']['id']}/revoke",  # type: ignore[attr-defined]
        headers=bearer(token),
    )
    client.post(
        "/api/v1/auth/change-password",
        headers=bearer(token),
        json={"current_password": PASSWORD, "new_password": "NewApprovalPassword8"},
    )
    new_token = login(client, role="admin", password="NewApprovalPassword8")
    client.post("/api/v1/auth/logout", headers=bearer(new_token))
    with sessions() as session:
        events = list(session.scalars(select(AuditEvent)))
    actions = {event.action for event in events}
    assert {
        "human.login",
        "human.logout",
        "human.password_changed",
        "agent.created",
        "agent_credential.created",
        "agent_credential.revoked",
    } <= actions
    serialized = str([event.metadata_json for event in events])
    assert PASSWORD not in serialized
    assert "NewApprovalPassword8" not in serialized
    assert created["token"] not in serialized


def test_audit_endpoint_is_tenant_scoped_and_rbac_protected(
    client: TestClient,
    approval_data: dict[str, object],
) -> None:
    admin = login(client)
    approver = login(client, role="approver")
    viewer = login(client, role="viewer")
    other = login(client, slug="beta")
    assert client.get("/api/v1/audit-events", headers=bearer(admin)).status_code == 200
    assert (
        client.get("/api/v1/audit-events", headers=bearer(approver)).status_code == 200
    )
    assert client.get("/api/v1/audit-events", headers=bearer(viewer)).status_code == 403
    other_events = client.get("/api/v1/audit-events", headers=bearer(other)).json()
    other_admin = approval_data["other_admin"]
    assert isinstance(other_admin, User)
    other_admin_id = str(other_admin.id)
    assert all(event["actor_user_id"] == other_admin_id for event in other_events)
