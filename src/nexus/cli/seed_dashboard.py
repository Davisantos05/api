"""Create an explicit, non-production Control Center demonstration dataset."""

import os
from uuid import uuid4

from sqlalchemy import select

from nexus.database.models import ApprovalChoice, Company, UserRole
from nexus.database.session import get_session_factory
from nexus.domain.authorization import OperationRequest
from nexus.repositories.agents import AgentRepository
from nexus.repositories.companies import CompanyRepository
from nexus.repositories.identity import AgentCredentialRepository
from nexus.repositories.operations import OperationRepository
from nexus.repositories.users import UserRepository
from nexus.security.passwords import hash_password
from nexus.services.approvals import ApprovalService
from nexus.services.authorization import PersistentAuthorizationService


def main() -> None:
    password = os.getenv("NEXUS_DEMO_ADMIN_PASSWORD")
    if not password:
        raise SystemExit(
            "Set NEXUS_DEMO_ADMIN_PASSWORD before running this explicit demo seed."
        )
    with get_session_factory()() as session:
        if session.scalar(select(Company).where(Company.slug == "nexus-demo")):
            raise SystemExit("Company nexus-demo already exists; no data was changed.")
        company = CompanyRepository(session).create(
            name="NEXUS Demo", slug="nexus-demo"
        )
        admin = UserRepository(session).create(
            company_id=company.id,
            name="Administrador Demo",
            email="admin@nexus.demo",
            role=UserRole.ADMIN,
            password_hash=hash_password(password),
        )
        agent = AgentRepository(session).create(
            company_id=company.id,
            name="Purchasing Agent",
            description="Agente de compras para a demonstração do Control Center",
            token=None,
            allowed_operations={"purchase"},
            automatic_limit_cents=50_000,
            maximum_limit_cents=200_000,
        )
        _credential, api_key = AgentCredentialRepository(session).create(agent)
        session.commit()

        service = PersistentAuthorizationService(session)
        for amount in (30_000, 300_000, 100_000, 125_000, 150_000):
            service.evaluate(
                token=api_key,
                request=OperationRequest(
                    request_id=uuid4(), operation="purchase", amount_cents=amount
                ),
            )
        pending = OperationRepository(session).list_detailed(
            company_id=company.id, outcome="pending_approval", limit=10
        )
        ApprovalService(session).decide(
            company_id=company.id,
            operation_id=pending[0].id,
            user_id=admin.id,
            decision=ApprovalChoice.APPROVED,
            reason="Compra validada para a demonstração",
        )
        ApprovalService(session).decide(
            company_id=company.id,
            operation_id=pending[1].id,
            user_id=admin.id,
            decision=ApprovalChoice.REJECTED,
            reason="Fornecedor não aprovado para a demonstração",
        )

        print("Control Center demo created explicitly.")
        print("Company slug: nexus-demo")
        print("Admin email: admin@nexus.demo")
        print("Agent API key (shown once):")
        print(api_key)


if __name__ == "__main__":
    main()
