# backend/utils/log_helpers.py
"""
Helper functions for common logging patterns
"""

from sqlalchemy.orm import Session
from .logger import log_user_action
from ..models import User
from typing import Optional

def log_member_action(
    db: Session,
    user: User,
    action: str,
    member_id: int,
    member_email: str,
    ip_address: Optional[str] = None,
    **kwargs
):
    """Log actions related to members"""
    details = f"Member {member_email} (ID: {member_id}) - {action}"
    if kwargs:
        details += f" - {kwargs}"
    
    return log_user_action(
        db=db,
        user=user,
        action=f"MEMBER_{action}",
        details=details,
        ip_address=ip_address
    )

def log_loan_action(
    db: Session,
    user: User,
    action: str,
    loan_id: int,
    loan_amount: float,
    member_email: str,
    ip_address: Optional[str] = None,
    **kwargs
):
    """Log actions related to loans"""
    details = f"Loan {loan_id} ({loan_amount}) for {member_email} - {action}"
    if kwargs:
        details += f" - {kwargs}"
    
    return log_user_action(
        db=db,
        user=user,
        action=f"LOAN_{action}",
        details=details,
        ip_address=ip_address
    )

def log_sacco_action(
    db: Session,
    user: User,
    action: str,
    sacco_name: str,
    sacco_id: int,
    ip_address: Optional[str] = None,
    **kwargs
):
    """Log actions related to SACCOs"""
    details = f"SACCO {sacco_name} (ID: {sacco_id}) - {action}"
    if kwargs:
        details += f" - {kwargs}"
    
    return log_user_action(
        db=db,
        user=user,
        action=f"SACCO_{action}",
        details=details,
        ip_address=ip_address
    )