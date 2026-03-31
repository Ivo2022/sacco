# backend/routers/credit_officer.py

from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
import logging

from ..core.dependencies import get_db, require_credit_officer_or_manager
from ..models import RoleEnum, Loan, LoanPayment, User, Log, Sacco
from ..utils import create_log
from ..utils.helpers import get_template_helpers, check_sacco_status

router = APIRouter()
logger = logging.getLogger(__name__)


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
        "sacco_id": user.sacco_id,
        "phone": user.phone,
    }


def serialize_user_full(user: User) -> dict:
    """Full user info including computed properties"""
    base = serialize_user_basic(user)
    base.update({
        "linked_member_account_id": user.linked_member_account_id,
        "linked_admin_id": user.linked_admin_id,
        "dashboard_url": user.get_dashboard_url,
        "is_admin": user.is_admin,
        "can_manage_loans": user.can_manage_loans,
        "can_send_loan_reminders": user.can_send_loan_reminders,
    })
    return base


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
        "approval_notes": loan.approval_notes,
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


def serialize_log(log: Log) -> dict:
    """Convert Log ORM object to safe dict"""
    return {
        "id": log.id,
        "action": log.action,
        "details": log.details,
        "ip_address": log.ip_address,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "user_id": log.user_id,
        "sacco_id": log.sacco_id,
        "user_email": log.user.email if log.user else None,
    }


def serialize_sacco(sacco: Sacco) -> dict:
    """Convert Sacco ORM object to safe dict"""
    if not sacco:
        return None
    return {
        "id": sacco.id,
        "name": sacco.name,
        "status": sacco.status,
    }


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_overdue_loans(db: Session, sacco_id: int):
    """Get overdue loans (days overdue > 0)"""
    active_loans_orm = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(["approved", "partial"])
    ).all()

    overdue = []
    for loan in active_loans_orm:
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        loan_outstanding = loan.total_payable - total_paid

        last_payment_orm = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()

        if last_payment_orm:
            next_payment_date = last_payment_orm.timestamp + timedelta(days=30)
        else:
            next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()

        days_overdue = 0
        if next_payment_date < datetime.utcnow():
            days_overdue = (datetime.utcnow() - next_payment_date).days

        if days_overdue > 0:
            member = db.query(User).filter(User.id == loan.user_id).first()
            loan_dict = serialize_loan(loan)
            loan_dict.update({
                "outstanding": loan_outstanding,
                "days_overdue": days_overdue,
                "monthly_payment": loan.calculate_monthly_payment(),
                "member": serialize_user_basic(member) if member else None,
            })
            overdue.append(loan_dict)

    return overdue


def get_upcoming_loans(db: Session, sacco_id: int):
    """Get loans with upcoming payments in next 7 days"""
    active_loans_orm = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(["approved", "partial"])
    ).all()

    upcoming = []
    for loan in active_loans_orm:
        last_payment_orm = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()

        if last_payment_orm:
            next_payment_date = last_payment_orm.timestamp + timedelta(days=30)
        else:
            next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()

        days_until_due = (next_payment_date - datetime.utcnow()).days

        if 0 < days_until_due <= 7:
            member = db.query(User).filter(User.id == loan.user_id).first()
            loan_dict = serialize_loan(loan)
            loan_dict.update({
                "next_payment_date": next_payment_date.isoformat(),
                "days_until_due": days_until_due,
                "monthly_payment": loan.calculate_monthly_payment(),
                "member": serialize_user_basic(member) if member else None,
            })
            upcoming.append(loan_dict)

    return upcoming


def get_monthly_payment_data(db: Session, sacco_id: int, start_date: datetime, end_date: datetime):
    """Get monthly payment data for charts"""
    payments = db.query(
        func.strftime("%Y-%m", LoanPayment.timestamp).label("month"),
        func.sum(LoanPayment.amount).label("total")
    ).filter(
        LoanPayment.sacco_id == sacco_id,
        LoanPayment.timestamp >= start_date,
        LoanPayment.timestamp <= end_date
    ).group_by("month").order_by("month").all()

    return [{"month": p.month, "total": p.total} for p in payments]


