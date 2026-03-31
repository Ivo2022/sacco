# backend/routers/superadmin.py
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from ..core.dependencies import get_db, require_superadmin
from ..models import RoleEnum, Log, User, Sacco, Saving, Loan
from typing import Optional
import logging
from ..utils.helpers import get_template_helpers
from ..services.user_service import create_user
from ..services.sacco_service import create_sacco
from ..utils import create_log
from datetime import datetime, timedelta

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# SERIALIZERS (JSON-safe dictionaries for templates)
# =============================================================================

def serialize_sacco(sacco: Sacco) -> dict:
    """Convert Sacco ORM object to safe dict for templates"""
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
        "referred_by_id": sacco.referred_by_id,
        "referral_commission_paid": sacco.referral_commission_paid,
    }


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
        "is_staff": user.is_staff,
    }


def serialize_user_full(user: User) -> dict:
    """Full user info including computed properties"""
    base = serialize_user_basic(user)
    base.update({
        "linked_member_account_id": user.linked_member_account_id,
        "linked_admin_id": user.linked_admin_id,
        "dashboard_url": user.get_dashboard_url,
        "is_admin": user.is_admin,
        "can_approve_loans": user.can_approve_loans,
        "can_approve_deposits": user.can_approve_deposits,
        "can_manage_loans": user.can_manage_loans,
        "can_send_loan_reminders": user.can_send_loan_reminders,
        "can_view_all_transactions": user.can_view_all_transactions,
    })
    return base


def serialize_log(log: Log) -> dict:
    """Convert Log ORM object to safe dict"""
    return {
        "id": log.id,
        "user_id": log.user_id,
        "sacco_id": log.sacco_id,
        "action": log.action,
        "details": log.details,
        "ip_address": log.ip_address,
        "timestamp": log.timestamp.isoformat() if log.timestamp else None,
        "user_email": log.user.email if log.user else None,
        "sacco_name": log.sacco.name if log.sacco else None,
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
        "approval_notes": loan.approval_notes,
        "user_id": loan.user_id,
        "sacco_id": loan.sacco_id,
    }


# =============================================================================
# ROUTES
# =============================================================================
@router.head("/superadmin/dashboard", response_class=HTMLResponse)
@router.get("/superadmin/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(require_superadmin), db: Session = Depends(get_db)):
    """Super admin dashboard with overview of all SACCOs and managers"""
    templates = request.app.state.templates

    saccos_orm = db.query(Sacco).order_by(Sacco.name).all()
    saccos = [serialize_sacco(s) for s in saccos_orm]

    # Add computed counts
    for s in saccos:
        s["managers"] = db.query(User).filter(
            User.sacco_id == s["id"],
            User.role == RoleEnum.MANAGER
        ).count()
        s["total_members"] = db.query(User).filter(
            User.sacco_id == s["id"],
            User.role == RoleEnum.MEMBER
        ).count()

    users_orm = db.query(User).order_by(User.created_at.desc()).all()
    users = [serialize_user_full(u) for u in users_orm]

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "saccos": saccos,
        "users": users,
        "show_admin_controls": True,
        **helpers,
    }
    return templates.TemplateResponse(request, "superadmin/dashboard.html", context)


@router.post("/superadmin/sacco/create")
def create_sacco_route(
    request: Request,
    name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    """Create a new SACCO"""
    sacco = create_sacco(db, name=name, email=email, phone=phone, address=address)

    # Log the creation
    create_log(db, "SACCO_CREATED", user.id, sacco.id, f"SACCO '{sacco.name}' created")

    request.session["flash_message"] = f"SACCO '{sacco.name}' created successfully!"
    request.session["flash_type"] = "success"
    return RedirectResponse(url="/superadmin/dashboard", status_code=303)

@router.head("/superadmin/managers", response_class=HTMLResponse)
@router.get("/superadmin/managers", response_class=HTMLResponse)
def list_managers(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin)
):
    """List all managers across all SACCOs"""
    templates = request.app.state.templates

    managers_orm = db.query(User).filter(
        User.role == RoleEnum.MANAGER
    ).order_by(User.created_at.desc()).all()

    managers = []
    for m in managers_orm:
        sacco = db.query(Sacco).filter(Sacco.id == m.sacco_id).first()
        sacco_name = sacco.name if sacco else "Not Assigned"

        staff_count = 0
        if m.sacco_id:
            staff_count = db.query(User).filter(
                User.sacco_id == m.sacco_id,
                User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
            ).count()

        m_dict = serialize_user_full(m)
        m_dict["sacco_name"] = sacco_name
        m_dict["staff_count"] = staff_count
        managers.append(m_dict)

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "managers": managers,
        "show_admin_controls": True,
        **helpers,
    }
    return templates.TemplateResponse(request,"superadmin/managers.html", context)


