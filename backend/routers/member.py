# backend/routers/member.py

import uuid
import shutil
import os
from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Form, Depends, HTTPException, File, UploadFile
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from passlib.context import CryptContext
import logging
from ..core.dependencies import get_db, require_member, get_current_user
from ..core.context import get_template_context
from ..models import User, Saving, Loan, LoanPayment, Log, PendingDeposit, Sacco, Share, ShareType, ShareTransaction, DividendDeclaration, DividendPayment
from ..utils.helpers import get_template_helpers, check_sacco_status
from ..services.user_service import create_user
from ..utils.logger import create_log, log_user_action

router = APIRouter()
logger = logging.getLogger(__name__)

# Configure upload directory
UPLOAD_DIR = "backend/static/uploads/profiles"
os.makedirs(UPLOAD_DIR, exist_ok=True)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# =============================================================================
# SERIALIZERS (JSON-safe dictionaries for templates)
# =============================================================================

def serialize_user_basic(user: User) -> dict:
    """Basic user info (no sensitive data)"""
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "username": user.username,
        "role": user.role.value if hasattr(user.role, 'value') else str(user.role).split('.')[-1] if user.role else None,
        "is_active": user.is_active,
        "is_approved": user.is_approved,
        "sacco_id": user.sacco_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "phone": user.phone,
        "profile_picture": user.profile_picture,
        "date_of_birth": user.date_of_birth.isoformat() if user.date_of_birth else None,
        "national_id": user.national_id,
        "address": user.address,
    }


def serialize_user_full(user: User) -> dict:
    """Full user info including computed properties"""
    base = serialize_user_basic(user)
    base.update({
        "linked_member_account_id": getattr(user, 'linked_member_account_id', None),
        "linked_admin_id": getattr(user, 'linked_admin_id', None),
        "dashboard_url": user.get_dashboard_url,
        "is_admin": user.is_admin,
        "can_apply_for_loans": user.can_apply_for_loans,
    })
    return base


def serialize_sacco(sacco: Sacco) -> dict:
    """Convert Sacco ORM object to safe dict"""
    if not sacco:
        return None
    return {
        "id": sacco.id,
        "name": sacco.name,
        "email": sacco.email,
        "phone": sacco.phone,
        "address": sacco.address,
        "status": sacco.status,
    }


def serialize_saving(saving: Saving) -> dict:
    """Convert Saving ORM object to safe dict"""
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


def serialize_loan(loan: Loan) -> dict:
    """Convert Loan ORM object to safe dict"""
    return {
        "id": loan.id,
        "amount": loan.amount,
        "term": loan.term,
        "interest_rate": loan.interest_rate,
        "purpose": loan.purpose,
        "status": loan.status,
        "timestamp": loan.timestamp.isoformat() if loan.timestamp else None,
        "total_interest": loan.total_interest,
        "total_payable": loan.total_payable,
        "total_paid": loan.total_paid,
        "approved_by": loan.approved_by,
        "approved_at": loan.approved_at.isoformat() if loan.approved_at else None,
        "user_id": loan.user_id,
        "sacco_id": loan.sacco_id,
    }


def serialize_loan_payment(payment: LoanPayment) -> dict:
    """Convert LoanPayment ORM object to safe dict"""
    return {
        "id": payment.id,
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "timestamp": payment.timestamp.isoformat() if payment.timestamp else None,
        "loan_id": payment.loan_id,
        "user_id": payment.user_id,
        "sacco_id": payment.sacco_id,
    }


def serialize_pending_deposit(deposit: PendingDeposit) -> dict:
    """Convert PendingDeposit ORM object to safe dict"""
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
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_user_loans_with_repayment(db: Session, user_id: int):
    """Helper to get loans with repayment data (returns dict list)"""
    loans_orm = db.query(Loan).filter(Loan.user_id == user_id).order_by(Loan.timestamp.desc()).all()
    loans = []
    for loan in loans_orm:
        repaid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0.0
        # Outstanding = total_payable (principal + interest) - repaid
        outstanding = max(0.0, loan.total_payable - repaid)
        loans.append({
            "id": loan.id,
            "amount": loan.amount,
            "term": loan.term,
            "status": loan.status,
            "timestamp": loan.timestamp.isoformat() if loan.timestamp else "",
            "repaid": float(repaid),
            "outstanding": outstanding,
            "purpose": loan.purpose,
            "interest_rate": loan.interest_rate,
            "total_payable": loan.total_payable,
        })
    return loans


