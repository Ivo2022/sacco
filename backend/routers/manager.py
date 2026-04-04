from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, desc
from ..core import get_db, require_manager, get_template_context
from ..schemas import RoleEnum
from ..services import get_sacco_statistics
from ..utils.helpers import get_template_helpers, check_sacco_status
from ..services.user_service import create_user
from ..models import Loan, PendingDeposit, User, Log, Saving, LoanPayment, Sacco, LoanPayment
import logging
from ..utils import create_log, get_recent_activities, log_user_action, get_logs_for_user, get_logs_count
from datetime import datetime, timedelta, timezone
from typing import Optional

router = APIRouter()
logger = logging.getLogger(__name__)

# Helper serializers
def serialize_loan(loan: Loan) -> dict:
    """Serialize loan ORM object to dictionary with user info."""
    return {
        "id": loan.id,
        "amount": loan.amount,
        "term": loan.term,
        "status": loan.status,
        "timestamp": loan.timestamp.isoformat() if loan.timestamp else None,
        "purpose": loan.purpose,
        "interest_rate": loan.interest_rate,
        "total_payable": loan.total_payable,
        "total_paid": loan.total_paid,
        "total_interest": loan.total_interest,
        "approved_by": loan.approved_by,
        "approved_at": loan.approved_at.isoformat() if loan.approved_at else None,
        "approval_notes": loan.approval_notes,
        "user_id": loan.user_id,
        "sacco_id": loan.sacco_id,
        # Add user information
        "user": {
            "id": loan.user.id if loan.user else None,
            "full_name": loan.user.full_name if loan.user else None,
            "email": loan.user.email if loan.user else None,
            #"member_number": loan.user.member_number if loan.user else None
        } if loan.user else None
    }

def serialize_loan(loan: Loan) -> dict:
    """Serialize loan ORM object to dictionary with calculated fields."""
    
    # Calculate monthly payment
    def calculate_monthly_payment(amount, interest_rate, duration_months):
        if duration_months and duration_months > 0:
            monthly_rate = (interest_rate / 100) / 12
            if monthly_rate > 0:
                payment = amount * (monthly_rate * (1 + monthly_rate) ** duration_months) / ((1 + monthly_rate) ** duration_months - 1)
                return round(payment, 2)
            else:
                return round(amount / duration_months, 2)
        return amount
    return {
        "id": loan.id,
        "amount": loan.amount,
        "term": loan.term,
        "status": loan.status,
        "timestamp": loan.timestamp.isoformat() if loan.timestamp else None,
        "purpose": loan.purpose,
        "interest_rate": loan.interest_rate,
        "total_payable": loan.total_payable,
        "total_paid": loan.total_paid,
        "total_interest": loan.total_interest,
        "approved_by": loan.approved_by,
        "approved_at": loan.approved_at.isoformat() if loan.approved_at else None,
        "approval_notes": loan.approval_notes,
        "user_id": loan.user_id,
        "sacco_id": loan.sacco_id,
        "calculate_monthly_payment": calculate_monthly_payment(
            float(loan.amount) if loan.amount else 0,
            float(loan.interest_rate) if loan.interest_rate else 0,
            loan.term or 0
        ),
        # Add user information
        "user": {
            "id": loan.user.id if loan.user else None,
            "full_name": loan.user.full_name if loan.user else None,
            "email": loan.user.email if loan.user else None,
            #"member_number": loan.user.member_number if loan.user else None
        } if loan.user else None
    }

def serialize_pending_deposit(deposit: PendingDeposit) -> dict:
    return {
        "id": deposit.id,
        "amount": deposit.amount,
        "payment_method": deposit.payment_method,
        "description": deposit.description,
        "reference_number": deposit.reference_number,
        "status": deposit.status,
        "timestamp": deposit.timestamp.isoformat() if deposit.timestamp else None,
        "user_id": deposit.user_id,
        "sacco_id": deposit.sacco_id,
        "member_name": deposit.user.full_name if deposit.user else None,
        "member_email": deposit.user.email if deposit.user else None,
    }

