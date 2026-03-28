# backend/routers/sacco_admin.py

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import cast, Optional
from datetime import datetime

from ..core.dependencies import get_db, require_sacco_admin, get_current_user
from ..services.user_service import create_user
from ..utils.logger import create_log
from ..utils.helpers import (
    get_template_helpers, 
    get_eligible_guarantors, 
    is_eligible_guarantor, 
    get_guarantor_balance
)
from .. import models
from ..models import RoleEnum, User, Saving, Loan, Sacco, ExternalLoan, ExternalLoanPayment, PendingDeposit
from sqlalchemy import func

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/sacco/dashboard", response_class=HTMLResponse)
def sacco_dashboard(
    request: Request, 
    user: User = Depends(require_sacco_admin), 
    db: Session = Depends(get_db)
):
    """SACCO admin dashboard with statistics"""
    sacco_id = user.sacco_id

    # Get basic data
    members = db.query(User).filter(User.sacco_id == sacco_id).all()
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    loans = db.query(Loan).filter(Loan.sacco_id == sacco_id).all()
    
    # Calculate savings statistics
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0.0)).filter(
        Saving.sacco_id == sacco_id, 
        Saving.type == 'deposit'
    ).scalar() or 0.0
    
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0.0)).filter(
        Saving.sacco_id == sacco_id, 
        Saving.type == 'withdraw'
    ).scalar() or 0.0
    
    net_savings = total_deposits - total_withdrawals
    
    # Calculate loan statistics
    total_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0.0
    
    outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'approved'
    ).scalar() or 0.0
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("admin/dashboard.html", {
        "request": request, 
        "user": user, 
        "sacco": sacco, 
        "members": members, 
        "loans": loans, 
        "total_deposits": total_deposits, 
        "total_withdrawals": total_withdrawals,
        "net_savings": net_savings,
        "total_loans": total_loans,
        "outstanding_loans": outstanding_loans,
        "show_admin_controls": True,
        **helpers
    })

# backend/routers/sacco_admin.py

@router.get("/sacco/pending-deposits", response_class=HTMLResponse)
def view_pending_deposits(
    request: Request,
    user: User = Depends(require_sacco_admin),
    db: Session = Depends(get_db)
):
    """View pending deposit requests for admin approval"""
    
    pending_deposits = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    
    # Get recent approved deposits for reference
    recent_approved = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "approved"
    ).order_by(PendingDeposit.approved_at.desc()).limit(20).all()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse(
        "admin/pending_deposits.html",
        {
            "request": request,
            "user": user,
            "pending_deposits": pending_deposits,
            "recent_approved": recent_approved,
            "show_admin_controls": True,
            **helpers
        }
    )


@router.post("/sacco/pending-deposit/{pending_id}/approve")
async def approve_deposit(
    pending_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_sacco_admin)
):
    """Approve a pending deposit and add to member's savings"""
    
    pending = db.query(PendingDeposit).filter(
        PendingDeposit.id == pending_id,
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).first()
    
    if not pending:
        raise HTTPException(status_code=404, detail="Pending deposit not found")
    
    # Get form data for notes
    form_data = await request.form()
    approval_notes = form_data.get("notes", None)
    
    # Create the actual savings record
    saving = Saving(
        sacco_id=pending.sacco_id,
        user_id=pending.user_id,
        type='deposit',
        amount=pending.amount,
        payment_method=pending.payment_method,
        description=pending.description,
        reference_number=pending.reference_number,
        approved_by=user.id,
        approved_at=datetime.utcnow(),
        pending_deposit_id=pending.id
    )
    
    db.add(saving)
    
    # Update pending deposit status
    pending.status = "approved"
    pending.approved_by = user.id
    pending.approved_at = datetime.utcnow()
    pending.approval_notes = approval_notes
    
    db.commit()
    
    # Create audit log
    create_log(
        db,
        action="DEPOSIT_APPROVED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Admin {user.email} approved deposit of UGX {pending.amount:,.2f} for member {pending.user_id}",
        ip_address=request.client.host if request.client else None
    )
    
    request.session["flash_message"] = f"Deposit of UGX {pending.amount:,.2f} approved successfully!"
    request.session["flash_type"] = "success"
    
    referer = request.headers.get("referer", "/sacco/pending-deposits")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/sacco/pending-deposit/{pending_id}/reject")
