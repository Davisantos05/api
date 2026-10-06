"""Create explicit local demonstration data after migrations are applied."""

from sqlalchemy import select

from nexus.database.models import Company
from nexus.database.session import get_session_factory
from nexus.repositories.agents import AgentRepository
from nexus.repositories.companies import CompanyRepository
from nexus.repositories.identity import AgentCredentialRepository


def main() -> None:
    with get_session_factory()() as session:
        existing = session.scalar(select(Company).where(Company.name == "NEXUS Demo"))
        if existing is not None:
            raise SystemExit("NEXUS Demo already exists; seed was not changed.")

        company = CompanyRepository(session).create(name="NEXUS Demo")
        agent = AgentRepository(session).create(
            company_id=company.id,
            name="Purchasing Agent",
            description="Local demonstration agent for simulated purchases",
            token=None,
            allowed_operations={"purchase"},
            automatic_limit_cents=50_000,
            maximum_limit_cents=200_000,
        )
        _credential, token = AgentCredentialRepository(session).create(agent)
        session.commit()
        print(f"Created company {company.id} and agent {agent.id}.")
        print("Agent API key (shown once):")
        print(token)


if __name__ == "__main__":
    main()
