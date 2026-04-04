# backend/services/membership_service.py
"""
Membership Service Layer
Handles business logic for membership applications and fees
"""
from sqlalchemy.orm import Session
from datetime import datetime
import uuid
import logging

from ..models import User
from ..models.membership import MembershipApplication, MembershipFee, MembershipStatus

logger = logging.getLogger(__name__)


def generate_membership_number(sacco_id: int, user_id: int) -> str:
    """Generate a unique membership number"""
    # Format: SACCO-YYYY-XXXXX
    year = datetime.utcnow().year
    unique_id = uuid.uuid4().hex[:8].upper()
    return f"SACCO-{sacco_id}-{year}-{unique_id}"


def apply_for_membership(db: Session, user_id: int, sacco_id: int) -> MembershipApplication:
    """Create a new membership application"""
    # Check if user already has an application
    existing = db.query(MembershipApplication).filter(
        MembershipApplication.user_id == user_id
    ).first()
    
    if existing:
        if existing.status == MembershipStatus.PENDING:
            raise ValueError("You already have a pending membership application")
        elif existing.status == MembershipStatus.ACTIVE:
            raise ValueError("You are already an active member")
    
    # Create new application
    application = MembershipApplication(
        user_id=user_id,
        sacco_id=sacco_id,
        status=MembershipStatus.PENDING
    )
    
    db.add(application)
    db.commit()
    db.refresh(application)
    
    return application


def approve_membership(db: Session, application_id: int, approver_id: int) -> MembershipApplication:
    """Approve a membership application"""
    application = db.query(MembershipApplication).filter(
        MembershipApplication.id == application_id
    ).first()
    
    if not application:
        raise ValueError("Application not found")
    
    if application.status != MembershipStatus.PENDING:
        raise ValueError(f"Cannot approve application with status: {application.status}")
    
    # Generate membership number
    membership_number = generate_membership_number(application.sacco_id, application.user_id)
    
    # Update application
    application.status = MembershipStatus.ACTIVE
    application.approved_by = approver_id
    application.approved_at = datetime.utcnow()
    application.membership_number = membership_number
    
    # Update user
    user = db.query(User).filter(User.id == application.user_id).first()
    if user:
        user.is_approved = True
    
    db.commit()
    db.refresh(application)
    
    return application


def reject_membership(db: Session, application_id: int, approver_id: int, reason: str) -> MembershipApplication:
    """Reject a membership application"""
    application = db.query(MembershipApplication).filter(
        MembershipApplication.id == application_id
    ).first()
    
    if not application:
        raise ValueError("Application not found")
    
    if application.status != MembershipStatus.PENDING:
        raise ValueError(f"Cannot reject application with status: {application.status}")
    
    application.status = MembershipStatus.TERMINATED
    application.approved_by = approver_id
    application.approved_at = datetime.utcnow()
    application.rejection_reason = reason
    
    db.commit()
    db.refresh(application)
    
    return application


def pay_membership_fee(
    db: Session,
    user_id: int,
    sacco_id: int,
    amount: float,
    payment_method: str,
    reference_number: str = None,
    membership_number: str = None
) -> MembershipFee:
    """Record a membership fee payment"""
    # Check if fee already paid
    existing = db.query(MembershipFee).filter(
        MembershipFee.user_id == user_id,
        MembershipFee.status == "approved"
    ).first()
    
    if existing:
        raise ValueError("Membership fee already paid")
    
    # Create fee record
    fee = MembershipFee(
        user_id=user_id,
        sacco_id=sacco_id,
        amount=amount,
        payment_method=payment_method,
        reference_number=reference_number,
        membership_number=membership_number,
        status="pending"
    )
    
    db.add(fee)
    db.commit()
    db.refresh(fee)
    
    return fee


def get_member_membership_status(db: Session, user_id: int) -> dict:
    """Get membership status for a user"""
    application = db.query(MembershipApplication).filter(
        MembershipApplication.user_id == user_id
    ).first()
    
    if not application:
        return {
            "has_applied": False,
            "status": None,
            "membership_number": None
        }
    
    fee = db.query(MembershipFee).filter(
        MembershipFee.user_id == user_id,
        MembershipFee.status == "approved"
    ).first()
    
    return {
        "has_applied": True,
        "status": application.status.value if application.status else None,
        "membership_number": application.membership_number,
        "fee_paid": fee is not None,
        "application_date": application.application_date,
        "approved_at": application.approved_at
    }