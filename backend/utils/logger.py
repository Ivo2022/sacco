# backend/utils/logger.py
"""
Logging utilities for the application
"""

from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List, Union
from ..models import Log, User, RoleEnum
import logging
import inspect
import warnings

logger = logging.getLogger(__name__)


def create_log(
    db: Session, 
    action: str, 
    user_id: int, 
    sacco_id: Optional[int], 
    details: str = None, 
    ip_address: str = None
) -> Log:
    """
    Create an audit log entry (legacy method)
    
    Note: This function will be deprecated. Use log_user_action() instead.
    """
    # Show deprecation warning
    warnings.warn(
        "create_log() is deprecated. Use log_user_action() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
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
    db.refresh(log)
    return log


def log_user_action(
    db: Session,
    user: Union[User, dict, int],  # Accept User object, dict, or user_id
    action: str,
    details: str = None,
    ip_address: str = None,
    sacco_id: Optional[int] = None  # Optional override
) -> Log:
    """
    Create a log entry with automatic SACCO detection
    
    Args:
        db: Database session
        user: User object, dict with 'id' and 'sacco_id', or just user_id
        action: Action performed
        details: Additional details about the action
        ip_address: IP address of the user
        sacco_id: Optional override for SACCO ID
    
    Returns:
        The created Log object
    """
    # Handle different user input types
    if isinstance(user, User):
        # User object passed
        user_id = user.id
        auto_sacco_id = user.sacco_id
    elif isinstance(user, dict):
        # Dictionary with user data
        user_id = user.get('id')
        auto_sacco_id = user.get('sacco_id')
    elif isinstance(user, int):
        # Just the user ID (will need to fetch from DB)
        user_id = user
        auto_sacco_id = None
        # Try to get user from session if available
        try:
            from ..core.database import SessionLocal
            temp_db = SessionLocal()
            user_obj = temp_db.query(User).filter(User.id == user_id).first()
            if user_obj:
                auto_sacco_id = user_obj.sacco_id
            temp_db.close()
        except:
            pass
    else:
        raise ValueError(f"Invalid user type: {type(user)}")
    
    # Use provided sacco_id or auto-detected one
    final_sacco_id = sacco_id if sacco_id is not None else auto_sacco_id
    
    return create_log(
        db=db,
        action=action,
        user_id=user_id,
        sacco_id=final_sacco_id,
        details=details,
        ip_address=ip_address
    )


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


# backend/utils/logger.py - Updated filtering functions

def get_logs_for_user(
    db: Session, 
    user: User,
    limit: int = 100,
    offset: int = 0,
    action_filter: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None
) -> List[Log]:
    """
    Get logs based on user role and permissions
    
    - Super Admin: Can see ALL logs
    - Manager/Admin: Can see logs only for their SACCO
    - Other roles: Can see their own logs only
    """
    query = db.query(Log)
    
    # Apply role-based filtering
    if user.role == RoleEnum.SUPER_ADMIN:
        # Super admin sees all logs - no filtering
        pass
    
    elif user.role == RoleEnum.SACCO_ADMIN or user.role == RoleEnum.MANAGER:
        # Managers and SACCO admins see ONLY logs from their SACCO
        if user.sacco_id:
            # CRITICAL: Filter by sacco_id to ensure they only see their SACCO's logs
            query = query.filter(Log.sacco_id == user.sacco_id)
            logger.debug(f"Filtering logs for manager with sacco_id: {user.sacco_id}")
        else:
            # If manager doesn't have a SACCO assigned, return empty list
            logger.warning(f"Manager {user.id} has no sacco_id assigned")
            return []
    
    else:
        # Regular users (members, etc.) see only their own logs
        query = query.filter(Log.user_id == user.id)
        logger.debug(f"Filtering logs for regular user: {user.id}")
    
    # Apply additional filters
    if action_filter:
        query = query.filter(Log.action.ilike(f"%{action_filter}%"))
    
    if date_from:
        query = query.filter(Log.timestamp >= date_from)
    
    if date_to:
        # Add one day to include the entire end date
        from datetime import timedelta
        query = query.filter(Log.timestamp <= date_to + timedelta(days=1))
    
    # Order by most recent first
    query = query.order_by(Log.timestamp.desc())
    
    # Apply pagination
    logs = query.offset(offset).limit(limit).all()
    
    # Debug: Log the count of logs found
    logger.debug(f"Found {len(logs)} logs for user {user.id} (role: {user.role})")
    
    return logs


def get_logs_count(
    db: Session, 
    user: User,
    action_filter: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None
) -> int:
    """Get count of logs based on user role and permissions"""
    query = db.query(Log)
    
    # Apply role-based filtering
    if user.role == RoleEnum.SUPER_ADMIN:
        # Super admin sees all logs - no filtering
        pass
    
    elif user.role == RoleEnum.SACCO_ADMIN or user.role == RoleEnum.MANAGER:
        # Managers and SACCO admins see ONLY logs from their SACCO
        if user.sacco_id:
            # CRITICAL: Filter by sacco_id
            query = query.filter(Log.sacco_id == user.sacco_id)
        else:
            return 0
    
    else:
        # Regular users see only their own logs
        query = query.filter(Log.user_id == user.id)
    
    # Apply additional filters
    if action_filter:
        query = query.filter(Log.action.ilike(f"%{action_filter}%"))
    
    if date_from:
        query = query.filter(Log.timestamp >= date_from)
    
    if date_to:
        from datetime import timedelta
        query = query.filter(Log.timestamp <= date_to + timedelta(days=1))
    
    count = query.count()
    logger.debug(f"Total log count for user {user.id}: {count}")
    
    return count


def get_recent_activities(
    db: Session, 
    user: User,
    limit: int = 5
) -> List[Log]:
    """Get recent activities for dashboard"""
    return get_logs_for_user(db, user, limit=limit)