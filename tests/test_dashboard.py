from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

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


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_pending_metric_excludes_human_decisions(
    client: TestClient, dashboard_data: dict[str, object], decision: str
) -> None:
    api_key = str(dashboard_data["api_key"])
    submit_operation(client, api_key, 1_000)
    submit_operation(client, api_key, 1_500)
    assert browser_login(client).status_code == 200
    before = client.get("/api/v1/dashboard/summary").json()
    assert before["pending_approval"] == 2
    attention = client.get("/api/v1/dashboard/attention").json()
    operation_id = attention[0]["operation_id"]
    result = client.post(
        f"/api/v1/approvals/{operation_id}/decision",
        headers=WEB_HEADERS,
        json={"decision": decision, "reason": "Revisada"},
    )
    assert result.status_code == 200
    after = client.get("/api/v1/dashboard/summary").json()
    assert after["pending_approval"] == 1
    assert after[f"human_{decision}"] == 1
    assert after["operations_total"] == before["operations_total"]
    remaining = client.get("/api/v1/dashboard/attention").json()
    assert len(remaining) == 1
    assert remaining[0]["operation_id"] != operation_id
    detail = client.get(f"/api/v1/operations/{operation_id}").json()
    assert detail["policy_outcome"] == "pending_approval"
    assert detail["approval"]["decided_by_user_name"] == "Admin"


def test_attention_uses_snapshot_and_filters_before_limit(
    client: TestClient,
    dashboard_data: dict[str, object],
    sessions: sessionmaker[Session],
) -> None:
    from nexus.database.models import Agent

    submit_operation(client, str(dashboard_data["api_key"]), 1_000)
    assert browser_login(client).status_code == 200
    initial = client.get("/api/v1/dashboard/attention").json()[0]
    # Simulate a later policy change. Historical attention must remain unchanged.
    with sessions() as session:
        agent = session.get(Agent, UUID(initial["agent_id"]))
        # The UUID column requires a UUID rather than its JSON representation.
        assert agent is not None
        agent.automatic_limit_cents = 50
        session.commit()
    for _ in range(6):
        submit_operation(client, str(dashboard_data["api_key"]), 1_000)
        newest = client.get("/api/v1/approvals?limit=1").json()[0]
        assert (
            client.post(
                f"/api/v1/approvals/{newest['operation_id']}/decision",
                headers=WEB_HEADERS,
                json={"decision": "approved"},
            ).status_code
            == 200
        )
    attention = client.get("/api/v1/dashboard/attention?limit=1").json()
    assert len(attention) == 1
    assert attention[0]["operation_id"] == initial["operation_id"]
    assert attention[0]["policy_snapshot"]["automatic_limit_cents"] == 500
    assert attention[0]["policy_snapshot"]["maximum_limit_cents"] == 2_000
    assert client.get("/api/v1/dashboard/summary").json()["pending_approval"] == 1