def serialize_log(log: Log) -> dict:
    return {
        "id": log.id,
        "action": log.action,
        "details": log.details,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "ip_address": log.ip_address,
        "user_id": log.user_id,
        "sacco_id": log.sacco_id,
        "user_email": log.user.email if log.user else None,
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

def serialize_saving(saving: Saving) -> dict:
    return {
        "id": saving.id,
        "amount": saving.amount,
        "type": saving.type,
        "payment_method": saving.payment_method.value if hasattr(saving.payment_method, 'value') else str(saving.payment_method),
        "description": saving.description,
        "reference_number": saving.reference_number,
        "timestamp": saving.timestamp.isoformat() if saving.timestamp else None,
        "user_id": saving.user_id,
        "sacco_id": saving.sacco_id,
        "approved_by": saving.approved_by,
        "approved_at": saving.approved_at.isoformat() if saving.approved_at else None,
    }

def serialize_loan_payment(payment: LoanPayment) -> dict:
    return {
        "id": payment.id,
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "timestamp": payment.timestamp.isoformat() if payment.timestamp else None,
        "loan_id": payment.loan_id,
        "user_id": payment.user_id,
        "sacco_id": payment.sacco_id,
    }


@router.head("/manager/dashboard", response_class=HTMLResponse)
@router.get("/manager/dashboard", response_class=HTMLResponse)
def manager_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    # 1. SACCO status check (unchanged)
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)

    # 3. Your existing business logic (all counts, queries, etc.)
    templates = request.app.state.templates
    sacco_id = user.sacco_id

    # ========== LOAN METRICS ==========
    # Counts by status
    pending_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id, Loan.status == "pending"
    ).count()
    approved_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id, Loan.status == "approved"
    ).count()
    active_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id, Loan.status == "active"
    ).count()
    completed_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id, Loan.status == "completed"
    ).count()
    overdue_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id, Loan.status == "overdue"
    ).count()
    rejected_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id, Loan.status == "rejected"
    ).count()

    # Total Interest Earned (from completed loans only - interest is earned when loan is completed)
    total_interest_earned = db.query(func.coalesce(func.sum(Loan.total_interest), 0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'completed'
    ).scalar() or 0

    # Total Payments Received (from all loan payments)
    total_payments_received = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.sacco_id == sacco_id
    ).scalar() or 0

    # Average Interest Rate
    avg_interest_rate = db.query(func.avg(Loan.interest_rate)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(['active', 'approved', 'pending'])
    ).scalar() or 0

    # Total Disbursed Amount (all approved/active/completed loans)
    total_disbursed = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(['active', 'completed', 'approved'])
    ).scalar() or 0

    # Get all active and overdue loans (those with outstanding balance)
    outstanding_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(['active', 'overdue'])
    ).all()

    total_outstanding = 0
    for loan in outstanding_loans:
        # Get total payments made
        total_paid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
    
        # Calculate outstanding balance using pre-calculated total_payable
        # (total_payable = principal + interest already calculated)
        outstanding = max(0.0, loan.total_payable - total_paid)
        total_outstanding += outstanding

    # ========== MEMBER METRICS ==========
    pending_members_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False,
        User.is_active == False
    ).count()

    # ========== DEPOSIT METRICS ==========
    pending_deposits_count = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == sacco_id,
        PendingDeposit.status == "pending"
    ).count()

    pending_notifications = pending_loans_count + pending_deposits_count + pending_members_count

    # ========== RECENT ITEMS ==========
    recent_pending_loans_orm = db.query(Loan).filter(
        Loan.sacco_id == sacco_id, Loan.status == "pending"
    ).order_by(Loan.timestamp.desc()).limit(5).all()
    recent_pending_loans = [serialize_loan(l) for l in recent_pending_loans_orm]

    recent_pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).limit(5).all()
    recent_pending_deposits = [serialize_pending_deposit(d) for d in recent_pending_deposits_orm]

    # ========== STAFF COUNTS ==========
    staff_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).count()
    accountant_count = db.query(User).filter(
        User.sacco_id == sacco_id, User.role == RoleEnum.ACCOUNTANT
    ).count()
    credit_officer_count = db.query(User).filter(
        User.sacco_id == sacco_id, User.role == RoleEnum.CREDIT_OFFICER
    ).count()

    # ========== MEMBER COUNTS ==========
    member_count = db.query(User).filter(
        User.sacco_id == sacco_id, User.role == RoleEnum.MEMBER
    ).count()
    active_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_active == True
    ).count()
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_members_this_month = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.created_at >= month_start
    ).count()

    # ========== FINANCIAL TOTALS ==========
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id
    ).scalar() or 0
    total_loan_amount = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0

    # ========== 30-DAY TRANSACTION TOTALS ==========
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    transactions_30d_orm = db.query(Saving).filter(
        Saving.sacco_id == sacco_id,
        Saving.timestamp >= thirty_days_ago
    ).all()
    total_deposits_30d = sum(t.amount for t in transactions_30d_orm if t.type == "deposit")
    total_withdrawals_30d = sum(t.amount for t in transactions_30d_orm if t.type == "withdrawal")
    transaction_count_30d = len(transactions_30d_orm)

    # ========== LOAN PERFORMANCE METRICS ==========
    # Calculate repayment rate
    if total_disbursed > 0:
        repayment_rate = (total_payments_received / total_disbursed) * 100
    else:
        repayment_rate = 0
    """
    # Calculate portfolio at risk (overdue loans percentage)
    total_active_portfolio = total_disbursed - completed_loans_count_amount
    if total_active_portfolio > 0:
        portfolio_at_risk = (overdue_loans_count_amount / total_active_portfolio) * 100
    else:
        portfolio_at_risk = 0
    """
    # Get recent activities (if you have a Log model)
    # from models import Log
    recent_activities_orm = db.query(Log).filter(
        Log.sacco_id == sacco_id
    ).order_by(Log.timestamp.desc()).limit(10).all()
    recent_activities = [serialize_log(l) for l in recent_activities_orm] if recent_activities_orm else []

    stats = get_sacco_statistics(db, sacco_id)
    helpers = get_template_helpers()

    # 4. Page‑specific context dictionary with NEW KPIs
    page_context = {
        # User info
        "user": user_dict,
        
        # Notification counts
        "pending_notifications": pending_notifications,
        
        # Loan counts (existing)
        "pending_loans": pending_loans_count,
        "pending_deposits": pending_deposits_count,
        "approved_loans": approved_loans_count,
        "completed_loans": completed_loans_count,
        "overdue_loans": overdue_loans_count,
        "overdue_loans_count": overdue_loans_count,
        "active_loans_count": active_loans_count,
        "rejected_loans_count": rejected_loans_count,
        
        # NEW LOAN KPI METRICS
        "total_interest_earned": total_interest_earned,
        "total_payments_received": total_payments_received,
        "avg_interest_rate": round(avg_interest_rate, 2),
        "total_disbursed": total_disbursed,
        "total_outstanding": total_outstanding,
        
        # Loan performance metrics
        "repayment_rate": round(repayment_rate, 2),
        # "portfolio_at_risk": round(portfolio_at_risk, 2),
        
        # Financial totals
        "total_savings": total_savings,
        "total_loan_amount": total_loan_amount,
        
        # Member metrics
        "member_count": member_count,
        "active_members": active_members,
        "new_members_this_month": new_members_this_month,
        "pending_members_count": pending_members_count,
        
        # Staff metrics
        "staff_count": staff_count,
        "accountant_count": accountant_count,
        "credit_officer_count": credit_officer_count,
        
        # Recent items
        "recent_pending_loans": recent_pending_loans,
        "recent_pending_deposits": recent_pending_deposits,
        "recent_activities": recent_activities,
        
        # 30-day transaction metrics
        "total_deposits_30d": total_deposits_30d,
        "total_withdrawals_30d": total_withdrawals_30d,
        "transaction_count_30d": transaction_count_30d,
        
        # Additional stats and helpers
        **stats,
        **helpers,
    }

    # 5. Merge base context (RBAC) with page context
    final_context = {**base_context, **page_context}

    # 6. Render template with merged context
    return templates.TemplateResponse(request, "manager/dashboard.html", final_context)

@router.get("/manager/pending-members")
def pending_members(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
	
    templates = request.app.state.templates
    pending_members_orm = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False,
        User.is_active == False
    ).order_by(User.created_at.desc()).all()

    pending_members = [serialize_user_basic(m) for m in pending_members_orm]

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "pending_members": pending_members,
        "pending_count": len(pending_members),
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/pending_members.html", final_context)


@router.post("/manager/member/{member_id}/approve")
def approve_member(
    request: Request,
    member_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    member = db.query(User).filter(
        User.id == member_id,
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found or already approved")

    member.is_approved = True
    member.is_active = True
    member.approved_at = datetime.utcnow()
    member.approved_by = user.id
    db.commit()

    log_user_action(
        db=db,
        user=user,
        action="MEMBER_APPROVED",
        details=f"Member {member.email} approved by {user.email}",
        ip_address=request.client.host
    )

    request.session["flash_message"] = f"✓ Member {member.full_name or member.email} approved successfully!"
    request.session["flash_type"] = "success"

    return RedirectResponse(url="/manager/pending-members", status_code=303)


@router.post("/manager/member/{member_id}/reject")
def reject_member(
    request: Request,
    member_id: int,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    member = db.query(User).filter(
        User.id == member_id,
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False
    ).first()

    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    member.is_active = False
    member.rejection_reason = reason
    member.approved_at = datetime.utcnow()
    member.approved_by = user.id
    db.commit()

    create_log(
        db,
        "MEMBER_REJECTED",
        user.id,
        user.sacco_id,
        f"Member {member.email} rejected by {user.email}. Reason: {reason}"
    )

    request.session["flash_message"] = f"✓ Member {member.full_name or member.email} rejected."
    request.session["flash_type"] = "warning"

    return RedirectResponse(url="/manager/pending-members", status_code=303)


@router.get("/manager/loan/{loan_id}/review")
def review_loan(
    request: Request,
    loan_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    loan_orm = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.sacco_id == user.sacco_id
    ).first()

    if not loan_orm:
        raise HTTPException(status_code=404, detail="Loan not found")

    member_orm = db.query(User).filter(User.id == loan_orm.user_id).first()
    loan = serialize_loan(loan_orm)
    member = serialize_user_basic(member_orm) if member_orm else None

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "loan": loan,
        "member": member,
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/loan_review.html", final_context)


@router.post("/manager/loan/{loan_id}/approve")
def approve_loan(
    request: Request,
    loan_id: int,
    approval_notes: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    loan = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.sacco_id == user.sacco_id
    ).first()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    if loan.status != "pending":
        raise HTTPException(status_code=400, detail="Loan already processed")

    loan.status = "approved"
    loan.approved_by = user.id
    loan.approved_at = datetime.now(timezone.utc)
    loan.approval_notes = approval_notes
    db.commit()

    create_log(
        db,
        "LOAN_APPROVED",
        user.id,
        user.sacco_id,
        f"Loan {loan.id} for UGX {loan.amount:,.2f} approved by manager {user.email}"
    )

    request.session["flash_message"] = f"✓ Loan #{loan_id} approved successfully!"
    request.session["flash_type"] = "success"

    return RedirectResponse(url="/manager/loans/pending", status_code=303)


@router.post("/manager/loan/{loan_id}/reject")
def reject_loan(
    request: Request,
    loan_id: int,
    rejection_reason: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    loan = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.sacco_id == user.sacco_id
    ).first()

    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    if loan.status != "pending":
        raise HTTPException(status_code=400, detail="Loan already processed")

    loan.status = "rejected"
    loan.approved_by = user.id
    loan.approved_at = datetime.now(timezone.utc)
    loan.approval_notes = rejection_reason
    db.commit()

    create_log(
        db,
        "LOAN_REJECTED",
        user.id,
        user.sacco_id,
        f"Loan {loan.id} rejected by manager {user.email}. Reason: {rejection_reason}"
    )

    request.session["flash_message"] = f"✓ Loan #{loan_id} rejected."
    request.session["flash_type"] = "warning"

    return RedirectResponse(url="/manager/loans/pending", status_code=303)


@router.get("/manager/loans/pending")
def pending_loans(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    loans_orm = db.query(Loan).filter(
        Loan.sacco_id == user.sacco_id,
        Loan.status == "pending"
    ).order_by(Loan.timestamp.desc()).all()

    loans = [serialize_loan(l) for l in loans_orm]
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "loans": loans,
        "pending_count": len(loans),
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/pending_loans.html", final_context)


@router.get("/manager/staff")
def manage_staff(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    staff_orm = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).all()

    staff = [serialize_user_basic(s) for s in staff_orm]
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "staff": staff,
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/staff.html", final_context)


@router.post("/manager/staff/create")
def create_staff(
    request: Request,
    role: str = Form(...),  # "ACCOUNTANT" or "CREDIT_OFFICER"
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    user: "User" = Depends(require_manager),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    try:
        if role not in ["ACCOUNTANT", "CREDIT_OFFICER"]:
            raise HTTPException(status_code=400, detail="Invalid role")

        role_enum = RoleEnum.ACCOUNTANT if role == "ACCOUNTANT" else RoleEnum.CREDIT_OFFICER

        existing = db.query(User).filter(User.email == email).first()
        if existing:
            request.session["flash_message"] = f"✗ Email {email} already exists"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/manager/staff", status_code=303)

        username = full_name.lower().replace(' ', '.')
        username = ''.join(c for c in username if c.isalnum() or c == '.')
        base_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1

        staff = create_user(
            db,
            email=email,
            password=password,
            role=role_enum,
            sacco_id=user.sacco_id,
            full_name=full_name,
            username=username,
            is_staff=True,
            can_apply_for_loans=False,
            can_receive_dividends=False
        )

        member_email = f"{email.split('@')[0]}_member@{email.split('@')[1]}"
        member_username = f"{username}_member"
        member = create_user(
            db,
            email=member_email,
            password=password,
            role=RoleEnum.MEMBER,
            sacco_id=user.sacco_id,
            full_name=f"{full_name} (Member Account)",
            username=member_username,
            is_staff=True,
            can_apply_for_loans=True,
            can_receive_dividends=True,
            requires_approval_for_loans=True
        )

        staff.linked_member_account_id = member.id
        member.linked_admin_id = staff.id
        db.commit()

        request.session["flash_message"] = (
            f"✓ {role.replace('_', ' ').title()} created successfully!\n"
            f"Login: {email}\n"
            f"Member login: {member_email}\n"
            f"Password: {password}"
        )
        request.session["flash_type"] = "success"

        create_log(
            db,
            f"{role}_CREATED",
            user.id,
            user.sacco_id,
            f"{role} {email} created by manager {user.email}"
        )

        return RedirectResponse(url="/manager/staff", status_code=303)

    except Exception as e:
        logger.error(f"Error creating staff: {e}")
        request.session["flash_message"] = f"✗ Error: {str(e)}"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/manager/staff", status_code=303)


@router.get("/manager/reports")
def reports(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    sacco_id = user.sacco_id

    active_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "approved"
    ).count()

    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id
    ).scalar() or 0

    member_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    ).count()

    staff_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).count()

    total_loan_amount = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0

    pending_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "pending"
    ).count()

    overdue_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "overdue"
    ).count()

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "active_loans_count": active_loans_count,
        "total_savings": total_savings,
        "member_count": member_count,
        "staff_count": staff_count,
        "total_loan_amount": total_loan_amount,
        "pending_loans": pending_loans,
        "overdue_loans": overdue_loans,
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/reports.html", final_context)


@router.get("/manager/members")
def manage_members(
    request: Request,
    search: str = Query(None),
    status: str = Query(None),
    has_loans: str = Query(None),
    sort: str = Query("newest"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    sacco_id = user.sacco_id

    query = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    )

    if search:
        query = query.filter(
            or_(
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.phone.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%")
            )
        )

    if status == "active":
        query = query.filter(User.is_active == True)
    elif status == "inactive":
        query = query.filter(User.is_active == False)

    if sort == "newest":
        query = query.order_by(User.created_at.desc())
    elif sort == "oldest":
        query = query.order_by(User.created_at.asc())
    elif sort == "name_asc":
        query = query.order_by(User.full_name.asc())
    elif sort == "name_desc":
        query = query.order_by(User.full_name.desc())

    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    members_orm = query.offset(offset).limit(per_page).all()

    members = []
    for m in members_orm:
        total_deposits = db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == m.id,
            Saving.type == "deposit"
        ).scalar() or 0
        total_withdrawals = db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == m.id,
            Saving.type == "withdrawal"
        ).scalar() or 0
        savings_balance = total_deposits - total_withdrawals

        active_loans = db.query(Loan).filter(
            Loan.user_id == m.id,
            Loan.status == "approved"
        ).count()

        member_dict = serialize_user_basic(m)
        member_dict["savings_balance"] = savings_balance
        member_dict["active_loans"] = active_loans
        members.append(member_dict)

    if has_loans == "yes":
        members = [m for m in members if m["active_loans"] > 0]
        total = len(members)
    elif has_loans == "no":
        members = [m for m in members if m["active_loans"] == 0]
        total = len(members)

    if sort == "savings_desc":
        members = sorted(members, key=lambda x: x["savings_balance"], reverse=True)

    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id
    ).scalar() or 0

    total_active_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "approved"
    ).count()

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.created_at >= month_start
    ).count()

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "members": members,
        "member_count": total,
        "total_savings": total_savings,
        "total_active_loans": total_active_loans,
        "new_members": new_members,
        "search_query": search,
        "status": status,
        "has_loans": has_loans,
        "sort": sort,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/members.html", final_context)