# =============================================================================
# ROUTES
# =============================================================================
@router.head("/member/dashboard", response_class=HTMLResponse)
@router.get("/member/dashboard", response_class=HTMLResponse)
def member_dashboard(
    request: Request,
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)

    templates = request.app.state.templates

    # Calculate balance
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit'
    ).scalar() or 0

    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw'
    ).scalar() or 0

    balance = total_deposits - total_withdrawals

    # Recent transactions
    transactions_orm = db.query(Saving).filter(
        Saving.user_id == user.id
    ).order_by(Saving.timestamp.desc()).limit(10).all()
    transactions = [serialize_saving(t) for t in transactions_orm]

    # Loans with repayment data
    loans = get_user_loans_with_repayment(db, user.id)

    # Calculate totals for summary cards
    total_repaid = sum(loan["repaid"] for loan in loans)
    total_outstanding = sum(loan["outstanding"] for loan in loans)

    active_loans_list = [loan for loan in loans if loan["status"] in ['approved', 'partial']]
    active_loans_count = len(active_loans_list)
    active_loans_total = sum(loan["amount"] for loan in active_loans_list)
    active_loans_outstanding = sum(loan["outstanding"] for loan in active_loans_list)

    sacco = serialize_sacco(user.sacco) if user.sacco else None

    helpers = get_template_helpers()
    base_context = get_template_context(request, user)
    context = {
        **base_context,
        "user": user_dict,
        "sacco": sacco,
        "balance": balance,
        "transactions": transactions,
        "loans": loans,
        "active_loans": active_loans_list,
        "summary": {
            "total_repaid": total_repaid,
            "total_outstanding": total_outstanding,
            "active_loans_count": active_loans_count,
            "active_loans_outstanding": active_loans_outstanding
        },
        **helpers,
    }
    return templates.TemplateResponse(request, "client/dashboard.html", context)


@router.get("/member/profile", response_class=HTMLResponse)
def view_profile(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    user_dict = serialize_user_full(user)
    templates = request.app.state.templates

    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit'
    ).scalar() or 0

    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw'
    ).scalar() or 0
    balance = total_deposits - total_withdrawals

    active_loans = db.query(Loan).filter(
        Loan.user_id == user.id,
        Loan.status.in_(['approved', 'partial'])
    ).count()

    total_repaid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.user_id == user.id
    ).scalar() or 0

    member_since = user.created_at.strftime('%B %Y') if user.created_at else 'N/A'

    helpers = get_template_helpers()
    base_context = get_template_context(request, user)
    context = {
        **base_context,
        "user": user_dict,
        "balance": balance,
        "active_loans": active_loans,
        "total_repaid": total_repaid,
        "member_since": member_since,
        **helpers,
    }
    return templates.TemplateResponse(request,"client/profile.html", context)