@pytest.mark.parametrize("role", ["admin", "approver", "viewer"])
def test_attention_preserves_rbac_and_tenant_isolation(
    client: TestClient, dashboard_data: dict[str, object], role: str
) -> None:
    assert client.get("/api/v1/dashboard/attention").status_code == 401
    submit_operation(client, str(dashboard_data["api_key"]), 1_000)
    assert browser_login(client, role=role).status_code == 200
    attention = client.get("/api/v1/dashboard/attention").json()
    assert len(attention) == 1
    assert attention[0]["approval"] is None
    operation_id = attention[0]["operation_id"]
    client.cookies.clear()
    assert browser_login(client, slug="other").status_code == 200
    assert client.get("/api/v1/dashboard/attention").json() == []
    assert client.get(f"/api/v1/operations/{operation_id}").status_code == 404
    assert (
        client.post(
            f"/api/v1/approvals/{operation_id}/decision",
            headers=WEB_HEADERS,
            json={"decision": "approved"},
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "asset",
    [
        "nexus-logo-black.png",
        "nexus-logo-white.png",
        "nexus-symbol-black.png",
        "nexus-symbol-white.png",
    ],
)
def test_official_brand_assets_are_served(client: TestClient, asset: str) -> None:
    response = client.get(f"/static/assets/{asset}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"


def test_premium_login_keeps_real_fields_and_no_session_token(
    client: TestClient,
) -> None:
    page = client.get("/login")
    for text in [
        "Acesse sua conta",
        "Controle. Governança.",
        "Decisões com confiança.",
        'name="company_slug"',
        'name="email"',
        'name="password"',
    ]:
        assert text in page.text
    assert "<select" not in page.text
    assert "nexus-logo-black.png" in page.text
    assert "nexus-logo-white.png" in page.text
    assert browser_login(client).status_code == 200
    token = client.cookies.get(WEB_SESSION_COOKIE)
    assert token
    assert token not in client.get("/").text
    assert token not in client.get("/api/v1/auth/me").text
    for script in ["api", "app", "ui", "login"]:
        source = client.get(f"/static/js/{script}.js").text
        assert "localStorage" not in source
        assert "sessionStorage" not in source
        assert "console." not in source
        assert token not in source


def test_secure_browser_cookie_is_configurable(
    sessions: sessionmaker[Session],
    dashboard_data: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_COOKIE_SECURE", "true")
    with TestClient(
        create_app(session_factory=sessions), base_url="https://testserver"
    ) as secure_client:
        response = browser_login(secure_client)
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        assert "HttpOnly" in response.headers["set-cookie"]
        assert "SameSite=strict" in response.headers["set-cookie"]
        assert secure_client.get("/").status_code == 200


@pytest.fixture
def browser_page(client: TestClient, sessions: sessionmaker[Session]):
    """Exercise the actual modules against the API, without a frontend framework."""
    import os
    import shutil
    import socket
    from threading import Thread
    from time import monotonic, sleep

    import uvicorn

    playwright = pytest.importorskip("playwright.sync_api")
    chromium = os.environ.get("NEXUS_CHROMIUM_PATH") or shutil.which("chromium")
    if not chromium:
        pytest.skip("Install Chromium or set NEXUS_CHROMIUM_PATH for browser checks")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(create_app(session_factory=sessions), log_level="warning")
    )
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = monotonic() + 10
    try:
        while not server.started and thread.is_alive() and monotonic() < deadline:
            sleep(0.02)
        assert server.started, "Uvicorn did not become ready"
        with playwright.sync_playwright() as driver:
            browser = driver.chromium.launch(
                executable_path=chromium, headless=True, args=["--no-sandbox"]
            )
            page = browser.new_page(
                viewport={"width": 1440, "height": 1000}, reduced_motion="reduce"
            )
            page.set_default_timeout(8_000)
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            yield page, f"http://127.0.0.1:{port}"
            assert page_errors == []
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        listener.close()
        assert not thread.is_alive()


def login_browser(page, base_url: str, role: str = "admin") -> None:
    page.goto(f"{base_url}/login")
    page.get_by_label("Empresa", exact=True).fill("demo")
    page.get_by_label("E-mail", exact=True).fill(f"{role}@example.com")
    page.get_by_label("Senha", exact=True).fill(PASSWORD)
    page.get_by_role("button", name="Entrar →", exact=True).click()
    page.get_by_role("heading", name="Visão geral", exact=True).wait_for()
    page.locator(".metric-card").first.wait_for()


def review_screenshot(page, name: str) -> None:
    import os

    directory = os.environ.get("NEXUS_REVIEW_DIR")
    if directory:
        destination = Path(directory)
        destination.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(destination / f"{name}.png"), full_page=True, animations="disabled"
        )


def test_browser_premium_views_and_responsive_navigation(
    browser_page, client: TestClient, dashboard_data: dict[str, object]
) -> None:
    page, url = browser_page
    submit_operation(client, str(dashboard_data["api_key"]), 1_000)
    page.goto(f"{url}/login")
    review_screenshot(page, "login-desktop")
    assert page.locator('input[name="company_slug"]').count() == 1
    assert page.locator('select[name="company_slug"]').count() == 0
    login_browser(page, url)
    assert page.locator(".metric-card").count() == 6
    assert page.get_by_text("1 solicitação aguardando decisão", exact=True).is_visible()
    assert page.get_by_text(
        "Acima do limite automático de R$ 5,00", exact=True
    ).is_visible()
    review_screenshot(page, "dashboard-desktop")
    for key, title in [
        ("operations", "Operações"),
        ("approvals", "Aprovações"),
        ("agents", "Agentes"),
        ("audit", "Auditoria"),
    ]:
        page.locator(f'nav a[data-page="{key}"]').click()
        page.get_by_role("heading", name=title, exact=True).wait_for()
        assert page.locator("nav a.active").get_attribute("aria-current") == "page"
        review_screenshot(page, f"{key}-desktop")
    page.set_viewport_size({"width": 390, "height": 844})
    page.get_by_role("button", name="Abrir navegação", exact=True).click()
    assert page.locator("#menu-toggle").get_attribute("aria-expanded") == "true"
    page.get_by_role("link", name="Visão geral", exact=True).click()
    page.get_by_role("heading", name="Visão geral", exact=True).wait_for()
    assert page.locator("#menu-toggle").get_attribute("aria-expanded") == "false"
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    review_screenshot(page, "dashboard-mobile")
    page.get_by_role("button", name="Sair", exact=True).click()
    page.get_by_role("heading", name="Acesse sua conta", exact=True).wait_for()
    review_screenshot(page, "login-mobile")


def test_browser_attention_approval_updates_metrics_and_logout_revokes_session(
    browser_page, client: TestClient, dashboard_data: dict[str, object]
) -> None:
    page, url = browser_page
    submit_operation(client, str(dashboard_data["api_key"]), 1_000)
    login_browser(page, url)
    assert page.evaluate("localStorage.length + sessionStorage.length") == 0
    assert "nexus_session" not in page.evaluate("document.cookie")
    page.get_by_role("button", name="Revisar solicitação →", exact=True).click()
    page.get_by_role("heading", name="Revisar solicitação", exact=True).wait_for()
    assert page.locator("dialog").get_by_text("R$ 5,00", exact=True).is_visible()
    page.get_by_role("button", name="Aprovar", exact=True).click()
    page.get_by_label("Justificativa", exact=True).fill("Revisada no navegador")
    page.get_by_role("button", name="Confirmar aprovação", exact=True).click()
    page.get_by_text("Nenhuma operação aguardando decisão.", exact=True).wait_for()
    pending_card = page.locator(".metric-card").filter(has_text="Aguardando decisão")
    assert pending_card.locator("strong").inner_text() == "0"
    assert page.get_by_text("1 aprovadas • 0 rejeitadas", exact=True).is_visible()
    # Session stays in HttpOnly cookie; it is never rendered or stored by JS.
    session_cookie = next(
        cookie
        for cookie in page.context.cookies()
        if cookie["name"] == WEB_SESSION_COOKIE
    )
    assert session_cookie["httpOnly"] is True
    assert session_cookie["value"] not in page.content()
    page.get_by_role("button", name="Sair", exact=True).click()
    page.get_by_role("heading", name="Acesse sua conta", exact=True).wait_for()
    assert page.request.get(f"{url}/api/v1/auth/me").status == 401
    replay = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {session_cookie['value']}"},
    )
    assert replay.status_code == 401


