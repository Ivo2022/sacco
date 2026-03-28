from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..core.dependencies import get_db, require_sacco_admin, get_current_user
from ..services import create_user, create_log
from ..utils.helpers import get_members_with_savings, get_eligible_guarantors, is_eligible_guarantor, get_guarantor_balance
from .. import models
from typing import cast, Optional
from ..models import RoleEnum, User, Saving, Loan, Sacco, ExternalLoan, ExternalLoanPayment
from sqlalchemy import func
from datetime import datetime

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/sacco/dashboard", response_class=HTMLResponse)
def sacco_dashboard(request: Request, user: User = Depends(require_sacco_admin), db: Session = Depends(get_db)):
    # user is sacco admin (or superadmin). show sacco-specific stats
    sacco_id = user.sacco_id

    members = db.query(User).filter(User.sacco_id == sacco_id).all()
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    
    # Existing savings calculations
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0.0)).filter(Saving.sacco_id == sacco_id, Saving.type == 'deposit').scalar() or 0.0
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0.0)).filter(Saving.sacco_id == sacco_id, Saving.type == 'withdraw').scalar() or 0.0
    
    # Net savings (total deposits - total withdrawals)
    net_savings = total_deposits - total_withdrawals
    
    # Total loans (sum of all loan amounts) - renamed to match template
    total_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(Loan.sacco_id == sacco_id).scalar() or 0.0
    
    # Outstanding loans (sum of approved loans)
    outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'approved'
    ).scalar() or 0.0
    
    # Keep simple counts for loans (all loans, regardless of status)
    loans = db.query(Loan).filter(Loan.sacco_id == sacco_id).all()
    
    # Debug prints to verify data
    print(f"Dashboard Stats for SACCO {sacco_id}:")
    print(f"  Net Savings: {net_savings}")
    print(f"  Total Loans: {total_loans}")
    print(f"  Outstanding Loans: {outstanding_loans}")
    print(f"  Total Deposits: {total_deposits}")
    print(f"  Total Withdrawals: {total_withdrawals}")
    
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
        "show_admin_controls": True
    })


@router.post("/sacco/loan/{loan_id}/approve")
def approve_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db), 
    user: User = Depends(require_sacco_admin)
):
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    
    # Get requester for audit log
    requester = db.query(User).filter(User.id == loan.user_id).first()
    
    # Only allow managing loans in own sacco unless superadmin
    user_role = cast(RoleEnum, user.role)
    if user_role != RoleEnum.SUPER_ADMIN and loan.sacco_id != user.sacco_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get approval notes from form if any
    form_data = request.form()
    approval_notes = form_data.get("notes", None) if hasattr(form_data, 'get') else None
    
    # Update loan with approval information
    loan.status = "approved"
    loan.approved_by = user.id  # Track who approved
    loan.approved_at = datetime.utcnow()  # Track when
    loan.approval_notes = approval_notes
    
    db.add(loan)
    db.commit()
    
    # Create audit log entry using existing Log model
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
def reject_loan(
    loan_id: int,
    request: Request,
    db: Session = Depends(get_db), 
    user: User = Depends(require_sacco_admin)
):
    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    
    user_role = cast(RoleEnum, user.role)
    if user_role != RoleEnum.SUPER_ADMIN and loan.sacco_id != user.sacco_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get rejection notes from form
    form_data = request.form()
    rejection_notes = form_data.get("notes", None) if hasattr(form_data, 'get') else None
    
    loan.status = "rejected"
    loan.approved_by = user.id  # Track who rejected
    loan.approved_at = datetime.utcnow()
    loan.approval_notes = rejection_notes
    
    db.add(loan)
    db.commit()
    
    # Create audit log entry
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
def create_member(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    full_name: str = Form(None), 
    db: Session = Depends(get_db), 
    user = Depends(get_current_user)
):
    # Only sacco admins can add members for their sacco
    user_role = cast(RoleEnum, user.role)
    if user_role not in (RoleEnum.SACCO_ADMIN, RoleEnum.SUPER_ADMIN):
        raise HTTPException(status_code=403)
    
    sacco_id = user.sacco_id
    
    # Generate username from full name
    if full_name:
        username = full_name.lower().replace(' ', '.')
        # Remove any special characters
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
        # On error re-render dashboard with the same context variables
        from ..models import Sacco, User, Saving, Loan
        from sqlalchemy import func
        
        sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
        members = db.query(User).filter(User.sacco_id == sacco_id).all()
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0.0)).filter(Saving.sacco_id == sacco_id, Saving.type == 'deposit').scalar() or 0.0
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0.0)).filter(Saving.sacco_id == sacco_id, Saving.type == 'withdraw').scalar() or 0.0
        
        # Calculate the additional metrics for error handling
        net_savings = total_deposits - total_withdrawals
        total_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(Loan.sacco_id == sacco_id).scalar() or 0.0
        outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
            Loan.sacco_id == sacco_id,
            Loan.status == 'approved'
        ).scalar() or 0.0
        
        loans = db.query(Loan).filter(Loan.sacco_id == sacco_id).all()
        
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
            "show_admin_controls": True
        })