@router.post("/member/profile/update")
async def update_profile(
    request: Request,
    full_name: Optional[str] = Form(None),
    phone: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    date_of_birth: Optional[str] = Form(None),
    national_id: Optional[str] = Form(None),
    profile_picture: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)
    templates = request.app.state.templates

    def get_balance():
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id,
            Saving.type == 'deposit'
        ).scalar() or 0
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id,
            Saving.type == 'withdraw'
        ).scalar() or 0
        return total_deposits - total_withdrawals

    def get_active_loans():
        return db.query(Loan).filter(
            Loan.user_id == user.id,
            Loan.status.in_(['approved', 'partial'])
        ).count()

    def get_total_repaid():
        return db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.user_id == user.id
        ).scalar() or 0

    try:
        if full_name:
            user.full_name = full_name
        if phone:
            user.phone = phone
        if address:
            user.address = address
        if national_id:
            user.national_id = national_id

        if date_of_birth:
            try:
                user.date_of_birth = datetime.strptime(date_of_birth, '%Y-%m-%d')
            except ValueError:
                pass

        if email and email != user.email:
            existing_user = db.query(User).filter(User.email == email).first()
            if existing_user:
                helpers = get_template_helpers()
                base_context = get_template_context(request, user)
                context = {
                    **base_context,
                    "user": user_dict,
                    "balance": get_balance(),
                    "active_loans": get_active_loans(),
                    "total_repaid": get_total_repaid(),
                    "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
                    "error": "Email already exists. Please use a different email address.",
                    "success": None,
                    **helpers,
                }
                return templates.TemplateResponse(request,"client/profile.html", context)
            user.email = email

        if profile_picture and profile_picture.filename:
            allowed_types = ['image/jpeg', 'image/png', 'image/jpg', 'image/gif']
            if profile_picture.content_type not in allowed_types:
                helpers = get_template_helpers()
                context = {
                    "request": request,
                    "user": user_dict,
                    "balance": get_balance(),
                    "active_loans": get_active_loans(),
                    "total_repaid": get_total_repaid(),
                    "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
                    "error": "Invalid file type. Please upload JPEG, PNG, or GIF images.",
                    "success": None,
                    **helpers,
                }
                return templates.TemplateResponse(request,"client/profile.html", context)

            file_extension = profile_picture.filename.split('.')[-1]
            filename = f"user_{user.id}_{uuid.uuid4().hex[:8]}.{file_extension}"
            file_path = os.path.join(UPLOAD_DIR, filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(profile_picture.file, buffer)

            if user.profile_picture:
                old_path = os.path.join(UPLOAD_DIR, user.profile_picture)
                if os.path.exists(old_path):
                    os.remove(old_path)

            user.profile_picture = filename

        db.commit()
        db.refresh(user)

        helpers = get_template_helpers()
        base_context = get_template_context(request, user)
        context = {
            **base_context,
            "balance": get_balance(),
            "user": user_dict,
            "active_loans": get_active_loans(),
            "total_repaid": get_total_repaid(),
            "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
            "success": "Profile updated successfully!",
            "error": None,
            **helpers,
        }
        return templates.TemplateResponse(request,"client/profile.html", context)

    except Exception as e:
        db.rollback()
        helpers = get_template_helpers()
        base_context = get_template_context(request, user)
        context = {
            **base_context,
            "user": user_dict,
            "balance": get_balance(),
            "active_loans": get_active_loans(),
            "total_repaid": get_total_repaid(),
            "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
            "error": f"An error occurred: {str(e)}",
            "success": None,
            **helpers,
        }
        return templates.TemplateResponse(request,"client/profile.html", context)


@router.post("/member/profile/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    templates = request.app.state.templates

    # Helper functions to get user data
    def get_balance():
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id,
            Saving.type == 'deposit'
        ).scalar() or 0
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id,
            Saving.type == 'withdraw'
        ).scalar() or 0
        return total_deposits - total_withdrawals
    
    def get_active_loans():
        return db.query(Loan).filter(
            Loan.user_id == user.id,
            Loan.status.in_(['approved', 'partial'])
        ).count()
    
    def get_total_repaid():
        return db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.user_id == user.id
        ).scalar() or 0

    if not pwd_context.verify(current_password, user.password_hash):
        helpers = get_template_helpers()
        base_context = get_template_context(request, user)
        context = {
            **base_context,
            "balance": get_balance(),
            "active_loans": get_active_loans(),
            "total_repaid": get_total_repaid(),
            "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
            "password_error": "Current password is incorrect.",
            "success": None,
            **helpers,
        }
        return templates.TemplateResponse(request,"client/profile.html", context)

    if len(new_password) < 6:
        helpers = get_template_helpers()
        base_context = get_template_context(request, user)
        context = {
            **base_context,
            "balance": get_balance(),
            "active_loans": get_active_loans(),
            "total_repaid": get_total_repaid(),
            "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
            "password_error": "New password must be at least 6 characters long.",
            "success": None,
            **helpers,
        }
        return templates.TemplateResponse(request,"client/profile.html", context)

    if new_password != confirm_password:
        helpers = get_template_helpers()
        base_context = get_template_context(request, user)
        context = {
            **base_context,
            "balance": get_balance(),
            "active_loans": get_active_loans(),
            "total_repaid": get_total_repaid(),
            "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
            "password_error": "New passwords do not match.",
            "success": None,
            **helpers,
        }
        return templates.TemplateResponse(request,"client/profile.html", context)
    # Update password
    user.password_hash = pwd_context.hash(new_password)
    user.password_reset_required = False
    db.commit()

    helpers = get_template_helpers()
    base_context = get_template_context(request, user)
    context = {
        **base_context,
        "balance": get_balance(),
        "active_loans": get_active_loans(),
        "total_repaid": get_total_repaid(),
        "member_since": user.created_at.strftime('%B %Y') if user.created_at else 'N/A',
        "password_success": "Password changed successfully!",
        "success": None,
        **helpers,
    }
    return templates.TemplateResponse(request,"client/profile.html", context)


