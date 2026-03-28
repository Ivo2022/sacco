# backend/routers/superadmin.py

from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..core.dependencies import get_db, require_superadmin
from ..core.database import get_db
from ..models import RoleEnum, Log, User, Sacco
from sqlalchemy import func, desc
from typing import Optional
import logging
from ..utils.helpers import get_template_helpers
from ..services.user_service import create_user
from ..services.sacco_service import create_sacco
from ..utils import create_log
from datetime import datetime, timedelta
router = APIRouter()
# templates = Jinja2Templates(directory="backend/templates")
logger = logging.getLogger(__name__)

def get_templates(request: Request):
    """Helper function to get templates from app state"""
    if hasattr(request.app.state, 'templates'):
        return request.app.state.templates
		
    from fastapi.templating import Jinja2Templates
    from pathlib import Path
    templates_dir = Path(__file__).parent.parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))

def set_templates(templates_obj: Jinja2Templates):
    """Set templates for the router"""
    global templates
    templates = templates_obj

@router.get("/superadmin/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user=Depends(require_superadmin), db: Session = Depends(get_db)):
    templates = get_templates(request)
    """Super admin dashboard with overview of all SACCOs and managers"""
    from ..models import Sacco, User
	
    saccos = db.query(Sacco).order_by(Sacco.name).all()
    
    # Get managers for each SACCO
    for sacco in saccos:
        sacco.managers = db.query(User).filter(
            User.sacco_id == sacco.id,
            User.role == RoleEnum.MANAGER
        ).count()
        sacco.total_members = db.query(User).filter(
            User.sacco_id == sacco.id,
            User.role == RoleEnum.MEMBER
        ).count()
    
    users = db.query(User).order_by(User.created_at.desc()).all()
    
    return templates.TemplateResponse("superadmin/dashboard.html", {
        "request": request,
        "user": user,
        "saccos": saccos,
        "users": users,
        "show_admin_controls": True
    })


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
    
    return RedirectResponse(url="/superadmin/dashboard", status_code=303)

# backend/routers/superadmin.py

@router.get("/superadmin/managers", response_class=HTMLResponse)
def list_managers(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin)
):
    templates = get_templates(request)
    """List all managers across all SACCOs"""
    from ..models import User, Sacco
    
    # Get all users with role MANAGER
    managers = db.query(User).filter(
        User.role == RoleEnum.MANAGER
    ).order_by(User.created_at.desc()).all()
    
    # Get SACCO details for each manager
    for manager in managers:
        sacco = db.query(Sacco).filter(Sacco.id == manager.sacco_id).first()
        manager.sacco_name = sacco.name if sacco else "Not Assigned"
        
        # Get staff count (Accountants + Credit Officers) for this manager's SACCO
        if manager.sacco_id:
            staff_count = db.query(User).filter(
                User.sacco_id == manager.sacco_id,
                User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
            ).count()
            manager.staff_count = staff_count
        else:
            manager.staff_count = 0
    helpers = get_template_helpers()
    return templates.TemplateResponse("superadmin/managers.html", {
        "request": request,
        "user": user,
        "managers": managers,
        "show_admin_controls": True,
		**helpers
    })

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
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    templates = get_templates(request)
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


@router.get("/superadmin/manager/{manager_id}", response_class=HTMLResponse)
def view_manager(
    request: Request,
    manager_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    templates = get_templates(request)
    """View manager details and staff they've created"""
    from ..models import User, Sacco
    
    manager = db.query(User).filter(
        User.id == manager_id,
        User.role == RoleEnum.MANAGER
    ).first()
    
    if not manager:
        raise HTTPException(status_code=404, detail="Manager not found")
    
    # Get the SACCO
    sacco = db.query(Sacco).filter(Sacco.id == manager.sacco_id).first()
    
    # Get staff created by this manager (Accountant, Credit Officer)
    staff = db.query(User).filter(
        User.sacco_id == manager.sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).order_by(User.created_at.desc()).all()
    
    # Get statistics
    total_members = db.query(User).filter(
        User.sacco_id == manager.sacco_id,
        User.role == RoleEnum.MEMBER
    ).count()
    
    from ..models import Saving, Loan
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == manager.sacco_id,
        Saving.type == 'deposit'
    ).scalar() or 0
    
    total_loans = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == manager.sacco_id
    ).scalar() or 0
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("superadmin/manager_detail.html", {
        "request": request,
        "user": user,
        "manager": manager,
        "sacco": sacco,
        "staff": staff,
        "total_members": total_members,
        "total_savings": total_savings,
        "total_loans": total_loans,
        "show_admin_controls": True,
		**helpers
    })


@router.get("/superadmin/sacco/{sacco_id}", response_class=HTMLResponse)
def view_sacco(
    request: Request,
    sacco_id: int,
    db: Session = Depends(get_db),
    user=Depends(require_superadmin)
):
    templates = get_templates(request)
    """View SACCO details and its manager"""
    from ..models import Sacco, User
    
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    if not sacco:
        raise HTTPException(status_code=404, detail="SACCO not found")
    
    # Get the manager for this SACCO (only one manager per SACCO)
    manager = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MANAGER
    ).first()
    
    # Get all staff (Accountant, Credit Officer) for this SACCO
    staff = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role.in_([RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).all()
    
    # Get member count
    members_count = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    ).count()
    
    # Get financial stats
    from ..models import Saving, Loan
    total_savings = db.query(func.sum(Saving.amount)).filter(
        Saving.sacco_id == sacco_id,
        Saving.type == 'deposit'
    ).scalar() or 0
    
    total_loans = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id
    ).scalar() or 0
	
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("superadmin/sacco_detail.html", {
        "request": request,
        "user": user,
        "sacco": sacco,
        "manager": manager,
        "staff": staff,
        "members_count": members_count,
        "total_savings": total_savings,
        "total_loans": total_loans,
        "show_admin_controls": True,
		**helpers
    })


@router.get("/superadmin/saccos", response_class=HTMLResponse)
def manage_saccos(request: Request, user=Depends(require_superadmin), db: Session = Depends(get_db)):
    templates = get_templates(request)
    """List all SACCOs with their managers"""
    from ..models import Sacco, User
    
    saccos = db.query(Sacco).order_by(Sacco.name).all()
    
    # Get manager for each SACCO
    for sacco in saccos:
        manager = db.query(User).filter(
            User.sacco_id == sacco.id,
            User.role == RoleEnum.MANAGER
        ).first()
        sacco.manager = manager
        sacco.members_count = db.query(User).filter(
            User.sacco_id == sacco.id,
            User.role == RoleEnum.MEMBER
        ).count()
    
    return templates.TemplateResponse("superadmin/saccos.html", {
        "request": request,
        "user": user,
        "saccos": saccos,
        "show_admin_controls": True
    })


@router.get("/superadmin/staff", response_class=HTMLResponse)
def manage_staff(request: Request, user=Depends(require_superadmin), db: Session = Depends(get_db)):
    templates = get_templates(request)
    """View all staff (Accountants and Credit Officers) across all SACCOs"""
    from ..models import User
    
    accountants = db.query(User).filter(User.role == RoleEnum.ACCOUNTANT).order_by(User.created_at.desc()).all()
    credit_officers = db.query(User).filter(User.role == RoleEnum.CREDIT_OFFICER).order_by(User.created_at.desc()).all()
    
    return templates.TemplateResponse("superadmin/staff.html", {
        "request": request,
        "user": user,
        "accountants": accountants,
        "credit_officers": credit_officers,
        "show_admin_controls": True
    })


