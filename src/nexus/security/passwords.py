"""Argon2id password hashing and validation."""

import re

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher(type=Type.ID)


def validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    if not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password):
        raise ValueError("password must contain lowercase and uppercase letters")
    if not re.search(r"\d", password):
        raise ValueError("password must contain a number")


def hash_password(password: str) -> str:
    validate_password(password)
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if password_hash is None:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
