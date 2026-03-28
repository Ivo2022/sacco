# backend/utils/logger.py
"""
Logging utilities for the application
"""

from sqlalchemy.orm import Session
from datetime import datetime
from ..models import Log
from typing import Optional

def create_log(
    db: Session, 
    action: str, 
    user_id: int, 
    sacco_id: Optional[int], 
    details: str = None, 
    ip_address: str = None
) -> Log:
    """
    Create an audit log entry
    
    Args:
        db: Database session
        action: Action performed (e.g., "LOAN_APPROVED", "DEPOSIT_MADE")
        user_id: ID of the user who performed the action
        sacco_id: ID of the SACCO
        details: Additional details about the action
        ip_address: IP address of the user
    
    Returns:
        The created Log object
    """
    log = Log(
        user_id=user_id,
        sacco_id=sacco_id,
        action=action,
        details=details,
        ip_address=ip_address,
        timestamp=datetime.utcnow()
    )
    db.add(log)
    db.commit()
    return log


def create_log_without_commit(
    db: Session, 
    action: str, 
    user_id: int, 
    sacco_id: int, 
    details: str = None, 
    ip_address: str = None
) -> Log:
    """
    Create an audit log entry without committing (for batch operations)
    """
    log = Log(
        user_id=user_id,
        sacco_id=sacco_id,
        action=action,
        details=details,
        ip_address=ip_address,
        timestamp=datetime.utcnow()
    )
    db.add(log)
    return log