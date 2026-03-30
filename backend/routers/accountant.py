# backend/routers/accountant.py

from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta
import logging

from ..core.dependencies import get_db, require_accountant_or_manager
from ..models import RoleEnum, PendingDeposit, Saving, User, Sacco
from ..utils.helpers import get_template_helpers, check_sacco_status
from ..utils import create_log

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
        "is_approved": user.is_approved,
        "sacco_id": user.sacco_id,
        "created_at": user.created_at.isoformat() if user.created_at else None,
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
    })
    return base


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
        "member_name": deposit.user.full_name if deposit.user else None,
        "member_email": deposit.user.email if deposit.user else None,
    }


def serialize_sacco(sacco: Sacco) -> dict:
    """Convert Sacco ORM object to safe dict"""
    return {
        "id": sacco.id,
        "name": sacco.name,
        "email": sacco.email,
        "phone": sacco.phone,
        "address": sacco.address,
        "registration_no": sacco.registration_no,
        "website": sacco.website,
        "status": sacco.status,
        "created_at": sacco.created_at.isoformat() if sacco.created_at else None,
    }


# =============================================================================
# ROUTES
# =============================================================================

@router.get("/accountant/dashboard")
def accountant_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_accountant_or_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    # Get pending deposits
    pending_count = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).count()

    pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).limit(10).all()
    pending_deposits = [serialize_pending_deposit(d) for d in pending_deposits_orm]

    # Get recent transactions
    recent_transactions_orm = db.query(Saving).filter(
        Saving.sacco_id == user.sacco_id
    ).order_by(Saving.timestamp.desc()).limit(10).all()
    recent_transactions = [serialize_saving(t) for t in recent_transactions_orm]

    # Summary statistics
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id
    ).scalar() or 0

    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_collections = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= today_start
    ).scalar() or 0

    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_collections = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= month_start
    ).scalar() or 0

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "pending_count": pending_count,
        "pending_deposits": pending_deposits,
        "recent_transactions": recent_transactions,
        "total_savings": total_savings,
        "today_collections": today_collections,
        "month_collections": month_collections,
        **helpers,
    }
    return templates.TemplateResponse("accountant/dashboard.html", context)


@router.get("/accountant/deposits/pending")
def pending_deposits_page(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_accountant_or_manager)
):
    """View all pending deposits"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    pending_deposits_orm = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    pending_deposits = [serialize_pending_deposit(d) for d in pending_deposits_orm]

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "pending_deposits": pending_deposits,
        "pending_count": len(pending_deposits),
        **helpers,
    }
    return templates.TemplateResponse("accountant/pending_deposits.html", context)


@router.post("/accountant/deposit/{deposit_id}/approve")
async def approve_deposit(
    deposit_id: int,
    request: Request,
    notes: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_accountant_or_manager)
):
    """Approve a pending deposit"""
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
        "DEPOSIT_APPROVED",
        user.id,
        user.sacco_id,
        f"Deposit of UGX {pending.amount:,.2f} approved for {member.email} by {user.email}"
    )

    request.session["flash_message"] = f"✓ Deposit of UGX {pending.amount:,.2f} approved successfully!"
    request.session["flash_type"] = "success"

    return RedirectResponse(url="/accountant/deposits/pending", status_code=303)


@router.post("/accountant/deposit/{deposit_id}/reject")
async def reject_deposit(
    deposit_id: int,
    request: Request,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_accountant_or_manager)
):
    """Reject a pending deposit"""
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
        "DEPOSIT_REJECTED",
        user.id,
        user.sacco_id,
        f"Deposit of UGX {pending.amount:,.2f} rejected for {member.email} by {user.email}. Reason: {reason}"
    )

    request.session["flash_message"] = f"✓ Deposit of UGX {pending.amount:,.2f} rejected."
    request.session["flash_type"] = "warning"

    return RedirectResponse(url="/accountant/deposits/pending", status_code=303)


@router.get("/accountant/transactions")
def transactions_page(
    request: Request,
    transaction_type: str = Query(None, description="Filter by transaction type"),
    start_date: str = Query(None),
    end_date: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user=Depends(require_accountant_or_manager)
):
    """View all transactions"""
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

    # Get member info for each transaction
    for tx in transactions:
        member = db.query(User).filter(User.id == tx["user_id"]).first()
        tx["member"] = serialize_user_basic(member) if member else None

    total_deposits = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.type == "deposit"
    ).scalar() or 0

    total_withdrawals = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.type == "withdrawal"
    ).scalar() or 0

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
    return templates.TemplateResponse("accountant/transactions.html", context)


@router.get("/accountant/savings")
def savings_page(
    request: Request,
    member_id: int = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user=Depends(require_accountant_or_manager)
):
    """View savings accounts and transactions"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    query = db.query(Saving).filter(Saving.sacco_id == user.sacco_id)

    if member_id:
        query = query.filter(Saving.user_id == member_id)

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

    for tx in transactions:
        member = db.query(User).filter(User.id == tx["user_id"]).first()
        tx["member"] = serialize_user_basic(member) if member else None

    # List of members for filter
    members_orm = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER
    ).order_by(User.full_name).all()
    members = [serialize_user_basic(m) for m in members_orm]

    # Member savings summary
    member_summary = []
    for m in members_orm:
        total = db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == m.id,
            Saving.type == "deposit"
        ).scalar() or 0
        withdrawals = db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == m.id,
            Saving.type == "withdrawal"
        ).scalar() or 0
        balance = total - withdrawals
        member_summary.append({
            "member": serialize_user_basic(m),
            "total_savings": total,
            "total_withdrawals": withdrawals,
            "balance": balance
        })

    member_summary.sort(key=lambda x: x["balance"], reverse=True)

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "transactions": transactions,
        "member_summary": member_summary,
        "selected_member": member_id,
        "start_date": start_date,
        "end_date": end_date,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page,
        **helpers,
    }
    return templates.TemplateResponse("accountant/savings.html", context)


