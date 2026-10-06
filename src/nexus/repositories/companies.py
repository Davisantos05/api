"""Company persistence operations."""

from uuid import UUID

from sqlalchemy.orm import Session

from nexus.database.models import Company


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self, *, name: str, slug: str | None = None, active: bool = True
    ) -> Company:
        normalized_slug = slug or name.lower().replace(" ", "-")
        company = Company(name=name, slug=normalized_slug, active=active)
        self.session.add(company)
        self.session.flush()
        return company

    def get(self, company_id: UUID) -> Company | None:
        return self.session.get(Company, company_id)
