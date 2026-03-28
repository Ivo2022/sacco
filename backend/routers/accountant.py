from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
import logging
from ..core.dependencies import get_db, require_accountant_or_manager 
from ..models import RoleEnum, PendingDeposit, Saving, User, Sacco
from ..utils.helpers import get_template_helpers, check_sacco_status
from ..utils import create_log
from ..services.user_service import get_user

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")
logger = logging.getLogger(__name__)

@router.get("/accountant/dashboard")
def accountant_dashboard(
    request: Request, 
    db: Session = Depends(get_db), 
    user=Depends(require_accountant_or_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Get pending deposits count
    pending_count = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).count()
    
    # Get pending deposits list
    pending_deposits = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).limit(10).all()
    
    # Get recent transactions
    recent_transactions = db.query(Saving).filter(
        Saving.sacco_id == user.sacco_id
    ).order_by(Saving.timestamp.desc()).limit(10).all()
    
    # Get summary statistics
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id
    ).scalar() or 0
    
    # Get today's collections
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_collections = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= today_start
    ).scalar() or 0
    
    # Get this month's collections
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_collections = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= month_start
    ).scalar() or 0
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("accountant/dashboard.html", {
        "request": request,
        "user": user,
        "pending_count": pending_count,
        "pending_deposits": pending_deposits,
        "recent_transactions": recent_transactions,
        "total_savings": total_savings,
        "today_collections": today_collections,
        "month_collections": month_collections,
        **helpers
    })

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
    
    pending_deposits = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    
    # Get member info for each deposit
    for deposit in pending_deposits:
        deposit.member = db.query(User).filter(User.id == deposit.user_id).first()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("accountant/pending_deposits.html", {
        "request": request,
        "user": user,
        "pending_deposits": pending_deposits,
        "pending_count": len(pending_deposits),
        **helpers
    })

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
    
    # Build query
    query = db.query(Saving).filter(Saving.sacco_id == user.sacco_id)
    
    # Apply filters
    if transaction_type:
        query = query.filter(Saving.type == transaction_type)
    
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(Saving.timestamp >= start)
    
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Saving.timestamp <= end)
    
    # Pagination
    total = query.count()
    offset = (page - 1) * per_page
    transactions = query.order_by(Saving.timestamp.desc()).offset(offset).limit(per_page).all()
    
    # Get member info for each transaction
    for transaction in transactions:
        transaction.member = db.query(User).filter(User.id == transaction.user_id).first()
    
    # Get summary statistics
    total_deposits = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.type == "deposit"
    ).scalar() or 0
    
    total_withdrawals = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.type == "withdrawal"
    ).scalar() or 0
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("accountant/transactions.html", {
        "request": request,
        "user": user,
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
        **helpers
    })

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
    
    # Build query for savings transactions
    query = db.query(Saving).filter(Saving.sacco_id == user.sacco_id)
    
    # Apply filters
    if member_id:
        query = query.filter(Saving.user_id == member_id)
    
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        query = query.filter(Saving.timestamp >= start)
    
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        query = query.filter(Saving.timestamp <= end)
    
    # Pagination
    total = query.count()
    offset = (page - 1) * per_page
    transactions = query.order_by(Saving.timestamp.desc()).offset(offset).limit(per_page).all()
    
    # Get member info for each transaction
    for transaction in transactions:
        transaction.member = db.query(User).filter(User.id == transaction.user_id).first()
    
    # Get list of members for filter
    members = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER
    ).order_by(User.full_name).all()
    
    # Get member savings summary
    member_summary = []
    for member in members:
        total = db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == member.id,
            Saving.type == "deposit"
        ).scalar() or 0
        
        withdrawals = db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == member.id,
            Saving.type == "withdrawal"
        ).scalar() or 0
        
        member_summary.append({
            "member": member,
            "total_savings": total,
            "total_withdrawals": withdrawals,
            "balance": total - withdrawals
        })
    
    # Sort by balance descending
    member_summary.sort(key=lambda x: x["balance"], reverse=True)
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("accountant/savings.html", {
        "request": request,
        "user": user,
        "transactions": transactions,
        "member_summary": member_summary,
        "selected_member": member_id,
        "start_date": start_date,
        "end_date": end_date,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page,
        **helpers
    })

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
    
    # Set date range based on report type
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
        # Default to last 30 days
        start = now - timedelta(days=30)
        end = now
    
    # Get transactions for period
    transactions = db.query(Saving).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= start,
        Saving.timestamp <= end
    ).order_by(Saving.timestamp.desc()).all()
    
    # Get member info for transactions and convert to dict
    transactions_data = []
    for transaction in transactions[:100]:  # Limit to 100 for display
        member = db.query(User).filter(User.id == transaction.user_id).first()
        transactions_data.append({
            "id": transaction.id,
            "timestamp": transaction.timestamp.isoformat(),
            "type": transaction.type,
            "amount": transaction.amount,
            "payment_method": transaction.payment_method,
            "reference_number": transaction.reference_number,
            "member": {
                "full_name": member.full_name if member else None,
                "email": member.email if member else None,
                "phone": member.phone if member else None
            },
            "approver": {
                "email": transaction.approver.email if transaction.approver else None
            } if transaction.approver else None
        })
    
    # Calculate totals
    total_deposits = sum(t.amount for t in transactions if t.type == "deposit")
    total_withdrawals = sum(t.amount for t in transactions if t.type == "withdrawal")
    net_flow = total_deposits - total_withdrawals
    
    # Get daily breakdown - Convert to dict
    daily_query = db.query(
        func.date(Saving.timestamp).label("date"),
        func.sum(Saving.amount).filter(Saving.type == "deposit").label("deposits"),
        func.sum(Saving.amount).filter(Saving.type == "withdrawal").label("withdrawals")
    ).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= start,
        Saving.timestamp <= end
    ).group_by(func.date(Saving.timestamp)).order_by("date").all()
    
    # Convert daily data to JSON serializable format
    daily_data = []
    for row in daily_query:
        daily_data.append({
            "date": row.date,
            "deposits": float(row.deposits) if row.deposits else 0,
            "withdrawals": float(row.withdrawals) if row.withdrawals else 0
        })
    
    # Get payment method breakdown - Convert to dict
    payment_query = db.query(
        Saving.payment_method,
        func.sum(Saving.amount).label("total"),
        func.count(Saving.id).label("count")
    ).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.timestamp >= start,
        Saving.timestamp <= end
    ).group_by(Saving.payment_method).all()
    
    # Convert payment data to JSON serializable format
    payment_methods = []
    for row in payment_query:
        payment_methods.append({
            "payment_method": row.payment_method.value if hasattr(row.payment_method, 'value') else str(row.payment_method),
            "total": float(row.total) if row.total else 0,
            "count": row.count
        })
    
    # Get top depositors - Convert to dict
    top_depositors_query = db.query(
        Saving.user_id,
        func.sum(Saving.amount).label("total")
    ).filter(
        Saving.sacco_id == user.sacco_id,
        Saving.type == "deposit",
        Saving.timestamp >= start,
        Saving.timestamp <= end
    ).group_by(Saving.user_id).order_by(func.sum(Saving.amount).desc()).limit(10).all()
    
    # Convert top depositors to JSON serializable format
    top_depositors = []
    for row in top_depositors_query:
        member = db.query(User).filter(User.id == row.user_id).first()
        top_depositors.append({
            "user_id": row.user_id,
            "total": float(row.total) if row.total else 0,
            "member": {
                "full_name": member.full_name if member else None,
                "email": member.email if member else None,
                "phone": member.phone if member else None
            }
        })
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("accountant/reports.html", {
        "request": request,
        "user": user,
        "report_type": report_type,
        "start_date": start.strftime("%Y-%m-%d"),
        "end_date": (end - timedelta(days=1)).strftime("%Y-%m-%d") if end else "",
        "transactions": transactions_data,
        "total_transactions": len(transactions),
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "net_flow": net_flow,
        "daily_data": daily_data,
        "payment_methods": payment_methods,
        "top_depositors": top_depositors,
        **helpers
    })
	
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
    
    member = db.query(User).filter(
        User.id == member_id,
        User.sacco_id == user.sacco_id
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Get all savings transactions for this member
    transactions = db.query(Saving).filter(
        Saving.user_id == member_id,
        Saving.sacco_id == user.sacco_id
    ).order_by(Saving.timestamp.desc()).all()
    
    # Calculate totals
    total_deposits = sum(t.amount for t in transactions if t.type == "deposit")
    total_withdrawals = sum(t.amount for t in transactions if t.type == "withdrawal")
    current_balance = total_deposits - total_withdrawals
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("accountant/member_savings.html", {
        "request": request,
        "user": user,
        "member": member,
        "transactions": transactions,
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "current_balance": current_balance,
        **helpers
    })