def get_monthly_trends(db: Session, sacco_id: int):
    """Get monthly trends for last 6 months"""
    six_months_ago = datetime.utcnow() - timedelta(days=180)

    # Monthly disbursements
    disbursements = db.query(
        func.strftime("%Y-%m", Loan.approved_at).label("month"),
        func.count(Loan.id).label("count"),
        func.sum(Loan.amount).label("amount")
    ).filter(
        Loan.sacco_id == sacco_id,
        Loan.approved_at >= six_months_ago,
        Loan.status.in_(["approved", "completed", "overdue"])
    ).group_by("month").order_by("month").all()

    # Monthly collections
    collections = db.query(
        func.strftime("%Y-%m", LoanPayment.timestamp).label("month"),
        func.sum(LoanPayment.amount).label("amount")
    ).filter(
        LoanPayment.sacco_id == sacco_id,
        LoanPayment.timestamp >= six_months_ago
    ).group_by("month").order_by("month").all()

    months = []
    disbursement_data = []
    collection_data = []

    for d in disbursements:
        months.append(d.month)
        disbursement_data.append(d.amount or 0)

    for c in collections:
        if c.month not in months:
            months.append(c.month)
            disbursement_data.append(0)
        idx = months.index(c.month)
        if idx < len(collection_data):
            collection_data.append(c.amount)
        else:
            collection_data.append(c.amount)

    # Sort by month
    combined = sorted(zip(months, disbursement_data, collection_data), key=lambda x: x[0])
    months = [c[0] for c in combined]
    disbursement_data = [c[1] for c in combined]
    collection_data = [c[2] for c in combined]

    return {
        "months": months,
        "disbursements": disbursement_data,
        "collections": collection_data
    }


def get_top_performing_loans(db: Session, sacco_id: int, limit: int = 5):
    """Get top performing loans by repayment rate"""
    loans_orm = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(["approved", "completed"])
    ).limit(limit).all()

    top_loans = []
    for loan in loans_orm:
        paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        repayment_rate = (paid / loan.total_payable * 100) if loan.total_payable > 0 else 0
        member = db.query(User).filter(User.id == loan.user_id).first()

        loan_dict = serialize_loan(loan)
        loan_dict.update({
            "member": serialize_user_basic(member) if member else None,
            "repayment_rate": repayment_rate,
            "paid": paid,
        })
        top_loans.append(loan_dict)

    return sorted(top_loans, key=lambda x: x["repayment_rate"], reverse=True)[:limit]


def get_upcoming_payments_analytics(db: Session, sacco_id: int):
    """Get upcoming payments for next 30 days"""
    active_loans_orm = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "approved"
    ).all()

    upcoming = []
    for loan in active_loans_orm:
        last_payment_orm = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()

        if last_payment_orm:
            next_payment_date = last_payment_orm.timestamp + timedelta(days=30)
        else:
            next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()

        days_until_due = (next_payment_date - datetime.utcnow()).days

        if 0 <= days_until_due <= 30:
            upcoming.append({
                "loan": serialize_loan(loan),
                "next_payment_date": next_payment_date.isoformat(),
                "days_until_due": days_until_due,
                "amount_due": loan.calculate_monthly_payment(),
            })

    return sorted(upcoming, key=lambda x: x["days_until_due"])


def get_payment_method_distribution(db: Session, sacco_id: int):
    """Get payment method distribution"""
    payments = db.query(
        LoanPayment.payment_method,
        func.count(LoanPayment.id).label("count"),
        func.sum(LoanPayment.amount).label("total")
    ).filter(
        LoanPayment.sacco_id == sacco_id
    ).group_by(LoanPayment.payment_method).all()

    return [{
        "method": p.payment_method,
        "count": p.count,
        "total": p.total
    } for p in payments]


