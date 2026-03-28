from fastapi import APIRouter, Depends, Request, Form, HTTPException, Query
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
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
templates = Jinja2Templates(directory="backend/templates")
logger = logging.getLogger(__name__)

def require_manager(user=Depends(require_role(RoleEnum.MANAGER))):
    return user

@router.get("/manager/dashboard")
def manager_dashboard(
    request: Request, 
    db: Session = Depends(get_db), 
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    sacco_id = user.sacco_id
    
    # Get pending loans
    pending_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "pending"
    ).count()
    
    # Get approved loans
    approved_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "approved"
    ).count()
    
    # Get completed loans
    completed_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "completed"
    ).count()
    
    # Get overdue loans
    overdue_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "overdue"
    ).count()
    
    # Get pending deposits
    pending_deposits = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == sacco_id,
        PendingDeposit.status == "pending"
    ).count()
    
    # Total pending notifications
    pending_notifications = pending_loans + pending_deposits
    
    # Get recent pending items for display
    recent_pending_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "pending"
    ).order_by(Loan.timestamp.desc()).limit(5).all()
    
    recent_pending_deposits = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).limit(5).all()
    
    # Get recent activities
    recent_activities = db.query(Log).filter(
        Log.sacco_id == sacco_id
    ).order_by(Log.timestamp.desc()).limit(10).all()
    
    # Get staff counts
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
    
    # Get member counts
    member_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    ).count()
    
    active_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_active == True
    ).count()
    
    # Get new members this month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_members_this_month = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.created_at >= month_start
    ).count()
    
    # Get pending member approvals count
    pending_members_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False,
        User.is_active == False
    ).count()
	
    # Total savings
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id
    ).scalar() or 0
    
    # Total loan amount
    total_loan_amount = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0
    
    # Active loans count
    active_loans_count = approved_loans
    
    # Get 30-day transaction totals
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    transactions_30d = db.query(Saving).filter(
        Saving.sacco_id == sacco_id,
        Saving.timestamp >= thirty_days_ago
    ).all()
    
    total_deposits_30d = sum(t.amount for t in transactions_30d if t.type == "deposit")
    total_withdrawals_30d = sum(t.amount for t in transactions_30d if t.type == "withdrawal")
    transaction_count_30d = len(transactions_30d)
    
    stats = get_sacco_statistics(db, sacco_id)
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/dashboard.html", {
        "request": request,
        "user": user,
        # Notification counts
        "pending_notifications": pending_notifications,
        "pending_loans": pending_loans,
        "pending_deposits": pending_deposits,
        # Loan status counts
        "approved_loans": approved_loans,
        "completed_loans": completed_loans,
        "overdue_loans": overdue_loans,
        "active_loans_count": active_loans_count,
        # Financial totals
        "total_savings": total_savings,
        "total_loan_amount": total_loan_amount,
        # Member counts
        "member_count": member_count,
        "active_members": active_members,
        "new_members_this_month": new_members_this_month,
        # Staff counts
        "staff_count": staff_count,
        "accountant_count": accountant_count,
        "credit_officer_count": credit_officer_count,
        # Recent items
        "recent_pending_loans": recent_pending_loans,
        "recent_pending_deposits": recent_pending_deposits,
        "recent_activities": recent_activities,
		"pending_members_count": pending_members_count,
        # 30-day transaction stats
        "total_deposits_30d": total_deposits_30d,
        "total_withdrawals_30d": total_withdrawals_30d,
        "transaction_count_30d": transaction_count_30d,
        # Additional stats from service
        **stats,
        **helpers
    })

