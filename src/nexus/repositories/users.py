"""User persistence operations, always scoped by company."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexus.database.models import User, UserRole


class UserRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        company_id: UUID,
        name: str,
        email: str,
        role: UserRole,
        active: bool = True,
    ) -> User:
        user = User(
            company_id=company_id,
            name=name,
            email=email,
            role=role,
            active=active,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def get(self, *, company_id: UUID, user_id: UUID) -> User | None:
        return self.session.scalar(
            select(User).where(User.company_id == company_id, User.id == user_id)
        )

    def list_for_company(self, company_id: UUID) -> list[User]:
        return list(
            self.session.scalars(select(User).where(User.company_id == company_id))
        )