@router.get("/manager/member/{member_id}")
def view_member_detail(
    request: Request,
    member_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    member_orm = db.query(User).filter(
        User.id == member_id,
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER
    ).first()

    if not member_orm:
        raise HTTPException(status_code=404, detail="Member not found")

    member = serialize_user_full(member_orm)

    savings_orm = db.query(Saving).filter(
        Saving.user_id == member_id
    ).order_by(Saving.timestamp.desc()).all()
    savings = [serialize_saving(s) for s in savings_orm]

    loans_orm = db.query(Loan).filter(
        Loan.user_id == member_id
    ).order_by(Loan.timestamp.desc()).all()
    loans = [serialize_loan(l) for l in loans_orm]

    total_deposits = sum(s["amount"] for s in savings if s["type"] == "deposit")
    total_withdrawals = sum(s["amount"] for s in savings if s["type"] == "withdrawal")
    savings_balance = total_deposits - total_withdrawals

    active_loans = [l for l in loans if l["status"] == "approved"]
    total_loan_amount = sum(l["amount"] for l in loans)
    total_paid = 0
    for l in loans_orm:
        paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == l.id
        ).scalar() or 0
        total_paid += paid

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "member": member,
        "savings": savings,
        "loans": loans,
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "savings_balance": savings_balance,
        "total_loan_amount": total_loan_amount,
        "total_paid": total_paid,
        "active_loans_count": len(active_loans),
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/member_detail.html", final_context)


from datetime import datetime, timedelta
from sqlalchemy import func

@router.get("/manager/staff-activity")
def staff_activity(
    request: Request,
    role: str = Query(None),
    staff_id: Optional[int] = None,
    action_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page: int = 1,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Get RBAC context
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    sacco_id = user.sacco_id
    
    # Get staff list for filter dropdown
    staff_list = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER, RoleEnum.MANAGER])
    ).all()
    
    # Build activity query
    query = db.query(Log).filter(Log.sacco_id == sacco_id)
    
    # Apply filters
    if staff_id:
        query = query.filter(Log.user_id == staff_id)
    if role:
        # Convert role string to RoleEnum
        role_enum = RoleEnum(role.upper())
        # Get users with that role
        user_ids = db.query(User.id).filter(
            User.sacco_id == sacco_id,
            User.role == role_enum
        ).all()
        user_ids = [u[0] for u in user_ids]
        if user_ids:
            query = query.filter(Log.user_id.in_(user_ids))
    if action_type:
        query = query.filter(Log.action.ilike(f'%{action_type}%'))
    if date_from:
        query = query.filter(Log.timestamp >= datetime.strptime(date_from, '%Y-%m-%d'))
    if date_to:
        query = query.filter(Log.timestamp <= datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
    
    # Get total count for pagination
    per_page = 50
    total_activities = query.count()
    total_pages = (total_activities + per_page - 1) // per_page
    
    # Get paginated activities
    activities_orm = query.order_by(Log.timestamp.desc()).offset((page - 1) * per_page).limit(per_page).all()
    activities = [serialize_log(a) for a in activities_orm]
    
    # Get staff activities for the card view (your existing logic)
    staff_query = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    )
    if role:
        staff_query = staff_query.filter(User.role == RoleEnum(role))
    staff_members_orm = staff_query.all()
    
    staff_activities = []
    for staff_orm in staff_members_orm:
        activities_orm = db.query(Log).filter(
            Log.user_id == staff_orm.id,
            Log.sacco_id == sacco_id
        ).order_by(Log.timestamp.desc()).limit(10).all()
        staff_acts = [serialize_log(a) for a in activities_orm]
        
        action_counts = {
            "approvals": len([a for a in staff_acts if "APPROVED" in a.get("action", "")]),
            "rejections": len([a for a in staff_acts if "REJECTED" in a.get("action", "")]),
            "creations": len([a for a in staff_acts if "CREATED" in a.get("action", "")]),
            "reminders": len([a for a in staff_acts if "REMINDER" in a.get("action", "")])
        }
        
        staff_activities.append({
            "staff": serialize_user_basic(staff_orm),
            "recent_activities": staff_acts[:5],
            "action_counts": action_counts,
            "total_actions": len(staff_acts)
        })
    
    # Calculate statistics
    today = datetime.utcnow().date()
    today_activities = db.query(Log).filter(
        Log.sacco_id == sacco_id,
        func.date(Log.timestamp) == today
    ).count()
    
    active_staff_today = db.query(Log.user_id).filter(
        Log.sacco_id == sacco_id,
        func.date(Log.timestamp) == today
    ).distinct().count()
    
    # Most active staff
    most_active_result = db.query(
        Log.user_id,
        User.full_name,
        func.count(Log.id).label('count')
    ).join(User, User.id == Log.user_id).filter(
        Log.sacco_id == sacco_id
    ).group_by(Log.user_id).order_by(func.count(Log.id).desc()).first()
    
    most_active_staff = {
        "name": most_active_result.full_name if most_active_result else None,
        "count": most_active_result.count if most_active_result else 0
    } if most_active_result else {"name": None, "count": 0}
    
    # Get all staff for the filter dropdown
    all_staff = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER, RoleEnum.MANAGER])
    ).all()
    
    helpers = get_template_helpers()
    
    page_context = {
        "staff_activities": staff_activities,
        "selected_role": role,
        "activities": activities,  # For the table view
        "staff_list": all_staff,
        "total_activities": total_activities,
        "today_activities": today_activities,
        "active_staff_today": active_staff_today,
        "most_active_staff": most_active_staff,
        "selected_staff_id": staff_id,
        "action_type": action_type,
        "date_from": date_from,
        "date_to": date_to,
        "current_page": page,
        "total_pages": total_pages,
        **helpers,
    }
    
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request, "manager/staff_activity.html", final_context)

