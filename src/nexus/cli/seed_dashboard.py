"""Create an explicit, non-production Control Center demonstration dataset."""

import os
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

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


def _seed_agent(
    session: Session,
    *,
    company_id: UUID,
    admin_id: UUID,
    name: str,
    description: str,
    operation: str,
    automatic_limit_cents: int,
    maximum_limit_cents: int,
    examples: tuple[tuple[int, ApprovalChoice | None], ...],
) -> str:
    """Evaluate simulated requests through the existing services and policy."""

    agent = AgentRepository(session).create(
        company_id=company_id,
        name=name,
        description=description,
        token=None,
        allowed_operations={operation},
        automatic_limit_cents=automatic_limit_cents,
        maximum_limit_cents=maximum_limit_cents,
    )
    _credential, api_key = AgentCredentialRepository(session).create(agent)
    session.commit()

    service = PersistentAuthorizationService(session)
    for amount, human_decision in examples:
        request = OperationRequest(
            request_id=uuid4(), operation=operation, amount_cents=amount
        )
        service.evaluate(token=api_key, request=request)
        if human_decision is not None:
            record = OperationRepository(session).get(
                company_id=company_id,
                agent_id=agent.id,
                request_id=request.request_id,
            )
            assert record is not None
            ApprovalService(session).decide(
                company_id=company_id,
                operation_id=record.id,
                user_id=admin_id,
                decision=human_decision,
                reason=(
                    "Operação simulada validada para a demonstração"
                    if human_decision is ApprovalChoice.APPROVED
                    else "Operação simulada rejeitada para a demonstração"
                ),
            )
    return api_key


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
        session.commit()

        purchasing_key = _seed_agent(
            session,
            company_id=company.id,
            admin_id=admin.id,
            name="Purchasing Agent",
            description="Agente responsável por solicitações de compras na demonstração.",
            operation="purchase",
            automatic_limit_cents=50_000,
            maximum_limit_cents=200_000,
            examples=(
                (30_000, None),
                (100_000, None),
                (125_000, ApprovalChoice.REJECTED),
                (150_000, ApprovalChoice.APPROVED),
                (300_000, None),
            ),
        )
        finance_key = _seed_agent(
            session,
            company_id=company.id,
            admin_id=admin.id,
            name="Finance Agent",
            description="Agente financeiro para demonstração de operações simuladas.",
            operation="pix",
            automatic_limit_cents=10_000,
            maximum_limit_cents=100_000,
            examples=(
                (5_000, None),
                (50_000, None),
                (70_000, ApprovalChoice.APPROVED),
                (80_000, ApprovalChoice.REJECTED),
                (200_000, None),
            ),
        )

        print("Control Center demo created explicitly.")
        print("Company slug: nexus-demo")
        print("Admin email: admin@nexus.demo")
        print("Purchasing Agent API key (shown once):")
        print(purchasing_key)
        print("Finance Agent API key (shown once):")
        print(finance_key)


if __name__ == "__main__":
    main()
