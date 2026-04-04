# backend/utils/helpers.py
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models import User, Saving, RoleEnum, Loan, Sacco
from fastapi import Request
from typing import Optional

# Define your local timezone (UTC+3)
LOCAL_OFFSET = timedelta(hours=3)
LOCAL_TZ = timezone(LOCAL_OFFSET, name='East Africa Time')

def format_money(value):
    """Format money with thousand separators and 2 decimal places"""
    if value is None:
        return 'UGX 0.00'
    
    try:
        amount = float(value)
        formatted = f"{amount:,.2f}"
        return f"UGX {formatted}"
    except (ValueError, TypeError):
        return 'UGX 0.00'

def format_local_time(value):
    """Convert UTC datetime to local timezone (UTC+3)"""
    if value is None:
        return ''
    
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except:
            try:
                value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S.%f')
            except:
                try:
                    value = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
                except:
                    return value
    
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    
    local_value = value.astimezone(LOCAL_TZ)
    return local_value.strftime('%Y-%m-%d %H:%M:%S')

def format_date(value, format_str='%Y-%m-%d'):
    """Format datetime to date string"""
    if value is None:
        return ''
    if hasattr(value, 'strftime'):
        return value.strftime(format_str)
    return str(value)

# Create a function that returns all helpers for template context
def get_template_helpers():
    """Return all helper functions for use in templates"""
    return {
        'money': format_money,
        'local_time': format_local_time,
        'date': format_date,
        'now': datetime.utcnow()
    }
	
def get_members_with_savings(db: Session, sacco_id: int, min_balance: float = 0):
    """Get members with savings balance above minimum threshold"""
    from ..models import User, Saving, RoleEnum
    from sqlalchemy import func
    
    members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_active == True
    ).all()
    
    eligible_members = []
    for member in members:
        # Calculate total deposits
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == member.id,
            Saving.type == 'deposit'
        ).scalar() or 0
        
        # Calculate total withdrawals
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == member.id,
            Saving.type == 'withdraw'
        ).scalar() or 0
        
        # Calculate current balance
        balance = total_deposits - total_withdrawals
        
        if balance >= min_balance:
            member.savings_balance = balance
            eligible_members.append(member)
    
    return eligible_members
	
def get_guarantor_balance(db: Session, user_id: int) -> float:
    """Get a member's savings balance"""
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user_id,
        Saving.type == 'deposit'
    ).scalar() or 0
    
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user_id,
        Saving.type == 'withdraw'
    ).scalar() or 0
    
    return total_deposits - total_withdrawals

def is_eligible_guarantor(db: Session, user_id: int, min_balance: float = 0) -> bool:
    """Check if a user is eligible to be a guarantor"""
    balance = get_guarantor_balance(db, user_id)
    return balance > min_balance

def get_eligible_guarantors(db: Session, sacco_id: int, min_balance: float = 1000):
    """Get all members with savings above minimum balance"""
    from ..models import User, RoleEnum
    
    members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_active == True
    ).all()
    
    eligible = []
    for member in members:
        balance = get_guarantor_balance(db, member.id)
        if balance >= min_balance:
            member.savings_balance = balance
            eligible.append(member)
    
    return eligible
	
# backend/utils/loan_helpers.py

def get_user_loans_with_repayment(db: Session, user_id: int):
    """Get all user loans with repayment, interest, and remaining balance"""
    loans = db.query(Loan).filter(Loan.user_id == user_id).order_by(Loan.timestamp.desc()).all()
    
    result = []
    for loan in loans:
        # Calculate total payments made
        total_paid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        
        # Ensure interest is calculated
        if loan.total_payable == 0 and loan.status != 'pending':
            loan.calculate_interest()
            db.commit()
        
        # Use stored values or calculate if not available
        total_payable = loan.total_payable if loan.total_payable > 0 else loan.amount
        total_interest = loan.total_interest if loan.total_interest > 0 else 0
        remaining = max(0.0, total_payable - total_paid)
        
        # Calculate monthly payment
        monthly_payment = total_payable / loan.term if loan.term > 0 else 0
        
        result.append({
            "id": loan.id,
            "amount": loan.amount,
            "term": loan.term,
            "status": loan.status,
            "timestamp": loan.timestamp,
            "purpose": loan.purpose,
            "interest_rate": loan.interest_rate,
            "total_interest": total_interest,
            "total_payable": total_payable,
            "repaid": total_paid,
            "outstanding": remaining,
            "monthly_payment": monthly_payment,
            "repayment_percentage": (total_paid / total_payable * 100) if total_payable > 0 else 0
        })
    
    return result
	
# backend/utils/account_helpers.py

def get_member_account_for_admin(db: Session, admin_user: User):
    """Get the linked member account for an admin"""
    if admin_user.linked_member_id:
        return db.query(User).filter(User.id == admin_user.linked_member_id).first()
    return None

