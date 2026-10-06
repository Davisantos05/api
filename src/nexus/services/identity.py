"""Human authentication use cases."""

from datetime import timedelta

from sqlalchemy.orm import Session

from nexus.database.models import User, UserSession
from nexus.repositories.identity import UserSessionRepository
from nexus.security.passwords import hash_password, verify_password

_DUMMY_PASSWORD_HASH = hash_password("NEXUS-Dummy-Password-9")


class InvalidCredentialsError(Exception):
    pass


class HumanAuthenticationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sessions = UserSessionRepository(session)

    def login(
        self, *, company_slug: str, email: str, password: str
    ) -> tuple[UserSession, str, User]:
        user = self.sessions.find_login(
            company_slug=company_slug.lower(), email=email.lower()
        )
        candidate_hash = (
            user.password_hash if user is not None else _DUMMY_PASSWORD_HASH
        )
        password_valid = verify_password(candidate_hash, password)
        if (
            user is None
            or not user.active
            or not user.company.active
            or not password_valid
        ):
            raise InvalidCredentialsError
        record, token = self.sessions.create(user, lifetime=timedelta(hours=8))
        self.session.commit()
        return record, token, user

    def change_password(
        self, user: User, *, current_password: str, new_password: str
    ) -> None:
        if not verify_password(user.password_hash, current_password):
            raise InvalidCredentialsError
        user.password_hash = hash_password(new_password)
        self.sessions.revoke_all_for_user(user.id)
        self.session.commit()