@pytest.mark.parametrize("role", ["approver", "viewer"])
def test_browser_rbac_keeps_operations_usable_without_widening_permissions(
    browser_page, role: str, client: TestClient, dashboard_data: dict[str, object]
) -> None:
    page, url = browser_page
    submit_operation(client, str(dashboard_data["api_key"]), 1_000)
    login_browser(page, url, role)
    page.get_by_role("link", name="Operações", exact=True).click()
    page.get_by_role("heading", name="Operações", exact=True).wait_for()
    assert page.get_by_role(
        "columnheader", name="Resultado da política", exact=True
    ).is_visible()
    if role == "approver":
        assert page.locator('nav a[data-page="agents"]').count() == 0
        assert page.request.get(f"{url}/api/v1/agents").status == 403
    else:
        assert page.locator('nav a[data-page="approvals"]').count() == 0
        assert page.locator('nav a[data-page="audit"]').count() == 0
        assert page.request.get(f"{url}/api/v1/approvals").status == 403
        page.get_by_role("link", name="Visão geral", exact=True).click()
        page.get_by_role("button", name="Revisar solicitação →", exact=True).click()
        page.get_by_role("heading", name="Revisar solicitação", exact=True).wait_for()
        assert (
            page.locator("dialog")
            .get_by_role("button", name="Aprovar", exact=True)
            .count()
            == 0
        )


def test_browser_credential_is_discarded_on_close_and_not_retrievable(
    browser_page,
) -> None:
    page, url = browser_page
    login_browser(page, url)
    page.get_by_role("link", name="Agentes", exact=True).click()
    page.get_by_role("button", name="Ver identidade e limites →", exact=True).click()
    page.get_by_role("button", name="Gerenciar credenciais", exact=True).click()
    page.get_by_role("button", name="Gerar nova credencial", exact=True).click()
    page.get_by_role("heading", name="Nova credencial criada", exact=True).wait_for()
    key = page.locator(".one-time-key").inner_text()
    assert key.startswith("nxs_ag_")
    page.get_by_role("button", name="Fechar", exact=True).click()
    page.locator("#modal-content > *").first.wait_for(state="detached")
    assert key not in page.content()
    assert page.evaluate("localStorage.length + sessionStorage.length") == 0
    page.get_by_role("button", name="Ver identidade e limites →", exact=True).click()
    page.get_by_role("button", name="Gerenciar credenciais", exact=True).click()
    page.locator(".credential-row").first.wait_for()
    assert key not in page.content()
    page.keyboard.press("Escape")
    page.locator("#modal-content > *").first.wait_for(state="detached")