async def reject_deposit(
    pending_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_sacco_admin)
):
    """Reject a pending deposit request"""
    
    pending = db.query(PendingDeposit).filter(
        PendingDeposit.id == pending_id,
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).first()
    
    if not pending:
        raise HTTPException(status_code=404, detail="Pending deposit not found")
    
    # Get form data for rejection reason
    form_data = await request.form()
    rejection_reason = form_data.get("rejection_reason", None)
    
    # Update pending deposit status
    pending.status = "rejected"
    pending.approved_by = user.id
    pending.approved_at = datetime.utcnow()
    pending.rejection_reason = rejection_reason
    
    db.commit()
    
    # Create audit log
    create_log(
        db,
        action="DEPOSIT_REJECTED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Admin {user.email} rejected deposit of UGX {pending.amount:,.2f} for member {pending.user_id}. Reason: {rejection_reason or 'Not specified'}",
        ip_address=request.client.host if request.client else None
    )
    
    request.session["flash_message"] = f"Deposit of UGX {pending.amount:,.2f} rejected"
    request.session["flash_type"] = "warning"
    
    referer = request.headers.get("referer", "/sacco/pending-deposits")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/sacco/loan/{loan_id}/approve")
async def approve_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db), 
    user: User = Depends(require_sacco_admin)
):
    """Approve a member loan request"""
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    
    # Check if admin is approving their own loan
    if user.id == loan.user_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot approve your own loan. This requires a different admin."
        )
		
    # Check if admin is approving a loan for their linked member account
    if user.linked_member_id == loan.user_id:
        raise HTTPException(
            status_code=403,
            detail="Cannot approve a loan for your linked member account. This requires a different admin to maintain separation of duties."
        )
		
    # Also check if the loan user has a linked admin and they're the same
    loan_user = db.query(User).filter(User.id == loan.user_id).first()
    if loan_user and loan_user.linked_admin_id == user.id:
        raise HTTPException(
            status_code=403,
            detail="Cannot approve a loan for a member account linked to your admin account. This is a conflict of interest."
        )
		
    # Get requester for audit log
    requester = db.query(User).filter(User.id == loan.user_id).first()
    
    # Check authorization
    user_role = cast(RoleEnum, user.role)
    if user_role != RoleEnum.SUPER_ADMIN and loan.sacco_id != user.sacco_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get approval notes from form
    form_data = await request.form()
    approval_notes = form_data.get("notes", None)
    
    # Update loan
    loan.status = "approved"
    loan.approved_by = user.id
    loan.approved_at = datetime.utcnow()
    loan.approval_notes = approval_notes
    
    db.commit()
    
    # Create audit log
    create_log(
        db,
        action="LOAN_APPROVED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Loan #{loan.id} for member {requester.full_name or requester.email} approved for UGX {loan.amount:,.2f}. Notes: {approval_notes or 'None'}",
        ip_address=request.client.host if request.client else None
    )
    
    referer = request.headers.get("referer", "/sacco/loans")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/sacco/loan/{loan_id}/reject")
async def reject_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db), 
    user: User = Depends(require_sacco_admin)
):
    """Reject a member loan request"""
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    
    # Check authorization
    user_role = cast(RoleEnum, user.role)
    if user_role != RoleEnum.SUPER_ADMIN and loan.sacco_id != user.sacco_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get rejection notes from form
    form_data = await request.form()
    rejection_notes = form_data.get("notes", None)
    
    # Update loan
    loan.status = "rejected"
    loan.approved_by = user.id
    loan.approved_at = datetime.utcnow()
    loan.approval_notes = rejection_notes
    
    db.commit()
    
    # Create audit log
    create_log(
        db, 
        action="LOAN_REJECTED", 
        user_id=user.id, 
        sacco_id=user.sacco_id,
        details=f"Loan #{loan.id} for user {loan.user_id} rejected. Reason: {rejection_notes or 'Not specified'}",
        ip_address=request.client.host if request.client else None
    )
    
    referer = request.headers.get("referer", "/sacco/loans")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/sacco/member/create")
