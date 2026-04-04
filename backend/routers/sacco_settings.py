# backend/routers/sacco_settings.py
"""
SACCO Settings Router
Handles SACCO configuration and feature toggles
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import logging

from ..core.dependencies import get_db, require_manager
from ..models import User
from ..utils.helpers import get_template_helpers
from ..utils import create_log

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/admin/sacco-settings")
async def sacco_settings(
    request: Request,
    user: User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """Display SACCO settings page"""
    templates = request.app.state.templates
    sacco = user.sacco
    
    helpers = get_template_helpers()
    
    context = {
        "request": request,
        "user": user,
        "sacco": {
            "id": sacco.id,
            "name": sacco.name,
            "shares_enabled": sacco.shares_enabled,
            "dividends_enabled": sacco.dividends_enabled,
            "membership_fee": sacco.membership_fee,
            "status": sacco.status
        },
        **helpers
    }
    return templates.TemplateResponse("admin/sacco_settings.html", context)


@router.post("/admin/sacco-settings/toggle-shares")
async def toggle_shares(
    request: Request,
    enabled: bool = Form(...),
    user: User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """Toggle shares system for SACCO"""
    try:
        sacco = user.sacco
        sacco.shares_enabled = enabled
        db.commit()
        
        create_log(
            db,
            action="SACCO_SETTING_CHANGED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Shares system {'enabled' if enabled else 'disabled'}"
        )
        
        status = "enabled" if enabled else "disabled"
        request.session["flash_message"] = f"Shares system {status} successfully!"
        request.session["flash_type"] = "success"
        
    except Exception as e:
        logger.error(f"Error toggling shares: {e}")
        request.session["flash_message"] = f"Error updating settings: {str(e)}"
        request.session["flash_type"] = "danger"
    
    return RedirectResponse(url="/admin/sacco-settings", status_code=303)


@router.post("/admin/sacco-settings/toggle-dividends")
async def toggle_dividends(
    request: Request,
    enabled: bool = Form(...),
    user: User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """Toggle dividends system for SACCO"""
    try:
        sacco = user.sacco
        sacco.dividends_enabled = enabled
        db.commit()
        
        create_log(
            db,
            action="SACCO_SETTING_CHANGED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Dividends system {'enabled' if enabled else 'disabled'}"
        )
        
        status = "enabled" if enabled else "disabled"
        request.session["flash_message"] = f"Dividends system {status} successfully!"
        request.session["flash_type"] = "success"
        
    except Exception as e:
        logger.error(f"Error toggling dividends: {e}")
        request.session["flash_message"] = f"Error updating settings: {str(e)}"
        request.session["flash_type"] = "danger"
    
    return RedirectResponse(url="/admin/sacco-settings", status_code=303)
