# backend/routers/membership.py
"""
Membership Management Router
Handles member applications, membership fees, and membership status
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime
import logging
import uuid

from ..core import get_db, get_current_user, require_role, require_manager, get_template_context
from ..models import User, RoleEnum, Sacco
from ..models.membership import MembershipFee, MembershipApplication, MembershipStatus
from ..services.membership_service import (
    apply_for_membership,
    approve_membership,
    reject_membership,
    pay_membership_fee,
    get_member_membership_status,
    generate_membership_number
)
from ..utils.helpers import get_template_helpers, check_sacco_status
from ..utils import create_log

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# SERIALIZERS
# =============================================================================

def serialize_membership_application(app: MembershipApplication) -> dict:
    """Convert MembershipApplication ORM to safe dict"""
    return {
        "id": app.id,
        "user_id": app.user_id,
        "sacco_id": app.sacco_id,
        "application_date": app.application_date.isoformat() if app.application_date else None,
        "status": app.status.value if app.status else None,
        "approved_by": app.approved_by,
        "approved_at": app.approved_at.isoformat() if app.approved_at else None,
        "rejection_reason": app.rejection_reason,
        "membership_number": app.membership_number,
        "user_email": app.user.email if app.user else None,
        "user_full_name": app.user.full_name if app.user else None,
        "sacco_name": app.sacco.name if app.sacco else None,
    }


def serialize_membership_fee(fee: MembershipFee) -> dict:
    """Convert MembershipFee ORM to safe dict"""
    return {
        "id": fee.id,
        "user_id": fee.user_id,
        "sacco_id": fee.sacco_id,
        "amount": fee.amount,
        "payment_method": fee.payment_method,
        "reference_number": fee.reference_number,
        "status": fee.status,
        "paid_at": fee.paid_at.isoformat() if fee.paid_at else None,
        "approved_by": fee.approved_by,
        "approved_at": fee.approved_at.isoformat() if fee.approved_at else None,
        "membership_number": fee.membership_number,
        "user_email": fee.user.email if fee.user else None,
        "user_full_name": fee.user.full_name if fee.user else None,
    }

def serialize_user_basic(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": str(user.role) if user.role else None,
        "is_active": user.is_active,
        "is_approved": user.is_approved,
        "phone": user.phone,
        "username": user.username,
		"created_at": user.created_at,
    }

def serialize_user_full(user: User) -> dict:
    base = serialize_user_basic(user)
    base.update({
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "sacco_id": user.sacco_id,
        "linked_member_account_id": user.linked_member_account_id,
        "linked_admin_id": user.linked_admin_id,
        "savings_balance": getattr(user, "savings_balance", 0),
        "active_loans": getattr(user, "active_loans", 0),
    })
    return base

# =============================================================================
# MEMBER ROUTES
# =============================================================================

@router.get("/membership/apply")
async def membership_application_form(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. SACCO status check (unchanged)
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
	
    """Display membership application form"""
    templates = request.app.state.templates
    
    # Check if user already has an application
    existing_app = db.query(MembershipApplication).filter(
        MembershipApplication.user_id == user.id
    ).first()
    
    if existing_app:
        if existing_app.status == MembershipStatus.PENDING:
            context = {
                "request": request,
                "user": user,
                "error": "You already have a pending membership application. Please wait for approval.",
                "application": serialize_membership_application(existing_app)
            }
            return templates.TemplateResponse("membership/pending.html", context)
        elif existing_app.status == MembershipStatus.ACTIVE:
            context = {
                "request": request,
                "user": user,
                "message": f"You are already an active member with number: {existing_app.membership_number}"
            }
            return templates.TemplateResponse("membership/active.html", context)
    
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        **helpers
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse("membership/apply.html", final_context)


@router.post("/membership/apply")
async def submit_membership_application(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit membership application"""
    try:
        # Check if user already has an active membership
        existing_active = db.query(MembershipApplication).filter(
            MembershipApplication.user_id == user.id,
            MembershipApplication.status == MembershipStatus.ACTIVE
        ).first()
        
        if existing_active:
            request.session["flash_message"] = "You are already an active member."
            request.session["flash_type"] = "warning"
            return RedirectResponse(url="/member/dashboard", status_code=303)
        
        # Check for pending application
        existing_pending = db.query(MembershipApplication).filter(
            MembershipApplication.user_id == user.id,
            MembershipApplication.status == MembershipStatus.PENDING
        ).first()
        
        if existing_pending:
            request.session["flash_message"] = "You already have a pending application."
            request.session["flash_type"] = "warning"
            return RedirectResponse(url="/membership/apply", status_code=303)
        
        # Create application
        application = apply_for_membership(db, user.id, user.sacco_id)
        
        create_log(
            db,
            action="MEMBERSHIP_APPLIED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Member {user.email} applied for membership"
        )
        
        request.session["flash_message"] = "Membership application submitted successfully! Please wait for approval."
        request.session["flash_type"] = "success"
        
        return RedirectResponse(url="/membership/status", status_code=303)
        
    except Exception as e:
        logger.error(f"Error submitting membership application: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
        return RedirectResponse(url="/membership/apply", status_code=303)


@router.get("/membership/status")
async def membership_status(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """View membership application status"""
    templates = request.app.state.templates
    
    application = db.query(MembershipApplication).filter(
        MembershipApplication.user_id == user.id
    ).first()
    
    if not application:
        return RedirectResponse(url="/membership/apply", status_code=303)
    
    # Get membership fee payment
    fee_payment = db.query(MembershipFee).filter(
        MembershipFee.user_id == user.id,
        MembershipFee.status == "approved"
    ).first()
    
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "application": serialize_membership_application(application),
        "fee_payment": serialize_membership_fee(fee_payment) if fee_payment else None,
        **helpers
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse("membership/status.html", final_context)


@router.get("/membership/fee/pay")
async def pay_membership_fee_form(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Display membership fee payment form"""
    templates = request.app.state.templates
    
    # Check if membership is approved
    application = db.query(MembershipApplication).filter(
        MembershipApplication.user_id == user.id,
        MembershipApplication.status == MembershipStatus.ACTIVE
    ).first()
    
    if not application:
        request.session["flash_message"] = "Your membership must be approved before paying fees."
        request.session["flash_type"] = "warning"
        return RedirectResponse(url="/membership/status", status_code=303)
    
    # Check if fee already paid
    existing_fee = db.query(MembershipFee).filter(
        MembershipFee.user_id == user.id,
        MembershipFee.status == "approved"
    ).first()
    
    if existing_fee:
        request.session["flash_message"] = "You have already paid your membership fee."
        request.session["flash_type"] = "info"
        return RedirectResponse(url="/member/dashboard", status_code=303)
    
    # Get SACCO's membership fee amount (configurable)
    sacco = db.query(Sacco).filter(Sacco.id == user.sacco_id).first()
    membership_fee = getattr(sacco, 'membership_fee', 50000)  # Default UGX 50,000
    
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "membership_fee": membership_fee,
        "membership_number": application.membership_number,
        **helpers
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse("membership/pay_fee.html", final_context)


@router.post("/membership/fee/pay")
async def submit_membership_fee(
    request: Request,
    amount: float = Form(...),
    payment_method: str = Form(...),
    reference_number: str = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Submit membership fee payment"""
    try:
        # Check if membership is approved
        application = db.query(MembershipApplication).filter(
            MembershipApplication.user_id == user.id,
            MembershipApplication.status == MembershipStatus.ACTIVE
        ).first()
        
        if not application:
            raise HTTPException(status_code=400, detail="Membership not approved")
        
        # Create fee payment record
        fee = pay_membership_fee(
            db=db,
            user_id=user.id,
            sacco_id=user.sacco_id,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            membership_number=application.membership_number
        )
        
        create_log(
            db,
            action="MEMBERSHIP_FEE_PAID",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Member {user.email} paid membership fee of UGX {amount:,.2f}"
        )
        
        request.session["flash_message"] = f"Membership fee of UGX {amount:,.2f} submitted for approval!"
        request.session["flash_type"] = "success"
        
        return RedirectResponse(url="/membership/status", status_code=303)
        
    except Exception as e:
        logger.error(f"Error paying membership fee: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
        return RedirectResponse(url="/membership/fee/pay", status_code=303)


# =============================================================================
# MANAGER/SUPERADMIN ROUTES
# =============================================================================

@router.get("/manager/membership/applications")
async def list_membership_applications(
    request: Request,
    status: str = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    # 1. SACCO status check (unchanged)
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    # 1. Serialize user to dictionary FIRST
    user_dict = serialize_user_full(user)
    
    # 2. Get RBAC context with serialized user
    base_context = get_template_context(request, user_dict)
	
    """List all membership applications for manager"""
    templates = request.app.state.templates
    
    query = db.query(MembershipApplication).filter(
        MembershipApplication.sacco_id == user.sacco_id
    )
    
    if status:
        try:
            query = query.filter(MembershipApplication.status == MembershipStatus(status))
        except ValueError:
            pass
    
    applications = query.order_by(MembershipApplication.application_date.desc()).all()
    
    # Get fee payments for each application
    for app in applications:
        fee = db.query(MembershipFee).filter(
            MembershipFee.user_id == app.user_id,
            MembershipFee.status == "approved"
        ).first()
        app.fee_paid = fee is not None
    
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "applications": [serialize_membership_application(app) for app in applications],
        "status_filter": status,
        **helpers
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse("manager/membership_applications.html", final_context)


@router.post("/manager/membership/application/{app_id}/approve")
async def approve_membership_application(
    request: Request,
    app_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """Approve a membership application"""
    try:
        application = db.query(MembershipApplication).filter(
            MembershipApplication.id == app_id,
            MembershipApplication.sacco_id == user.sacco_id
        ).first()
        
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        
        # Approve membership
        approve_membership(db, application.id, user.id)
        
        create_log(
            db,
            action="MEMBERSHIP_APPROVED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Membership application #{app_id} approved by {user.email}"
        )
        
        request.session["flash_message"] = "Membership application approved successfully!"
        request.session["flash_type"] = "success"
        
    except Exception as e:
        logger.error(f"Error approving membership: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
    
    return RedirectResponse(url="/manager/membership/applications", status_code=303)


@router.post("/manager/membership/application/{app_id}/reject")
async def reject_membership_application(
    request: Request,
    app_id: int,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """Reject a membership application"""
    try:
        application = db.query(MembershipApplication).filter(
            MembershipApplication.id == app_id,
            MembershipApplication.sacco_id == user.sacco_id
        ).first()
        
        if not application:
            raise HTTPException(status_code=404, detail="Application not found")
        
        # Reject membership
        reject_membership(db, application.id, user.id, reason)
        
        create_log(
            db,
            action="MEMBERSHIP_REJECTED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Membership application #{app_id} rejected by {user.email}. Reason: {reason}"
        )
        
        request.session["flash_message"] = "Membership application rejected."
        request.session["flash_type"] = "warning"
        
    except Exception as e:
        logger.error(f"Error rejecting membership: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
    
    return RedirectResponse(url="/manager/membership/applications", status_code=303)


@router.get("/manager/membership/fees")
async def list_membership_fees(
    request: Request,
    status: str = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """List all membership fee payments for manager"""
    templates = request.app.state.templates
    
    query = db.query(MembershipFee).filter(
        MembershipFee.sacco_id == user.sacco_id
    )
    
    if status:
        query = query.filter(MembershipFee.status == status)
    
    fees = query.order_by(MembershipFee.paid_at.desc()).all()
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "fees": [serialize_membership_fee(fee) for fee in fees],
        "status_filter": status,
        **helpers
    }
    return templates.TemplateResponse("manager/membership_fees.html", context)


@router.post("/manager/membership/fee/{fee_id}/approve")
async def approve_membership_fee(
    request: Request,
    fee_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """Approve a membership fee payment"""
    try:
        fee = db.query(MembershipFee).filter(
            MembershipFee.id == fee_id,
            MembershipFee.sacco_id == user.sacco_id
        ).first()
        
        if not fee:
            raise HTTPException(status_code=404, detail="Fee payment not found")
        
        if fee.status != "pending":
            raise HTTPException(status_code=400, detail="Fee already processed")
        
        # Approve fee
        fee.status = "approved"
        fee.approved_by = user.id
        fee.approved_at = datetime.utcnow()
        
        # Also approve the user if not already active
        user_member = db.query(User).filter(User.id == fee.user_id).first()
        if user_member and not user_member.is_approved:
            user_member.is_approved = True
            user_member.is_active = True
        
        db.commit()
        
        create_log(
            db,
            action="MEMBERSHIP_FEE_APPROVED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Membership fee UGX {fee.amount:,.2f} for {fee.user.email} approved by {user.email}"
        )
        
        request.session["flash_message"] = "Membership fee approved successfully!"
        request.session["flash_type"] = "success"
        
    except Exception as e:
        logger.error(f"Error approving membership fee: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
    
    return RedirectResponse(url="/manager/membership/fees", status_code=303)