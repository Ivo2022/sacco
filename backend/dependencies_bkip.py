from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from .core.database import SessionLocal
from .services import get_user
from typing import Generator, Optional
from . import models
from .models import RoleEnum
from typing import cast


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(request: Request, db: Session = Depends(get_db)) -> models.User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user = get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def optional_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    """Return current user or None (does NOT raise). Useful for public pages/templates."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = get_user(db, user_id)
    return user


def require_role(role: RoleEnum):
    def inner(user: models.User = Depends(get_current_user)) -> models.User:
        # Cast for static type-checkers: treat the ORM-mapped attribute as the Enum value
        user_role = cast(models.RoleEnum, user.role)
        if user_role != role:
            raise HTTPException(status_code=403, detail="Insufficient privileges")
        return user
    return inner


def require_superadmin(user: models.User = Depends(get_current_user)) -> models.User:
    # Cast role for static checkers: user.role is an ORM-mapped Enum column at runtime
    user_role = cast(models.RoleEnum, user.role)
    if user_role != RoleEnum.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Super admin only")
    return user


def require_sacco_admin(user: models.User = Depends(get_current_user)) -> models.User:
    # allow either sacco admin or global super admin
    user_role = cast(models.RoleEnum, user.role)
    if user_role not in (RoleEnum.SACCO_ADMIN, RoleEnum.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Sacco admin only")
    return user