@router.get("/manager/pending/all")
async def all_pending_approvals(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """View all pending approvals (deposits, members, loans) in one page"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    sacco_id = user.sacco_id
    
    # Get pending deposits
    pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    
    pending_deposits_list = []  # Use different variable name
    for deposit in pending_deposits_orm:
        member = db.query(User).filter(User.id == deposit.user_id).first()
        pending_deposits_list.append({
            "id": deposit.id,
            "amount": deposit.amount,
            "payment_method": deposit.payment_method,
            "description": deposit.description,
            "reference_number": deposit.reference_number,
            "timestamp": deposit.timestamp,
            "member_name": member.full_name if member else "Unknown",
            "member_email": member.email if member else "Unknown",
            "member_phone": member.phone if member else "Unknown"
        })
    
    # Get pending member approvals
    pending_members_orm = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False,
        User.is_active == False
    ).order_by(User.created_at.desc()).all()
    
    pending_members_list = []  # Use different variable name
    for member in pending_members_orm:
        pending_members_list.append({
            "id": member.id,
            "email": member.email,
            "full_name": member.full_name,
            "username": member.username,
            "phone": member.phone,
            "created_at": member.created_at,
            "member_referral_code": getattr(member, 'member_referral_code', None)
        })
    
    # Get pending loans
    pending_loans_orm = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "pending"
    ).order_by(Loan.timestamp.desc()).all()
    
    pending_loans_list = []  # Use different variable name
    for loan in pending_loans_orm:
        member = db.query(User).filter(User.id == loan.user_id).first()
        pending_loans_list.append({
            "id": loan.id,
            "amount": loan.amount,
            "term": loan.term,
            "purpose": loan.purpose,
            "timestamp": loan.timestamp,
            "interest_rate": loan.interest_rate,
            "member_name": member.full_name if member else "Unknown",
            "member_email": member.email if member else "Unknown",
            "member_phone": member.phone if member else "Unknown",
            "monthly_payment": loan.calculate_monthly_payment(),
            "total_payable": loan.total_payable
        })
    
    # Calculate totals
    total_deposits_amount = sum(d["amount"] for d in pending_deposits_list)
    total_loans_amount = sum(l["amount"] for l in pending_loans_list)
    
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "pending_deposits": pending_deposits_list,  # Now this is a list
        "pending_deposits_count": len(pending_deposits_list),
        "total_deposits_amount": total_deposits_amount,
        "pending_members": pending_members_list,  # Now this is a list
        "pending_members_count": len(pending_members_list),
        "pending_loans": pending_loans_list,  # Now this is a list
        "pending_loans_count": len(pending_loans_list),
        "total_loans_amount": total_loans_amount,
        **helpers
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request, "manager/all_pending.html", final_context)

@router.get("/manager/deposits/pending")
async def manager_pending_deposits(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    # View all pending deposits (Manager view)
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    
    # Get pending deposits for the manager's SACCO
    pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    
    # Serialize deposits with member info
    pending_deposits = []
    for deposit in pending_deposits_orm:
        member = db.query(User).filter(User.id == deposit.user_id).first()
        pending_deposits.append({
            "id": deposit.id,
            "amount": deposit.amount,
            "payment_method": deposit.payment_method,
            "description": deposit.description,
            "reference_number": deposit.reference_number,
            "timestamp": deposit.timestamp,
            "member_name": member.full_name if member else "Unknown",
            "member_email": member.email if member else "Unknown",
            "member_phone": member.phone if member else "Unknown"
        })
    
    # Calculate totals
    total_pending = sum(d["amount"] for d in pending_deposits)
    
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "pending_deposits": pending_deposits,
        "pending_count": len(pending_deposits),
        "total_pending": total_pending,
        **helpers
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request, "manager/pending_deposits.html", final_context)


@router.post("/manager/deposit/{deposit_id}/approve")
async def manager_approve_deposit(
    deposit_id: int,
    request: Request,
    notes: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    # Approve a pending deposit (Manager view)
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    pending = db.query(PendingDeposit).filter(
        PendingDeposit.id == deposit_id,
        PendingDeposit.sacco_id == user.sacco_id
    ).first()
    
    if not pending:
        raise HTTPException(status_code=404, detail="Deposit not found")
    
    if pending.status != "pending":
        raise HTTPException(status_code=400, detail="Deposit already processed")
    
    # Create savings record
    saving = Saving(
        sacco_id=pending.sacco_id,
        user_id=pending.user_id,
        type="deposit",
        amount=pending.amount,
        payment_method=pending.payment_method,
        description=pending.description,
        reference_number=pending.reference_number,
        approved_by=user.id,
        approved_at=datetime.utcnow(),
        pending_deposit_id=pending.id
    )
    db.add(saving)
    
    # Update pending deposit
    pending.status = "approved"
    pending.approved_by = user.id
    pending.approved_at = datetime.utcnow()
    pending.approval_notes = notes
    
    db.commit()
    
    # Create log entry
    member = db.query(User).filter(User.id == pending.user_id).first()
    create_log(
        db,
        "DEPOSIT_APPROVED_BY_MANAGER",
        user.id,
        user.sacco_id,
        f"Deposit of UGX {pending.amount:,.2f} approved for {member.email} by Manager {user.email}"
    )
    
    request.session["flash_message"] = f"✓ Deposit of UGX {pending.amount:,.2f} approved successfully!"
    request.session["flash_type"] = "success"
    
    return RedirectResponse(url="/manager/deposits/pending", status_code=303)


@router.post("/manager/deposit/{deposit_id}/reject")
async def manager_reject_deposit(
    deposit_id: int,
    request: Request,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    # Reject a pending deposit (Manager view)
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    pending = db.query(PendingDeposit).filter(
        PendingDeposit.id == deposit_id,
        PendingDeposit.sacco_id == user.sacco_id
    ).first()
    
    if not pending:
        raise HTTPException(status_code=404, detail="Deposit not found")
    
    if pending.status != "pending":
        raise HTTPException(status_code=400, detail="Deposit already processed")
    
    # Update pending deposit
    pending.status = "rejected"
    pending.approved_by = user.id
    pending.approved_at = datetime.utcnow()
    pending.rejection_reason = reason
    
    db.commit()
    
    # Create log entry
    member = db.query(User).filter(User.id == pending.user_id).first()
    create_log(
        db,
        "DEPOSIT_REJECTED_BY_MANAGER",
        user.id,
        user.sacco_id,
        f"Deposit of UGX {pending.amount:,.2f} rejected for {member.email} by Manager {user.email}. Reason: {reason}"
    )
    
    request.session["flash_message"] = f"✓ Deposit of UGX {pending.amount:,.2f} rejected."
    request.session["flash_type"] = "warning"
    
    return RedirectResponse(url="/manager/deposits/pending", status_code=303)

@router.get("/manager/accountant-dashboard")
def view_accountant_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    pending_deposits_act = [serialize_pending_deposit(d) for d in pending_deposits_orm]

    recent_transactions_orm = db.query(Saving).filter(
        Saving.sacco_id == user.sacco_id
    ).order_by(Saving.timestamp.desc()).limit(20).all()
    recent_transactions = [serialize_saving(t) for t in recent_transactions_orm]

    # Add member info to transactions
    for tx in recent_transactions:
        member_orm = db.query(User).filter(User.id == tx["user_id"]).first()
        tx["member"] = serialize_user_basic(member_orm) if member_orm else None

    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id
    ).scalar() or 0

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_collections = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= today_start,
        Saving.type == "deposit"
    ).scalar() or 0

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "pending_deposits": pending_deposits_act,
        "recent_transactions": recent_transactions,
        "total_savings": total_savings,
        "today_collections": today_collections,
        "pending_count": len(pending_deposits_act),
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/accountant_view.html", final_context)


@router.get("/manager/credit-officer-dashboard")
def view_credit_officer_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    active_loans_orm = db.query(Loan).filter(
        Loan.sacco_id == user.sacco_id,
        Loan.status == "approved"
    ).all()

    active_loans = []
    for loan in active_loans_orm:
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        outstanding = loan.total_payable - total_paid
        member_orm = db.query(User).filter(User.id == loan.user_id).first()
        member = serialize_user_basic(member_orm) if member_orm else None

        last_payment_orm = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()

        days_since_last_payment = 0
        if last_payment_orm:
            days_since_last_payment = (datetime.utcnow() - last_payment_orm.timestamp).days
        else:
            days_since_last_payment = (datetime.utcnow() - loan.approved_at).days if loan.approved_at else 0

        is_overdue = days_since_last_payment > 30

        loan_dict = serialize_loan(loan)
        loan_dict.update({
            "outstanding": outstanding,
            "member": member,
            "days_since_last_payment": days_since_last_payment,
            "is_overdue": is_overdue,
        })
        active_loans.append(loan_dict)

    overdue_loans = [l for l in active_loans if l["is_overdue"]]

    reminders_orm = db.query(Log).filter(
        Log.sacco_id == user.sacco_id,
        Log.action == "LOAN_REMINDER_SENT"
    ).order_by(Log.timestamp.desc()).limit(20).all()
    reminders = [serialize_log(r) for r in reminders_orm]

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": serialize_user_full(user),
        "active_loans": active_loans,
        "overdue_loans": overdue_loans,
        "reminders": reminders,
        "active_count": len(active_loans),
        "overdue_count": len(overdue_loans),
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/credit_officer_view.html", final_context)


@router.get("/manager/all-transactions")
def all_transactions(
    request: Request,
    transaction_type: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    query = db.query(Saving).filter(Saving.sacco_id == user.sacco_id)

    if transaction_type:
        query = query.filter(Saving.type == transaction_type)

    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(Saving.timestamp >= start)

    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Saving.timestamp <= end)

    total = query.count()
    offset = (page - 1) * per_page
    transactions_orm = query.order_by(Saving.timestamp.desc()).offset(offset).limit(per_page).all()
    transactions = [serialize_saving(t) for t in transactions_orm]

    # Add member info
    for tx in transactions:
        member_orm = db.query(User).filter(User.id == tx["user_id"]).first()
        tx["member"] = serialize_user_basic(member_orm) if member_orm else None

    total_deposits = sum(t["amount"] for t in transactions if t["type"] == "deposit")
    total_withdrawals = sum(t["amount"] for t in transactions if t["type"] == "withdrawal")

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "transactions": transactions,
        "transaction_type": transaction_type,
        "start_date": start_date,
        "end_date": end_date,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page,
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/all_transactions.html", final_context)


@router.get("/manager/all-loans")
def all_loans(
    request: Request,
    status: str = Query(None),
    search: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    templates = request.app.state.templates
    sacco_id = user.sacco_id

    query = db.query(Loan).filter(Loan.sacco_id == sacco_id)
    if status:
        query = query.filter(Loan.status == status)

    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    loans_orm = query.order_by(Loan.timestamp.desc()).offset(offset).limit(per_page).all()

    loans = []
    for loan in loans_orm:
        member_orm = db.query(User).filter(User.id == loan.user_id).first()
        member = serialize_user_basic(member_orm) if member_orm else None

        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        outstanding = loan.total_payable - total_paid
        payment_percentage = (total_paid / loan.total_payable * 100) if loan.total_payable > 0 else 0
        monthly_payment = loan.calculate_monthly_payment()

        last_payment_orm = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()

        last_payment_date = last_payment_orm.timestamp if last_payment_orm else None
        days_since_last_payment = 0
        if last_payment_date:
            days_since_last_payment = (datetime.utcnow() - last_payment_date).days
        else:
            days_since_last_payment = (datetime.utcnow() - loan.approved_at).days if loan.approved_at else 0

        approver_orm = db.query(User).filter(User.id == loan.approved_by).first() if loan.approved_by else None
        approver = serialize_user_basic(approver_orm) if approver_orm else None

        loan_dict = serialize_loan(loan)
        loan_dict.update({
            "member": member,
            "total_paid": total_paid,
            "outstanding": outstanding,
            "payment_percentage": payment_percentage,
            "monthly_payment": monthly_payment,
            "last_payment_date": last_payment_date.isoformat() if last_payment_date else None,
            "days_since_last_payment": days_since_last_payment,
            "approver": approver,
        })
        loans.append(loan_dict)

    if search:
        search_lower = search.lower()
        loans = [l for l in loans if (l.get("member") and
                                      (search_lower in (l["member"].get("full_name") or "").lower() or
                                       search_lower in (l["member"].get("email") or "").lower()))]
        total = len(loans)

    status_counts = {
        "pending": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "pending").count(),
        "approved": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "approved").count(),
        "completed": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "completed").count(),
        "overdue": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "overdue").count(),
        "rejected": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "rejected").count(),
    }

    total_loan_amount = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0

    all_loans_for_outstanding = db.query(Loan).filter(Loan.sacco_id == sacco_id).all()
    total_outstanding = 0
    for loan in all_loans_for_outstanding:
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        total_outstanding += (loan.total_payable - total_paid)

    helpers = get_template_helpers()
    page_context = {
        "request": request,
        "user": user_dict,
        "loans": loans,
        "status": status,
        "search_query": search,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "status_counts": status_counts,
        "total_loan_amount": total_loan_amount,
        "total_outstanding": total_outstanding,
        **helpers,
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request,"manager/all_loans.html", final_context)
	
import logging
logger = logging.getLogger(__name__)

@router.get("/manager/logs")
async def view_logs(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_manager),
    page: int = 1,
    limit: int = 20,
    action_filter: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
):
    """View logs for manager's SACCO"""
    user_dict = serialize_user_full(user)

    # 2. Get base RBAC context (permissions, menu_config, current_path, now)
    base_context = get_template_context(request, user)
    # Debug logging
    logger.info(f"Manager {current_user.id} viewing logs")
    logger.info(f"Manager SACCO ID: {current_user.sacco_id}")
    logger.info(f"Manager Role: {current_user.role}")
    
    # Parse dates if provided
    from datetime import datetime
    date_from_obj = None
    date_to_obj = None
    
    if date_from:
        date_from_obj = datetime.strptime(date_from, "%Y-%m-%d")
        logger.info(f"Filtering from date: {date_from_obj}")
    if date_to:
        date_to_obj = datetime.strptime(date_to, "%Y-%m-%d")
        logger.info(f"Filtering to date: {date_to_obj}")
    
    # Get logs filtered for this manager
    offset = (page - 1) * limit
    logs = get_logs_for_user(
        db=db,
        user=current_user,
        limit=limit,
        offset=offset,
        action_filter=action_filter,
        date_from=date_from_obj,
        date_to=date_to_obj
    )
    
    total_count = get_logs_count(
        db=db,
        user=current_user,
        action_filter=action_filter,
        date_from=date_from_obj,
        date_to=date_to_obj
    )
    
    # Debug: Show what logs were found
    logger.info(f"Found {len(logs)} logs for manager (total: {total_count})")
    for log in logs[:5]:  # Log first 5 for debugging
        logger.debug(f"Log: {log.id} - {log.action} - SACCO: {log.sacco_id} - User: {log.user_id}")
    
    total_pages = (total_count + limit - 1) // limit
    
    # Get SACCO info
    sacco = db.query(Sacco).filter(Sacco.id == current_user.sacco_id).first()
    
    templates = request.app.state.templates
    helpers = get_template_helpers()
    page_context = {
        "request": request,
        #"user": current_user,
		"user": user_dict,
        "sacco": sacco,
        "logs": logs,
        "page": page,
        "total_pages": total_pages,
        "total_count": total_count,
        "action_filter": action_filter,
        "date_from": date_from,
        "date_to": date_to,
        "show_admin_controls": True,
        **helpers
    }
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request, "manager/logs.html", final_context)

# routers/manager.py
@router.get("/manager/insights/dashboard", response_class=HTMLResponse)
def manager_insights_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """Manager Insights Dashboard - SACCO-specific analytics."""
    
    # Get templates from request state
    templates = request.app.state.templates
    
    # Check SACCO status
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Serialize user
    user_dict = serialize_user_full(user)
    
    # Get RBAC context
    base_context = get_template_context(request, user_dict)
    
    sacco_id = user.sacco_id
    
    # ========== SACCO OVERVIEW ==========
    
    # Get SACCO details
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    
    # Member statistics
    total_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    ).count()
    
    active_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_active == True
    ).count()
    
    new_members_this_month = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.created_at >= datetime.utcnow().replace(day=1)
    ).count()
    
    # ========== LOAN METRICS ==========
    
    # Loan portfolio
    total_disbursed = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(['active', 'completed', 'approved'])
    ).scalar() or 0
    
    active_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'active'
    ).count()
    
    pending_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'pending'
    ).count()
    
    overdue_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'overdue'
    ).count()
    
    completed_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'completed'
    ).count()
    
    # Calculate interest earned
    total_interest_earned = db.query(func.sum(Loan.total_interest)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(['completed', 'active'])
    ).scalar() or 0
    
    # Total payments received
    total_payments_received = db.query(func.sum(LoanPayment.amount)).filter(
        LoanPayment.sacco_id == sacco_id
    ).scalar() or 0
    
    # Average interest rate
    avg_interest_rate = db.query(func.avg(Loan.interest_rate)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(['active', 'approved', 'pending'])
    ).scalar() or 0
    
    # Calculate repayment rate
    if total_disbursed > 0:
        repayment_rate = (total_payments_received / total_disbursed) * 100
    else:
        repayment_rate = 0
    
    # ========== SAVINGS METRICS ==========
    
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id
    ).scalar() or 0
    
    avg_savings_per_member = total_savings / total_members if total_members > 0 else 0
    
    # ========== STAFF METRICS ==========
    
    total_staff = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).count()
    
    # ========== RECENT ACTIVITIES ==========
    
    # Recent loan applications
    recent_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id
    ).order_by(desc(Loan.timestamp)).limit(10).all()
    
    # Recent member registrations
    recent_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    ).order_by(desc(User.created_at)).limit(10).all()
    
    # Recent transactions
    recent_transactions = db.query(Saving).filter(
        Saving.sacco_id == sacco_id
    ).order_by(desc(Saving.timestamp)).limit(10).all()
    
    # ========== CHART DATA ==========
    
    # Monthly loan disbursements (last 12 months)
    monthly_loan_data = []
    for i in range(11, -1, -1):
        month_date = datetime.utcnow().replace(day=1) - timedelta(days=30 * i)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_date.month == 12:
            next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
        else:
            next_month = month_date.replace(month=month_date.month + 1, day=1)
        
        monthly_amount = db.query(func.sum(Loan.amount)).filter(
            Loan.sacco_id == sacco_id,
            Loan.timestamp >= month_start,
            Loan.timestamp < next_month
        ).scalar() or 0
        
        monthly_loan_data.append({
            "month": month_date.strftime("%b %Y"),
            "amount": float(monthly_amount)
        })
    
    # Monthly member growth (last 12 months)
    monthly_member_data = []
    for i in range(11, -1, -1):
        month_date = datetime.utcnow().replace(day=1) - timedelta(days=30 * i)
        month_start = month_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_date.month == 12:
            next_month = month_date.replace(year=month_date.year + 1, month=1, day=1)
        else:
            next_month = month_date.replace(month=month_date.month + 1, day=1)
        
        monthly_count = db.query(User).filter(
            User.sacco_id == sacco_id,
            User.role == RoleEnum.MEMBER,
            User.created_at >= month_start,
            User.created_at < next_month
        ).count()
        
        monthly_member_data.append({
            "month": month_date.strftime("%b %Y"),
            "count": monthly_count
        })
    
    # Loan status distribution for pie chart
    loan_status_data = {
        "active": active_loans,
        "pending": pending_loans,
        "overdue": overdue_loans,
        "completed": completed_loans
    }
    
    page_context = {
        # SACCO info
        "sacco": sacco,
        "sacco_name": sacco.name if sacco else "N/A",
        
        # Member metrics
        "total_members": total_members,
        "active_members": active_members,
        "new_members_this_month": new_members_this_month,
        "member_growth_percent": round((new_members_this_month / total_members * 100) if total_members > 0 else 0, 1),
        
        # Loan metrics
        "total_disbursed": total_disbursed,
        "active_loans": active_loans,
        "pending_loans": pending_loans,
        "overdue_loans": overdue_loans,
        "completed_loans": completed_loans,
        "total_interest_earned": total_interest_earned,
        "total_payments_received": total_payments_received,
        "avg_interest_rate": round(avg_interest_rate, 2),
        "repayment_rate": round(repayment_rate, 1),
        
        # Savings metrics
        "total_savings": total_savings,
        "avg_savings_per_member": avg_savings_per_member,
        
        # Staff metrics
        "total_staff": total_staff,
        
        # Recent activities
        "recent_loans": recent_loans,
        "recent_members": recent_members,
        "recent_transactions": recent_transactions,
        
        # Chart data
        "monthly_loan_data": monthly_loan_data,
        "monthly_member_data": monthly_member_data,
        "loan_status_data": loan_status_data,
        
        "page_title": f"{sacco.name if sacco else 'SACCO'} Insights Dashboard"
    }
    
    final_context = {**base_context, **page_context}
    
    return templates.TemplateResponse(request, "manager/insights_dashboard.html", final_context)