@router.post("/superadmin/sacco/create-manager")
def create_sacco_manager(
    request: Request,
    sacco_id: int = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    create_member_account: bool = Form(True),
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin)
):
    """Create a Manager for a SACCO (who will then manage staff)"""
    try:
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

        # Create the Manager account
        manager = create_user(
            db,
            email=email,
            password=password,
            role=RoleEnum.MANAGER,
            sacco_id=sacco_id,
            full_name=full_name,
            username=username,
            is_staff=True,
            can_apply_for_loans=False,
            can_receive_dividends=False
        )

        # Create linked member account if requested
        if create_member_account:
            member_email = f"{email.split('@')[0]}_member@{email.split('@')[1]}"
            member_username = f"{username}_member"

            member = create_user(
                db,
                email=member_email,
                password=password,
                role=RoleEnum.MEMBER,
                sacco_id=sacco_id,
                full_name=f"{full_name} (Member Account)",
                username=member_username,
                is_staff=True,
                can_apply_for_loans=True,
                can_receive_dividends=True,
                requires_approval_for_loans=True
            )

            # Link accounts
            manager.linked_member_account_id = member.id
            member.linked_admin_id = manager.id
            db.commit()

            request.session["flash_message"] = (
                f"✓ Manager created successfully!\n"
                f"Manager login: {email}\n"
                f"Member login: {member_email}\n"
                f"Password: {password}"
            )
        else:
            request.session["flash_message"] = f"✓ Manager {full_name} created successfully!"

        request.session["flash_type"] = "success"

        # Log the creation
        create_log(db, "MANAGER_CREATED", user.id, sacco_id, f"Manager {email} created for SACCO ID {sacco_id}")

        return RedirectResponse(url=f"/superadmin/sacco/{sacco_id}", status_code=303)

    except Exception as e:
        logger.error(f"Error creating manager: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/superadmin/manager/{manager_id}/reset-password")