@router.get("/member/savings", response_class=HTMLResponse)
def view_savings(
    request: Request,
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)
    templates = request.app.state.templates

    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit',
        Saving.approved_by.isnot(None)
    ).scalar() or 0

    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw',
        Saving.approved_by.isnot(None)
    ).scalar() or 0

    balance = total_deposits - total_withdrawals

    pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.user_id == user.id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    pending_deposits = [serialize_pending_deposit(d) for d in pending_deposits_orm]

    transactions_orm = db.query(Saving).filter(
        Saving.user_id == user.id
    ).order_by(Saving.timestamp.desc()).all()
    transactions = [serialize_saving(t) for t in transactions_orm]

    helpers = get_template_helpers()
    base_context = get_template_context(request, user)
    context = {
        **base_context,
        "user": user_dict,
        "balance": balance,
        "transactions": transactions,
        "pending_deposits": pending_deposits,
        "now": datetime.utcnow(),
        "session": request.session,
        **helpers,
    }
    return templates.TemplateResponse(request,"client/savings.html", context)


@router.post("/member/savings/deposit/initiate")
async def initiate_deposit(
    request: Request,
    amount: float = Form(...),
    payment_method: str = Form(...),
    reference_number: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    if amount <= 0:
        request.session["flash_message"] = "Amount must be positive"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/savings", status_code=303)

    pending = PendingDeposit(
        sacco_id=user.sacco_id,
        user_id=user.id,
        amount=amount,
        payment_method=payment_method,
        description=description,
        reference_number=reference_number,
        status="pending",
        timestamp=datetime.utcnow()
    )

    db.add(pending)
    db.commit()

    create_log(
        db,
        action="DEPOSIT_INITIATED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Member {user.email} initiated deposit of UGX {amount:,.2f}",
        ip_address=request.client.host if request.client else None
    )

    request.session["flash_message"] = f"Deposit request of UGX {amount:,.2f} submitted for approval"
    request.session["flash_type"] = "success"

    return RedirectResponse("/member/savings", status_code=303)


@router.post("/member/savings/deposit/{pending_id}/cancel")
def cancel_pending_deposit(
    pending_id: int,
    request: Request,
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    pending = db.query(PendingDeposit).filter(
        PendingDeposit.id == pending_id,
        PendingDeposit.user_id == user.id,
        PendingDeposit.status == "pending"
    ).first()

    if not pending:
        raise HTTPException(status_code=404, detail="Pending deposit not found")

    pending.status = "cancelled"
    db.commit()

    request.session["flash_message"] = "Deposit request cancelled"
    request.session["flash_type"] = "info"

    return RedirectResponse("/member/savings", status_code=303)


@router.post("/member/savings/deposit")
def deposit(
    request: Request,
    amount: float = Form(...),
    payment_method: str = Form(...),
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    if amount <= 0:
        request.session["flash_message"] = "Amount must be positive"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/savings", status_code=303)

    deposit_record = Saving(
        sacco_id=user.sacco_id,
        user_id=user.id,
        type='deposit',
        amount=amount,
        payment_method=payment_method
    )
    db.add(deposit_record)
    db.commit()

    create_log(
        db,
        action="DEPOSIT_MADE",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Deposit of UGX {amount:,.2f} made via {payment_method}",
        ip_address=request.client.host if request.client else None
    )

    request.session["flash_message"] = f"Deposit of UGX {amount:,.2f} successful!"
    request.session["flash_type"] = "success"
    return RedirectResponse("/member/savings", status_code=303)


@router.post("/member/savings/withdraw")
def withdraw(
    request: Request,
    amount: float = Form(...),
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit'
    ).scalar() or 0
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw'
    ).scalar() or 0
    balance = total_deposits - total_withdrawals

    if amount <= 0:
        request.session["flash_message"] = "Amount must be positive"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/savings", status_code=303)

    if amount > balance:
        request.session["flash_message"] = "Insufficient balance"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/savings", status_code=303)

    withdrawal_record = Saving(
        sacco_id=user.sacco_id,
        user_id=user.id,
        type='withdraw',
        amount=amount
    )
    db.add(withdrawal_record)
    db.commit()

    request.session["flash_message"] = f"Withdrawal of UGX {amount:,.2f} successful!"
    request.session["flash_type"] = "success"
    return RedirectResponse("/member/savings", status_code=303)


@router.get("/member/loans", response_class=HTMLResponse)
def view_loans(
    request: Request,
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    user_dict = serialize_user_full(user)
    templates = request.app.state.templates

    # Get loans with repayment data
    loans = get_user_loans_with_repayment(db, user.id)

    # Payment history
    payments_orm = db.query(LoanPayment).filter(
        LoanPayment.user_id == user.id
    ).order_by(LoanPayment.timestamp.desc()).all()
    payments_history = []
    for p in payments_orm:
        loan_orm = db.query(Loan).filter(Loan.id == p.loan_id).first()
        payments_history.append({
            "id": p.id,
            "loan_id": p.loan_id,
            "amount": p.amount,
            "payment_method": p.payment_method,
            "timestamp": p.timestamp.isoformat() if p.timestamp else "",
            "date": p.timestamp.strftime("%Y-%m-%d") if p.timestamp else ""
        })

    total_payments = sum(p["amount"] for p in payments_history)
    # Loans with repayment data
    loans = get_user_loans_with_repayment(db, user.id)

    # Calculate totals for summary cards
    total_repaid = sum(loan["repaid"] for loan in loans)
    total_outstanding = sum(loan["outstanding"] for loan in loans)
			
    # Savings balance
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit'
    ).scalar() or 0.0
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw'
    ).scalar() or 0.0
    balance = total_deposits - total_withdrawals

    # Recent transactions (for notifications)
    recent_transactions_orm = db.query(Saving).filter(
        Saving.user_id == user.id
    ).order_by(Saving.timestamp.desc()).limit(5).all()
    recent_transactions = [serialize_saving(t) for t in recent_transactions_orm]

    # Notifications
    notifications = []
    for loan in loans:
        if loan["status"] in ["approved", "partial"] and loan["outstanding"] > 0:
            last_payment = db.query(func.max(LoanPayment.timestamp)).filter(
                LoanPayment.loan_id == loan["id"]
            ).scalar()
            if last_payment:
                if datetime.utcnow() - last_payment > timedelta(days=30):
                    notifications.append({
                        "icon": "exclamation-triangle",
                        "message": f"Loan #{loan['id']} payment is overdue. Outstanding: UGX {loan['outstanding']:.2f}",
                        "due_date": None
                    })
            else:
                # No payments made yet
                notifications.append({
                    "icon": "exclamation-triangle",
                    "message": f"Loan #{loan['id']} has no payments yet. Please start repaying.",
                    "due_date": None
                })

    if balance < 10000:
        notifications.append({
            "icon": "piggy-bank",
            "message": f"Your savings balance (UGX {balance:.2f}) is low. Consider making a deposit.",
            "due_date": None
        })

    pending_loans = [l for l in loans if l["status"] == "pending"]
    if pending_loans:
        notifications.append({
            "icon": "clock",
            "message": f"You have {len(pending_loans)} pending loan request(s) awaiting review.",
            "due_date": None
        })

    helpers = get_template_helpers()
    base_context = get_template_context(request, user)
    context = {
        **base_context,
        "user": user_dict,
        "total_outstanding": total_outstanding,
        "loans": loans,
        "balance": balance,
        "payments_history": payments_history,
        "total_payments": total_payments,
        "current_savings": balance,
        "notifications": notifications,
        "recent_transactions": recent_transactions,
        **helpers,
    }
    return templates.TemplateResponse(request,"client/loans.html", context)


@router.post("/member/loan/request")
def request_loan(
    request: Request,
    amount: float = Form(...),
    term: int = Form(12),
    purpose: str = Form(None),
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    if not user.can_apply_for_loans:
        request.session["flash_message"] = "Your account is not authorized to apply for loans."
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/loans", status_code=303)

    if amount <= 0:
        request.session["flash_message"] = "Loan amount must be positive"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/loans", status_code=303)

    if term <= 0 or term > 60:
        request.session["flash_message"] = "Loan term must be between 1 and 60 months"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/loans", status_code=303)

    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'deposit'
    ).scalar() or 0
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.user_id == user.id,
        Saving.type == 'withdraw'
    ).scalar() or 0
    balance = total_deposits - total_withdrawals
    max_loan = balance * 3
    if amount > max_loan:
        request.session["flash_message"] = f"Maximum loan amount is UGX {max_loan:.2f} (3x your savings)"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/loans", status_code=303)

    loan = Loan(
        sacco_id=user.sacco_id,
        user_id=user.id,
        amount=amount,
        term=term,
        status='pending',
        purpose=purpose,
        interest_rate=12.0
    )
    loan.calculate_interest()
    db.add(loan)
    db.commit()

    create_log(
        db,
        action="LOAN_REQUESTED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Loan request of UGX {amount:,.2f} for {term} months. Purpose: {purpose or 'Not specified'}",
        ip_address=request.client.host if request.client else None
    )

    request.session["flash_message"] = "Loan request submitted successfully!"
    request.session["flash_type"] = "success"
    return RedirectResponse("/member/loans", status_code=303)