async def create_member(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    full_name: str = Form(None), 
    db: Session = Depends(get_db), 
    user: User = Depends(get_current_user)
):
    """Create a new member in the SACCO"""
    # Authorization check
    user_role = cast(RoleEnum, user.role)
    if user_role not in (RoleEnum.SACCO_ADMIN, RoleEnum.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Not authorized")
    
    sacco_id = user.sacco_id
    
    # Generate username from full name
    if full_name:
        username = full_name.lower().replace(' ', '.')
        username = ''.join(c for c in username if c.isalnum() or c == '.')
    else:
        username = email.split('@')[0]
    
    # Ensure username is unique
    base_username = username
    counter = 1
    while db.query(User).filter(User.username == username).first():
        username = f"{base_username}{counter}"
        counter += 1
    
    try:
        member = create_user(
            db, 
            full_name=full_name, 
            email=email, 
            username=username,
            password=password, 
            role=RoleEnum.MEMBER, 
            sacco_id=sacco_id
        )
        
        # Create audit log
        create_log(
            db,
            action="MEMBER_CREATED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"New member created: {email} (username: {username})",
            ip_address=request.client.host if request.client else None
        )
        
        return RedirectResponse(url="/sacco/dashboard", status_code=303)
        
    except Exception as e:
        # Re-render dashboard with error
        from ..models import Sacco, User, Saving, Loan
        from sqlalchemy import func
        
        sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
        members = db.query(User).filter(User.sacco_id == sacco_id).all()
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0.0)).filter(
            Saving.sacco_id == sacco_id, Saving.type == 'deposit'
        ).scalar() or 0.0
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0.0)).filter(
            Saving.sacco_id == sacco_id, Saving.type == 'withdraw'
        ).scalar() or 0.0
        
        net_savings = total_deposits - total_withdrawals
        total_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
            Loan.sacco_id == sacco_id
        ).scalar() or 0.0
        outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
            Loan.sacco_id == sacco_id,
            Loan.status == 'approved'
        ).scalar() or 0.0
        
        loans = db.query(Loan).filter(Loan.sacco_id == sacco_id).all()
        helpers = get_template_helpers()
        
        return templates.TemplateResponse("admin/dashboard.html", {
            "request": request, 
            "user": user, 
            "sacco": sacco, 
            "members": members, 
            "loans": loans, 
            "total_deposits": total_deposits, 
            "total_withdrawals": total_withdrawals,
            "net_savings": net_savings,
            "total_loans": total_loans,
            "outstanding_loans": outstanding_loans,
            "error": str(e), 
            "show_admin_controls": True,
            **helpers
        })


@router.get("/sacco/users", response_class=HTMLResponse)
def manage_users(
    request: Request, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(require_sacco_admin)
):
    """Manage users in the SACCO"""
    users = db.query(User).filter(
        User.sacco_id == current_user.sacco_id,
        User.id != current_user.id
    ).order_by(User.created_at.desc()).all()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "user": current_user,
            "users": users,
            "sacco": current_user.sacco,
            "show_admin_controls": True,
            **helpers
        }
    )


# backend/routers/sacco_admin.py