def reset_manager_password(
    manager_id: int,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    """Reset manager password"""
    from ..services import hash_password

    manager = db.query(User).filter(
        User.id == manager_id,
        User.role == RoleEnum.MANAGER
    ).first()

    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    if new_password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    manager.password_hash = hash_password(new_password)
    manager.password_reset_required = True
    db.commit()

    create_log(db, "MANAGER_PASSWORD_RESET", user.id, manager.sacco_id, f"Password reset for {manager.email}")

    request.session["flash_message"] = "Password reset successfully"
    request.session["flash_type"] = "success"

    return RedirectResponse(url=f"/superadmin/manager/{manager_id}", status_code=303)


@router.post("/superadmin/manager/{manager_id}/deactivate")
def deactivate_manager(
    manager_id: int,
    reason: str = Form(None),
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    """Deactivate a manager"""
    manager = db.query(User).filter(
        User.id == manager_id,
        User.role == RoleEnum.MANAGER
    ).first()

    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    if manager.id == user.id:
        raise HTTPException(status_code=403, detail="Cannot deactivate your own account")

    manager.is_active = False
    db.commit()

    create_log(db, "MANAGER_DEACTIVATED", user.id, manager.sacco_id,
               f"Manager {manager.email} deactivated. Reason: {reason or 'Not specified'}")

    request.session["flash_message"] = f"Manager {manager.full_name or manager.email} deactivated"
    request.session["flash_type"] = "warning"

    return RedirectResponse(url=f"/superadmin/manager/{manager_id}", status_code=303)


@router.post("/superadmin/manager/{manager_id}/activate")
def activate_manager(
    manager_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    """Activate a manager"""
    manager = db.query(User).filter(
        User.id == manager_id,
        User.role == RoleEnum.MANAGER
    ).first()

    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")

    manager.is_active = True
    db.commit()

    create_log(db, "MANAGER_ACTIVATED", user.id, manager.sacco_id, f"Manager {manager.email} activated")

    request.session["flash_message"] = f"Manager {manager.full_name or manager.email} activated"
    request.session["flash_type"] = "success"

    return RedirectResponse(url=f"/superadmin/manager/{manager_id}", status_code=303)

@router.head("/superadmin/manager/{manager_id}", response_class=HTMLResponse)
@router.get("/superadmin/manager/{manager_id}", response_class=HTMLResponse)
def view_manager(
    request: Request,
    manager_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    """View manager details and staff they've created"""
    templates = request.app.state.templates

    manager_orm = db.query(User).filter(
        User.id == manager_id,
        User.role == RoleEnum.MANAGER
    ).first()

    if not manager_orm:
        raise HTTPException(status_code=404, detail="Manager not found")

    manager = serialize_user_full(manager_orm)

    # Get the SACCO
    sacco_orm = db.query(Sacco).filter(Sacco.id == manager_orm.sacco_id).first()
    sacco = serialize_sacco(sacco_orm) if sacco_orm else None

    # Get staff created by this manager (Accountant, Credit Officer)
    staff_orm = db.query(User).filter(
        User.sacco_id == manager_orm.sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).order_by(User.created_at.desc()).all()
    staff = [serialize_user_basic(s) for s in staff_orm]

    # Get statistics
    total_members = db.query(User).filter(
        User.sacco_id == manager_orm.sacco_id,
        User.role == RoleEnum.MEMBER
    ).count()

    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == manager_orm.sacco_id,
        Saving.type == 'deposit'
    ).scalar() or 0

    total_loans = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == manager_orm.sacco_id
    ).scalar() or 0

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "manager": manager,
        "sacco": sacco,
        "staff": staff,
        "total_members": total_members,
        "total_savings": total_savings,
        "total_loans": total_loans,
        "show_admin_controls": True,
        **helpers,
    }
    return templates.TemplateResponse(request,"superadmin/manager_detail.html", context)

@router.head("/superadmin/sacco/{sacco_id}", response_class=HTMLResponse)
@router.get("/superadmin/sacco/{sacco_id}", response_class=HTMLResponse)
def view_sacco(
    request: Request,
    sacco_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    """View SACCO details and its manager"""
    templates = request.app.state.templates

    sacco_orm = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    if not sacco_orm:
        raise HTTPException(status_code=404, detail="SACCO not found")

    sacco = serialize_sacco(sacco_orm)

    # Get the manager for this SACCO (only one manager per SACCO)
    manager_orm = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MANAGER
    ).first()
    manager = serialize_user_full(manager_orm) if manager_orm else None

    # Get all staff (Accountant, Credit Officer) for this SACCO
    staff_orm = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).all()
    staff = [serialize_user_basic(s) for s in staff_orm]

    members_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    ).count()

    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id,
        Saving.type == 'deposit'
    ).scalar() or 0

    total_loans = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "sacco": sacco,
        "manager": manager,
        "staff": staff,
        "members_count": members_count,
        "total_savings": total_savings,
        "total_loans": total_loans,
        "show_admin_controls": True,
        **helpers,
    }
    return templates.TemplateResponse(request,"superadmin/sacco_detail.html", context)

@router.head("/superadmin/saccos", response_class=HTMLResponse)
@router.get("/superadmin/saccos", response_class=HTMLResponse)
def manage_saccos(request: Request, user=Depends(require_superadmin), db: Session = Depends(get_db)):
    """List all SACCOs with their managers"""
    templates = request.app.state.templates

    saccos_orm = db.query(Sacco).order_by(Sacco.name).all()
    saccos = []
    for s in saccos_orm:
        manager_orm = db.query(User).filter(
            User.sacco_id == s.id,
            User.role == RoleEnum.MANAGER
        ).first()
        members_count = db.query(User).filter(
            User.sacco_id == s.id,
            User.role == RoleEnum.MEMBER
        ).count()

        s_dict = serialize_sacco(s)
        s_dict["manager"] = serialize_user_full(manager_orm) if manager_orm else None
        s_dict["members_count"] = members_count
        saccos.append(s_dict)
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "saccos": saccos,
        "show_admin_controls": True,
        **helpers
    }
    return templates.TemplateResponse(request,"superadmin/saccos.html", context)

