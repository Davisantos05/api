"""Create explicit local demonstration data after migrations are applied."""

import os

from sqlalchemy import select

from nexus.database.models import Company
from nexus.database.session import get_session_factory
from nexus.repositories.agents import AgentRepository
from nexus.repositories.companies import CompanyRepository


def main() -> None:
    token = os.getenv("NEXUS_DEV_AGENT_TOKEN")
    if not token:
        raise SystemExit("Set NEXUS_DEV_AGENT_TOKEN before running nexus-seed.")

    with get_session_factory()() as session:
        existing = session.scalar(select(Company).where(Company.name == "NEXUS Demo"))
        if existing is not None:
            raise SystemExit("NEXUS Demo already exists; seed was not changed.")

        company = CompanyRepository(session).create(name="NEXUS Demo")
        agent = AgentRepository(session).create(
            company_id=company.id,
            name="Purchasing Agent",
            description="Local demonstration agent for simulated purchases",
            token=token,
            allowed_operations={"purchase"},
            automatic_limit_cents=50_000,
            maximum_limit_cents=200_000,
        )
        session.commit()
        print(f"Created company {company.id} and agent {agent.id}.")
        print(
            "The token was read from the environment and was not displayed or stored."
        )


if __name__ == "__main__":
    main()