@router.post("/member/loan/repay")
def repay_loan(
    request: Request,
    loan_id: int = Form(...),
    amount: float = Form(...),
    payment_method: str = Form(...),
    user: User = Depends(require_member),
    db: Session = Depends(get_db)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    if amount <= 0:
        request.session["flash_message"] = "Payment amount must be positive"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/loans", status_code=303)

    loan = db.query(Loan).filter(Loan.id == loan_id).first()
    if not loan:
        request.session["flash_message"] = "Loan not found"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/loans", status_code=303)

    if loan.user_id != user.id:
        request.session["flash_message"] = "Not authorized to repay this loan"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/loans", status_code=303)

    if loan.status not in ("approved", "partial"):
        request.session["flash_message"] = "This loan is not approved or already completed"
        request.session["flash_type"] = "danger"
        return RedirectResponse("/member/loans", status_code=303)

    if loan.total_payable == 0:
        loan.calculate_interest()
        db.commit()

    total_paid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.loan_id == loan_id
    ).scalar() or 0
    remaining = max(0.0, loan.total_payable - total_paid)

    if remaining <= 0:
        request.session["flash_message"] = "Loan already fully paid"
        request.session["flash_type"] = "warning"
        return RedirectResponse("/member/loans", status_code=303)

    pay_amount = min(amount, remaining)

    if payment_method == "SAVINGS":
        total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id,
            Saving.type == 'deposit'
        ).scalar() or 0
        total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
            Saving.user_id == user.id,
            Saving.type == 'withdraw'
        ).scalar() or 0
        balance = total_deposits - total_withdrawals

        if pay_amount > balance:
            request.session["flash_message"] = "Insufficient savings balance"
            request.session["flash_type"] = "danger"
            return RedirectResponse("/member/loans", status_code=303)

        withdrawal = Saving(
            sacco_id=user.sacco_id,
            user_id=user.id,
            type='withdraw',
            amount=pay_amount,
            payment_method=payment_method,
            description=f"Loan repayment for loan #{loan_id}"
        )
        db.add(withdrawal)

    payment = LoanPayment(
        loan_id=loan_id,
        sacco_id=user.sacco_id,
        user_id=user.id,
        amount=pay_amount,
        payment_method=payment_method
    )
    db.add(payment)

    loan.total_paid = total_paid + pay_amount
    new_remaining = loan.total_payable - loan.total_paid

    if new_remaining <= 0.01:
        loan.status = 'completed'
        payment_message = f"Loan fully repaid! Total paid: UGX {loan.total_paid:,.2f}"
    else:
        loan.status = 'partial'
        payment_message = f"Payment of UGX {pay_amount:,.2f} recorded. Remaining: UGX {new_remaining:,.2f}"

    db.commit()

    create_log(
        db,
        action="LOAN_PAYMENT",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Payment of UGX {pay_amount:,.2f} recorded for loan #{loan_id}. {payment_message}",
        ip_address=request.client.host if request.client else None
    )

    request.session["flash_message"] = f"Payment of UGX {pay_amount:,.2f} recorded successfully!"
    request.session["flash_type"] = "success"
    return RedirectResponse("/member/loans", status_code=303)