def test_browser_untrusted_agent_and_audit_metadata_are_text(
    browser_page,
    client: TestClient,
    dashboard_data: dict[str, object],
    sessions: sessionmaker[Session],
) -> None:
    from nexus.database.models import Agent, AuditActorType, AuditEvent
    from nexus.repositories.audit import AuditAction, AuditRepository

    attack = '<img src=x onerror="window.nexusXss=1">'
    agent = dashboard_data["agent"]
    assert isinstance(agent, Agent)
    with sessions() as session:
        stored = session.get(Agent, agent.id)
        assert stored is not None
        stored.name = attack
        stored.description = attack
        AuditRepository(session).add(
            company_id=stored.company_id,
            actor_type=AuditActorType.SYSTEM,
            action=AuditAction.AGENT_CREATED,
            target_type="agent",
            target_id=stored.id,
            metadata={"name": attack},
        )
        session.commit()
        event_id = session.scalar(
            select(AuditEvent.id).where(AuditEvent.actor_type == AuditActorType.SYSTEM)
        )
    submit_operation(client, str(dashboard_data["api_key"]), 1_000)
    page, url = browser_page
    login_browser(page, url)
    assert attack in page.locator(".attention-row").inner_text()
    page.get_by_role("link", name="Agentes", exact=True).click()
    page.get_by_role("heading", name="Agentes", exact=True).wait_for()
    assert page.locator(".agent-card").get_by_role("heading").inner_text() == attack
    page.get_by_role("link", name="Auditoria", exact=True).click()
    page.get_by_role("heading", name="Auditoria", exact=True).wait_for()
    event = (
        page.locator("tbody tr")
        .filter(has_text=f"agent · {str(agent.id)[:8]}")
        .filter(has_text="Sistema")
    )  # type: ignore[attr-defined]
    assert event_id is not None
    event.first.click()
    assert page.locator("dialog dd").filter(has_text=attack).count() == 1
    assert page.locator('img[src="x"]').count() == 0
    assert page.evaluate("window.nexusXss === undefined")


def test_browser_concurrent_decision_refreshes_without_duplicate_submission(
    browser_page, client: TestClient, dashboard_data: dict[str, object]
) -> None:
    page, url = browser_page
    submit_operation(client, str(dashboard_data["api_key"]), 1_000)
    login_browser(page, url)
    page.get_by_role("button", name="Revisar solicitação →", exact=True).click()
    page.get_by_role("button", name="Aprovar", exact=True).click()
    operation_id = page.request.get(f"{url}/api/v1/approvals").json()[0]["operation_id"]
    # Another human decides after this browser opened its review.
    assert browser_login(client).status_code == 200
    assert (
        client.post(
            f"/api/v1/approvals/{operation_id}/decision",
            headers=WEB_HEADERS,
            json={"decision": "rejected", "reason": "Decisão concorrente"},
        ).status_code
        == 200
    )
    submissions: list[str] = []
    page.on(
        "request",
        lambda request: (
            submissions.append(request.url)
            if request.method == "POST" and request.url.endswith("/decision")
            else None
        ),
    )
    page.locator("dialog button.button").evaluate(
        "button => { button.click(); button.click(); }"
    )
    page.get_by_text(
        "Esta operação já foi decidida por outro usuário.", exact=True
    ).wait_for()
    page.get_by_text("Nenhuma operação aguardando decisão.", exact=True).wait_for()
    assert len(submissions) == 1
    assert page.get_by_text("0 aprovadas • 1 rejeitadas", exact=True).is_visible()
    assert not page.locator("dialog").is_visible()


def test_browser_late_credential_response_does_not_reopen_dismissed_modal(
    browser_page,
) -> None:
    page, url = browser_page
    login_browser(page, url)
    page.get_by_role("link", name="Agentes", exact=True).click()
    page.get_by_role("button", name="Ver identidade e limites →", exact=True).click()
    page.get_by_role("button", name="Gerenciar credenciais", exact=True).click()

    def dismiss_before_response(route) -> None:
        response = route.fetch()
        page.get_by_role("button", name="Fechar", exact=True).click()
        route.fulfill(response=response)

    page.route("**/api/v1/agents/*/credentials", dismiss_before_response)
    page.get_by_role("button", name="Gerar nova credencial", exact=True).click()
    page.locator("#modal-content > *").first.wait_for(state="detached")
    assert not page.locator("dialog").is_visible()
    assert page.locator(".one-time-key").count() == 0


def test_audit_metadata_keeps_validation_contract_for_non_scalar_values() -> None:
    from nexus.repositories.audit import sanitize_metadata

    with pytest.raises(ValueError, match="must be scalar"):
        sanitize_metadata({"name": {"unsupported": "nested"}})
