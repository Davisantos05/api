from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from nexus.api.app import WEB_REQUEST_HEADER, WEB_SESSION_COOKIE, create_app
from nexus.database.base import Base
from nexus.database.models import UserRole, UserSession
from nexus.database.session import create_database_engine, create_session_factory
from nexus.repositories.agents import AgentRepository
from nexus.repositories.companies import CompanyRepository
from nexus.repositories.identity import AgentCredentialRepository
from nexus.repositories.users import UserRepository
from nexus.security.passwords import hash_password

PASSWORD = "DashboardPassword9!"
WEB_HEADERS = {WEB_REQUEST_HEADER: "1"}


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    value = create_database_engine(f"sqlite:///{tmp_path / 'dashboard.db'}")
    Base.metadata.create_all(value)
    yield value
    value.dispose()


@pytest.fixture
def sessions(engine: Engine) -> sessionmaker[Session]:
    return create_session_factory(engine)


@pytest.fixture
def dashboard_data(sessions: sessionmaker[Session]) -> dict[str, object]:
    with sessions() as session:
        company = CompanyRepository(session).create(name="NEXUS Demo", slug="demo")
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
            name="Purchasing Agent",
            description="Demo",
            token=None,
            allowed_operations={"purchase"},
            automatic_limit_cents=500,
            maximum_limit_cents=2_000,
        )
        _credential, api_key = AgentCredentialRepository(session).create(agent)
        other = CompanyRepository(session).create(name="Other", slug="other")
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
            "api_key": api_key,
            "other_admin": other_admin,
        }


@pytest.fixture
def client(
    sessions: sessionmaker[Session], dashboard_data: dict[str, object]
) -> Iterator[TestClient]:
    with TestClient(create_app(session_factory=sessions)) as value:
        yield value


def browser_login(client: TestClient, role: str = "admin", slug: str = "demo"):
    return client.post(
        "/api/v1/auth/browser-login",
        json={
            "company_slug": slug,
            "email": f"{role}@example.com",
            "password": PASSWORD,
        },
    )


def submit_operation(
    client: TestClient, api_key: str, amount: int
) -> dict[str, object]:
    response = client.post(
        "/api/v1/operations",
        headers={"X-Nexus-Agent-Token": api_key},
        json={
            "request_id": str(uuid4()),
            "operation": "purchase",
            "amount_cents": amount,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_login_page_and_private_dashboard_protection(client: TestClient) -> None:
    redirect = client.get("/", follow_redirects=False)
    assert redirect.status_code == 303
    assert redirect.headers["location"] == "/login"
    page = client.get("/login")
    assert page.status_code == 200
    assert "NEXUS" in page.text
    assert "CONTROL CENTER" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"


def test_browser_login_uses_httponly_cookie_without_returning_token(
    client: TestClient,
) -> None:
    response = browser_login(client)
    assert response.status_code == 200
    assert "token" not in response.json()
    cookie = response.headers["set-cookie"]
    assert f"{WEB_SESSION_COOKIE}=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    profile = client.get("/api/v1/auth/me")
    assert profile.status_code == 200
    assert profile.json()["company_name"] == "NEXUS Demo"
    assert profile.json()["company_slug"] == "demo"
    assert client.get("/").status_code == 200


def test_cookie_authenticated_writes_require_csrf_header(client: TestClient) -> None:
    assert browser_login(client).status_code == 200
    blocked = client.post("/api/v1/auth/browser-logout")
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "csrf_check_failed"
    assert (
        client.post("/api/v1/auth/browser-logout", headers=WEB_HEADERS).status_code
        == 204
    )
    assert client.get("/api/v1/auth/me").status_code == 401


def test_expired_browser_session_redirects_to_login(
    client: TestClient, sessions: sessionmaker[Session]
) -> None:
    assert browser_login(client).status_code == 200
    with sessions() as session:
        record = session.scalar(select(UserSession))
        assert record is not None
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_dashboard_summary_and_detailed_operations_are_tenant_scoped(
    client: TestClient, dashboard_data: dict[str, object]
) -> None:
    api_key = str(dashboard_data["api_key"])
    submit_operation(client, api_key, 100)
    pending = submit_operation(client, api_key, 1_000)
    submit_operation(client, api_key, 3_000)
    assert browser_login(client).status_code == 200

    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary == {
        "agents_active": 1,
        "operations_total": 3,
        "authorized": 1,
        "pending_approval": 1,
        "blocked": 1,
        "human_approved": 0,
        "human_rejected": 0,
    }
    operations = client.get("/api/v1/operations?outcome=pending_approval").json()
    assert len(operations) == 1
    assert operations[0]["agent_name"] == "Purchasing Agent"
    assert operations[0]["request_id"] == pending["request_id"]
    assert operations[0]["outcome"] == "pending_approval"
    assert operations[0]["reason"] == "human_approval_required"
    detail = client.get(f"/api/v1/operations/{operations[0]['operation_id']}").json()
    assert detail["policy_snapshot"]["automatic_limit_cents"] == 500
    assert detail["policy_snapshot"]["maximum_limit_cents"] == 2_000

    client.cookies.clear()
    assert browser_login(client, slug="other").status_code == 200
    assert client.get("/api/v1/dashboard/summary").json()["operations_total"] == 0
    assert (
        client.get(f"/api/v1/operations/{operations[0]['operation_id']}").status_code
        == 404
    )


@pytest.mark.parametrize("role", ["admin", "approver", "viewer"])
def test_dashboard_summary_respects_existing_view_operations_rbac(
    client: TestClient, role: str
) -> None:
    assert browser_login(client, role=role).status_code == 200
    assert client.get("/api/v1/dashboard/summary").status_code == 200
    expected = 200 if role in {"admin", "approver"} else 403
    assert client.get("/api/v1/approvals").status_code == expected
    assert client.get("/api/v1/audit-events").status_code == expected


def test_admin_credential_is_returned_once_and_can_be_revoked(
    client: TestClient, dashboard_data: dict[str, object]
) -> None:
    agent = dashboard_data["agent"]
    assert browser_login(client).status_code == 200
    created = client.post(
        f"/api/v1/agents/{agent.id}/credentials",  # type: ignore[attr-defined]
        headers=WEB_HEADERS,
        json={},
    )
    assert created.status_code == 200
    api_key = created.json()["token"]
    credential_id = created.json()["credential"]["id"]
    listed = client.get(
        f"/api/v1/agents/{agent.id}/credentials"  # type: ignore[attr-defined]
    )
    assert listed.status_code == 200
    assert api_key not in listed.text
    assert '"token":' not in listed.text
    assert "token_hash" not in listed.text
    revoked = client.post(
        f"/api/v1/agents/{agent.id}/credentials/{credential_id}/revoke",  # type: ignore[attr-defined]
        headers=WEB_HEADERS,
    )
    assert revoked.status_code == 204


def test_control_center_renders_untrusted_data_with_safe_dom_apis(
    client: TestClient,
) -> None:
    source = client.get("/static/js/app.js").text
    ui_source = client.get("/static/js/ui.js").text
    assert "innerHTML" not in source
    assert "innerHTML" not in ui_source
    assert "textContent" in source
    assert "textContent" in ui_source


def test_reproducible_dashboard_approval_e2e_flow(
    client: TestClient, dashboard_data: dict[str, object]
) -> None:
    submitted = submit_operation(client, str(dashboard_data["api_key"]), 1_000)
    assert submitted["outcome"] == "pending_approval"
    assert browser_login(client).status_code == 200
    pending = client.get("/api/v1/approvals").json()
    assert len(pending) == 1
    operation_id = pending[0]["operation_id"]
    decided = client.post(
        f"/api/v1/approvals/{operation_id}/decision",
        headers=WEB_HEADERS,
        json={"decision": "approved", "reason": "Validada no Control Center"},
    )
    assert decided.status_code == 200
    detail = client.get(f"/api/v1/operations/{operation_id}").json()
    assert detail["approval"]["decision"] == "approved"
    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["human_approved"] == 1
    events = client.get("/api/v1/audit-events").json()
    actions = {event["action"] for event in events}
    assert all(event["actor_name"] for event in events)
    assert {
        "operation.requested",
        "operation.pending_approval",
        "approval.approved",
        "human.login",
    }.issubset(actions)