@router.get("/sacco/loans", response_class=HTMLResponse)
def admin_view_loans(
    request: Request, 
    db: Session = Depends(get_db),
    user: User = Depends(require_sacco_admin)
):
    # Get internal member loans
    loans = db.query(Loan).join(User, Loan.user_id == User.id).filter(
        User.sacco_id == user.sacco_id
    ).order_by(Loan.timestamp.desc()).all()
    
    # Get external loans
    external_loans = db.query(ExternalLoan).join(
        User, ExternalLoan.guarantor_id == User.id
    ).filter(
        ExternalLoan.sacco_id == user.sacco_id
    ).order_by(ExternalLoan.timestamp.desc()).all()
    
    # Calculate total_paid and remaining for each external loan
    for ext_loan in external_loans:
        # Calculate total payments for this loan
        total_paid = db.query(func.coalesce(func.sum(ExternalLoanPayment.amount), 0)).filter(
            ExternalLoanPayment.external_loan_id == ext_loan.id
        ).scalar() or 0
        # Ensure interest is calculated
        if ext_loan.total_payable == 0 and ext_loan.status != 'pending':
            ext_loan.calculate_interest()
		
        # Add attributes to the object (temporarily)
        ext_loan.total_paid = total_paid
        ext_loan.remaining = max(0.0, ext_loan.total_payable - total_paid)
        
        # Also get payment history
        payments = db.query(ExternalLoanPayment).filter(
            ExternalLoanPayment.external_loan_id == ext_loan.id
        ).order_by(ExternalLoanPayment.timestamp.desc()).all()
        # Fetch recorder names for each payment
        for payment in payments:
            if payment.recorded_by:
                recorder = db.query(User).filter(User.id == payment.recorded_by).first()
                payment.recorder = recorder
		
        # Add payment history to the object
        ext_loan.payments = payments
        
        # Get guarantor's savings balance (if you need it)
        guarantor = db.query(User).filter(User.id == ext_loan.guarantor_id).first()
        if guarantor:
            total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
                Saving.user_id == guarantor.id,
                Saving.type == 'deposit'
            ).scalar() or 0
            total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
                Saving.user_id == guarantor.id,
                Saving.type == 'withdraw'
            ).scalar() or 0
            ext_loan.guarantor.savings_balance = total_deposits - total_withdrawals
    
    # Get eligible guarantors
    eligible_guarantors = get_eligible_guarantors(db, user.sacco_id, min_balance=1000)
    
    # Count pending loans
    pending_count = db.query(Loan).join(User, Loan.user_id == User.id).filter(
        User.sacco_id == user.sacco_id,
        Loan.status == 'pending'
    ).count()
    
    external_pending_count = db.query(ExternalLoan).filter(
        ExternalLoan.sacco_id == user.sacco_id,
        ExternalLoan.status == 'pending'
    ).count()
    
    # Enhance loans with requester information
    enhanced_loans = []
    for loan in loans:
        requester = db.query(User).filter(User.id == loan.user_id).first()
        approver = db.query(User).filter(User.id == loan.approved_by).first() if loan.approved_by else None
        
        enhanced_loans.append({
            "id": loan.id,
            "amount": loan.amount,
            "term": loan.term,
            "purpose": loan.purpose,
            "status": loan.status,
            "timestamp": loan.timestamp,
            "requester_name": requester.full_name or requester.email if requester else "Unknown",
            "requester_email": requester.email if requester else "Unknown",
            "approver_name": approver.full_name if approver else None,
            "approved_at": loan.approved_at,
            "approval_notes": loan.approval_notes
        })
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse(
        "admin/loans.html", 
        {
            "request": request, 
            "admin": user,
            "user": user,
            "loans": enhanced_loans,
            "external_loans": external_loans,  # Now has total_paid and remaining
            "members": eligible_guarantors,
            "pending_count": pending_count,
            "external_pending_count": external_pending_count,
            "show_admin_controls": True,
            **helpers
        }
    )


@router.get("/sacco/external-loans/create", response_class=HTMLResponse)
def create_external_loan_form(
    request: Request,
    user: User = Depends(require_sacco_admin),
    db: Session = Depends(get_db)
):
    """Display form to create external loan"""
    # Get eligible guarantors using helper function (minimum UGX 1,000 savings)
    eligible_guarantors = get_eligible_guarantors(db, user.sacco_id, min_balance=1000)
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse(
        "admin/external_loan_form.html",
        {
            "request": request,
            "user": user,
            "members": eligible_guarantors,
            **helpers
        }
    )


@router.post("/sacco/external-loans/create")
def create_external_loan(
    request: Request,
    borrower_name: str = Form(...),
    borrower_contact: str = Form(...),
    borrower_national_id: str = Form(...),
    amount: float = Form(...),
    term: int = Form(...),
    purpose: Optional[str] = Form(None),
    collateral_description: str = Form(...),
    collateral_value: float = Form(...),
    guarantor_id: int = Form(...),
    user: User = Depends(require_sacco_admin),
    db: Session = Depends(get_db)
):
    """Create a new external loan request with strict validation using helpers"""
    
    try:
        # 1. Validate basic loan parameters
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Loan amount must be positive")
        
        if term <= 0 or term > 60:
            raise HTTPException(status_code=400, detail="Loan term must be between 1 and 60 months")
        
        if collateral_value <= 0:
            raise HTTPException(status_code=400, detail="Collateral value must be positive")
        
        if amount < 10000:
            raise HTTPException(status_code=400, detail="Minimum loan amount is UGX 10,000")
        
        # 2. Validate guarantor using helper functions
        guarantor = db.query(User).filter(
            User.id == guarantor_id,
            User.sacco_id == user.sacco_id,
            User.role == RoleEnum.MEMBER,
            User.is_active == True
        ).first()
        
        if not guarantor:
            raise HTTPException(
                status_code=400, 
                detail="Invalid guarantor. Guarantor must be an active member of this SACCO."
            )
        
        # Check if guarantor has savings using helper
        if not is_eligible_guarantor(db, guarantor.id, min_balance=0):
            raise HTTPException(
                status_code=400, 
                detail=f"Guarantor {guarantor.full_name or guarantor.email} has no savings balance. "
                       f"Guarantor must have savings to guarantee a loan."
            )
        
        # Get guarantor balance using helper
        guarantor_balance = get_guarantor_balance(db, guarantor.id)
        
        # Check loan amount against guarantor's savings (3x rule)
        max_loan = guarantor_balance * 3
        if amount > max_loan:
            raise HTTPException(
                status_code=400, 
                detail=f"Loan amount (UGX {amount:,.2f}) exceeds maximum allowed. "
                       f"Maximum is 3x guarantor's savings = UGX {max_loan:,.2f}. "
                       f"Guarantor's current savings: UGX {guarantor_balance:,.2f}"
            )
        
        # Create external loan with interest
        external_loan = ExternalLoan(
            sacco_id=user.sacco_id,
            borrower_name=borrower_name,
            borrower_contact=borrower_contact,
            borrower_national_id=borrower_national_id,
            amount=amount,
            term=term,
            purpose=purpose,
            collateral_description=collateral_description,
            collateral_value=collateral_value,
            guarantor_id=guarantor.id,
            status="pending",
            timestamp=datetime.utcnow(),
			interest_rate=15.0  # Higher rate for external loans
        )
        
        # Calculate interest
        external_loan.calculate_interest()
        db.add(external_loan)
        db.commit()
        db.refresh(external_loan)
        
        # Create audit log
        create_log(
            db,
            action="EXTERNAL_LOAN_CREATED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"External loan request #{external_loan.id} for {borrower_name} (UGX {amount:,.2f}) with guarantor {guarantor.full_name or guarantor.email} (Balance: UGX {guarantor_balance:,.2f})",
            ip_address=request.client.host if request.client else None
        )
        
        return RedirectResponse(url="/sacco/loans", status_code=303)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error creating external loan: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create loan: {str(e)}")


@router.post("/sacco/external-loan/{loan_id}/approve")
async def approve_external_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_sacco_admin)
):
    """Approve an external loan"""
    loan = db.query(ExternalLoan).filter(
        ExternalLoan.id == loan_id,
        ExternalLoan.sacco_id == user.sacco_id
    ).first()
    
    if not loan:
        raise HTTPException(status_code=404, detail="External loan not found")
    
    if loan.status != "pending":
        raise HTTPException(status_code=400, detail="Loan already processed")
    
    # Get approval notes from form
    form_data = await request.form()
    approval_notes = form_data.get("notes", None)
    
    # Update loan
    loan.status = "approved"
    loan.approved_by = user.id
    loan.approved_at = datetime.utcnow()
    loan.approval_notes = approval_notes
    
    db.commit()
    
    # Create audit log
    create_log(
        db,
        action="EXTERNAL_LOAN_APPROVED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"External loan #{loan.id} for {loan.borrower_name} approved for UGX {loan.amount:,.2f}",
        ip_address=request.client.host if request.client else None
    )
    
    referer = request.headers.get("referer", "/sacco/loans")
    return RedirectResponse(url=referer, status_code=303)


@router.post("/sacco/external-loan/{loan_id}/reject")
async def reject_external_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_sacco_admin)
):
    """Reject an external loan"""
    loan = db.query(ExternalLoan).filter(
        ExternalLoan.id == loan_id,
        ExternalLoan.sacco_id == user.sacco_id
    ).first()
    
    if not loan:
        raise HTTPException(status_code=404, detail="External loan not found")
    
    if loan.status != "pending":
        raise HTTPException(status_code=400, detail="Loan already processed")
    
    # Get rejection reason from form
    form_data = await request.form()
    rejection_notes = form_data.get("notes", None)
    
    # Update loan
    loan.status = "rejected"
    loan.approved_by = user.id
    loan.approved_at = datetime.utcnow()
    loan.approval_notes = rejection_notes
    
    db.commit()
    
    # Create audit log
    create_log(
        db,
        action="EXTERNAL_LOAN_REJECTED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"External loan #{loan.id} for {loan.borrower_name} rejected. Reason: {rejection_notes or 'Not specified'}",
        ip_address=request.client.host if request.client else None
    )
    
    referer = request.headers.get("referer", "/sacco/loans")
    return RedirectResponse(url=referer, status_code=303)

# backend/routers/sacco_admin.py

@router.post("/sacco/external-loan/{loan_id}/repay")
async def repay_external_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_sacco_admin)
):
    """Record a payment for an external loan with interest tracking"""
    
    try:
        # Get form data
        form_data = await request.form()
        
        # Extract form fields with defaults
        amount = float(form_data.get("amount", 0))
        payment_method = form_data.get("payment_method", None)
        reference_number = form_data.get("reference_number", None)
        notes = form_data.get("notes", None)
        
        print(f"=== Recording payment for external loan {loan_id} ===")
        print(f"Payment amount: {amount}")
        print(f"Payment method: {payment_method}")
        print(f"Reference: {reference_number}")
        
        # Get the loan
        loan = db.query(ExternalLoan).filter(
            ExternalLoan.id == loan_id,
            ExternalLoan.sacco_id == user.sacco_id
        ).first()
        
        if not loan:
            raise HTTPException(status_code=404, detail="External loan not found")
        
        # Check if loan is approved
        if loan.status != "approved":
            raise HTTPException(
                status_code=400, 
                detail=f"Loan is not active. Current status: {loan.status}"
            )
        
        # Validate payment amount
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Payment amount must be positive")
        
        # Validate payment method
        if not payment_method:
            raise HTTPException(status_code=400, detail="Payment method is required")
        
        # Calculate interest if not already set
        if loan.total_payable == 0:
            loan.calculate_interest()
            db.commit()
            print(f"Calculated interest: UGX {loan.total_interest:,.2f}")
            print(f"Total payable: UGX {loan.total_payable:,.2f}")
        
        # Calculate total paid so far
        total_paid = db.query(func.coalesce(func.sum(ExternalLoanPayment.amount), 0)).filter(
            ExternalLoanPayment.external_loan_id == loan.id
        ).scalar() or 0
        
        # Calculate remaining balance (total payable - total paid)
        remaining = max(0.0, loan.total_payable - total_paid)
        
        print(f"Total paid: {total_paid}, Remaining: {remaining}")
        print(f"Principal: {loan.amount}, Interest: {loan.total_interest}, Total: {loan.total_payable}")
        
        # Check if payment exceeds remaining balance
        if amount > remaining:
            raise HTTPException(
                status_code=400, 
                detail=f"Payment amount (UGX {amount:,.2f}) exceeds remaining balance (UGX {remaining:,.2f})"
            )
        
        # Create payment record with all fields
        payment = ExternalLoanPayment(
            external_loan_id=loan.id,
            amount=amount,
            payment_method=payment_method,
            reference_number=reference_number,
            notes=notes or f"Payment recorded by {user.full_name or user.email}",
            recorded_by=user.id,
            timestamp=datetime.utcnow()
        )
        
        db.add(payment)
        
        # Update loan total paid
        loan.total_paid = total_paid + amount
        
        # Check if fully repaid
        payment_message = ""
        if loan.total_paid >= loan.total_payable:
            loan.status = "paid"
            payment_message = f"Loan fully repaid! Total paid: UGX {loan.total_paid:,.2f} (Principal: UGX {loan.amount:,.2f}, Interest: UGX {loan.total_interest:,.2f})"
        else:
            remaining_after = loan.total_payable - loan.total_paid
            payment_message = f"Payment of UGX {amount:,.2f} recorded. Remaining balance: UGX {remaining_after:,.2f} (Principal + Interest)"
        
        db.commit()
        
        print(f"Payment recorded: {payment_message}")
        
        # Create audit log
        create_log(
            db,
            action="EXTERNAL_LOAN_PAYMENT",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Payment of UGX {amount:,.2f} via {payment_method} recorded for external loan #{loan.id} ({loan.borrower_name}). {payment_message}. Ref: {reference_number or 'N/A'}",
            ip_address=request.client.host if request.client else None
        )
        
        # Set flash message
        request.session["flash_message"] = f"✓ Payment of UGX {amount:,.2f} recorded successfully!"
        request.session["flash_type"] = "success"
        
        referer = request.headers.get("referer", "/sacco/loans")
        return RedirectResponse(url=referer, status_code=303)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error recording payment: {e}")
        request.session["flash_message"] = f"✗ Error recording payment: {str(e)}"
        request.session["flash_type"] = "danger"
        referer = request.headers.get("referer", "/sacco/loans")
        return RedirectResponse(url=referer, status_code=303)