@router.get("/sacco/users", response_class=HTMLResponse)
def manage_users(
    request: Request, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(require_sacco_admin)
):
    # Get all users belonging to the same SACCO as the current admin
    users = db.query(User).filter(
        User.sacco_id == current_user.sacco_id,
        User.id != current_user.id
    ).order_by(User.created_at.desc()).all()
    
    # For debugging - print to console to verify
    print(f"Found {len(users)} users for SACCO ID: {current_user.sacco_id}")
    for user in users:
        print(f"  User: {user.email}, Role: {user.role}")
    
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "user": current_user,
            "users": users,
            "sacco": current_user.sacco,
			"show_admin_controls": True  # ← CRITICAL: Add this
        }
    )

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
    
    # Get members with savings balance (only those who can be guarantors)
    members = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_active == True
    ).all()
    
    eligible_guarantors = get_members_with_savings(db, user.sacco_id, min_balance=1000)
        
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
    
    return templates.TemplateResponse(
        "admin/loans.html", 
        {
            "request": request, 
            "admin": user,
            "user": user,
            "loans": enhanced_loans,
            "external_loans": external_loans,
            "members": eligible_guarantors,  # Now only members with savings
            "pending_count": pending_count,
            "external_pending_count": external_pending_count,
            "show_admin_controls": True
        }
    )
	
"""
@router.get("/sacco/loans", response_class=HTMLResponse)
def admin_view_loans(
    request: Request, 
    db: Session = Depends(get_db),
    user: User = Depends(require_sacco_admin)
):
	
    # Get all loans from users in the same SACCO as the admin
    loans = db.query(Loan).join(User, Loan.user_id == User.id).filter(
        User.sacco_id == user.sacco_id
    ).order_by(Loan.timestamp.desc()).all()
	
    # Enhance loans with requester and approver information
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
	
    return templates.TemplateResponse(
        "admin/loans.html", 
        {
            "request": request, 
            "admin": user,
			"user": user,
            "loans": enhanced_loans,
            "show_admin_controls": True
        }
    )
"""

@router.get("/sacco/external-loans", response_class=HTMLResponse)
def external_loans_list(
    request: Request,
    user: User = Depends(require_sacco_admin),
    db: Session = Depends(get_db)
):
    sacco_id = user.sacco_id
    
    # Get pending external loans - explicitly specify joins
    pending = db.query(ExternalLoan).join(
        User, ExternalLoan.guarantor_id == User.id
    ).filter(
        ExternalLoan.sacco_id == sacco_id,
        ExternalLoan.status == "pending"
    ).all()
    
    # Get approved/paid external loans
    approved = db.query(ExternalLoan).join(
        User, ExternalLoan.guarantor_id == User.id
    ).filter(
        ExternalLoan.sacco_id == sacco_id,
        ExternalLoan.status.in_(["approved", "paid"])
    ).order_by(ExternalLoan.timestamp.desc()).all()
    
    # Get template helpers (if you have this function)
    helpers = get_template_helpers()
    
    return templates.TemplateResponse(
        "admin/external_loans.html",
        {
            "request": request,
            "user": user,
            "pending": pending,
            "approved": approved,
            **helpers,  # Uncomment if you have helpers,
			"show_admin_controls": True  # ← CRITICAL: Add this
        }
    )

@router.get("/sacco/external-loans/create", response_class=HTMLResponse)
def create_external_loan_form(
    request: Request,
    user: User = Depends(require_sacco_admin),
    db: Session = Depends(get_db)
):
    """Display form to create external loan"""
    
    # Get members who can be guarantors (with savings)
    members = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_active == True
    ).all()
    
    eligible_guarantors = get_members_with_savings(db, user.sacco_id, min_balance=1000)
    
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


@router.post("/external-loans/create")
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
    """Create a new external loan request with strict validation"""
    
    try:
        # 1. Validate loan amount
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Loan amount must be positive")
        
        # 2. Validate term
        if term <= 0 or term > 60:
            raise HTTPException(status_code=400, detail="Loan term must be between 1 and 60 months")
        
        # 3. Validate collateral value
        if collateral_value <= 0:
            raise HTTPException(status_code=400, detail="Collateral value must be positive")
        
        # 4. Validate guarantor
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
        
        # 5. Check if guarantor has savings
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == guarantor.id,
            Saving.type == 'deposit'
        ).scalar() or 0
        
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == guarantor.id,
            Saving.type == 'withdraw'
        ).scalar() or 0
        
        guarantor_balance = total_deposits - total_withdrawals
        
        # CRITICAL: Guarantor MUST have savings
        if guarantor_balance <= 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Guarantor {guarantor.full_name or guarantor.email} has no savings balance. "
                       f"Guarantor must have savings to guarantee a loan."
            )
        
        # 6. Check loan amount against guarantor's savings (3x rule)
        max_loan = guarantor_balance * 3
        if amount > max_loan:
            raise HTTPException(
                status_code=400, 
                detail=f"Loan amount (UGX {amount:,.2f}) exceeds maximum allowed based on guarantor's savings. "
                       f"Maximum allowed is 3x guarantor's savings = UGX {max_loan:,.2f}. "
                       f"Guarantor's current savings: UGX {guarantor_balance:,.2f}"
            )
        
        # 7. Check if loan amount is reasonable (optional: minimum loan)
        if amount < 10000:
            raise HTTPException(
                status_code=400,
                detail="Minimum loan amount is UGX 10,000"
            )
        
        # Create external loan
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
            timestamp=datetime.utcnow()
        )
        
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
        
        # Redirect with success message
        from fastapi.responses import RedirectResponse
        response = RedirectResponse(url="/sacco/loans", status_code=303)
        # You could add a session flash message here if needed
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error creating external loan: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create loan: {str(e)}")

@router.post("/sacco/external-loan/{loan_id}/approve")
def approve_external_loan(
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
    form_data = request.form()
    approval_notes = form_data.get("notes", None) if hasattr(form_data, 'get') else None
    
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
def reject_external_loan(
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
    form_data = request.form()
    rejection_notes = form_data.get("notes", None) if hasattr(form_data, 'get') else None
    
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


@router.post("/sacco/external-loan/{loan_id}/repay")
def repay_external_loan(
    loan_id: int,
    amount: float = Form(...),
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_sacco_admin)
):
    """Record a payment for an external loan"""
    
    try:
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
        
        # Calculate total paid so far
        total_paid = db.query(func.coalesce(func.sum(ExternalLoanPayment.amount), 0)).filter(
            ExternalLoanPayment.external_loan_id == loan.id
        ).scalar() or 0
        
        remaining = loan.amount - total_paid
        
        # Check if payment exceeds remaining balance
        if amount > remaining:
            raise HTTPException(
                status_code=400, 
                detail=f"Payment amount (UGX {amount:,.2f}) exceeds remaining balance (UGX {remaining:,.2f})"
            )
        
        # Create payment record
        payment = ExternalLoanPayment(
            external_loan_id=loan.id,
            amount=amount,
            recorded_by=user.id,
            timestamp=datetime.utcnow(),
            notes=f"Payment recorded by {user.full_name or user.email}"
        )
        
        db.add(payment)
        
        # Check if fully repaid
        if amount >= remaining:
            loan.status = "paid"
            payment_message = f"Loan fully repaid! Total: UGX {loan.amount:,.2f}"
        else:
            payment_message = f"Payment of UGX {amount:,.2f} recorded. Remaining: UGX {remaining - amount:,.2f}"
        
        db.commit()
        
        # Create audit log
        create_log(
            db,
            action="EXTERNAL_LOAN_PAYMENT",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Payment of UGX {amount:,.2f} recorded for external loan #{loan.id} ({loan.borrower_name}). {payment_message}",
            ip_address=request.client.host if request.client else None
        )
        
        referer = request.headers.get("referer", "/sacco/loans")
        return RedirectResponse(url=referer, status_code=303)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error recording payment: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to record payment: {str(e)}")