@router.get("/superadmin/sacco/{sacco_id}/edit", response_class=HTMLResponse)
def edit_sacco_form(
    request: Request,
    sacco_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_superadmin)
):
    templates = get_templates(request)
    """Display form to edit SACCO details"""
    from ..models import Sacco
    
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    if not sacco:
        raise HTTPException(status_code=404, detail="SACCO not found")
    
    return templates.TemplateResponse("superadmin/sacco_edit.html", {
        "request": request,
        "user": user,
        "sacco": sacco,
        "show_admin_controls": True
    })


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
    from ..models import Sacco, Log
    
    # Get the SACCO
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    if not sacco:
        raise HTTPException(status_code=404, detail="SACCO not found")
    
    # Check if name is being changed and if it's already taken
    if name != sacco.name:
        existing = db.query(Sacco).filter(Sacco.name == name).first()
        if existing:
            raise HTTPException(status_code=400, detail="SACCO name already exists")
        sacco.name = name
    
    # Update other fields
    sacco.email = email
    sacco.phone = phone
    sacco.address = address
    sacco.registration_no = registration_no
    sacco.website = website
    
    db.commit()
    
    # Create audit log
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
    from ..models import Sacco
    
    # Get the SACCO
    sacco = db.query(Sacco).filter(Sacco.id == sacco_id).first()
    if not sacco:
        raise HTTPException(status_code=404, detail="SACCO not found")
    
    # Validate status
    valid_statuses = ['active', 'inactive', 'suspended']
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    
    # Update status
    old_status = sacco.status
    sacco.status = status
    
    db.commit()
    
    # Create audit log
    create_log(db, "SACCO_STATUS_UPDATED", user.id, sacco.id, 
               f"SACCO {sacco.name} status changed from {old_status} to {status}")
    
    # Set flash message
    request.session["flash_message"] = f"SACCO status updated to {status}"
    request.session["flash_type"] = "success"
    
    return RedirectResponse(url=f"/superadmin/sacco/{sacco_id}", status_code=303)

	
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
    templates = get_templates(request)
    """View all system logs (superadmin only)"""
    
    templates = get_templates(request)
    
    # Build query
    query = db.query(Log)
    
    # Apply filters
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
    
    # Get total count
    total = query.count()
    total_pages = (total + per_page - 1) // per_page
    
    # Apply pagination
    offset = (page - 1) * per_page
    logs = query.order_by(desc(Log.timestamp)).offset(offset).limit(per_page).all()
    
    # Get related data for each log
    for log in logs:
        # Get user info
        if log.user_id:
            log.user = db.query(User).filter(User.id == log.user_id).first()
        
        # Get SACCO info
        if log.sacco_id:
            from ..models import Sacco
            log.sacco = db.query(Sacco).filter(Sacco.id == log.sacco_id).first()
    
    # Get filter options
    action_types = db.query(Log.action).distinct().all()
    action_types = [a[0] for a in action_types]
    
    users = db.query(User).filter(User.role != RoleEnum.SUPER_ADMIN).order_by(User.email).all()
    
    from ..models import Sacco
    saccos = db.query(Sacco).order_by(Sacco.name).all()
    
    # Get statistics
    total_logs = db.query(func.count(Log.id)).scalar()
    logs_today = db.query(func.count(Log.id)).filter(
        Log.timestamp >= datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    ).scalar()
    
    # Get recent actions count
    recent_actions = {}
    for action_type in action_types[:10]:
        recent_actions[action_type] = db.query(func.count(Log.id)).filter(
            Log.action == action_type,
            Log.timestamp >= datetime.now() - timedelta(days=7)
        ).scalar()
    
    helpers = get_template_helpers()
    
    return templates.TemplateResponse("superadmin/logs.html", {
        "request": request,
        "user": user,
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
        **helpers
    })


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
    templates = get_templates(request)
    """Export logs to CSV"""
    
    # Build query
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
    
    logs = query.order_by(desc(Log.timestamp)).all()
    
    # Create CSV
    import csv
    from io import StringIO
    from fastapi.responses import StreamingResponse
    
    output = StringIO()
    writer = csv.writer(output)
    
    # Write headers
    writer.writerow(['ID', 'Timestamp', 'User', 'SACCO', 'Action', 'Details', 'IP Address'])
    
    # Write data
    for log in logs:
        user_name = ""
        if log.user_id:
            user = db.query(User).filter(User.id == log.user_id).first()
            user_name = user.email if user else f"User {log.user_id}"
        
        sacco_name = ""
        if log.sacco_id:
            from ..models import Sacco
            sacco = db.query(Sacco).filter(Sacco.id == log.sacco_id).first()
            sacco_name = sacco.name if sacco else f"SACCO {log.sacco_id}"
        
        writer.writerow([
            log.id,
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            user_name,
            sacco_name,
            log.action,
            log.details or "",
            log.ip_address or ""
        ])
    
    # Prepare response
    output.seek(0)
    filename = f"logs_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )