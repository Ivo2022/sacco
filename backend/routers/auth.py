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

# Templates will be set from main.py
templates = None

def get_templates(request: Request):
    """Helper function to get templates from app state"""
    if hasattr(request.app.state, 'templates'):
        return request.app.state.templates
    # Fallback
    templates_dir = Path(__file__).parent.parent / "templates"
    return Jinja2Templates(directory=str(templates_dir))

def set_templates(templates_obj: Jinja2Templates):
    """Set templates for the router"""
    global templates
    templates = templates_obj


# ============ LOGIN ROUTES ============

@router.get("/login", response_class=HTMLResponse)
def login_get(request: Request):
    """Display login page"""
    templates = get_templates(request)
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
def login_post(
    request: Request, 
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    """Process login"""
    templates = get_templates(request)
    user = authenticate_user(db, email=email, password=password)
    
    if not user:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Invalid credentials"}
        )
    
    # Check if user is active
    if not user.is_active:
        return templates.TemplateResponse(
            "login.html", 
            {"request": request, "error": "Account is deactivated. Please contact administrator."}
        )
    
    # Store user in session
    request.session["user_id"] = user.id
    
    # Log login
    create_log(
        db,
        action="USER_LOGIN",
        user_id=user.id,
        sacco_id=user.sacco_id,
        details=f"User {user.email} logged in"
    )
    
    # Redirect based on role
    user_role = cast(RoleEnum, user.role)
    role_redirects = {
        RoleEnum.SUPER_ADMIN: "/superadmin/dashboard",
        RoleEnum.MANAGER: "/manager/dashboard",
        RoleEnum.ACCOUNTANT: "/accountant/dashboard",
        RoleEnum.CREDIT_OFFICER: "/credit-officer/dashboard",
        RoleEnum.MEMBER: "/member/dashboard",
    }
    
    redirect_url = role_redirects.get(user_role, "/member/dashboard")
    return RedirectResponse(url=redirect_url, status_code=303)


# ============ REGISTRATION ROUTES ============

@router.get("/register", response_class=HTMLResponse)
def register_form(
    request: Request, 
    referral_code: Optional[str] = None,
    staff_registration: bool = False,
    db: Session = Depends(get_db)
):
    """
    Show registration form
    
    - Regular users: self-register as members
    - Staff with staff_registration=true: can create accounts for members
    """
    templates = get_templates(request)
    
    # Get active SACCOs for dropdown
    saccos = db.query(Sacco).filter(Sacco.status == 'active').order_by(Sacco.name).all()
    
    return templates.TemplateResponse("register.html", {
        "request": request, 
        "saccos": saccos,
        "referral_code": referral_code,
        "staff_registration": staff_registration
    })


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
    """
    Register a new member with proper error handling
    """
    templates = get_templates(request)
    
    # Collect form data for re-rendering
    form_data = {
        "email": email,
        "username": username,
        "full_name": full_name,
        "phone": phone,
        "referral_code_input": referral_code,
        "sacco_id": sacco_id,
        "staff_registration": staff_registration
    }
    
    # Validation errors list
    errors = []
    
    # Validate required fields
    if not email:
        errors.append("Email address is required")
    elif not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        errors.append("Please enter a valid email address")
    
    if not password:
        errors.append("Password is required")
    elif len(password) < 6:
        errors.append("Password must be at least 6 characters long")
    
    if not username:
        errors.append("Username is required")
    elif len(username) < 3:
        errors.append("Username must be at least 3 characters long")
    
    if not sacco_id:
        errors.append("Please select a SACCO to register under")
    
    # Check if user already exists
    if email and not errors:
        existing_user = db.query(User).filter(User.email == email).first()
        if existing_user:
            errors.append(f"Email '{email}' is already registered. Please use a different email or login.")
    
    if username and not errors:
        existing_username = db.query(User).filter(User.username == username).first()
        if existing_username:
            errors.append(f"Username '{username}' is already taken. Please choose a different username.")
    
    # Validate SACCO exists and is active
    if sacco_id and not errors:
        sacco = db.query(Sacco).filter(
            Sacco.id == sacco_id,
            Sacco.status == 'active'
        ).first()
        
        if not sacco:
            errors.append("Selected SACCO is not available for registration")
    
    # If there are validation errors, re-render form with error messages
    if errors:
        saccos = db.query(Sacco).filter(Sacco.status == 'active').order_by(Sacco.name).all()
        
        # Format errors for display
        error_messages = "<br>".join(errors)
        
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": error_messages,
            "saccos": saccos,
            **form_data
        })
    
    try:
        # Determine if member needs approval
        requires_approval = not staff_registration
        
        # Create the new member
        user = create_user(
            db, 
            full_name=full_name, 
            username=username, 
            email=email, 
            password=password, 
            role=RoleEnum.MEMBER, 
            sacco_id=sacco_id,
            phone=phone,
            is_active=staff_registration,  # Staff-created accounts are active immediately
            requires_approval_for_loans=True
        )
        
        # Generate referral codes
        user.member_referral_code = ReferralService.generate_referral_code(user, "member")
        user.sacco_referral_code = ReferralService.generate_referral_code(user, "sacco")
        db.commit()
        
        # Process referral if provided
        referrer_info = None
        if referral_code:
            referral_result = ReferralService.apply_member_referral(db, user, referral_code)
            
            if referral_result["success"]:
                referrer = db.query(User).filter(User.id == referral_result["referrer_id"]).first()
                referrer_info = {
                    "referrer_name": referrer.full_name or referrer.email,
                    "current_tier": referral_result["current_tier"]
                }
                
                create_log(
                    db,
                    action="MEMBER_REFERRAL_APPLIED",
                    user_id=referrer.id,
                    sacco_id=user.sacco_id,
                    details=f"User {user.email} referred by {referrer.email}"
                )
        
        # Set success message
        if staff_registration:
            request.session["flash_message"] = (
                f"✓ Member {full_name or email} created successfully!\n"
                f"They can now log in with: {email}"
            )
            request.session["flash_type"] = "success"
            return RedirectResponse(url="/manager/staff", status_code=303)
        else:
            if requires_approval:
                request.session["flash_message"] = (
                    "✓ Registration successful! Your account requires approval.\n"
                    "You will be notified once your account is activated."
                )
            else:
                request.session["flash_message"] = "✓ Registration successful! Please login."
            
            request.session["flash_type"] = "success"
            
            if referrer_info:
                request.session["flash_message"] += f"\n\n🎉 You were referred by {referrer_info['referrer_name']}!"
            
            return RedirectResponse(url="/auth/login", status_code=303)
        
    except ValueError as e:
        # Handle validation errors from service layer
        saccos = db.query(Sacco).filter(Sacco.status == 'active').order_by(Sacco.name).all()
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": str(e),
            "saccos": saccos,
            **form_data
        })
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        saccos = db.query(Sacco).filter(Sacco.status == 'active').order_by(Sacco.name).all()
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Registration failed. Please try again or contact support.",
            "saccos": saccos,
            **form_data
        })

# ============ LOGOUT ROUTE ============

@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    """Logout user"""
    user_id = request.session.get("user_id")
    
    if user_id:
        # Log logout
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