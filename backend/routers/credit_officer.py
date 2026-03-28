from fastapi import APIRouter, Depends, Request, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from ..core.dependencies import get_db, require_credit_officer_or_manager
from ..models import RoleEnum, Loan, LoanPayment, User, Log
from ..utils import create_log
from ..utils.helpers import get_template_helpers, check_sacco_status
import logging

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")
logger = logging.getLogger(__name__)

@router.get("/credit-officer/dashboard")
def credit_officer_dashboard(
    request: Request, 
    db: Session = Depends(get_db), 
    user=Depends(require_credit_officer_or_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Get all active loans
    active_loans = db.query(Loan).filter(
        Loan.sacco_id == user.sacco_id,
        Loan.status.in_(["approved", "partial"])
    ).all()
    
    # Calculate loan details
    for loan in active_loans:
        # Calculate total paid
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        loan.total_paid = total_paid
        loan.outstanding = loan.total_payable - total_paid
        loan.monthly_payment = loan.calculate_monthly_payment()
        
        # Calculate next payment date (assuming monthly payments)
        last_payment = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()
        
        if last_payment:
            loan.next_payment_date = last_payment.timestamp + timedelta(days=30)
        else:
            loan.next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()
        
        # Calculate days overdue
        if loan.next_payment_date < datetime.utcnow():
            loan.days_overdue = (datetime.utcnow() - loan.next_payment_date).days
        else:
            loan.days_overdue = 0
        
        # Get member info
        loan.member = db.query(User).filter(User.id == loan.user_id).first()
    
    # Separate loans by status
    overdue_loans = [l for l in active_loans if l.days_overdue > 0]
    upcoming_payments = [l for l in active_loans if 0 < l.days_overdue <= 7]  # Due in next 7 days
    current_loans = [l for l in active_loans if l.days_overdue == 0]
    
    # Statistics
    total_outstanding = sum(l.outstanding for l in active_loans)
    total_overdue_amount = sum(l.outstanding for l in overdue_loans)
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("credit_officer/dashboard.html", {
        "request": request,
        "user": user,
        "overdue_loans": overdue_loans,
        "upcoming_payments": upcoming_payments,
        "current_loans": current_loans,
        "active_loans": active_loans,
        "total_outstanding": total_outstanding,
        "total_overdue_amount": total_overdue_amount,
        "overdue_count": len(overdue_loans),
        "upcoming_count": len(upcoming_payments),
        **helpers,
    })

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
    
    # Get loan details
    loan = db.query(Loan).filter(
        Loan.id == loan_id,
        Loan.sacco_id == user.sacco_id
    ).first()
    
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    
    # Get member information
    member = db.query(User).filter(User.id == loan.user_id).first()
    
    # Get payment history
    payments = db.query(LoanPayment).filter(
        LoanPayment.loan_id == loan_id
    ).order_by(LoanPayment.timestamp.desc()).all()
    
    # Calculate payment statistics
    total_paid = sum(p.amount for p in payments)
    outstanding = loan.total_payable - total_paid
    payment_percentage = (total_paid / loan.total_payable * 100) if loan.total_payable > 0 else 0
    
    # Calculate next payment date
    last_payment = payments[0] if payments else None
    if last_payment:
        next_payment_date = last_payment.timestamp + timedelta(days=30)
    else:
        next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()
    
    # Check if overdue
    days_overdue = 0
    if next_payment_date < datetime.utcnow():
        days_overdue = (datetime.utcnow() - next_payment_date).days
    
    # Get recent reminders sent for this loan
    reminders = db.query(Log).filter(
        Log.action == "LOAN_REMINDER_SENT",
        Log.details.like(f"%loan #{loan_id}%")
    ).order_by(Log.timestamp.desc()).limit(10).all()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("credit_officer/loan_detail.html", {
        "request": request,
        "user": user,
        "loan": loan,
        "member": member,
        "payments": payments,
        "total_paid": total_paid,
        "outstanding": outstanding,
        "payment_percentage": payment_percentage,
        "next_payment_date": next_payment_date,
        "days_overdue": days_overdue,
        "reminders": reminders,
        **helpers
    })

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
    
    # Prepare reminder message
    reminder_messages = {
        "payment": f"Dear {member.full_name or member.email}, your loan payment of UGX {loan.monthly_payment:,.2f} is due. Please make payment promptly.",
        "overdue": f"Dear {member.full_name or member.email}, your loan payment is overdue. Please clear UGX {loan.outstanding:,.2f} to avoid penalties.",
        "custom": message or f"Reminder about your loan #{loan.id}"
    }
    
    final_message = reminder_messages.get(reminder_type, reminder_messages["payment"])
    
    # Create log entry
    create_log(
        db,
        action="LOAN_REMINDER_SENT",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"Reminder sent for loan #{loan.id} to {member.email}: {final_message[:100]}"
    )
    
    # Here you would integrate with SMS/Email service
    # For now, just log it
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
    
    # Update loan total paid
    total_paid = db.query(func.sum(LoanPayment.amount)).filter(
        LoanPayment.loan_id == loan_id
    ).scalar() or 0
    total_paid += amount
    
    loan.total_paid = total_paid
    
    # Check if loan is fully paid
    if total_paid >= loan.total_payable:
        loan.status = "completed"
        loan.completed_at = datetime.utcnow()
    
    db.commit()
    
    # Create log entry
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
    
    query = db.query(Loan).filter(Loan.sacco_id == user.sacco_id)
    
    if status:
        query = query.filter(Loan.status == status)
    
    loans = query.order_by(Loan.timestamp.desc()).all()
    
    # Calculate additional info for each loan
    for loan in loans:
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        loan.outstanding = loan.total_payable - total_paid
        loan.member = db.query(User).filter(User.id == loan.user_id).first()
        
        # Calculate days since last payment
        last_payment = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()
        
        if last_payment:
            loan.days_since_last_payment = (datetime.utcnow() - last_payment.timestamp).days
        else:
            loan.days_since_last_payment = (datetime.utcnow() - loan.approved_at).days if loan.approved_at else 0
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("credit_officer/loans.html", {
        "request": request,
        "user": user,
        "loans": loans,
        "status_filter": status,
        **helpers
    })
	
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
    
    # Get overdue loans
    overdue_loans = get_overdue_loans(db, user.sacco_id)
    
    # Get upcoming payments (next 7 days)
    upcoming_loans = get_upcoming_loans(db, user.sacco_id)
    
    # Get reminder history (last 30 days)
    reminder_history = db.query(Log).filter(
        Log.sacco_id == user.sacco_id,
        Log.action == "LOAN_REMINDER_SENT",
        Log.timestamp >= datetime.utcnow() - timedelta(days=30)
    ).order_by(Log.timestamp.desc()).limit(50).all()
    
    # Enhance reminder history with additional data
    enhanced_history = []
    for reminder in reminder_history:
        # Extract loan ID from details
        loan_id = None
        if "loan #" in reminder.details:
            loan_id = reminder.details.split("loan #")[1].split(" ")[0]
        
        enhanced_history.append({
            "timestamp": reminder.timestamp,
            "loan_id": loan_id,
            "member_name": "Extracted from details",  # You can parse this from details
            "reminder_type": "overdue" if "overdue" in reminder.details.lower() else "payment",
            "sent_by": reminder.user.email if reminder.user else "Unknown"
        })
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("credit_officer/reminders.html", {
        "request": request,
        "user": user,
        "overdue_loans": overdue_loans,
        "upcoming_loans": upcoming_loans,
        "reminder_history": enhanced_history,
        **helpers
    })

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
        loan_ids = [loan.id for loan in loans]
    elif loan_ids == 'all_upcoming':
        loans = get_upcoming_loans(db, user.sacco_id)
        loan_ids = [loan.id for loan in loans]
    
    sent_count = 0
    for loan_id in loan_ids:
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if loan:
            member = db.query(User).filter(User.id == loan.user_id).first()
            
            # Create log entry for each reminder
            create_log(
                db,
                action="LOAN_REMINDER_SENT",
                user_id=user.id,
                sacco_id=user.sacco_id,
                details=f"Bulk reminder sent for loan #{loan.id} to {member.email} - Type: {reminder_type}"
            )
            sent_count += 1
    
    return {"success": True, "count": sent_count}

def get_overdue_loans(db: Session, sacco_id: int):
    """Get overdue loans"""
    active_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(["approved", "partial"])
    ).all()
    
    overdue = []
    for loan in active_loans:
        # Calculate total paid
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        loan.outstanding = loan.total_payable - total_paid
        
        # Get last payment date
        last_payment = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()
        
        if last_payment:
            next_payment_date = last_payment.timestamp + timedelta(days=30)
        else:
            next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()
        
        days_overdue = 0
        if next_payment_date < datetime.utcnow():
            days_overdue = (datetime.utcnow() - next_payment_date).days
        
        if days_overdue > 0:
            loan.days_overdue = days_overdue
            loan.monthly_payment = loan.calculate_monthly_payment()
            loan.member = db.query(User).filter(User.id == loan.user_id).first()
            overdue.append(loan)
    
    return overdue

def get_upcoming_loans(db: Session, sacco_id: int):
    """Get loans with upcoming payments in next 7 days"""
    active_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(["approved", "partial"])
    ).all()
    
    upcoming = []
    for loan in active_loans:
        # Get last payment date
        last_payment = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()
        
        if last_payment:
            next_payment_date = last_payment.timestamp + timedelta(days=30)
        else:
            next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()
        
        days_until_due = (next_payment_date - datetime.utcnow()).days
        
        if 0 < days_until_due <= 7:
            loan.next_payment_date = next_payment_date
            loan.monthly_payment = loan.calculate_monthly_payment()
            loan.member = db.query(User).filter(User.id == loan.user_id).first()
            upcoming.append(loan)
    
    return upcoming
	
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
    
    # Parse dates if provided
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start = datetime.utcnow() - timedelta(days=30)
    
    if end_date:
        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    else:
        end = datetime.utcnow()
    
    # Get all loans for the SACCO
    query = db.query(Loan).filter(Loan.sacco_id == user.sacco_id)
    
    if report_type == "active":
        query = query.filter(Loan.status == "approved")
    elif report_type == "overdue":
        query = query.filter(Loan.status == "overdue")
    elif report_type == "completed":
        query = query.filter(Loan.status == "completed")
    
    loans = query.order_by(Loan.timestamp.desc()).all()
    
    # Calculate loan statistics
    total_loans = len(loans)
    total_amount = sum(l.amount for l in loans)
    total_outstanding = 0
    total_paid = 0
    
    for loan in loans:
        paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        total_paid += paid
        total_outstanding += (loan.total_payable - paid)
        loan.total_paid = paid
        loan.outstanding = loan.total_payable - paid
        loan.payment_percentage = (paid / loan.total_payable * 100) if loan.total_payable > 0 else 0
        
        # Get member info
        loan.member = db.query(User).filter(User.id == loan.user_id).first()
    
    # Get monthly payment data for chart
    monthly_data = get_monthly_payment_data(db, user.sacco_id, start, end)
    
    # Get overdue summary
    overdue_loans = [l for l in loans if l.status == "overdue" or (hasattr(l, 'outstanding') and l.outstanding > 0 and l.status == "approved")]
    overdue_count = len(overdue_loans)
    overdue_amount = sum(l.outstanding for l in overdue_loans if hasattr(l, 'outstanding'))
    
    # Get payment history for the period
    payments = db.query(LoanPayment).filter(
        LoanPayment.sacco_id == user.sacco_id,
        LoanPayment.timestamp >= start,
        LoanPayment.timestamp <= end
    ).all()
    
    total_collections = sum(p.amount for p in payments)
    export_filename = f"loan_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("credit_officer/reports.html", {
        "request": request,
        "user": user,
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
    })

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
    
    # Get all loans
    all_loans = db.query(Loan).filter(Loan.sacco_id == user.sacco_id).all()
    
    # Calculate loan status distribution
    status_counts = {
        "approved": len([l for l in all_loans if l.status == "approved"]),
        "pending": len([l for l in all_loans if l.status == "pending"]),
        "completed": len([l for l in all_loans if l.status == "completed"]),
        "overdue": len([l for l in all_loans if l.status == "overdue"]),
        "rejected": len([l for l in all_loans if l.status == "rejected"])
    }
    
    # Calculate payment performance
    total_disbursed = sum(l.amount for l in all_loans if l.status in ["approved", "completed", "overdue"])
    total_received = 0
    total_outstanding = 0
    
    for loan in all_loans:
        paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        total_received += paid
        if loan.status in ["approved", "overdue"]:
            total_outstanding += (loan.total_payable - paid)
    
    collection_rate = (total_received / total_disbursed * 100) if total_disbursed > 0 else 0
    
    # Get monthly trends (last 6 months)
    monthly_trends = get_monthly_trends(db, user.sacco_id)
    
    # Get top performing loans
    top_loans = get_top_performing_loans(db, user.sacco_id)
    
    # Get upcoming payments (next 30 days)
    upcoming_payments = get_upcoming_payments_analytics(db, user.sacco_id)
    
    # Get payment method distribution
    payment_methods = get_payment_method_distribution(db, user.sacco_id)
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("credit_officer/analytics.html", {
        "request": request,
        "user": user,
        "status_counts": status_counts,
        "total_disbursed": total_disbursed,
        "total_received": total_received,
        "total_outstanding": total_outstanding,
        "collection_rate": collection_rate,
        "monthly_trends": monthly_trends,
        "top_loans": top_loans,
        "upcoming_payments": upcoming_payments,
        "payment_methods": payment_methods,
        **helpers
    })

# Helper functions
def get_monthly_payment_data(db: Session, sacco_id: int, start_date: datetime, end_date: datetime):
    """Get monthly payment data for chart"""
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
    
    # Combine data
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
        # Add collection amount
        idx = months.index(c.month) if c.month in months else -1
        if idx >= 0:
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
    loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(["approved", "completed"])
    ).limit(limit).all()
    
    top_loans = []
    for loan in loans:
        paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        repayment_rate = (paid / loan.total_payable * 100) if loan.total_payable > 0 else 0
        member = db.query(User).filter(User.id == loan.user_id).first()
        
        top_loans.append({
            "loan": loan,
            "member": member,
            "repayment_rate": repayment_rate,
            "paid": paid
        })
    
    return sorted(top_loans, key=lambda x: x["repayment_rate"], reverse=True)[:limit]

def get_upcoming_payments_analytics(db: Session, sacco_id: int):
    """Get upcoming payments for next 30 days"""
    active_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "approved"
    ).all()
    
    upcoming = []
    for loan in active_loans:
        # Get last payment date
        last_payment = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()
        
        if last_payment:
            next_payment_date = last_payment.timestamp + timedelta(days=30)
        else:
            next_payment_date = loan.approved_at + timedelta(days=30) if loan.approved_at else datetime.utcnow()
        
        days_until_due = (next_payment_date - datetime.utcnow()).days
        
        if 0 <= days_until_due <= 30:
            upcoming.append({
                "loan": loan,
                "next_payment_date": next_payment_date,
                "days_until_due": days_until_due,
                "amount_due": loan.calculate_monthly_payment()
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