@router.get("/member/inactive", response_class=HTMLResponse)
def inactive_page(request: Request, user: User = Depends(require_member), db: Session = Depends(get_db)):
    templates = request.app.state.templates
    sacco = None
    if user.sacco_id:
        sacco_orm = db.query(Sacco).filter(Sacco.id == user.sacco_id).first()
        sacco = serialize_sacco(sacco_orm) if sacco_orm else None
    base_context = get_template_context(request, user)
    context = {
        **base_context,
        "sacco": sacco
    }
    return templates.TemplateResponse(request,"member/inactive.html", context)


@router.get("/member/suspended", response_class=HTMLResponse)
def suspended_page(request: Request, user: User = Depends(require_member), db: Session = Depends(get_db)):
    templates = request.app.state.templates
    sacco = None
    if user.sacco_id:
        sacco_orm = db.query(Sacco).filter(Sacco.id == user.sacco_id).first()
        sacco = serialize_sacco(sacco_orm) if sacco_orm else None
    base_context = get_template_context(request, user)
    context = {
        **base_context,
        "sacco": sacco
    }
    return templates.TemplateResponse(request,"member/suspended.html", context)

    # routers/member.py

@router.get("/member/shares", response_class=HTMLResponse)
async def member_shares(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_member)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates
    """
    Display the member's share account details.
    Shows share types, holdings, total value, and transaction history.
    """
    # 1. Get the member's share holdings (using Share model)
    holdings = db.query(Share).filter(
        Share.user_id == user.id,
        Share.sacco_id == user.sacco_id,
        Share.is_active == True  # This exists in Share model
    ).all()

    # 2. Get all available share types for this SACCO (no is_active filter)
    share_types = db.query(ShareType).filter(
        ShareType.sacco_id == user.sacco_id
    ).all()

    # 3. Calculate total value of shares
    total_shares_value = 0
    total_share_units = 0
    for holding in holdings:
        total_share_units += holding.quantity
        total_shares_value += holding.total_value

    # 4. Get recent share transactions
    share_transactions = db.query(ShareTransaction).filter(
        ShareTransaction.user_id == user.id,
        ShareTransaction.sacco_id == user.sacco_id
    ).order_by(ShareTransaction.transaction_date.desc()).limit(10).all()

    # 5. Prepare the context for the template
    user_dict = serialize_user_full(user)
    base_context = get_template_context(request, user_dict)
    helpers = get_template_helpers()
    page_context = {
        "holdings": holdings,
        "share_types": share_types,
        "total_shares_value": total_shares_value,
        "total_share_units": total_share_units,
        "transactions": share_transactions,
        "page_title": "My Share Account",
        **helpers
    }

    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request, "client/shares.html", final_context)


