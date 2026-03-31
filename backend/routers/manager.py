from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from ..core.dependencies import get_db, require_role
from ..schemas import RoleEnum
from ..services import get_sacco_statistics
from ..utils.helpers import get_template_helpers, check_sacco_status
from ..services.user_service import create_user
from ..models import Loan, PendingDeposit, User, Log, Saving, LoanPayment
import logging
from ..utils import create_log
from datetime import datetime, timedelta, timezone

router = APIRouter()
logger = logging.getLogger(__name__)

def require_manager(user=Depends(require_role(RoleEnum.MANAGER))):
    return user

# Helper serializers
def serialize_loan(loan: Loan) -> dict:
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

# Routes
@router.head("/manager/dashboard", response_class=HTMLResponse)
@router.get("/manager/dashboard", response_class=HTMLResponse)
def manager_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates
    sacco_id = user.sacco_id

    # Counts
    pending_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "pending"
    ).count()

    approved_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "approved"
    ).count()

    completed_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "completed"
    ).count()

    overdue_loans_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "overdue"
    ).count()

    pending_deposits_count = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == sacco_id,
        PendingDeposit.status == "pending"
    ).count()

    pending_notifications = pending_loans_count + pending_deposits_count

    # Recent items (serialized)
    recent_pending_loans_orm = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "pending"
    ).order_by(Loan.timestamp.desc()).limit(5).all()
    recent_pending_loans = [serialize_loan(l) for l in recent_pending_loans_orm]

    recent_pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).limit(5).all()
    recent_pending_deposits = [serialize_pending_deposit(d) for d in recent_pending_deposits_orm]

    recent_activities_orm = db.query(Log).filter(
        Log.sacco_id == sacco_id
    ).order_by(Log.timestamp.desc()).limit(10).all()
    recent_activities = [serialize_log(l) for l in recent_activities_orm]

    # Staff counts
    staff_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).count()

    accountant_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.ACCOUNTANT
    ).count()

    credit_officer_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.CREDIT_OFFICER
    ).count()

    # Member counts
    member_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
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

    pending_members_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False,
        User.is_active == False
    ).count()

    # Financial totals
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id
    ).scalar() or 0

    total_loan_amount = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0

    active_loans_count = approved_loans_count

    # 30-day transaction totals
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    transactions_30d_orm = db.query(Saving).filter(
        Saving.sacco_id == sacco_id,
        Saving.timestamp >= thirty_days_ago
    ).all()
    total_deposits_30d = sum(t.amount for t in transactions_30d_orm if t.type == "deposit")
    total_withdrawals_30d = sum(t.amount for t in transactions_30d_orm if t.type == "withdrawal")
    transaction_count_30d = len(transactions_30d_orm)

    stats = get_sacco_statistics(db, sacco_id)  # This likely returns dicts already; if not, serialize.
    helpers = get_template_helpers()

    context = {
        "request": request,
        "user": serialize_user_full(user),
        "pending_notifications": pending_notifications,
        "pending_loans": pending_loans_count,
        "pending_deposits": pending_deposits_count,
        "approved_loans": approved_loans_count,
        "completed_loans": completed_loans_count,
        "overdue_loans": overdue_loans_count,
        "active_loans_count": active_loans_count,
        "total_savings": total_savings,
        "total_loan_amount": total_loan_amount,
        "member_count": member_count,
        "active_members": active_members,
        "new_members_this_month": new_members_this_month,
        "staff_count": staff_count,
        "accountant_count": accountant_count,
        "credit_officer_count": credit_officer_count,
        "recent_pending_loans": recent_pending_loans,
        "recent_pending_deposits": recent_pending_deposits,
        "recent_activities": recent_activities,
        "pending_members_count": pending_members_count,
        "total_deposits_30d": total_deposits_30d,
        "total_withdrawals_30d": total_withdrawals_30d,
        "transaction_count_30d": transaction_count_30d,
        **stats,
        **helpers,
    }

    return templates.TemplateResponse(request, "manager/dashboard.html", context)


@router.get("/manager/pending-members")
def pending_members(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates
    pending_members_orm = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False,
        User.is_active == False
    ).order_by(User.created_at.desc()).all()

    pending_members = [serialize_user_basic(m) for m in pending_members_orm]

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "pending_members": pending_members,
        "pending_count": len(pending_members),
        **helpers,
    }
    return templates.TemplateResponse(request,"manager/pending_members.html", context)


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

    create_log(
        db,
        "MEMBER_APPROVED",
        user.id,
        user.sacco_id,
        f"Member {member.email} approved by {user.email}"
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
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "loan": loan,
        "member": member,
        **helpers,
    }
    return templates.TemplateResponse(request,"manager/loan_review.html", context)


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

    templates = request.app.state.templates
    loans_orm = db.query(Loan).filter(
        Loan.sacco_id == user.sacco_id,
        Loan.status == "pending"
    ).order_by(Loan.timestamp.desc()).all()

    loans = [serialize_loan(l) for l in loans_orm]
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "loans": loans,
        "pending_count": len(loans),
        **helpers,
    }
    return templates.TemplateResponse(request,"manager/pending_loans.html", context)


@router.get("/manager/staff")
def manage_staff(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates
    staff_orm = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).all()

    staff = [serialize_user_basic(s) for s in staff_orm]
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "staff": staff,
        **helpers,
    }
    return templates.TemplateResponse(request,"manager/staff.html", context)


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
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "active_loans_count": active_loans_count,
        "total_savings": total_savings,
        "member_count": member_count,
        "staff_count": staff_count,
        "total_loan_amount": total_loan_amount,
        "pending_loans": pending_loans,
        "overdue_loans": overdue_loans,
        **helpers,
    }
    return templates.TemplateResponse(request,"manager/reports.html", context)


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
    context = {
        "request": request,
        "user": serialize_user_full(user),
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
    return templates.TemplateResponse(request,"manager/members.html", context)


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
    context = {
        "request": request,
        "user": serialize_user_full(user),
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
    return templates.TemplateResponse(request,"manager/member_detail.html", context)


@router.get("/manager/staff-activity")
def staff_activity(
    request: Request,
    role: str = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates
    staff_query = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    )
    if role:
        staff_query = staff_query.filter(User.role == RoleEnum(role))
    staff_members_orm = staff_query.all()

    staff_activities = []
    for staff_orm in staff_members_orm:
        activities_orm = db.query(Log).filter(
            Log.user_id == staff_orm.id,
            Log.sacco_id == user.sacco_id
        ).order_by(Log.timestamp.desc()).limit(10).all()
        activities = [serialize_log(a) for a in activities_orm]

        action_counts = {
            "approvals": len([a for a in activities if "APPROVED" in a["action"]]),
            "rejections": len([a for a in activities if "REJECTED" in a["action"]]),
            "creations": len([a for a in activities if "CREATED" in a["action"]]),
            "reminders": len([a for a in activities if "REMINDER" in a["action"]])
        }

        staff_activities.append({
            "staff": serialize_user_basic(staff_orm),
            "recent_activities": activities[:5],
            "action_counts": action_counts,
            "total_actions": len(activities)
        })

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "staff_activities": staff_activities,
        "selected_role": role,
        **helpers,
    }
    return templates.TemplateResponse(request,"manager/staff_activity.html", context)


@router.get("/manager/accountant-dashboard")
def view_accountant_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates
    pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    pending_deposits = [serialize_pending_deposit(d) for d in pending_deposits_orm]

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
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "pending_deposits": pending_deposits,
        "recent_transactions": recent_transactions,
        "total_savings": total_savings,
        "today_collections": today_collections,
        "pending_count": len(pending_deposits),
        **helpers,
    }
    return templates.TemplateResponse(request,"manager/accountant_view.html", context)


@router.get("/manager/credit-officer-dashboard")
def view_credit_officer_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

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
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "active_loans": active_loans,
        "overdue_loans": overdue_loans,
        "reminders": reminders,
        "active_count": len(active_loans),
        "overdue_count": len(overdue_loans),
        **helpers,
    }
    return templates.TemplateResponse(request,"manager/credit_officer_view.html", context)


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
    context = {
        "request": request,
        "user": serialize_user_full(user),
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
    return templates.TemplateResponse(request,"manager/all_transactions.html", context)


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
    context = {
        "request": request,
        "user": serialize_user_full(user),
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
    return templates.TemplateResponse(request,"manager/all_loans.html", context)