def get_admin_account_for_member(db: Session, member_user: User):
    """Get the linked admin account for a member"""
    if member_user.linked_admin_id:
        return db.query(User).filter(User.id == member_user.linked_admin_id).first()
    return None

def get_linked_admin_account(db: Session, member_user: User):
    """Get the admin account linked to this member"""
    # If we have the back-reference field
    if hasattr(member_user, 'linked_admin_id') and member_user.linked_admin_id:
        return db.query(User).filter(User.id == member_user.linked_admin_id).first()
    
    # Fallback: Search for admin that links to this member
    return db.query(User).filter(
        User.linked_member_account_id == member_user.id
    ).first()

def can_approve_loan(db: Session, admin: User, loan: Loan):
    """Check if an admin can approve a specific loan"""
    # Cannot approve own loan
    if admin.id == loan.user_id:
        return False, "Cannot approve your own loan"
    
    # Cannot approve loan for linked member
    if admin.linked_member_id == loan.user_id:
        return False, "Cannot approve loan for your linked member account"
    
    # Check if loan user is linked to this admin
    loan_user = db.query(User).filter(User.id == loan.user_id).first()
    if loan_user and loan_user.linked_admin_id == admin.id:
        return False, "Cannot approve loan for a member account linked to your admin account"
    
    return True, "OK"

def get_linked_member_account(db: Session, admin_user: User):
    """Get the linked member account for an admin"""
    if admin_user.linked_member_account_id:
        return db.query(User).filter(User.id == admin_user.linked_member_account_id).first()
    return None

def get_linked_admin_account(db: Session, member_user: User):
    """Get the linked admin account for a member"""
    if member_user.linked_admin_id:
        return db.query(User).filter(User.id == member_user.linked_admin_id).first()
    return None
	
def check_sacco_status(request: Request, user: User, db: Session):
    """Check if user's SACCO is active. Returns None if OK, or RedirectResponse if inactive."""
    
    if user is None:
        return None

    # Super admins bypass SACCO status checks
    if user.role == RoleEnum.SUPER_ADMIN:
        return None
    
    if user.sacco_id:
        sacco = db.query(Sacco).filter(Sacco.id == user.sacco_id).first()
        
        if sacco and sacco.status == 'inactive':
            request.session["flash_message"] = f"Your SACCO '{sacco.name}' is currently inactive. Services are temporarily unavailable."
            request.session["flash_type"] = "danger"
            return RedirectResponse(url="/member/inactive", status_code=303)
        
        if sacco and sacco.status == 'suspended':
            request.session["flash_message"] = f"Your SACCO '{sacco.name}' has been suspended. Please contact the administrator."
            request.session["flash_type"] = "danger"
            return RedirectResponse(url="/member/suspended", status_code=303)
    
    return None
	
def get_active_users_today(
    db: Session,
    sacco_id: Optional[int] = None,
    role: Optional[RoleEnum] = None
) -> int:
    """
    Get count of active users today (users who have had activity in the last 24 hours)
    
    Args:
        db: Database session
        sacco_id: Optional filter by SACCO
        role: Optional filter by role
    
    Returns:
        Count of active users
    """
    # Get start of today (00:00:00)
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Query users with activity today
    query = db.query(User).filter(
        User.last_activity >= today_start,
        User.is_active == True
    )
    
    if sacco_id:
        query = query.filter(User.sacco_id == sacco_id)
    
    if role:
        query = query.filter(User.role == role)
    
    count = query.count()
    logger.debug(f"Active users today: {count}")
    
    return count


def get_active_users_last_hour(
    db: Session,
    sacco_id: Optional[int] = None,
    role: Optional[RoleEnum] = None
) -> int:
    """
    Get count of active users in the last hour
    """
    one_hour_ago = datetime.utcnow() - timedelta(hours=1)
    
    query = db.query(User).filter(
        User.last_activity >= one_hour_ago,
        User.is_active == True
    )
    
    if sacco_id:
        query = query.filter(User.sacco_id == sacco_id)
    
    if role:
        query = query.filter(User.role == role)
    
    return query.count()


def get_user_activity_stats(
    db: Session,
    sacco_id: Optional[int] = None
) -> dict:
    """
    Get comprehensive user activity statistics
    """
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    stats = {
        "active_today": 0,
        "active_this_week": 0,
        "active_this_month": 0,
        "total_users": 0,
        "new_users_today": 0,
        "new_users_this_week": 0
    }
    
    # Base query
    query = db.query(User).filter(User.is_active == True)
    if sacco_id:
        query = query.filter(User.sacco_id == sacco_id)
    
    # Active users
    stats["active_today"] = query.filter(User.last_activity >= today_start).count()
    stats["active_this_week"] = query.filter(User.last_activity >= week_ago).count()
    stats["active_this_month"] = query.filter(User.last_activity >= month_ago).count()
    stats["total_users"] = query.count()
    
    # New users
    stats["new_users_today"] = query.filter(User.created_at >= today_start).count()
    stats["new_users_this_week"] = query.filter(User.created_at >= week_ago).count()
    
    return stats