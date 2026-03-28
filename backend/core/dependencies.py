from fastapi import Request, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Optional, TYPE_CHECKING, cast, List, Any

from ..core.database import get_db
from ..schemas import RoleEnum

# Use TYPE_CHECKING to avoid circular imports at runtime
if TYPE_CHECKING:
    from ..models import User

def normalize_role(role: Any) -> str:
    """Normalize role to consistent format for comparison"""
    # Get the string value
    if hasattr(role, 'value'):
        role_str = role.value
    else:
        role_str = str(role)
    
    # Convert to lowercase for comparison (since schemas use lowercase)
    return role_str.lower()

async def get_current_user(
    request: Request,
    db: Session = Depends(get_db)
) -> Optional["User"]:
    """Get current user from session"""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    
    from ..models import User  # Import inside function to avoid circular import
    user = db.query(User).filter(User.id == user_id).first()
    return user

async def require_auth(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Require authentication"""
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

def require_role(role: RoleEnum):
    """Require a specific role"""
    async def inner(
        user: "User" = Depends(get_current_user)
    ) -> "User":
        # Check if user exists
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        # Normalize both roles for comparison
        user_role = normalize_role(user.role)
        expected_role = normalize_role(role)
        
        if user_role != expected_role:
            raise HTTPException(
                status_code=403, 
                detail=f"Role {role.value} required. Your role: {user_role}"
            )
        return user
    return inner

# ============ ROLE-SPECIFIC DEPENDENCIES ============

async def require_superadmin(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Require super admin role"""
    user = await require_auth(request, db)
    
    user_role = normalize_role(user.role)
    expected_role = normalize_role(RoleEnum.SUPER_ADMIN)
    
    if user_role != expected_role:
        raise HTTPException(
            status_code=403, 
            detail=f"Super admin only. Your role: {user_role}"
        )
    return user

async def require_manager(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Require manager role"""
    user = await require_auth(request, db)
    user_role = normalize_role(user.role)
    expected_role = normalize_role(RoleEnum.MANAGER)
    
    if user_role != expected_role:
        raise HTTPException(
            status_code=403, 
            detail=f"Manager access required. Your role: {user_role}"
        )
    return user

async def require_accountant(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Require accountant role"""
    user = await require_auth(request, db)
    user_role = normalize_role(user.role)
    expected_role = normalize_role(RoleEnum.ACCOUNTANT)
    
    if user_role != expected_role:
        raise HTTPException(
            status_code=403, 
            detail=f"Accountant access required. Your role: {user_role}"
        )
    return user

async def require_credit_officer(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Require credit officer role"""
    user = await require_auth(request, db)
    user_role = normalize_role(user.role)
    expected_role = normalize_role(RoleEnum.CREDIT_OFFICER)
    
    if user_role != expected_role:
        raise HTTPException(
            status_code=403, 
            detail=f"Credit officer access required. Your role: {user_role}"
        )
    return user

async def require_member(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Require member role"""
    user = await require_auth(request, db)
    
    user_role = normalize_role(user.role)
    expected_role = normalize_role(RoleEnum.MEMBER)
    
    if user_role != expected_role:
        raise HTTPException(
            status_code=403, 
            detail=f"Member access required. Your role: {user_role}"
        )
    return user

# ============ MANAGER VIEW-ONLY DEPENDENCIES ============
# These allow managers to view role-specific dashboards

async def require_accountant_or_manager(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """
    Require accountant role, but allow managers to view (read-only)
    Use this for accountant dashboard views that managers should see
    """
    user = await require_auth(request, db)
    user_role = normalize_role(user.role)
    
    allowed_roles = [
        normalize_role(RoleEnum.ACCOUNTANT),
        normalize_role(RoleEnum.MANAGER),
        normalize_role(RoleEnum.SUPER_ADMIN)  # Super admin can also view
    ]
    
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=403, 
            detail=f"Accountant or Manager access required. Your role: {user_role}"
        )
    return user

async def require_credit_officer_or_manager(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """
    Require credit officer role, but allow managers to view (read-only)
    Use this for credit officer dashboard views that managers should see
    """
    user = await require_auth(request, db)
    user_role = normalize_role(user.role)
    
    allowed_roles = [
        normalize_role(RoleEnum.CREDIT_OFFICER),
        normalize_role(RoleEnum.MANAGER),
        normalize_role(RoleEnum.SUPER_ADMIN)  # Super admin can also view
    ]
    
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=403, 
            detail=f"Credit Officer or Manager access required. Your role: {user_role}"
        )
    return user

async def require_staff_or_manager(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """
    Require staff role (accountant/credit officer) or manager/superadmin
    Use for pages that any staff or manager can access
    """
    user = await require_auth(request, db)
    user_role = normalize_role(user.role)
    
    allowed_roles = [
        normalize_role(RoleEnum.ACCOUNTANT),
        normalize_role(RoleEnum.CREDIT_OFFICER),
        normalize_role(RoleEnum.MANAGER),
        normalize_role(RoleEnum.SUPER_ADMIN)
    ]
    
    if user_role not in allowed_roles:
        raise HTTPException(
            status_code=403, 
            detail=f"Staff or Manager access required. Your role: {user_role}"
        )
    return user

# ============ COMBINED ROLE REQUIREMENTS ============

def require_any_role(allowed_roles: List[RoleEnum]):
    """Require any of the specified roles"""
    async def inner(
        user: "User" = Depends(get_current_user)
    ) -> "User":
        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")
        
        user_role = normalize_role(user.role)
        allowed_values = [normalize_role(role) for role in allowed_roles]
        
        if user_role not in allowed_values:
            raise HTTPException(
                status_code=403, 
                detail=f"Access requires one of these roles: {allowed_values}. Your role: {user_role}"
            )
        return user
    return inner

# Alias for staff access (existing function)
async def require_staff(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Require any staff role (manager, accountant, credit officer, superadmin)"""
    user = await require_auth(request, db)
    
    user_role = normalize_role(user.role)
    staff_roles = [
        normalize_role(RoleEnum.SUPER_ADMIN),
        normalize_role(RoleEnum.MANAGER),
        normalize_role(RoleEnum.ACCOUNTANT),
        normalize_role(RoleEnum.CREDIT_OFFICER)
    ]
    
    if user_role not in staff_roles:
        raise HTTPException(
            status_code=403, 
            detail=f"Staff access required. Your role: {user_role}"
        )
    return user

# ============ PERMISSION-BASED FUNCTIONS ============

async def can_approve_loans(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Check if user can approve loans (Managers and Credit Officers)"""
    user = await require_auth(request, db)
    if not user.can_approve_loans:
        raise HTTPException(
            status_code=403, 
            detail="You don't have permission to approve loans"
        )
    return user

async def can_approve_deposits(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Check if user can approve deposits (Accountants and Managers)"""
    user = await require_auth(request, db)
    if not user.can_approve_deposits:
        raise HTTPException(
            status_code=403, 
            detail="You don't have permission to approve deposits"
        )
    return user

async def can_manage_loans(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Check if user can manage loans (Credit Officers, Managers)"""
    user = await require_auth(request, db)
    if not user.can_manage_loans:
        raise HTTPException(
            status_code=403, 
            detail="You don't have permission to manage loans"
        )
    return user

async def can_send_loan_reminders(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Check if user can send loan reminders (Credit Officers, Managers)"""
    user = await require_auth(request, db)
    if not user.can_send_loan_reminders:
        raise HTTPException(
            status_code=403, 
            detail="You don't have permission to send loan reminders"
        )
    return user

async def can_view_all_transactions(
    request: Request,
    db: Session = Depends(get_db)
) -> "User":
    """Check if user can view all transactions (Accountants, Managers)"""
    user = await require_auth(request, db)
    if not user.can_view_all_transactions:
        raise HTTPException(
            status_code=403, 
            detail="You don't have permission to view all transactions"
        )
    return user