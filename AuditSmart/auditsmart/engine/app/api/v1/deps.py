"""Reusable FastAPI dependencies: current user, role checks, engagement membership."""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import get_db
from app.core.security import AuthError, Principal, TokenValidator
from app.models import EngagementMember
from app.services.rules import firm_of_engagement

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _validator_for(settings_id: int) -> TokenValidator:  # pragma: no cover - trivial cache
    return TokenValidator(get_settings())


def get_validator(settings: Annotated[Settings, Depends(get_settings)]) -> TokenValidator:
    return _validator_for(id(settings))


DbSession = Annotated[Session, Depends(get_db)]


def current_principal(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    validator: Annotated[TokenValidator, Depends(get_validator)],
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Sign in required: send a valid bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return validator.validate(creds.credentials)
    except AuthError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Your sign-in token is not valid or has expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None


CurrentUser = Annotated[Principal, Depends(current_principal)]


def require_roles(*roles: str) -> Callable[[Principal], Principal]:
    """Dependency factory: the user must hold at least one of ``roles`` (global app role)."""

    def _dep(user: CurrentUser) -> Principal:
        if not user.has_any(*roles):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"This action needs one of these roles: {', '.join(roles)}.",
            )
        return user

    return _dep


def check_membership(
    db: Session, user: Principal, engagement_id: str, roles: tuple[str, ...] = ()
) -> EngagementMember:
    member = db.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == user.user_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "You are not a member of this engagement."
        )
    if user.firm_id is not None:  # D42: never cross a firm boundary, even with a stray member row
        engagement_firm = firm_of_engagement(db, engagement_id)
        if engagement_firm is not None and engagement_firm != user.firm_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "This engagement belongs to another firm."
            )
    if roles and member.role not in roles:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Your engagement role ({member.role}) cannot do this; needs {', '.join(roles)}.",
        )
    return member


def require_engagement_member(*roles: str) -> Callable[..., EngagementMember]:
    """Dependency factory for routes with an ``{engagement_id}`` path parameter."""

    def _dep(
        engagement_id: Annotated[str, Path()], user: CurrentUser, db: DbSession
    ) -> EngagementMember:
        return check_membership(db, user, engagement_id, roles)

    return _dep