@router.post("/member/shares/purchase")
async def purchase_shares(
    request: Request,
    share_type_id: int = Form(...),
    units: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_member)
):
    """Purchase shares"""
    
    # Get the share type
    share_type = db.query(ShareType).filter(
        ShareType.id == share_type_id,
        ShareType.sacco_id == user.sacco_id
    ).first()
    
    if not share_type:
        raise HTTPException(status_code=404, detail="Share type not found")
    
    # Check minimum shares
    if units < share_type.minimum_shares:
        raise HTTPException(
            status_code=400, 
            detail=f"Minimum purchase is {share_type.minimum_shares} shares"
        )
    
    # Check maximum shares if set
    if share_type.maximum_shares and units > share_type.maximum_shares:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum purchase is {share_type.maximum_shares} shares"
        )
    
    # Calculate total amount (using par_value)
    total_amount = units * share_type.par_value
    
    # Check if user already has shares of this type
    existing_share = db.query(Share).filter(
        Share.user_id == user.id,
        Share.sacco_id == user.sacco_id,
        Share.share_type_id == share_type_id,
        Share.is_active == True
    ).first()
    
    if existing_share:
        # Update existing holding
        existing_share.quantity += units
        existing_share.total_value += total_amount
        existing_share.last_updated = datetime.utcnow()
        share_id = existing_share.id
    else:
        # Create new share holding
        new_share = Share(
            user_id=user.id,
            sacco_id=user.sacco_id,
            share_type_id=share_type_id,
            quantity=units,
            total_value=total_amount,
            is_active=True,
            last_updated=datetime.utcnow()
        )
        db.add(new_share)
        db.flush()
        share_id = new_share.id
    
    # Create transaction record
    transaction = ShareTransaction(
        share_id=share_id,
        user_id=user.id,
        sacco_id=user.sacco_id,
        transaction_type="subscription",
        quantity=units,
        price_per_share=share_type.par_value,
        total_amount=total_amount,
        transaction_date=datetime.utcnow(),
        notes=f"Purchase of {units} {share_type.name} shares"
    )
    db.add(transaction)
    
    db.commit()
    
    # Redirect back to shares page with success message
    return RedirectResponse(
        url="/member/shares?message=Shares purchased successfully",
        status_code=303
    )

