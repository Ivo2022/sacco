# backend/routers/auth.py
from fastapi import APIRouter, Request, Form, Depends, Query, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import logging
from typing import Optional, cast
import re

from ..core import get_db, get_current_user
from ..services.user_service import authenticate_user, create_user
from ..models import RoleEnum, User, Sacco
from ..services.referral_service import ReferralService
from ..utils import create_log

router = APIRouter()
logger = logging.getLogger(__name__)


# ================= SERIALIZERS =================

def serialize_user(user: User) -> dict | None:
    if not user:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role.value if user.role else None,
        "is_active": user.is_active,
        "is_admin": user.is_admin,
    }

def serialize_sacco(sacco: Sacco) -> dict:
    return {
        "id": sacco.id,
        "name": sacco.name,
        "status": sacco.status,
    }

# ================= TEMPLATE HANDLER =================

def get_templates(request: Request):
    if hasattr(request.app.state, 'templates'):
        return request.app.state.templates
    templates_dir = Path(__file__).parent.parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))


# ================= LOGIN =================
@router.head("/login", response_class=HTMLResponse)
@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    templates = get_templates(request)
    context = {"request": request}
    return templates.TemplateResponse(request, "login.html", context)

@router.post("/login")
def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    templates = get_templates(request)

    user = authenticate_user(db, email=email, password=password)

    if not user:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid credentials"}
        )

    if not user.is_active:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Account is deactivated"}
        )

    # Session
    request.session["user_id"] = user.id

    create_log(
        db,
        action="USER_LOGIN",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"User {user.email} logged in"
    )

    role_redirects = {
        RoleEnum.SUPER_ADMIN: "/superadmin/dashboard",
        RoleEnum.MANAGER: "/manager/dashboard",
        RoleEnum.ACCOUNTANT: "/accountant/dashboard",
        RoleEnum.CREDIT_OFFICER: "/credit-officer/dashboard",
        RoleEnum.MEMBER: "/member/dashboard",
    }

    return RedirectResponse(
        url=role_redirects.get(user.role, "/member/dashboard"),
        status_code=303
    )


# ================= REGISTER =================
@router.head("/register", response_class=HTMLResponse)
@router.get("/register", response_class=HTMLResponse)
def register_form(
    request: Request,
    referral_code: Optional[str] = None,
    staff_registration: bool = False,
    db: Session = Depends(get_db)
):
    templates = get_templates(request)

    saccos = db.query(Sacco).filter(
        Sacco.status == 'active'
    ).order_by(Sacco.name).all()

    safe_saccos = [serialize_sacco(s) for s in saccos]

    context = {
        "request": request,
        "saccos": safe_saccos,
        "referral_code": referral_code,
        "staff_registration": staff_registration
        }
    return templates.TemplateResponse(request, "register.html", context)

@router.post("/register", response_class=HTMLResponse)
async def register_post(
    request: Request,
    email: str = Form(None),
    password: str = Form(None),
    username: str = Form(None),
    full_name: str = Form(None),
    phone: str = Form(None),
    sacco_id: int = Form(None),
    referral_code: Optional[str] = Form(None),
    staff_registration: bool = Form(False),
    db: Session = Depends(get_db)
):
    templates = get_templates(request)

    form_data = {
        "email": email,
        "username": username,
        "full_name": full_name,
        "phone": phone,
        "referral_code_input": referral_code,
        "sacco_id": sacco_id,
        "staff_registration": staff_registration
    }

    errors = []

    # Validation
    if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        errors.append("Valid email required")

    if not password or len(password) < 6:
        errors.append("Password must be at least 6 characters")

    if not username or len(username) < 3:
        errors.append("Username too short")

    if not sacco_id:
        errors.append("Select a SACCO")

    # If errors
    if errors:
        saccos = db.query(Sacco).filter(Sacco.status == 'active').all()
        safe_saccos = [serialize_sacco(s) for s in saccos]

        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "<br>".join(errors),
            "saccos": safe_saccos,
            **form_data
        })

    try:
        user = create_user(
            db,
            full_name=full_name,
            username=username,
            email=email,
            password=password,
            role=RoleEnum.MEMBER,
            sacco_id=sacco_id,
            phone=phone,
            is_active=staff_registration
        )

        request.session["flash_message"] = "Registration successful"
        request.session["flash_type"] = "success"

        return RedirectResponse("/auth/login", status_code=303)

    except Exception as e:
        logger.error(f"Registration error: {e}")

        saccos = db.query(Sacco).filter(Sacco.status == 'active').all()
        safe_saccos = [serialize_sacco(s) for s in saccos]

        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Registration failed",
            "saccos": safe_saccos,
            **form_data
        })


# ================= LOGOUT =================

@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")

    if user_id:
        create_log(
            db,
            action="USER_LOGOUT",
            user_id=user_id,
            sacco_id=None,
            details="User logged out"
        )

    request.session.clear()
    return RedirectResponse(url="/", status_code=303)


# ============ ACCOUNT SWITCHING ROUTES ============

@router.get("/switch-to-member")
def switch_to_member(
    request: Request,
    as_member: int = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Switch from staff account to linked member account"""
    
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    member_id = as_member or user.linked_member_account_id
    
    if not member_id:
        request.session["flash_message"] = "No member account linked"
        request.session["flash_type"] = "warning"
        return RedirectResponse(url=f"/{user.role.value.lower()}/dashboard", status_code=303)
    
    member = db.query(User).filter(
        User.id == member_id,
        User.role == RoleEnum.MEMBER
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Member account not found")
    
    staff_roles = [RoleEnum.MANAGER, RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER]
    
    if user.role in staff_roles and user.linked_member_account_id != member.id:
        raise HTTPException(status_code=403, detail="Not authorized to switch to this account")
    
    # Switch session
    request.session["user_id"] = member.id
    request.session["user_role"] = member.role.value
    request.session["original_staff_id"] = user.id
    
    request.session["flash_message"] = f"Switched to member view: {member.full_name or member.email}"
    request.session["flash_type"] = "info"
    
    return RedirectResponse(url="/member/dashboard", status_code=303)


@router.get("/switch-to-admin")
def switch_to_admin(
    request: Request,
    as_admin: int = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """Switch from member account to linked staff account"""
    
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    if as_admin:
        admin_id = as_admin
    else:
        admin_id = user.linked_admin_id
    
    if not admin_id:
        request.session["flash_message"] = "No staff account linked"
        request.session["flash_type"] = "warning"
        return RedirectResponse(url="/member/dashboard", status_code=303)
    
    admin = db.query(User).filter(
        User.id == admin_id,
        User.role.in_([RoleEnum.MANAGER, RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).first()
    
    if not admin:
        raise HTTPException(status_code=404, detail="Staff account not found")
    
    if admin.linked_member_account_id != user.id:
        raise HTTPException(status_code=403, detail="Not authorized to switch to this account")
    
    # Switch session
    request.session["user_id"] = admin.id
    request.session["user_role"] = admin.role.value
    
    request.session["flash_message"] = f"Switched to {admin.role.value} view: {admin.full_name or admin.email}"
    request.session["flash_type"] = "info"
    
    role_redirects = {
        RoleEnum.MANAGER: "/manager/dashboard",
        RoleEnum.ACCOUNTANT: "/accountant/dashboard",
        RoleEnum.CREDIT_OFFICER: "/credit-officer/dashboard",
    }
    
    redirect_url = role_redirects.get(admin.role, "/dashboard")
    return RedirectResponse(url=redirect_url, status_code=303)