@router.head("/superadmin/staff", response_class=HTMLResponse)
@router.get("/superadmin/staff", response_class=HTMLResponse)
def manage_staff(request: Request, user=Depends(require_superadmin), db: Session = Depends(get_db)):
    """View all staff (Accountants and Credit Officers) across all SACCOs"""
    templates = request.app.state.templates

    accountants_orm = db.query(User).filter(User.role == RoleEnum.ACCOUNTANT).order_by(User.created_at.desc()).all()
    accountants = [serialize_user_full(a) for a in accountants_orm]

    credit_officers_orm = db.query(User).filter(User.role == RoleEnum.CREDIT_OFFICER).order_by(User.created_at.desc()).all()
    credit_officers = [serialize_user_full(c) for c in credit_officers_orm]

    context = {
        "request": request,
        "user": serialize_user_full(user),
        "accountants": accountants,
        "credit_officers": credit_officers,
        "show_admin_controls": True,
    }
    return templates.TemplateResponse(request,"superadmin/staff.html", context)

@router.head("/superadmin/sacco/{sacco_id}/edit", response_class=HTMLResponse)
@router.get("/superadmin/sacco/{sacco_id}/edit", response_class=HTMLResponse)
def edit_sacco_form(
    request: Request,
    sacco_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin)
):
    """Display form to edit SACCO details"""
    templates = request.app.state.templates

    sacco_orm = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    if not sacco_orm:
        raise HTTPException(status_code=404, detail="SACCO not found")

    sacco = serialize_sacco(sacco_orm)

    context = {
        "request": request,
        "user": serialize_user_full(user),
        "sacco": sacco,
        "show_admin_controls": True,
    }
    return templates.TemplateResponse(request,"superadmin/sacco_edit.html", context)


@router.post("/superadmin/sacco/{sacco_id}/edit")
def edit_sacco(
    request: Request,
    sacco_id: int,
    name: str = Form(...),
    email: str = Form(None),
    phone: str = Form(None),
    address: str = Form(None),
    registration_no: str = Form(None),
    website: str = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin)
):
    """Update SACCO details"""
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    if not sacco:
        raise HTTPException(status_code=404, detail="SACCO not found")

    if name != sacco.name:
        existing = db.query(Sacco).filter(Sacco.name == name).first()
        if existing:
            raise HTTPException(status_code=400, detail="SACCO name already exists")
        sacco.name = name

    sacco.email = email
    sacco.phone = phone
    sacco.address = address
    sacco.registration_no = registration_no
    sacco.website = website
    db.commit()

    create_log(db, "SACCO_UPDATED", user.id, sacco.id, f"SACCO {sacco.name} details updated")

    request.session["flash_message"] = "SACCO details updated successfully!"
    request.session["flash_type"] = "success"

    return RedirectResponse(url=f"/superadmin/sacco/{sacco_id}", status_code=303)


@router.post("/superadmin/sacco/{sacco_id}/status")
def update_sacco_status(
    request: Request,
    sacco_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin)
):
    """Update SACCO status (active/inactive/suspended)"""
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    if not sacco:
        raise HTTPException(status_code=404, detail="SACCO not found")

    valid_statuses = ['active', 'inactive', 'suspended']
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    old_status = sacco.status
    sacco.status = status
    db.commit()

    create_log(db, "SACCO_STATUS_UPDATED", user.id, sacco.id,
               f"SACCO {sacco.name} status changed from {old_status} to {status}")

    request.session["flash_message"] = f"SACCO status updated to {status}"
    request.session["flash_type"] = "success"

    return RedirectResponse(url=f"/superadmin/sacco/{sacco_id}", status_code=303)

