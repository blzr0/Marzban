from dataclasses import dataclass
from enum import Enum
from typing import Optional, Union
from app.models.admin import AdminInDB, AdminValidationResult, Admin
from app.models.user import UserResponse, UserStatus
from app.db import Session, crud, get_db
from config import (
    DELETED_SUB_ENABLED,
    DELETED_SUB_LINK,
    DELETED_SUB_TITLES,
    REVOKED_SUB_ENABLED,
    REVOKED_SUB_LINK,
    REVOKED_SUB_TITLES,
    SUDOERS,
)
from fastapi import Depends, HTTPException
from datetime import datetime, timezone, timedelta
from app.utils.jwt import get_subscription_payload


def validate_admin(db: Session, username: str, password: str) -> Optional[AdminValidationResult]:
    """Validate admin credentials with environment variables or database."""
    if SUDOERS.get(username) == password:
        return AdminValidationResult(username=username, is_sudo=True)

    dbadmin = crud.get_admin(db, username)
    if dbadmin and AdminInDB.model_validate(dbadmin).verify_password(password):
        return AdminValidationResult(username=dbadmin.username, is_sudo=dbadmin.is_sudo)

    return None


def get_admin_by_username(username: str, db: Session = Depends(get_db)):
    """Fetch an admin by username from the database."""
    dbadmin = crud.get_admin(db, username)
    if not dbadmin:
        raise HTTPException(status_code=404, detail="Admin not found")
    return dbadmin


def get_dbnode(node_id: int, db: Session = Depends(get_db)):
    """Fetch a node by its ID from the database, raising a 404 error if not found."""
    dbnode = crud.get_node_by_id(db, node_id)
    if not dbnode:
        raise HTTPException(status_code=404, detail="Node not found")
    return dbnode


def validate_dates(start: Optional[Union[str, datetime]], end: Optional[Union[str, datetime]]) -> (datetime, datetime):
    """Validate if start and end dates are correct and if end is after start."""
    try:
        if start:
            start_date = start if isinstance(start, datetime) else datetime.fromisoformat(
                start).astimezone(timezone.utc)
        else:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if end:
            end_date = end if isinstance(end, datetime) else datetime.fromisoformat(end).astimezone(timezone.utc)
            if start_date and end_date < start_date:
                raise HTTPException(status_code=400, detail="Start date must be before end date")
        else:
            end_date = datetime.now(timezone.utc)

        return start_date, end_date
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date range or format")


def get_user_template(template_id: int, db: Session = Depends(get_db)):
    """Fetch a User Template by its ID, raise 404 if not found."""
    dbuser_template = crud.get_user_template(db, template_id)
    if not dbuser_template:
        raise HTTPException(status_code=404, detail="User Template not found")
    return dbuser_template


def _resolve_sub_token(token: str, db: Session):
    """Validate a subscription token's signature and look up its user.

    Raises 404 for an invalid/unsigned token. Returns (sub_payload, dbuser)
    otherwise; dbuser is None (or stale, i.e. created after the token) when
    the token's username no longer matches a live user.
    """
    sub = get_subscription_payload(token)
    if not sub:
        raise HTTPException(status_code=404, detail="Not Found")

    dbuser = crud.get_user(db, sub['username'])
    return sub, dbuser


def get_validated_sub(
        token: str,
        db: Session = Depends(get_db)
) -> UserResponse:
    sub, dbuser = _resolve_sub_token(token, db)
    if not dbuser or dbuser.created_at > sub['created_at']:
        raise HTTPException(status_code=404, detail="Not Found")

    if dbuser.sub_revoked_at and dbuser.sub_revoked_at > sub['created_at']:
        raise HTTPException(status_code=404, detail="Not Found")

    return dbuser


class SubState(Enum):
    """State of a signature-valid subscription token."""
    LIVE = "live"
    DELETED = "deleted"
    REVOKED = "revoked"


@dataclass
class ResolvedSub:
    """Result of resolving a subscription token, as an explicit state rather
    than magic combinations of Optional fields.

    For REVOKED, `dbuser` is deliberately left unset even though the user
    still exists in the DB: the link may be held by someone other than the
    account owner, so real account data (traffic, expiry, status) must never
    reach the response for a revoked link. Only `username` (from the token)
    is available in that case, same as DELETED.
    """
    state: SubState = SubState.LIVE
    dbuser: Optional[UserResponse] = None
    username: Optional[str] = None


def get_resolved_sub(
        token: str,
        db: Session = Depends(get_db)
) -> ResolvedSub:
    """Like get_validated_sub, but resolves to an explicit state instead of
    404ing outright, so the caller can serve a stub subscription:

    - DELETED: signature-valid token whose user no longer exists (or was
      recreated after the token was issued). Requires DELETED_SUB_ENABLED
      and both DELETED_SUB_LINK/DELETED_SUB_TITLES to be set, otherwise
      falls back to 404 - an incomplete config must not silently serve an
      empty stub subscription.
    - REVOKED: user still exists, but this specific link was revoked
      (sub_revoked_at is after the token's issue time). Checked only once
      DELETED is ruled out - deletion always wins. Revocation also takes
      priority over the user's own status (e.g. expired/limited): a revoked
      link says something more specific about *this link* than the
      account's overall state does. Requires REVOKED_SUB_ENABLED and both
      REVOKED_SUB_LINK/REVOKED_SUB_TITLES, same as DELETED.
    - LIVE: token is current for an existing, non-revoked user.
    """
    sub, dbuser = _resolve_sub_token(token, db)

    if not dbuser or dbuser.created_at > sub['created_at']:
        if DELETED_SUB_ENABLED and DELETED_SUB_LINK and DELETED_SUB_TITLES:
            return ResolvedSub(state=SubState.DELETED, username=sub['username'])
        raise HTTPException(status_code=404, detail="Not Found")

    if dbuser.sub_revoked_at and dbuser.sub_revoked_at > sub['created_at']:
        if REVOKED_SUB_ENABLED and REVOKED_SUB_LINK and REVOKED_SUB_TITLES:
            return ResolvedSub(state=SubState.REVOKED, username=sub['username'])
        raise HTTPException(status_code=404, detail="Not Found")

    return ResolvedSub(state=SubState.LIVE, dbuser=dbuser)


def get_validated_user(
        username: str,
        admin: Admin = Depends(Admin.get_current),
        db: Session = Depends(get_db)
) -> UserResponse:
    dbuser = crud.get_user(db, username)
    if not dbuser:
        raise HTTPException(status_code=404, detail="User not found")

    if not (admin.is_sudo or (dbuser.admin and dbuser.admin.username == admin.username)):
        raise HTTPException(status_code=403, detail="You're not allowed")

    return dbuser


def get_expired_users_list(db: Session, admin: Admin, expired_after: Optional[datetime] = None,
                           expired_before: Optional[datetime] = None):
    expired_before = expired_before or datetime.now(timezone.utc)
    expired_after = expired_after or datetime.min.replace(tzinfo=timezone.utc)

    dbadmin = crud.get_admin(db, admin.username)
    dbusers = crud.get_users(
        db=db,
        status=[UserStatus.expired, UserStatus.limited],
        admin=dbadmin if not admin.is_sudo else None
    )

    return [
        u for u in dbusers
        if u.expire and expired_after.timestamp() <= u.expire <= expired_before.timestamp()
    ]