@router.get("/accountant/reports")
def accountant_reports(
    request: Request,
    report_type: str = Query("daily", description="daily, weekly, monthly, custom"),
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_accountant_or_manager)
):
    """Financial reports page"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates
    now = datetime.utcnow()

    if report_type == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif report_type == "weekly":
        start = now - timedelta(days=now.weekday())
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
    elif report_type == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=32)
        end = end.replace(day=1)
    elif report_type == "custom" and start_date and end_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    else:
        start = now - timedelta(days=30)
        end = now

    # Get transactions for period
    transactions_orm = db.query(Saving).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= start,
        Saving.timestamp <= end
    ).order_by(Saving.timestamp.desc()).all()

    transactions_data = []
    for t in transactions_orm[:100]:  # Limit to 100 for display
        member = db.query(User).filter(User.id == t.user_id).first()
        member_dict = serialize_user_basic(member) if member else None
        tx_dict = serialize_saving(t)
        tx_dict["member"] = member_dict
        if t.approver:
            tx_dict["approver"] = {"email": t.approver.email} if t.approver else None
        else:
            tx_dict["approver"] = None
        transactions_data.append(tx_dict)

    total_deposits = sum(t.amount for t in transactions_orm if t.type == "deposit")
    total_withdrawals = sum(t.amount for t in transactions_orm if t.type == "withdrawal")
    net_flow = total_deposits - total_withdrawals

    # Daily breakdown
    daily_query = db.query(
        func.date(Saving.timestamp).label("date"),
        func.sum(Saving.amount).filter(Saving.type == "deposit").label("deposits"),
        func.sum(Saving.amount).filter(Saving.type == "withdrawal").label("withdrawals")
    ).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= start,
        Saving.timestamp <= end
    ).group_by(func.date(Saving.timestamp)).order_by("date").all()

    daily_data = []
    for row in daily_query:
        daily_data.append({
            "date": row.date,
            "deposits": float(row.deposits) if row.deposits else 0,
            "withdrawals": float(row.withdrawals) if row.withdrawals else 0
        })

    # Payment method breakdown
    payment_query = db.query(
        Saving.payment_method,
        func.sum(Saving.amount).label("total"),
        func.count(Saving.id).label("count")
    ).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= start,
        Saving.timestamp <= end
    ).group_by(Saving.payment_method).all()

    payment_methods = []
    for row in payment_query:
        payment_methods.append({
            "payment_method": row.payment_method.value if hasattr(row.payment_method, 'value') else str(row.payment_method),
            "total": float(row.total) if row.total else 0,
            "count": row.count
        })

    # Top depositors
    top_depositors_query = db.query(
        Saving.user_id,
        func.sum(Saving.amount).label("total")
    ).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.type == "deposit",
        Saving.timestamp >= start,
        Saving.timestamp <= end
    ).group_by(Saving.user_id).order_by(func.sum(Saving.amount).desc()).limit(10).all()

    top_depositors = []
    for row in top_depositors_query:
        member = db.query(User).filter(User.id == row.user_id).first()
        top_depositors.append({
            "user_id": row.user_id,
            "total": float(row.total) if row.total else 0,
            "member": serialize_user_basic(member) if member else None
        })

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "report_type": report_type,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": (end - timedelta(days=1)).strftime("%Y-%m-%d") if end else "",
        "transactions": transactions_data,
        "total_transactions": len(transactions_orm),
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "net_flow": net_flow,
        "daily_data": daily_data,
        "payment_methods": payment_methods,
        "top_depositors": top_depositors,
        **helpers,
    }
    return templates.TemplateResponse("accountant/reports.html", context)


@router.get("/accountant/member/{member_id}")
def member_savings_detail(
    request: Request,
    member_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_accountant_or_manager)
):
    """View detailed savings for a specific member"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check

    templates = request.app.state.templates

    member_orm = db.query(User).filter(
        User.id == member_id,
        User.sacco_id == user.sacco_id
    ).first()

    if not member_orm:
        raise HTTPException(status_code=404, detail="Member not found")

    member = serialize_user_full(member_orm)

    transactions_orm = db.query(Saving).filter(
        Saving.user_id == member_id,
        Saving.sacco_id == user.sacco_id
    ).order_by(Saving.timestamp.desc()).all()
    transactions = [serialize_saving(t) for t in transactions_orm]

    total_deposits = sum(t.amount for t in transactions_orm if t.type == "deposit")
    total_withdrawals = sum(t.amount for t in transactions_orm if t.type == "withdrawal")
    current_balance = total_deposits - total_withdrawals

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "member": member,
        "transactions": transactions,
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "current_balance": current_balance,
        **helpers,
    }
    return templates.TemplateResponse("accountant/member_savings.html", context)