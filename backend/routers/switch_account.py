from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..core.dependencies import get_db, get_current_user
from ..schemas import RoleEnum
from ..models import User
import logging

router = APIRouter(prefix="", tags=["account-switching"])
logger = logging.getLogger(__name__)


@router.get("/to-member")
async def switch_to_member(
    request: Request,
    as_member: int = Query(None, description="Member ID to switch to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Switch from staff account (Manager/Accountant/Credit Officer) to linked member account
    """
    # Check if user is authenticated
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Get the target member ID
    member_id = as_member or current_user.linked_member_account_id
    
    if not member_id:
        request.session["flash_message"] = "No member account linked to your staff account"
        request.session["flash_type"] = "warning"
        # Redirect based on role
        redirect_url = get_dashboard_url(current_user.role)
        return RedirectResponse(url=redirect_url, status_code=303)
    
    # Verify the member account exists and has MEMBER role
    member = db.query(User).filter(
        User.id == member_id,
        User.role == RoleEnum.MEMBER
    ).first()
    
    if not member:
        request.session["flash_message"] = "Member account not found"
        request.session["flash_type"] = "error"
        redirect_url = get_dashboard_url(current_user.role)
        return RedirectResponse(url=redirect_url, status_code=303)
    
    # Verify this staff account is linked to this member
    staff_roles = [RoleEnum.MANAGER, RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER]
    
    if current_user.role in staff_roles:
        if current_user.linked_member_account_id != member.id:
            request.session["flash_message"] = "Not authorized to switch to this member account"
            request.session["flash_type"] = "error"
            redirect_url = get_dashboard_url(current_user.role)
            return RedirectResponse(url=redirect_url, status_code=303)
    
    # Store original staff ID before switching
    request.session["original_staff_id"] = current_user.id
    request.session["original_staff_role"] = current_user.role.value
    
    # Switch session to member
    request.session["user_id"] = member.id
    request.session["user_role"] = member.role.value
    request.session["is_switched"] = True
    
    # Add flash message
    request.session["flash_message"] = f"✓ Switched to member view: {member.full_name or member.email}"
    request.session["flash_type"] = "success"
    
    logger.info(f"User {current_user.email} switched to member account {member.email}")
    
    return RedirectResponse(url="/member/dashboard", status_code=303)


@router.get("/to-staff")
async def switch_to_staff(
    request: Request,
    as_staff: int = Query(None, description="Staff ID to switch to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Switch from member account to linked staff account (Manager/Accountant/Credit Officer)
    """
    # Check if user is authenticated
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Check if this is a switched session (coming from staff)
    original_staff_id = request.session.get("original_staff_id")
    
    # Get the target staff ID
    if as_staff:
        staff_id = as_staff
    elif original_staff_id:
        staff_id = original_staff_id
    else:
        staff_id = current_user.linked_admin_id
    
    if not staff_id:
        request.session["flash_message"] = "No staff account linked to your member account"
        request.session["flash_type"] = "warning"
        return RedirectResponse(url="/member/dashboard", status_code=303)
    
    # Verify the staff account exists and has appropriate role
    staff = db.query(User).filter(
        User.id == staff_id,
        User.role.in_([RoleEnum.MANAGER, RoleEnum.ACCOUNTANT, RoleEnum.CREDIT_OFFICER])
    ).first()
    
    if not staff:
        request.session["flash_message"] = "Staff account not found"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/member/dashboard", status_code=303)
    
    # Verify this member is linked to this staff account
    if staff.linked_member_account_id != current_user.id:
        request.session["flash_message"] = "Not authorized to switch to this staff account"
        request.session["flash_type"] = "error"
        return RedirectResponse(url="/member/dashboard", status_code=303)
    
    # Switch session to staff
    request.session["user_id"] = staff.id
    request.session["user_role"] = staff.role.value
    
    # Clear the original staff ID if it exists (since we're switching back)
    if "original_staff_id" in request.session:
        del request.session["original_staff_id"]
    if "original_staff_role" in request.session:
        del request.session["original_staff_role"]
    if "is_switched" in request.session:
        del request.session["is_switched"]
    
    # Add flash message
    request.session["flash_message"] = f"✓ Switched to {staff.role.value} view: {staff.full_name or staff.email}"
    request.session["flash_type"] = "success"
    
    logger.info(f"User {current_user.email} switched to staff account {staff.email} ({staff.role.value})")
    
    # Redirect based on staff role
    redirect_url = get_dashboard_url(staff.role)
    
    return RedirectResponse(url=redirect_url, status_code=303)


@router.get("/back")
async def switch_back(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Switch back to original account if currently in switched mode
    """
    # Check if we're in a switched session
    original_staff_id = request.session.get("original_staff_id")
    
    if not original_staff_id:
        # Not in switched mode, just redirect to appropriate dashboard
        redirect_url = get_dashboard_url(current_user.role)
        return RedirectResponse(url=redirect_url, status_code=303)
    
    # Get the original staff account
    original_staff = db.query(User).filter(User.id == original_staff_id).first()
    
    if not original_staff:
        request.session["flash_message"] = "Original staff account not found"
        request.session["flash_type"] = "error"
        # Clear the session and redirect to member dashboard
        if "original_staff_id" in request.session:
            del request.session["original_staff_id"]
        return RedirectResponse(url="/member/dashboard", status_code=303)
    
    # Switch back to staff account
    request.session["user_id"] = original_staff.id
    request.session["user_role"] = original_staff.role.value
    
    # Clear switched session data
    if "original_staff_id" in request.session:
        del request.session["original_staff_id"]
    if "original_staff_role" in request.session:
        del request.session["original_staff_role"]
    if "is_switched" in request.session:
        del request.session["is_switched"]
    
    # Add flash message
    request.session["flash_message"] = f"✓ Switched back to {original_staff.role.value} view: {original_staff.full_name or original_staff.email}"
    request.session["flash_type"] = "success"
    
    logger.info(f"User switched back to staff account {original_staff.email}")
    
    # Redirect based on staff role
    redirect_url = get_dashboard_url(original_staff.role)
    
    return RedirectResponse(url=redirect_url, status_code=303)


def get_dashboard_url(role: RoleEnum) -> str:
    """Get dashboard URL based on user role"""
    dashboard_urls = {
        RoleEnum.SUPER_ADMIN: "/superadmin/dashboard",
        RoleEnum.MANAGER: "/manager/dashboard",
        RoleEnum.ACCOUNTANT: "/accountant/dashboard",
        RoleEnum.CREDIT_OFFICER: "/credit-officer/dashboard",
        RoleEnum.MEMBER: "/member/dashboard",
    }
    return dashboard_urls.get(role, "/dashboard")