@router.get("/member/dividends", response_class=HTMLResponse)
async def member_dividends(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_member)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates
    """
    Display member's dividend earnings and history.
    Shows declared dividends, payments, and pending dividends.
    """
    # 1. Get all dividend payments made to this member
    dividend_payments = db.query(DividendPayment).filter(
        DividendPayment.user_id == user.id,
        DividendPayment.sacco_id == user.sacco_id
    ).order_by(DividendPayment.paid_at.desc()).all()
    
    # 2. Get all dividend declarations for this SACCO
    dividend_declarations = db.query(DividendDeclaration).filter(
        DividendDeclaration.sacco_id == user.sacco_id
    ).order_by(DividendDeclaration.declared_date.desc()).all()
    
    # 3. Calculate dividend statistics
    total_dividends_received = sum(payment.amount for payment in dividend_payments if payment.paid_at)
    total_dividends_pending = 0
    last_dividend_date = None
    
    # Find pending dividends (declared but not yet paid)
    pending_declarations = [d for d in dividend_declarations if d.status == 'pending' and d.payment_date > datetime.utcnow()]
    for declaration in pending_declarations:
        # Check if member has shares that qualify for this dividend
        member_shares = db.query(Share).filter(
            Share.user_id == user.id,
            Share.sacco_id == user.sacco_id,
            Share.is_active == True
        ).all()
        
        for share in member_shares:
            if declaration.share_type_id is None or declaration.share_type_id == share.share_type_id:
                expected_payment = share.quantity * declaration.amount_per_share
                total_dividends_pending += expected_payment
    
    # Get last dividend payment date
    if dividend_payments:
        last_dividend_date = dividend_payments[0].paid_at
    
    # 4. Get member's share holdings for dividend calculation
    holdings = db.query(Share).filter(
        Share.user_id == user.id,
        Share.sacco_id == user.sacco_id,
        Share.is_active == True
    ).all()
    
    # 5. Calculate total shares and potential earnings
    total_shares = sum(holding.quantity for holding in holdings)
    total_share_value = sum(holding.total_value for holding in holdings)
    
    # 6. Prepare context
    user_dict = serialize_user_full(user)
    base_context = get_template_context(request, user_dict)
    helpers = get_template_helpers()
    page_context = {
        "dividend_payments": dividend_payments,
        "dividend_declarations": dividend_declarations,
        "total_dividends_received": total_dividends_received,
        "total_dividends_pending": total_dividends_pending,
        "last_dividend_date": last_dividend_date,
        "holdings": holdings,
        "total_shares": total_shares,
        "total_share_value": total_share_value,
        "pending_declarations_count": len(pending_declarations),
        "page_title": "My Dividends",
        **helpers
    }
    
    final_context = {**base_context, **page_context}
    return templates.TemplateResponse(request, "client/dividends.html", final_context)


@router.get("/api/member/dividends/summary")
async def get_dividends_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_member)
):
    """API endpoint to get dividend summary for charts"""
    
    # Get dividend payments by year
    from sqlalchemy import func, extract
    
    dividends_by_year = db.query(
        extract('year', DividendPayment.paid_at).label('year'),
        func.sum(DividendPayment.amount).label('total')
    ).filter(
        DividendPayment.user_id == user.id,
        DividendPayment.sacco_id == user.sacco_id
    ).group_by('year').order_by('year').all()
    
    # Get dividend declarations by year
    declarations_by_year = db.query(
        extract('year', DividendDeclaration.declared_date).label('year'),
        func.count(DividendDeclaration.id).label('count'),
        func.avg(DividendDeclaration.rate).label('avg_rate')
    ).filter(
        DividendDeclaration.sacco_id == user.sacco_id
    ).group_by('year').order_by('year').all()
    
    return {
        "success": True,
        "dividends_by_year": [{"year": int(y), "total": float(t)} for y, t in dividends_by_year],
        "declarations_by_year": [{"year": int(y), "count": c, "avg_rate": float(r) if r else 0} for y, c, r in declarations_by_year]
    }
