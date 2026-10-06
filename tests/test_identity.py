from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from nexus.api.app import create_app
from nexus.database.base import Base
from nexus.database.models import AgentCredential, User, UserRole, UserSession
from nexus.database.session import create_database_engine, create_session_factory
from nexus.repositories.agents import AgentRepository
from nexus.repositories.companies import CompanyRepository
from nexus.repositories.users import UserRepository
from nexus.security.passwords import hash_password

PASSWORD = "CorrectHorse9!"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    value = create_database_engine(f"sqlite:///{tmp_path / 'identity.db'}")
    Base.metadata.create_all(value)
    yield value
    value.dispose()


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def identity_data(sessions: sessionmaker[Session]) -> dict[str, object]:
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
            name="Purchaser",
            description="Identity test",
            token=None,
            allowed_operations={"purchase"},
            automatic_limit_cents=500,
            maximum_limit_cents=2_000,
        )
        other = CompanyRepository(session).create(name="Beta", slug="beta")
        other_admin = UserRepository(session).create(
            company_id=other.id,
            name="Other Admin",
            email="admin@example.com",
            role=UserRole.ADMIN,
            password_hash=hash_password(PASSWORD),
        )
        session.commit()
        return {
            "company": company,
            "users": users,
            "agent": agent,
            "other": other,
            "other_admin": other_admin,
        }


@pytest.fixture
def client(
    sessions: sessionmaker[Session], identity_data: dict[str, object]
) -> Iterator[TestClient]:
    with TestClient(create_app(session_factory=sessions)) as value:
        yield value


def login(
    client: TestClient,
    *,
    slug: str = "alpha",
    email: str = "admin@example.com",
    password: str = PASSWORD,
) -> Response:
    return client.post(
        "/api/v1/auth/login",
        json={"company_slug": slug, "email": email, "password": password},
    )


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_valid_login_returns_opaque_session_and_user(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    response = login(client)
    assert response.status_code == 200
    token = response.json()["token"]
    assert token.startswith("nxs_us_")
    assert response.json()["user"]["role"] == "admin"
    with sessions() as session:
        stored_session = session.scalar(select(UserSession))
        stored_user = session.scalar(
            select(User).where(User.email == "admin@example.com")
        )
        assert stored_session is not None and stored_user is not None
        assert stored_session.token_hash != token.encode()
        assert stored_user.password_hash != PASSWORD
        assert stored_user.password_hash is not None
        assert stored_user.password_hash.startswith("$argon2id$")


@pytest.mark.parametrize(
    ("slug", "password"),
    [("missing", PASSWORD), ("alpha", "WrongPassword9!")],
)
def test_login_uses_generic_error_for_invalid_identity(
    client: TestClient, slug: str, password: str
) -> None:
    response = login(client, slug=slug, password=password)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_inactive_user_cannot_login(
    client: TestClient,
    sessions: sessionmaker[Session],
    identity_data: dict[str, object],
) -> None:
    user = identity_data["users"]["admin"]  # type: ignore[index]
    with sessions() as session:
        stored = session.get(type(user), user.id)  # type: ignore[attr-defined]
        assert stored is not None
        stored.active = False
        session.commit()
    assert login(client).status_code == 401


def test_me_and_logout_lifecycle(client: TestClient) -> None:
    token = login(client).json()["token"]
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=bearer(token)).status_code == 204
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401


def test_password_change_replaces_hash(client: TestClient) -> None:
    first_token = login(client).json()["token"]
    second_token = login(client).json()["token"]
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=bearer(first_token),
        json={
            "current_password": PASSWORD,
            "new_password": "DifferentHorse8!",
        },
    )
    assert changed.status_code == 204
    assert client.get("/api/v1/auth/me", headers=bearer(first_token)).status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers=bearer(second_token)).status_code == 401
    )
    assert login(client).status_code == 401
    assert login(client, password="DifferentHorse8!").status_code == 200


def test_password_change_rejects_wrong_current_password(client: TestClient) -> None:
    token = login(client).json()["token"]
    changed = client.post(
        "/api/v1/auth/change-password",
        headers=bearer(token),
        json={
            "current_password": "WrongCurrentPassword9",
            "new_password": "DifferentHorse8!",
        },
    )
    assert changed.status_code == 400
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 200
    assert login(client).status_code == 200


def test_inactive_user_cannot_change_password(
    client: TestClient,
    sessions: sessionmaker[Session],
    identity_data: dict[str, object],
) -> None:
    token = login(client).json()["token"]
    user = identity_data["users"]["admin"]  # type: ignore[index]
    with sessions() as session:
        stored = session.get(type(user), user.id)  # type: ignore[attr-defined]
        assert stored is not None
        original_hash = stored.password_hash
        stored.active = False
        session.commit()
    response = client.post(
        "/api/v1/auth/change-password",
        headers=bearer(token),
        json={"current_password": PASSWORD, "new_password": "DifferentHorse8!"},
    )
    assert response.status_code == 401
    with sessions() as session:
        stored = session.get(type(user), user.id)  # type: ignore[attr-defined]
        assert stored is not None
        assert stored.password_hash == original_hash


@pytest.mark.parametrize("state", ["expired", "revoked"])
def test_invalid_session_state_is_rejected(
    client: TestClient, sessions: sessionmaker[Session], state: str
) -> None:
    token = login(client).json()["token"]
    with sessions() as session:
        record = session.scalar(select(UserSession))
        assert record is not None
        if state == "expired":
            record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        else:
            record.revoked_at = datetime.now(UTC)
        session.commit()
    assert client.get("/api/v1/auth/me", headers=bearer(token)).status_code == 401
    with sessions() as session:
        record = session.scalar(select(UserSession))
        assert record is not None
        assert record.last_used_at is None


def test_rbac_admin_approver_and_viewer(client: TestClient) -> None:
    admin = login(client).json()["token"]
    approver = login(client, email="approver@example.com").json()["token"]
    viewer = login(client, email="viewer@example.com").json()["token"]
    payload = {
        "name": "New Agent",
        "allowed_operations": ["purchase"],
        "automatic_limit_cents": 100,
        "maximum_limit_cents": 200,
    }
    assert (
        client.post("/api/v1/agents", headers=bearer(admin), json=payload).status_code
        == 200
    )
    assert client.get("/api/v1/operations", headers=bearer(approver)).status_code == 200
    assert (
        client.post("/api/v1/agents", headers=bearer(viewer), json=payload).status_code
        == 403
    )


def test_agent_credential_creation_listing_and_no_plaintext_storage(
    client: TestClient,
    sessions: sessionmaker[Session],
    identity_data: dict[str, object],
) -> None:
    admin = login(client).json()["token"]
    agent = identity_data["agent"]
    created = client.post(
        f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
        headers=bearer(admin),
        json={},
    )
    assert created.status_code == 200
    token = created.json()["token"]
    assert token.startswith("nxs_ag_")
    listed = client.get(
        f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
        headers=bearer(admin),
    )
    assert "token" not in listed.json()[0]
    assert created.json()["credential"]["token_prefix"] == token[:12]
    assert len(created.json()["credential"]["token_prefix"]) == 12
    with sessions() as session:
        stored = session.scalar(select(AgentCredential))
        assert stored is not None
        assert token.encode() != stored.token_hash


def test_valid_revoked_and_rotated_agent_credentials(
    client: TestClient, identity_data: dict[str, object]
) -> None:
    admin = login(client).json()["token"]
    agent = identity_data["agent"]
    url = f"/api/v1/agents/{agent.id}/credentials"  # type: ignore[attr-defined]
    first = client.post(url, headers=bearer(admin), json={}).json()
    second = client.post(url, headers=bearer(admin), json={}).json()
    request = {"request_id": str(uuid4()), "operation": "purchase", "amount_cents": 1}
    assert (
        client.post(
            "/api/v1/operations",
            headers={"X-Nexus-Agent-Token": first["token"]},
            json=request,
        ).status_code
        == 200
    )
    revoke = client.post(
        f"{url}/{first['credential']['id']}/revoke", headers=bearer(admin)
    )
    assert revoke.status_code == 204
    request["request_id"] = str(uuid4())
    assert (
        client.post(
            "/api/v1/operations",
            headers={"X-Nexus-Agent-Token": first["token"]},
            json=request,
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/operations",
            headers={"X-Nexus-Agent-Token": second["token"]},
            json=request,
        ).status_code
        == 200
    )


def test_expired_agent_credential_is_rejected(
    client: TestClient,
    sessions: sessionmaker[Session],
    identity_data: dict[str, object],
) -> None:
    admin = login(client).json()["token"]
    agent = identity_data["agent"]
    created = client.post(
        f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
        headers=bearer(admin),
        json={"expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
    ).json()
    response = client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": created["token"]},
        json={"request_id": str(uuid4()), "operation": "purchase", "amount_cents": 1},
    )
    assert response.status_code == 401
    with sessions() as session:
        stored = session.scalar(select(AgentCredential))
        assert stored is not None
        assert stored.last_used_at is None


def test_revoked_unused_credential_does_not_update_last_used(
    client: TestClient,
    sessions: sessionmaker[Session],
    identity_data: dict[str, object],
) -> None:
    admin = login(client).json()["token"]
    agent = identity_data["agent"]
    url = f"/api/v1/agents/{agent.id}/credentials"  # type: ignore[attr-defined]
    created = client.post(url, headers=bearer(admin), json={}).json()
    client.post(f"{url}/{created['credential']['id']}/revoke", headers=bearer(admin))
    response = client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": created["token"]},
        json={"request_id": str(uuid4()), "operation": "purchase", "amount_cents": 1},
    )
    assert response.status_code == 401
    with sessions() as session:
        stored = session.get(AgentCredential, UUID(created["credential"]["id"]))
        assert stored is not None
        assert stored.last_used_at is None


def test_identity_token_hashes_have_unique_constraints(engine: Engine) -> None:
    inspector = inspect(engine)
    session_constraints = inspector.get_unique_constraints("user_sessions")
    credential_constraints = inspector.get_unique_constraints("agent_credentials")
    assert any(item["column_names"] == ["token_hash"] for item in session_constraints)
    assert any(
        item["column_names"] == ["token_hash"] for item in credential_constraints
    )


def test_administrative_responses_never_expose_secret_fields(
    client: TestClient, identity_data: dict[str, object]
) -> None:
    admin = login(client).json()["token"]
    agent = identity_data["agent"]
    created = client.post(
        f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
        headers=bearer(admin),
        json={},
    ).json()
    responses = [
        client.get("/api/v1/auth/me", headers=bearer(admin)).json(),
        client.get("/api/v1/agents", headers=bearer(admin)).json(),
        client.get(
            f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
            headers=bearer(admin),
        ).json(),
        client.get("/api/v1/operations", headers=bearer(admin)).json(),
    ]
    for payload in responses:
        serialized = str(payload)
        assert "password_hash" not in serialized
        assert "token_hash" not in serialized
        assert created["token"] not in serialized
        assert admin not in serialized


def test_cross_tenant_admin_cannot_access_agent(
    client: TestClient, identity_data: dict[str, object]
) -> None:
    other_token = login(client, slug="beta").json()["token"]
    agent = identity_data["agent"]
    assert (
        client.post(
            f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
            headers=bearer(other_token),
            json={},
        ).status_code
        == 404
    )
    assert client.get("/api/v1/agents", headers=bearer(other_token)).json() == []


def test_human_and_agent_credentials_are_not_interchangeable(
    client: TestClient, identity_data: dict[str, object]
) -> None:
    human = login(client).json()["token"]
    admin = human
    agent = identity_data["agent"]
    api_key = client.post(
        f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
        headers=bearer(admin),
        json={},
    ).json()["token"]
    assert (
        client.get(
            "/api/v1/agents", headers={"X-Nexus-Agent-Token": api_key}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/agents",
            headers={"X-Nexus-Agent-Token": api_key},
            json={
                "name": "Self escalation",
                "allowed_operations": ["purchase"],
                "automatic_limit_cents": 999,
                "maximum_limit_cents": 999,
            },
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/operations",
            headers=bearer(human),
            json={
                "request_id": str(uuid4()),
                "operation": "purchase",
                "amount_cents": 1,
            },
        ).status_code
        == 401
    )