# routers/manager.py

from backend.models.share import Share, ShareType, ShareTransaction, DividendDeclaration, DividendPayment

@router.get("/manager/shares/holdings", response_class=HTMLResponse)
def manager_share_holdings(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """View all share holdings in the SACCO"""
    
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    templates = request.app.state.templates
    sacco_id = user.sacco_id
    
    # Get all share holdings with member info
    holdings = db.query(Share).filter(
        Share.sacco_id == sacco_id,
        Share.is_active == True
    ).all()
    
    # Enrich holdings with member and share type data
    enriched_holdings = []
    total_shares_value = 0
    total_share_units = 0
    
    for holding in holdings:
        member = db.query(User).filter(User.id == holding.user_id).first()
        share_type = db.query(ShareType).filter(ShareType.id == holding.share_type_id).first()
        
        if member and share_type:
            enriched_holdings.append({
                "id": holding.id,
                "member": {
                    "id": member.id,
                    "full_name": member.full_name,
                    "email": member.email,
                    "member_number": getattr(member, 'member_number', 'N/A')
                },
                "share_type": {
                    "id": share_type.id,
                    "name": share_type.name,
                    "class_type": share_type.class_type,
                    "par_value": float(share_type.par_value),
                    "is_voting": share_type.is_voting,
                    "dividend_rate": share_type.dividend_rate
                },
                "quantity": holding.quantity,
                "total_value": float(holding.total_value),
                "last_updated": holding.last_updated
            })
            total_shares_value += holding.total_value
            total_share_units += holding.quantity
    
    # Calculate summary statistics
    unique_members = len(set(h["member"]["id"] for h in enriched_holdings))
    
    # Get recent share transactions
    recent_transactions = db.query(ShareTransaction).filter(
        ShareTransaction.sacco_id == sacco_id
    ).order_by(ShareTransaction.transaction_date.desc()).limit(10).all()
    
    user_dict = serialize_user_full(user)
    base_context = get_template_context(request, user_dict)
    
    helpers = get_template_helpers()
    
    context = {
        **base_context,
        "holdings": enriched_holdings,
        "recent_transactions": recent_transactions,
        "total_shares_value": total_shares_value,
        "total_share_units": total_share_units,
        "unique_members": unique_members,
        "total_holdings": len(enriched_holdings),
        "page_title": "Share Holdings Management",
        **helpers,
    }
    
    return templates.TemplateResponse(request, "manager/share_holdings.html", context)

@router.get("/manager/shares/types", response_class=HTMLResponse)
def manager_share_types(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """Manage share types in the SACCO"""
    
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    templates = request.app.state.templates
    sacco_id = user.sacco_id
    
    # Get all share types
    share_types = db.query(ShareType).filter(
        ShareType.sacco_id == sacco_id
    ).all()
    
    # Calculate statistics for each share type
    enriched_types = []
    for st in share_types:
        # Count total shares issued
        total_shares = db.query(func.sum(Share.quantity)).filter(
            Share.share_type_id == st.id,
            Share.is_active == True
        ).scalar() or 0
        
        # Count number of shareholders
        shareholders = db.query(Share.user_id).filter(
            Share.share_type_id == st.id,
            Share.is_active == True
        ).distinct().count()
        
        # Calculate total value
        total_value = total_shares * st.par_value
        
        enriched_types.append({
            "id": st.id,
            "name": st.name,
            "class_type": st.class_type,
            "par_value": float(st.par_value),
            "minimum_shares": st.minimum_shares,
            "maximum_shares": st.maximum_shares,
            "is_voting": st.is_voting,
            "dividend_rate": st.dividend_rate,
            "total_shares_issued": total_shares,
            "shareholders_count": shareholders,
            "total_value": total_value
        })
    
    user_dict = serialize_user_full(user)
    base_context = get_template_context(request, user_dict)
    
    helpers = get_template_helpers()
    
    context = {
        **base_context,
        "share_types": enriched_types,
        "page_title": "Share Types Management",
        **helpers,
    }
    
    return templates.TemplateResponse(request, "manager/share_types.html", context)


@router.post("/manager/shares/types/create")
def create_share_type(
    request: Request,
    name: str = Form(...),
    class_type: str = Form(...),
    par_value: float = Form(...),
    minimum_shares: int = Form(1),
    maximum_shares: Optional[int] = Form(None),
    is_voting: bool = Form(False),
    dividend_rate: float = Form(0.0),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """Create a new share type"""
    
    sacco_id = user.sacco_id
    
    new_share_type = ShareType(
        sacco_id=sacco_id,
        name=name,
        class_type=class_type,
        par_value=par_value,
        minimum_shares=minimum_shares,
        maximum_shares=maximum_shares if maximum_shares > 0 else None,
        is_voting=is_voting,
        dividend_rate=dividend_rate
    )
    
    db.add(new_share_type)
    db.commit()
    
    return RedirectResponse(url="/manager/shares/types", status_code=303)

@router.get("/manager/dividends/declare", response_class=HTMLResponse)
def manager_dividends_declare(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """Declare dividends for share types"""
    
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    templates = request.app.state.templates
    sacco_id = user.sacco_id
    
    # Get all share types
    share_types = db.query(ShareType).filter(
        ShareType.sacco_id == sacco_id
    ).all()
    
    # Get past dividend declarations
    past_declarations = db.query(DividendDeclaration).filter(
        DividendDeclaration.sacco_id == sacco_id
    ).order_by(DividendDeclaration.declared_date.desc()).limit(20).all()
    
    # Calculate total dividend pool for each share type
    share_type_data = []
    for st in share_types:
        total_shares = db.query(func.sum(Share.quantity)).filter(
            Share.share_type_id == st.id,
            Share.is_active == True
        ).scalar() or 0
        
        share_type_data.append({
            "id": st.id,
            "name": st.name,
            "par_value": float(st.par_value),
            "dividend_rate": st.dividend_rate,
            "total_shares": total_shares,
            "total_value": total_shares * st.par_value,
            "suggested_dividend": (total_shares * st.par_value) * (st.dividend_rate / 100)
        })
    
    user_dict = serialize_user_full(user)
    base_context = get_template_context(request, user_dict)
    
    helpers = get_template_helpers()
    
    context = {
        **base_context,
        "share_types": share_type_data,
        "past_declarations": past_declarations,
        "page_title": "Declare Dividends",
        **helpers,
    }
    
    return templates.TemplateResponse(request, "manager/declare_dividend.html", context)


@router.post("/manager/dividends/declare/create")
def create_dividend_declaration(
    request: Request,
    share_type_id: Optional[int] = Form(None),
    fiscal_year: int = Form(...),
    rate: float = Form(...),
    amount_per_share: float = Form(...),
    payment_date: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """Create a dividend declaration"""
    
    sacco_id = user.sacco_id
    
    # Calculate total dividend pool
    if share_type_id:
        # For specific share type
        total_shares = db.query(func.sum(Share.quantity)).filter(
            Share.share_type_id == share_type_id,
            Share.sacco_id == sacco_id,
            Share.is_active == True
        ).scalar() or 0
        total_dividend_pool = total_shares * amount_per_share
    else:
        # For all share types
        total_shares = db.query(func.sum(Share.quantity)).filter(
            Share.sacco_id == sacco_id,
            Share.is_active == True
        ).scalar() or 0
        total_dividend_pool = total_shares * amount_per_share
    
    declaration = DividendDeclaration(
        sacco_id=sacco_id,
        share_type_id=share_type_id if share_type_id else None,
        declared_date=datetime.utcnow(),
        fiscal_year=fiscal_year,
        rate=rate,
        amount_per_share=amount_per_share,
        total_dividend_pool=total_dividend_pool,
        payment_date=datetime.strptime(payment_date, '%Y-%m-%d'),
        declared_by=user.id,
        status="pending"
    )
    
    db.add(declaration)
    db.commit()
    
    return RedirectResponse(url="/manager/dividends/declare", status_code=303)


@router.post("/manager/dividends/declare/{declaration_id}/process")
def process_dividend_payment(
    declaration_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """Process dividend payments for a declaration"""
    
    declaration = db.query(DividendDeclaration).filter(
        DividendDeclaration.id == declaration_id,
        DividendDeclaration.sacco_id == user.sacco_id
    ).first()
    
    if not declaration:
        raise HTTPException(status_code=404, detail="Declaration not found")
    
    # Get all share holdings that qualify for this dividend
    query = db.query(Share).filter(
        Share.sacco_id == user.sacco_id,
        Share.is_active == True
    )
    
    if declaration.share_type_id:
        query = query.filter(Share.share_type_id == declaration.share_type_id)
    
    holdings = query.all()
    
    # Create dividend payments for each shareholder
    payments_created = 0
    for holding in holdings:
        # Check if payment already exists
        existing = db.query(DividendPayment).filter(
            DividendPayment.declaration_id == declaration_id,
            DividendPayment.user_id == holding.user_id,
            DividendPayment.share_id == holding.id
        ).first()
        
        if not existing:
            dividend_amount = holding.quantity * declaration.amount_per_share
            
            payment = DividendPayment(
                declaration_id=declaration_id,
                user_id=holding.user_id,
                sacco_id=user.sacco_id,
                share_id=holding.id,
                shares_held=holding.quantity,
                amount=dividend_amount,
                payment_method="pending",
                is_reinvested=False
            )
            db.add(payment)
            payments_created += 1
    
    # Update declaration status
    declaration.status = "processing"
    db.commit()
    
    return RedirectResponse(url="/manager/dividends/declare", status_code=303)