@router.head("/superadmin/logs", response_class=HTMLResponse)
@router.get("/superadmin/logs")
def superadmin_logs(
    request: Request,
    action: str = Query(None, description="Filter by action type"),
    user_id: int = Query(None, description="Filter by user ID"),
    sacco_id: int = Query(None, description="Filter by SACCO ID"),
    date_from: str = Query(None, description="Filter from date (YYYY-MM-DD)"),
    date_to: str = Query(None, description="Filter to date (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    """View all system logs (superadmin only)"""
    templates = request.app.state.templates

    query = db.query(Log)

    if action:
        query = query.filter(Log.action == action)
    if user_id:
        query = query.filter(Log.user_id == user_id)
    if sacco_id:
        query = query.filter(Log.sacco_id == sacco_id)
    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Log.timestamp >= from_date)
        except ValueError:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Log.timestamp <= to_date)
        except ValueError:
            pass

    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    offset = (page - 1) * per_page
    logs_orm = query.order_by(desc(Log.timestamp)).offset(offset).limit(per_page).all()
    logs = [serialize_log(l) for l in logs_orm]

    # Get filter options
    action_types = [a[0] for a in db.query(Log.action).distinct().all()]

    users_orm = db.query(User).filter(User.role != RoleEnum.SUPER_ADMIN).order_by(User.email).all()
    users = [serialize_user_basic(u) for u in users_orm]

    saccos_orm = db.query(Sacco).order_by(Sacco.name).all()
    saccos = [serialize_sacco(s) for s in saccos_orm]

    # Statistics
    total_logs = db.query(func.count(Log.id)).scalar()
    logs_today = db.query(func.count(Log.id)).filter(
        Log.timestamp >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ).scalar()

    recent_actions = {}
    for action_type in action_types[:10]:
        recent_actions[action_type] = db.query(func.count(Log.id)).filter(
            Log.action == action_type,
            Log.timestamp >= datetime.now() - timedelta(days=7)
        ).scalar()

    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": serialize_user_full(user),
        "logs": logs,
        "action_filter": action,
        "user_filter": user_id,
        "sacco_filter": sacco_id,
        "date_from": date_from,
        "date_to": date_to,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
        "action_types": action_types,
        "users": users,
        "saccos": saccos,
        "total_logs": total_logs,
        "logs_today": logs_today,
        "recent_actions": recent_actions,
        **helpers,
    }
    return templates.TemplateResponse(request,"superadmin/logs.html", context)

@router.head("/superadmin/logs/export", response_class=HTMLResponse)
@router.get("/superadmin/logs/export")
def export_logs(
    request: Request,
    action: str = Query(None),
    user_id: int = Query(None),
    sacco_id: int = Query(None),
    date_from: str = Query(None),
    date_to: str = Query(None),
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    """Export logs to CSV"""
    query = db.query(Log)

    if action:
        query = query.filter(Log.action == action)
    if user_id:
        query = query.filter(Log.user_id == user_id)
    if sacco_id:
        query = query.filter(Log.sacco_id == sacco_id)
    if date_from:
        try:
            from_date = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Log.timestamp >= from_date)
        except ValueError:
            pass
    if date_to:
        try:
            to_date = datetime.strptime(date_to, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(Log.timestamp <= to_date)
        except ValueError:
            pass

    logs_orm = query.order_by(desc(Log.timestamp)).all()

    import csv
    from io import StringIO
    from fastapi.responses import StreamingResponse

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(['ID', 'Timestamp', 'User', 'SACCO', 'Action', 'Details', 'IP Address'])

    for log in logs_orm:
        user_name = ""
        if log.user_id:
            user_obj = db.query(User).filter(User.id == log.user_id).first()
            user_name = user_obj.email if user_obj else f"User {log.user_id}"

        sacco_name = ""
        if log.sacco_id:
            sacco_obj = db.query(Sacco).filter(Sacco.id == log.sacco_id).first()
            sacco_name = sacco_obj.name if sacco_obj else f"SACCO {log.sacco_id}"

        writer.writerow([
            log.id,
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            user_name,
            sacco_name,
            log.action,
            log.details or "",
            log.ip_address or ""
        ])

    output.seek(0)
    filename = f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )