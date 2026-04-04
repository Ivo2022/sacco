# backend/routers/dividend.py
"""
Dividend Management Router
Handles dividend declarations and payments
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime
import logging

from ..core.dependencies import get_db, get_current_user, require_manager, require_dividends_enabled
from ..models import User
from ..models.share import DividendDeclaration, DividendPayment, Share
from ..services.dividend_service import (
    declare_dividend,
    calculate_dividend_for_member,
    pay_dividends,
    get_dividend_history
)
from ..utils.helpers import get_template_helpers
from ..utils import create_log

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# SERIALIZERS
# =============================================================================

def serialize_dividend_declaration(declaration: DividendDeclaration) -> dict:
    """Convert DividendDeclaration ORM to safe dict"""
    return {
        "id": declaration.id,
        "sacco_id": declaration.sacco_id,
        "share_type_id": declaration.share_type_id,
        "declared_date": declaration.declared_date.isoformat() if declaration.declared_date else None,
        "fiscal_year": declaration.fiscal_year,
        "rate": declaration.rate,
        "amount_per_share": declaration.amount_per_share,
        "total_dividend_pool": declaration.total_dividend_pool,
        "payment_date": declaration.payment_date.isoformat() if declaration.payment_date else None,
        "declared_by": declaration.declared_by,
        "status": declaration.status,
        "declarer_email": declaration.declarer.email if declaration.declarer else None,
    }


def serialize_dividend_payment(payment: DividendPayment) -> dict:
    """Convert DividendPayment ORM to safe dict"""
    return {
        "id": payment.id,
        "declaration_id": payment.declaration_id,
        "user_id": payment.user_id,
        "sacco_id": payment.sacco_id,
        "share_id": payment.share_id,
        "shares_held": payment.shares_held,
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
        "reference_number": payment.reference_number,
        "is_reinvested": payment.is_reinvested,
        "user_email": payment.user.email if payment.user else None,
    }


# =============================================================================
# ADMIN ROUTES
# =============================================================================

@router.get("/admin/dividends/declare")
async def declare_dividend_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """Display dividend declaration form"""
    templates = request.app.state.templates
    
    from ..models.share import ShareType
    share_types = db.query(ShareType).filter(
        ShareType.sacco_id == user.sacco_id
    ).all()
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "share_types": [{"id": st.id, "name": st.name, "dividend_rate": st.dividend_rate} for st in share_types],
        **helpers
    }
    return templates.TemplateResponse("admin/declare_dividend.html", context)


@router.post("/admin/dividends/declare")
async def declare_dividend_route(
    request: Request,
    fiscal_year: int = Form(...),
    rate: float = Form(...),
    share_type_id: int = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """Declare a dividend"""
    try:
        declaration = declare_dividend(
            db=db,
            sacco_id=user.sacco_id,
            fiscal_year=fiscal_year,
            rate=rate,
            declared_by=user.id,
            share_type_id=share_type_id
        )
        
        create_log(
            db,
            action="DIVIDEND_DECLARED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Dividend declared for FY {fiscal_year} at {rate}% rate. Total pool: UGX {declaration.total_dividend_pool:,.2f}"
        )
        
        request.session["flash_message"] = f"Dividend declared successfully! Total pool: UGX {declaration.total_dividend_pool:,.2f}"
        request.session["flash_type"] = "success"
        
        return RedirectResponse(url="/admin/dividends/history", status_code=303)
        
    except Exception as e:
        logger.error(f"Error declaring dividend: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
        return RedirectResponse(url="/admin/dividends/declare", status_code=303)


@router.post("/admin/dividends/{declaration_id}/pay")
async def process_dividend_payment(
    request: Request,
    declaration_id: int,
    payment_method: str = Form("bank_transfer"),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """Process dividend payments for a declaration"""
    try:
        payments = pay_dividends(
            db=db,
            declaration_id=declaration_id,
            payment_method=payment_method
        )
        
        create_log(
            db,
            action="DIVIDEND_PAID",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Dividend payments processed for declaration #{declaration_id}. {len(payments)} members paid."
        )
        
        request.session["flash_message"] = f"Dividend payments processed for {len(payments)} members!"
        request.session["flash_type"] = "success"
        
        return RedirectResponse(url="/admin/dividends/history", status_code=303)
        
    except Exception as e:
        logger.error(f"Error processing dividends: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
        return RedirectResponse(url="/admin/dividends/history", status_code=303)


@router.get("/admin/dividends/history")
async def dividend_history(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """View dividend declaration history"""
    templates = request.app.state.templates
    
    declarations = db.query(DividendDeclaration).filter(
        DividendDeclaration.sacco_id == user.sacco_id
    ).order_by(DividendDeclaration.declared_date.desc()).all()
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "declarations": [serialize_dividend_declaration(d) for d in declarations],
        **helpers
    }
    return templates.TemplateResponse("admin/dividend_history.html", context)


# =============================================================================
# MEMBER ROUTES
# =============================================================================

@router.get("/dividends/entitlement")
async def dividend_entitlement(
    request: Request,
    fiscal_year: int = Query(None),
    user: User = Depends(require_dividends_enabled),
    db: Session = Depends(get_db)
):
    """View member's dividend entitlement"""
    templates = request.app.state.templates
    
    if not fiscal_year:
        fiscal_year = datetime.utcnow().year
    
    entitlement = calculate_dividend_for_member(db, user.id, fiscal_year)
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "entitlement": entitlement,
        "fiscal_year": fiscal_year,
        **helpers
    }
    return templates.TemplateResponse("dividends/entitlement.html", context)


@router.get("/dividends/history")
async def dividend_payment_history(
    request: Request,
    user: User = Depends(require_dividends_enabled),
    db: Session = Depends(get_db)
):
    """View member's dividend payment history"""
    templates = request.app.state.templates
    
    payments = db.query(DividendPayment).filter(
        DividendPayment.user_id == user.id
    ).order_by(DividendPayment.paid_at.desc()).all()
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "payments": [serialize_dividend_payment(p) for p in payments],
        **helpers
    }
    return templates.TemplateResponse("dividends/history.html", context)