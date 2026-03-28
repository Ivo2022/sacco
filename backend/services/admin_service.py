# backend/services/admin_service.py
"""
Admin-related service functions
"""

from sqlalchemy.orm import Session
from .. import models
from .user_service import create_user


def create_admin_with_member_account(
    db: Session,
    admin_email: str,
    admin_password: str,
    admin_full_name: str,
    sacco_id: int,
    member_username: str = None,
    member_email: str = None
) -> dict:
    """Create an admin account and a linked member account for the same person"""
    
    # Create admin account
    admin = create_user(
        db,
        email=admin_email,
        password=admin_password,
        role=models.RoleEnum.SACCO_ADMIN,
        sacco_id=sacco_id,
        full_name=admin_full_name,
        is_staff=True,
        can_apply_for_loans=False,
        can_receive_dividends=False
    )
    
    # Create member email (if not provided)
    if not member_email:
        member_email = f"{admin_email.split('@')[0]}_member@{admin_email.split('@')[1]}"
    
    # Create member account
    member = create_user(
        db,
        email=member_email,
        password=admin_password,
        role=models.RoleEnum.MEMBER,
        sacco_id=sacco_id,
        full_name=f"{admin_full_name} (Member Account)",
        username=member_username or f"{admin.username}_member",
        is_staff=True,
        can_apply_for_loans=True,
        can_receive_dividends=True,
        requires_approval_for_loans=True
    )
    
    # Link accounts using simple ID references
    admin.linked_member_account_id = member.id
    member.linked_admin_id = admin.id
    
    db.commit()
    db.refresh(admin)
    db.refresh(member)
    
    return {
        "admin": admin,
        "member": member,
        "admin_credentials": {
            "email": admin_email,
            "password": admin_password,
            "role": "SACCO_ADMIN"
        },
        "member_credentials": {
            "email": member_email,
            "password": admin_password,
            "role": "MEMBER"
        }
    }


def get_linked_member_account(db: Session, admin_user: models.User) -> models.User:
    """Get the linked member account for an admin"""
    if admin_user.linked_member_account_id:
        return db.query(models.User).filter(models.User.id == admin_user.linked_member_account_id).first()
    return None