@router.get("/manager/pending-members")
def pending_members(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """View pending member approvals"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Get pending members (not approved, not staff-created)
    pending_members = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False,
        User.is_active == False  # Not yet activated
    ).order_by(User.created_at.desc()).all()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/pending_members.html", {
        "request": request,
        "user": user,
        "pending_members": pending_members,
        "pending_count": len(pending_members),
        **helpers
    })


@router.post("/manager/member/{member_id}/approve")
def approve_member(
    request: Request,
    member_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """Approve a pending member"""
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
    
    # Approve member
    member.is_approved = True
    member.is_active = True
    member.approved_at = datetime.utcnow()
    member.approved_by = user.id
    
    db.commit()
    
    # Log approval
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
    """Reject a pending member"""
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
    
    # Mark as rejected (delete or mark inactive)
    member.is_active = False
    member.rejection_reason = reason
    member.approved_at = datetime.utcnow()
    member.approved_by = user.id
    
    db.commit()
    
    # Log rejection
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
    
    # Get loan details for review
    loan = db.query(Loan).filter(
        Loan.id == loan_id, 
        Loan.sacco_id == user.sacco_id
    ).first()
    
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    
    # Get member information
    member = db.query(User).filter(User.id == loan.user_id).first()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/loan_review.html", {
        "request": request,
        "user": user,
        "loan": loan,
        "member": member,
        **helpers
    })

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
    
    # Approve loan
    loan.status = "approved"
    loan.approved_by = user.id
    loan.approved_at = datetime.now(timezone.utc)
    loan.approval_notes = approval_notes
    
    db.commit()
    
    # Log approval
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
    
    # Reject loan
    loan.status = "rejected"
    loan.approved_by = user.id
    loan.approved_at = datetime.now(timezone.utc)
    loan.approval_notes = rejection_reason
    
    db.commit()
    
    # Log rejection
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
    
    loans = db.query(Loan).filter(
        Loan.sacco_id == user.sacco_id,
        Loan.status == "pending"
    ).order_by(Loan.timestamp.desc()).all()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/pending_loans.html", {
        "request": request,
        "user": user,
        "loans": loans,
        "pending_count": len(loans),
        **helpers
    })

@router.get("/manager/staff")
def manage_staff(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    staff = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).all()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/staff.html", {
        "request": request,
        "user": user,
        "staff": staff,
        **helpers
    })

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
        # Validate role
        if role not in ["ACCOUNTANT", "CREDIT_OFFICER"]:
            raise HTTPException(status_code=400, detail="Invalid role")
        
        role_enum = RoleEnum.ACCOUNTANT if role == "ACCOUNTANT" else RoleEnum.CREDIT_OFFICER
        
        # Check if email already exists
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            request.session["flash_message"] = f"✗ Email {email} already exists"
            request.session["flash_type"] = "error"
            return RedirectResponse(url="/manager/staff", status_code=303)
        
        # Generate username
        username = full_name.lower().replace(' ', '.')
        username = ''.join(c for c in username if c.isalnum() or c == '.')
        
        base_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1
        
        # Create staff account
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
        
        # Create linked member account for staff
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
        
        # Link accounts
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
        
        # Log creation
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
    
    sacco_id = user.sacco_id
    
    # Get statistics for preview
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
    
    # Optional: Add more statistics
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
    
    return templates.TemplateResponse("manager/reports.html", {
        "request": request,
        "user": user,
        "active_loans_count": active_loans_count,
        "total_savings": total_savings,
        "member_count": member_count,
        "staff_count": staff_count,
        "total_loan_amount": total_loan_amount,
        "pending_loans": pending_loans,
        "overdue_loans": overdue_loans,
        **helpers
    })
	
# Add these new routes to your existing manager.py
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
    """View all members in the SACCO"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    sacco_id = user.sacco_id
    
    # Build query
    query = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    )
    
    # Apply search filter
    if search:
        query = query.filter(
            or_(
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.phone.ilike(f"%{search}%"),
                User.username.ilike(f"%{search}%")
            )
        )
    
    # Apply status filter
    if status == "active":
        query = query.filter(User.is_active == True)
    elif status == "inactive":
        query = query.filter(User.is_active == False)
    
    # Apply sorting
    if sort == "newest":
        query = query.order_by(User.created_at.desc())
    elif sort == "oldest":
        query = query.order_by(User.created_at.asc())
    elif sort == "name_asc":
        query = query.order_by(User.full_name.asc())
    elif sort == "name_desc":
        query = query.order_by(User.full_name.desc())
    
    # Get total count before pagination
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    
    # Apply pagination
    offset = (page - 1) * per_page
    members = query.offset(offset).limit(per_page).all()
    
    # Get savings totals and loan counts for each member
    for member in members:
        # Get savings balance
        total_deposits = db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == member.id,
            Saving.type == "deposit"
        ).scalar() or 0
        
        total_withdrawals = db.query(func.sum(Saving.amount)).filter(
            Saving.user_id == member.id,
            Saving.type == "withdrawal"
        ).scalar() or 0
        
        member.savings_balance = total_deposits - total_withdrawals
        
        # Get active loans count
        member.active_loans = db.query(Loan).filter(
            Loan.user_id == member.id,
            Loan.status == "approved"
        ).count()
    
    # Get summary statistics
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id
    ).scalar() or 0
    
    total_active_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "approved"
    ).count()
    
    # Get new members this month
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    new_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.created_at >= month_start
    ).count()
    
    # Apply has_loans filter after getting member data
    if has_loans == "yes":
        members = [m for m in members if m.active_loans > 0]
        total = len(members)
    elif has_loans == "no":
        members = [m for m in members if m.active_loans == 0]
        total = len(members)
    
    # Apply savings sorting if needed
    if sort == "savings_desc":
        members = sorted(members, key=lambda x: x.savings_balance, reverse=True)
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/members.html", {
        "request": request,
        "user": user,
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
        **helpers
    })

@router.get("/manager/member/{member_id}")
def view_member_detail(
    request: Request,
    member_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """View detailed member information"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    member = db.query(User).filter(
        User.id == member_id,
        User.sacco_id == user.sacco_id,
        User.role == RoleEnum.MEMBER
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Get savings transactions
    savings = db.query(Saving).filter(
        Saving.user_id == member_id
    ).order_by(Saving.timestamp.desc()).all()
    
    # Get loans
    loans = db.query(Loan).filter(
        Loan.user_id == member_id
    ).order_by(Loan.timestamp.desc()).all()
    
    # Calculate totals
    total_deposits = sum(s.amount for s in savings if s.type == "deposit")
    total_withdrawals = sum(s.amount for s in savings if s.type == "withdrawal")
    savings_balance = total_deposits - total_withdrawals
    
    # Get loan statistics
    active_loans = [l for l in loans if l.status == "approved"]
    total_loan_amount = sum(l.amount for l in loans)
    total_paid = 0
    for loan in loans:
        paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        loan.total_paid = paid
        loan.outstanding = loan.total_payable - paid
        total_paid += paid
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/member_detail.html", {
        "request": request,
        "user": user,
        "member": member,
        "savings": savings,
        "loans": loans,
        "total_deposits": total_deposits,
        "total_withdrawals": total_withdrawals,
        "savings_balance": savings_balance,
        "total_loan_amount": total_loan_amount,
        "total_paid": total_paid,
        "active_loans_count": len(active_loans),
        **helpers
    })

@router.get("/manager/staff-activity")
def staff_activity(
    request: Request,
    role: str = Query(None, description="Filter by role: ACCOUNTANT, CREDIT_OFFICER"),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """View activity logs for staff members"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Get staff members
    staff_query = db.query(User).filter(
        User.sacco_id == user.sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    )
    
    if role:
        staff_query = staff_query.filter(User.role == RoleEnum(role))
    
    staff_members = staff_query.all()
    
    # Get recent activities for each staff member
    staff_activities = []
    for staff in staff_members:
        activities = db.query(Log).filter(
            Log.user_id == staff.id,
            Log.sacco_id == user.sacco_id
        ).order_by(Log.timestamp.desc()).limit(10).all()
        
        # Count actions by type
        action_counts = {
            "approvals": len([a for a in activities if "APPROVED" in a.action]),
            "rejections": len([a for a in activities if "REJECTED" in a.action]),
            "creations": len([a for a in activities if "CREATED" in a.action]),
            "reminders": len([a for a in activities if "REMINDER" in a.action])
        }
        
        staff_activities.append({
            "staff": staff,
            "recent_activities": activities[:5],
            "action_counts": action_counts,
            "total_actions": len(activities)
        })
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/staff_activity.html", {
        "request": request,
        "user": user,
        "staff_activities": staff_activities,
        "selected_role": role,
        **helpers
    })

@router.get("/manager/accountant-dashboard")
def view_accountant_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """View accountant's dashboard (read-only)"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Get pending deposits
    pending_deposits = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == user.sacco_id,
        PendingDeposit.status == "pending"
    ).order_by(PendingDeposit.timestamp.desc()).all()
    
    # Get recent transactions
    recent_transactions = db.query(Saving).filter(
        Saving.sacco_id == user.sacco_id
    ).order_by(Saving.timestamp.desc()).limit(20).all()
    
    # Get member info for transactions
    for tx in recent_transactions:
        tx.member = db.query(User).filter(User.id == tx.user_id).first()
    
    # Get summary statistics
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
    
    return templates.TemplateResponse("manager/accountant_view.html", {
        "request": request,
        "user": user,
        "pending_deposits": pending_deposits,
        "recent_transactions": recent_transactions,
        "total_savings": total_savings,
        "today_collections": today_collections,
        "pending_count": len(pending_deposits),
        **helpers
    })

@router.get("/manager/credit-officer-dashboard")
def view_credit_officer_dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """View credit officer's dashboard (read-only)"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Get active loans
    active_loans = db.query(Loan).filter(
        Loan.sacco_id == user.sacco_id,
        Loan.status == "approved"
    ).all()
    
    # Calculate loan details
    for loan in active_loans:
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
        
        # Determine if overdue (30+ days without payment)
        loan.is_overdue = loan.days_since_last_payment > 30
    
    # Get overdue loans
    overdue_loans = [l for l in active_loans if l.is_overdue]
    
    # Get recent reminders
    reminders = db.query(Log).filter(
        Log.sacco_id == user.sacco_id,
        Log.action == "LOAN_REMINDER_SENT"
    ).order_by(Log.timestamp.desc()).limit(20).all()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/credit_officer_view.html", {
        "request": request,
        "user": user,
        "active_loans": active_loans,
        "overdue_loans": overdue_loans,
        "reminders": reminders,
        "active_count": len(active_loans),
        "overdue_count": len(overdue_loans),
        **helpers
    })

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
    """View all transactions across the SACCO"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    # Build query
    query = db.query(Saving).filter(Saving.sacco_id == user.sacco_id)
    
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
    
    # Get member info
    for tx in transactions:
        tx.member = db.query(User).filter(User.id == tx.user_id).first()
    
    # Calculate totals
    total_deposits = sum(t.amount for t in transactions if t.type == "deposit")
    total_withdrawals = sum(t.amount for t in transactions if t.type == "withdrawal")
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/all_transactions.html", {
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

@router.get("/manager/all-loans")
def all_loans(
    request: Request,
    status: str = Query(None, description="Filter by loan status"),
    search: str = Query(None, description="Search by member name or email"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    db: Session = Depends(get_db),
    user=Depends(require_manager)
):
    """View all loans across the SACCO with filtering"""
    status_check = check_sacco_status(request, user, db)
    if status_check:
        return status_check
    
    sacco_id = user.sacco_id
    
    # Build query
    query = db.query(Loan).filter(Loan.sacco_id == sacco_id)
    
    # Apply status filter
    if status:
        query = query.filter(Loan.status == status)
    
    # Get total count before pagination
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    
    # Apply pagination
    offset = (page - 1) * per_page
    loans = query.order_by(Loan.timestamp.desc()).offset(offset).limit(per_page).all()
    
    # Get member info and payment data for each loan
    for loan in loans:
        loan.member = db.query(User).filter(User.id == loan.user_id).first()
        
        # Get total paid
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        
        loan.total_paid = total_paid
        loan.outstanding = loan.total_payable - total_paid
        loan.payment_percentage = (total_paid / loan.total_payable * 100) if loan.total_payable > 0 else 0
        loan.monthly_payment = loan.calculate_monthly_payment()
        
        # Get last payment date
        last_payment = db.query(LoanPayment).filter(
            LoanPayment.loan_id == loan.id
        ).order_by(LoanPayment.timestamp.desc()).first()
        
        if last_payment:
            loan.last_payment_date = last_payment.timestamp
            loan.days_since_last_payment = (datetime.utcnow() - last_payment.timestamp).days
        else:
            loan.last_payment_date = None
            loan.days_since_last_payment = (datetime.utcnow() - loan.approved_at).days if loan.approved_at else 0
        
        # Get approver info
        if loan.approved_by:
            loan.approver = db.query(User).filter(User.id == loan.approved_by).first()
    
    # Apply search filter after getting member data (since we need member info)
    if search:
        search_lower = search.lower()
        loans = [l for l in loans if (l.member and (search_lower in (l.member.full_name or "").lower() or 
                                                     search_lower in (l.member.email or "").lower()))]
        total = len(loans)
    
    # Get status counts for filter badges (use the original query without pagination)
    status_counts = {
        "pending": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "pending").count(),
        "approved": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "approved").count(),
        "completed": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "completed").count(),
        "overdue": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "overdue").count(),
        "rejected": db.query(Loan).filter(Loan.sacco_id == sacco_id, Loan.status == "rejected").count(),
    }
    
    # Get totals (using original query without pagination for accurate totals)
    total_loan_amount = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0
    
    # Get total outstanding (sum of all loans' outstanding amounts)
    all_loans_for_outstanding = db.query(Loan).filter(Loan.sacco_id == sacco_id).all()
    total_outstanding = 0
    for loan in all_loans_for_outstanding:
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        total_outstanding += (loan.total_payable - total_paid)
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("manager/all_loans.html", {
        "request": request,
        "user": user,
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
        **helpers
    })