# =============================================================================
# ROUTES
# =============================================================================
@router.head("/credit-officer/dashboard", response_class=HTMLResponse)
@router.get("/credit-officer/dashboard", response_class=HTMLResponse)
def credit_officer_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    # Get all active loans
    active_loans_orm = db.query(Loan).filter(
        Loan.sacco_id == user.sacco_id,
        Loan.status.in_(["approved", "partial"])
    ).all()

    active_loans = []
    for loan in active_loans_orm:
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        outstanding = loan.total_payable - total_paid
        monthly_payment = loan.calculate_monthly_payment()

        last_payment_orm = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()

        if last_payment_orm:
            next_payment_date = last_payment_orm.timestamp + timedelta(days=30)
        else:
            next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()

        days_overdue = 0
        if next_payment_date < datetime.utcnow():
            days_overdue = (datetime.utcnow() - next_payment_date).days

        member = db.query(User).filter(User.id == loan.user_id).first()

        loan_dict = serialize_loan(loan)
        loan_dict.update({
            "total_paid": total_paid,
            "outstanding": outstanding,
            "monthly_payment": monthly_payment,
            "next_payment_date": next_payment_date.isoformat(),
            "days_overdue": days_overdue,
            "member": serialize_user_basic(member) if member else None,
        })
        active_loans.append(loan_dict)

    # Separate loans by status
    overdue_loans = [l for l in active_loans if l["days_overdue"] > 0]
    upcoming_payments = [l for l in active_loans if 0 < l["days_overdue"] <= 7]  # Due in next 7 days
    current_loans = [l for l in active_loans if l["days_overdue"] == 0]

    total_outstanding = sum(l["outstanding"] for l in active_loans)
    total_overdue_amount = sum(l["outstanding"] for l in overdue_loans)

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "overdue_loans": overdue_loans,
        "upcoming_payments": upcoming_payments,
        "current_loans": current_loans,
        "active_loans": active_loans,
        "total_outstanding": total_outstanding,
        "total_overdue_amount": total_overdue_amount,
        "overdue_count": len(overdue_loans),
        "upcoming_count": len(upcoming_payments),
        **helpers,
    }
    return templates.TemplateResponse(request, "credit_officer/dashboard.html", context)


@router.get("/credit-officer/loan/{loan_id}")
def view_loan(
    request: Request,
    loan_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    """View detailed loan information"""
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
    payments_orm = db.query(LoanPayment).filter(
        LoanPayment.loan_id == loan_id
    ).order_by(LoanPayment.timestamp.desc()).all()
    payments = [serialize_loan_payment(p) for p in payments_orm]

    total_paid = sum(p["amount"] for p in payments)
    outstanding = loan_orm.total_payable - total_paid
    payment_percentage = (total_paid / loan_orm.total_payable * 100) if loan_orm.total_payable > 0 else 0

    last_payment = payments_orm[0] if payments_orm else None
    if last_payment:
        next_payment_date = last_payment.timestamp + timedelta(days=30)
    else:
        next_payment_date = loan_orm.approved_at + timedelta(days=30) if loan_orm.approved_at else datetime.utcnow()

    days_overdue = 0
    if next_payment_date < datetime.utcnow():
        days_overdue = (datetime.utcnow() - next_payment_date).days

    reminders_orm = db.query(Log).filter(
        Log.action == "LOAN_REMINDER_SENT",
        Log.details.like(f"%loan #{loan_id}%")
    ).order_by(Log.timestamp.desc()).limit(10).all()
    reminders = [serialize_log(r) for r in reminders_orm]

    loan = serialize_loan(loan_orm)
    member = serialize_user_basic(member_orm) if member_orm else None

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "loan": loan,
        "member": member,
        "payments": payments,
        "total_paid": total_paid,
        "outstanding": outstanding,
        "payment_percentage": payment_percentage,
        "next_payment_date": next_payment_date.isoformat(),
        "days_overdue": days_overdue,
        "reminders": reminders,
        **helpers,
    }
    return templates.TemplateResponse("credit_officer/loan_detail.html", context)


@router.post("/credit-officer/loan/{loan_id}/send-reminder")
def send_loan_reminder(
    request: Request,
    loan_id: int,
    reminder_type: str = Form("payment"),
    message: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    """Send a reminder for a loan"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    loan = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.sacco_id == user.sacco_id
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    member = db.query(User).filter(User.id == loan.user_id).first()

    reminder_messages = {
        "payment": f"Dear {member.full_name or member.email}, your loan payment of UGX {loan.calculate_monthly_payment():,.2f} is due. Please make payment promptly.",
        "overdue": f"Dear {member.full_name or member.email}, your loan payment is overdue. Please clear the outstanding balance to avoid penalties.",
        "custom": message or f"Reminder about your loan #{loan.id}"
    }

    final_message = reminder_messages.get(reminder_type, reminder_messages["payment"])

    create_log(
        db,
        action="LOAN_REMINDER_SENT",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Reminder sent for loan #{loan.id} to {member.email}: {final_message[:100]}"
    )

    logger.info(f"Reminder sent for loan {loan_id}: {final_message}")

    request.session["flash_message"] = f"✓ Reminder sent successfully to {member.email}"
    request.session["flash_type"] = "success"

    return RedirectResponse(url=f"/credit-officer/loan/{loan_id}", status_code=303)


@router.post("/credit-officer/loan/{loan_id}/record-payment")
def record_payment(
    request: Request,
    loan_id: int,
    amount: float = Form(...),
    payment_method: str = Form("CASH"),
    reference_number: str = Form(None),
    notes: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    """Record a loan payment"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    loan = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.sacco_id == user.sacco_id
    ).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    # Create payment record
    payment = LoanPayment(
        loan_id=loan_id,
        sacco_id=user.sacco_id,
        user_id=loan.user_id,
        amount=amount,
        payment_method=payment_method,
        reference_number=reference_number,
        notes=notes
    )
    db.add(payment)

    total_paid = db.query(func.sum(LoanPayment.amount)).filter(
        LoanPayment.loan_id == loan_id
    ).scalar() or 0
    total_paid += amount
    loan.total_paid = total_paid

    if total_paid >= loan.total_payable:
        loan.status = "completed"
        loan.completed_at = datetime.utcnow()

    db.commit()

    create_log(
        db,
        action="LOAN_PAYMENT_RECORDED",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Payment of UGX {amount:,.2f} recorded for loan #{loan.id} by {user.email}"
    )

    request.session["flash_message"] = f"✓ Payment of UGX {amount:,.2f} recorded successfully"
    request.session["flash_type"] = "success"

    return RedirectResponse(url=f"/credit-officer/loan/{loan_id}", status_code=303)


