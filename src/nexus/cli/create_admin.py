"""Explicitly create the first company administrator."""

import argparse
import getpass
import os

from sqlalchemy import select

from nexus.database.models import Company, UserRole
from nexus.database.session import get_session_factory
from nexus.repositories.companies import CompanyRepository
from nexus.repositories.users import UserRepository
from nexus.security.passwords import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a NEXUS company administrator")
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--company-slug", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--email", required=True)
    args = parser.parse_args()
    password = os.getenv("NEXUS_ADMIN_PASSWORD") or getpass.getpass("Password: ")
    password_hash = hash_password(password)

    with get_session_factory()() as session:
        company = session.scalar(
            select(Company).where(Company.slug == args.company_slug.lower())
        )
        if company is None:
            company = CompanyRepository(session).create(
                name=args.company_name, slug=args.company_slug.lower()
            )
        user = UserRepository(session).create(
            company_id=company.id,
            name=args.name,
            email=args.email.lower(),
            role=UserRole.ADMIN,
            password_hash=password_hash,
        )
        session.commit()
        print(f"Created administrator {user.id} for company {company.slug}.")


if __name__ == "__main__":
    main()