@router.get("/credit-officer/loans")
def list_loans(
    request: Request,
    status: str = None,
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    """List all loans with filtering"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    query = db.query(Loan).filter(Loan.sacco_id == user.sacco_id)
    if status:
        query = query.filter(Loan.status == status)

    loans_orm = query.order_by(Loan.timestamp.desc()).all()

    loans = []
    for loan in loans_orm:
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        outstanding = loan.total_payable - total_paid
        member = db.query(User).filter(User.id == loan.user_id).first()

        last_payment_orm = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()
        if last_payment_orm:
            days_since_last_payment = (datetime.utcnow() - last_payment_orm.timestamp).days
        else:
            days_since_last_payment = (datetime.utcnow() - loan.approved_at).days if loan.approved_at else 0

        loan_dict = serialize_loan(loan)
        loan_dict.update({
            "outstanding": outstanding,
            "member": serialize_user_basic(member) if member else None,
            "days_since_last_payment": days_since_last_payment,
        })
        loans.append(loan_dict)

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "loans": loans,
        "status_filter": status,
        **helpers,
    }
    return templates.TemplateResponse("credit_officer/loans.html", context)


@router.get("/credit-officer/reminders")
def reminders_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    """Reminders management page"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    overdue_loans = get_overdue_loans(db, user.sacco_id)
    upcoming_loans = get_upcoming_loans(db, user.sacco_id)

    reminder_history_orm = db.query(Log).filter(
        Log.sacco_id == user.sacco_id,
        Log.action == "LOAN_REMINDER_SENT",
        Log.timestamp >= datetime.utcnow() - timedelta(days=30)
    ).order_by(Log.timestamp.desc()).limit(50).all()

    enhanced_history = []
    for reminder in reminder_history_orm:
        loan_id = None
        if "loan #" in reminder.details:
            loan_id = reminder.details.split("loan #")[1].split(" ")[0]
        enhanced_history.append({
            "timestamp": reminder.timestamp.isoformat(),
            "loan_id": loan_id,
            "member_name": "Extracted from details",
            "reminder_type": "overdue" if "overdue" in reminder.details.lower() else "payment",
            "sent_by": reminder.user.email if reminder.user else "Unknown"
        })

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "overdue_loans": overdue_loans,
        "upcoming_loans": upcoming_loans,
        "reminder_history": enhanced_history,
        **helpers,
    }
    return templates.TemplateResponse("credit_officer/reminders.html", context)


@router.post("/credit-officer/reminders/bulk-send")
async def bulk_send_reminders(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    """Send reminders in bulk"""
    data = await request.json()
    loan_ids = data.get('loan_ids', [])
    reminder_type = data.get('reminder_type', 'payment')

    if loan_ids == 'all_overdue':
        loans = get_overdue_loans(db, user.sacco_id)
        loan_ids = [l["id"] for l in loans]
    elif loan_ids == 'all_upcoming':
        loans = get_upcoming_loans(db, user.sacco_id)
        loan_ids = [l["id"] for l in loans]

    sent_count = 0
    for loan_id in loan_ids:
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if loan:
            member = db.query(User).filter(User.id == loan.user_id).first()
            create_log(
                db,
                action="LOAN_REMINDER_SENT",
                user_id=user.id,
                sacco_id=user.sacco_id,
                details=f"Bulk reminder sent for loan #{loan.id} to {member.email} - Type: {reminder_type}"
            )
            sent_count += 1

    return {"success": True, "count": sent_count}


@router.get("/credit-officer/reports")
def loan_reports(
    request: Request,
    report_type: str = None,
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    """Loan reports page"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start = datetime.utcnow() - timedelta(days=30)

    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    else:
        end = datetime.utcnow()

    query = db.query(Loan).filter(Loan.sacco_id == user.sacco_id)
    if report_type == "active":
        query = query.filter(Loan.status == "approved")
    elif report_type == "overdue":
        query = query.filter(Loan.status == "overdue")
    elif report_type == "completed":
        query = query.filter(Loan.status == "completed")

    loans_orm = query.order_by(Loan.timestamp.desc()).all()

    total_loans = len(loans_orm)
    total_amount = sum(l.amount for l in loans_orm)
    total_outstanding = 0
    total_paid = 0

    loans = []
    for loan in loans_orm:
        paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        total_paid += paid
        outstanding = loan.total_payable - paid
        total_outstanding += outstanding
        member = db.query(User).filter(User.id == loan.user_id).first()

        loan_dict = serialize_loan(loan)
        loan_dict.update({
            "total_paid": paid,
            "outstanding": outstanding,
            "payment_percentage": (paid / loan.total_payable * 100) if loan.total_payable > 0 else 0,
            "member": serialize_user_basic(member) if member else None,
        })
        loans.append(loan_dict)

    overdue_loans = [l for l in loans if l["status"] == "overdue" or (l["outstanding"] > 0 and l["status"] == "approved")]
    overdue_count = len(overdue_loans)
    overdue_amount = sum(l["outstanding"] for l in overdue_loans)

    monthly_data = get_monthly_payment_data(db, user.sacco_id, start, end)

    total_collections = db.query(func.sum(LoanPayment.amount)).filter(
        LoanPayment.sacco_id == user.sacco_id,
        LoanPayment.timestamp >= start,
        LoanPayment.timestamp <= end
    ).scalar() or 0

    export_filename = f"loan_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "loans": loans,
        "report_type": report_type,
        "start_date": start.strftime("%Y-%m-%d") if start_date else None,
        "end_date": end.strftime("%Y-%m-%d") if end_date else None,
        "total_loans": total_loans,
        "total_amount": total_amount,
        "total_outstanding": total_outstanding,
        "total_paid": total_paid,
        "total_collections": total_collections,
        "overdue_count": overdue_count,
        "overdue_amount": overdue_amount,
        "monthly_data": monthly_data,
        "export_filename": export_filename,
        **helpers,
    }
    return templates.TemplateResponse("credit_officer/reports.html", context)


@router.get("/credit-officer/analytics")
def loan_analytics(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_credit_officer_or_manager)
):
    """Loan analytics dashboard"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    all_loans_orm = db.query(Loan).filter(Loan.sacco_id == user.sacco_id).all()

    # Loan status distribution
    status_counts = {
        "approved": len([l for l in all_loans_orm if l.status == "approved"]),
        "pending": len([l for l in all_loans_orm if l.status == "pending"]),
        "completed": len([l for l in all_loans_orm if l.status == "completed"]),
        "overdue": len([l for l in all_loans_orm if l.status == "overdue"]),
        "rejected": len([l for l in all_loans_orm if l.status == "rejected"])
    }

    # Payment performance
    total_disbursed = sum(l.amount for l in all_loans_orm if l.status in ["approved", "completed", "overdue"])
    total_received = 0
    total_outstanding = 0
    for loan in all_loans_orm:
        paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        total_received += paid
        if loan.status in ["approved", "overdue"]:
            total_outstanding += (loan.total_payable - paid)

    collection_rate = (total_received / total_disbursed * 100) if total_disbursed > 0 else 0

    monthly_trends = get_monthly_trends(db, user.sacco_id)
    top_loans = get_top_performing_loans(db, user.sacco_id)
    upcoming_payments = get_upcoming_payments_analytics(db, user.sacco_id)
    payment_methods = get_payment_method_distribution(db, user.sacco_id)

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "status_counts": status_counts,
        "total_disbursed": total_disbursed,
        "total_received": total_received,
        "total_outstanding": total_outstanding,
        "collection_rate": collection_rate,
        "monthly_trends": monthly_trends,
        "top_loans": top_loans,
        "upcoming_payments": upcoming_payments,
        "payment_methods": payment_methods,
        **helpers,
    }
    return templates.TemplateResponse("credit_officer/analytics.html", context)