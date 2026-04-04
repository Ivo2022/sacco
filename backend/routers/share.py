# backend/routers/share.py
"""
Share Capital Management Router
Handles share subscriptions, purchases, transfers, and tracking
"""
from fastapi import APIRouter, Depends, Request, HTTPException, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime
import logging

from ..core.dependencies import get_db, get_current_user, require_role, require_manager, require_shares_enabled, require_dividends_enabled
from ..models import User, RoleEnum, Sacco, Share, ShareType, ShareTransaction, ShareTransactionType, ShareClass
from ..services.share_service import (
    create_share_type,
    subscribe_to_shares,
    transfer_shares,
    withdraw_shares,
    get_withdrawal_options,
    get_member_share_holdings,
    get_share_transaction_history
)
from ..utils.helpers import get_template_helpers, check_sacco_status
from ..utils import create_log

router = APIRouter()
logger = logging.getLogger(__name__)


# =============================================================================
# SERIALIZERS
# =============================================================================

def serialize_share_type(share_type: ShareType) -> dict:
    """Convert ShareType ORM to safe dict"""
    return {
        "id": share_type.id,
        "sacco_id": share_type.sacco_id,
        "name": share_type.name,
        "class_type": share_type.class_type.value if share_type.class_type else None,
        "par_value": share_type.par_value,
        "minimum_shares": share_type.minimum_shares,
        "maximum_shares": share_type.maximum_shares,
        "is_voting": share_type.is_voting,
        "dividend_rate": share_type.dividend_rate,
    }


def serialize_share(share: Share) -> dict:
    """Convert Share ORM to safe dict"""
    return {
        "id": share.id,
        "user_id": share.user_id,
        "sacco_id": share.sacco_id,
        "share_type_id": share.share_type_id,
        "quantity": share.quantity,
        "total_value": share.total_value,
        "is_active": share.is_active,
        "last_updated": share.last_updated.isoformat() if share.last_updated else None,
        "share_type": serialize_share_type(share.share_type) if share.share_type else None,
        "user_email": share.user.email if share.user else None,
        "user_full_name": share.user.full_name if share.user else None,
    }


def serialize_share_transaction(transaction: ShareTransaction) -> dict:
    """Convert ShareTransaction ORM to safe dict"""
    return {
        "id": transaction.id,
        "share_id": transaction.share_id,
        "user_id": transaction.user_id,
        "sacco_id": transaction.sacco_id,
        "transaction_type": transaction.transaction_type.value if transaction.transaction_type else None,
        "quantity": transaction.quantity,
        "price_per_share": transaction.price_per_share,
        "total_amount": transaction.total_amount,
        "payment_method": transaction.payment_method,
        "reference_number": transaction.reference_number,
        "transaction_date": transaction.transaction_date.isoformat() if transaction.transaction_date else None,
        "approved_by": transaction.approved_by,
        "approved_at": transaction.approved_at.isoformat() if transaction.approved_at else None,
        "notes": transaction.notes,
        "user_email": transaction.user.email if transaction.user else None,
        "approver_email": transaction.approver.email if transaction.approver else None,
    }


# =============================================================================
# MEMBER ROUTES
# =============================================================================

@router.get("/shares/dashboard")
@router.get("/shares/dashboard")
async def share_dashboard(
    request: Request,
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
    """Display member's share portfolio"""
    templates = request.app.state.templates
    
    # Get member's share holdings
    holdings = get_member_share_holdings(db, user.id)
    
    # Calculate total value
    total_shares = sum(h["quantity"] for h in holdings)
    total_value = sum(h["total_value"] for h in holdings)
    
    # Get transaction history
    transactions = get_share_transaction_history(db, user.id, limit=10)
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "holdings": holdings,
        "total_shares": total_shares,
        "total_value": total_value,
        "transactions": [serialize_share_transaction(t) for t in transactions],
        **helpers
    }
    return templates.TemplateResponse("shares/dashboard.html", context)


@router.get("/shares/subscribe")
async def share_subscription_form(
    request: Request,
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
    """Display share subscription form"""
    templates = request.app.state.templates
    
    # Get available share types for this SACCO
    share_types = db.query(ShareType).filter(
        ShareType.sacco_id == user.sacco_id
    ).all()
    
    if not share_types:
        context = {
            "request": request,
            "user": user,
            "error": "No share types configured for this SACCO. Please contact the administrator."
        }
        return templates.TemplateResponse("shares/no_shares.html", context)
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "share_types": [serialize_share_type(st) for st in share_types],
        **helpers
    }
    return templates.TemplateResponse("shares/subscribe.html", context)


@router.post("/shares/subscribe")
async def subscribe_to_shares_route(
    request: Request,
    share_type_id: int = Form(...),
    quantity: int = Form(...),
    payment_method: str = Form(...),
    reference_number: str = Form(None),
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
    """Process share subscription"""
    try:
        # Get share type
        share_type = db.query(ShareType).filter(
            ShareType.id == share_type_id,
            ShareType.sacco_id == user.sacco_id
        ).first()
        
        if not share_type:
            raise HTTPException(status_code=404, detail="Share type not found")
        
        # Check minimum and maximum
        if quantity < share_type.minimum_shares:
            raise HTTPException(
                status_code=400,
                detail=f"Minimum shares required: {share_type.minimum_shares}"
            )
        
        if share_type.maximum_shares and quantity > share_type.maximum_shares:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum shares allowed: {share_type.maximum_shares}"
            )
        
        # Calculate total amount
        total_amount = quantity * share_type.par_value
        
        # Create subscription
        share = subscribe_to_shares(
            db=db,
            user_id=user.id,
            sacco_id=user.sacco_id,
            share_type_id=share_type_id,
            quantity=quantity,
            total_amount=total_amount,
            payment_method=payment_method,
            reference_number=reference_number
        )
        
        create_log(
            db,
            action="SHARE_SUBSCRIPTION",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Member {user.email} subscribed to {quantity} shares of {share_type.name} (Total: UGX {total_amount:,.2f})"
        )
        
        request.session["flash_message"] = f"Successfully subscribed to {quantity} shares! Total: UGX {total_amount:,.2f}"
        request.session["flash_type"] = "success"
        
        return RedirectResponse(url="/shares/dashboard", status_code=303)
        
    except Exception as e:
        logger.error(f"Error subscribing to shares: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
        return RedirectResponse(url="/shares/subscribe", status_code=303)


@router.get("/shares/history")
async def share_transaction_history(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
    """View share transaction history"""
    templates = request.app.state.templates
    
    transactions = get_share_transaction_history(db, user.id, limit=per_page, offset=(page-1)*per_page)
    total = db.query(ShareTransaction).filter(ShareTransaction.user_id == user.id).count()
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "transactions": [serialize_share_transaction(t) for t in transactions],
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": (total + per_page - 1) // per_page,
        **helpers
    }
    return templates.TemplateResponse("shares/history.html", context)


@router.get("/shares/withdraw")
async def withdrawal_form(
    request: Request,
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
    """Display share withdrawal form"""
    templates = request.app.state.templates
    
    withdrawal_options = get_withdrawal_options(db, user.id, user.sacco_id)
    
    if not withdrawal_options:
        context = {
            "request": request,
            "user": user,
            "error": "You have no shares to withdraw.",
            **get_template_helpers()
        }
        return templates.TemplateResponse("shares/no_shares.html", context)
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "withdrawal_options": withdrawal_options,
        **helpers
    }
    return templates.TemplateResponse("shares/withdraw.html", context)


@router.post("/shares/withdraw")
async def process_withdrawal(
    request: Request,
    share_type_id: int = Form(...),
    quantity: int = Form(...),
    reason: str = Form(None),
    payment_method: str = Form("bank_transfer"),
    reference_number: str = Form(None),
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
    """Process share withdrawal"""
    try:
        # Validate quantity
        if quantity <= 0:
            raise ValueError("Quantity must be greater than 0")
        
        # Get the share to validate
        share = db.query(Share).filter(
            Share.user_id == user.id,
            Share.share_type_id == share_type_id,
            Share.is_active == True
        ).first()
        
        if not share:
            raise ValueError("Share holdings not found")
        
        if share.quantity < quantity:
            raise ValueError(f"Insufficient shares. You have {share.quantity} shares.")
        
        # Process withdrawal
        bank_details = {
            "payment_method": payment_method,
            "reference_number": reference_number
        }
        
        transaction = withdraw_shares(
            db=db,
            user_id=user.id,
            share_type_id=share_type_id,
            quantity=quantity,
            withdrawal_reason=reason,
            bank_details=bank_details
        )
        
        # Calculate refund amount
        refund_amount = abs(transaction.total_amount)
        
        # Create log
        create_log(
            db,
            action="SHARE_WITHDRAWAL",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Member {user.email} withdrew {quantity} shares. Refund amount: UGX {refund_amount:,.2f}"
        )
        
        request.session["flash_message"] = f"Successfully withdrawn {quantity} shares. Refund amount: UGX {refund_amount:,.2f}"
        request.session["flash_type"] = "success"
        
        return RedirectResponse(url="/shares/dashboard", status_code=303)
        
    except ValueError as e:
        logger.warning(f"Withdrawal validation error: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "warning"
        return RedirectResponse(url="/shares/withdraw", status_code=303)
    except Exception as e:
        logger.error(f"Error processing withdrawal: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
        return RedirectResponse(url="/shares/withdraw", status_code=303)


# =============================================================================
# ADMIN ROUTES
# =============================================================================

@router.get("/admin/shares/types")
async def manage_share_types(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """Manage share types for the SACCO"""
    templates = request.app.state.templates
    
    share_types = db.query(ShareType).filter(
        ShareType.sacco_id == user.sacco_id
    ).all()
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "share_types": [serialize_share_type(st) for st in share_types],
        **helpers
    }
    return templates.TemplateResponse("admin/share_types.html", context)


@router.post("/admin/shares/types/create")
async def create_share_type_route(
    request: Request,
    name: str = Form(...),
    class_type: str = Form(...),
    par_value: float = Form(...),
    minimum_shares: int = Form(1),
    maximum_shares: int = Form(None),
    is_voting: bool = Form(True),
    dividend_rate: float = Form(0.0),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """Create a new share type"""
    try:
        share_type = create_share_type(
            db=db,
            sacco_id=user.sacco_id,
            name=name,
            class_type=class_type,
            par_value=par_value,
            minimum_shares=minimum_shares,
            maximum_shares=maximum_shares,
            is_voting=is_voting,
            dividend_rate=dividend_rate
        )
        
        create_log(
            db,
            action="SHARE_TYPE_CREATED",
            user_id=user.id,
            sacco_id=user.sacco_id,
            details=f"Share type '{name}' created with par value UGX {par_value:,.2f}"
        )
        
        request.session["flash_message"] = f"Share type '{name}' created successfully!"
        request.session["flash_type"] = "success"
        
    except Exception as e:
        logger.error(f"Error creating share type: {e}")
        request.session["flash_message"] = f"Error: {str(e)}"
        request.session["flash_type"] = "danger"
    
    return RedirectResponse(url="/admin/shares/types", status_code=303)


@router.get("/admin/shares/holdings")
async def view_share_holdings(
    request: Request,
    search: str = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_manager)
):
    """View all members' share holdings"""
    templates = request.app.state.templates
    
    query = db.query(Share).filter(Share.sacco_id == user.sacco_id)
    
    if search:
        query = query.join(User).filter(
            User.email.ilike(f"%{search}%") | User.full_name.ilike(f"%{search}%")
        )
    
    holdings = query.order_by(Share.last_updated.desc()).all()
    
    # Calculate totals
    total_shares = sum(h.quantity for h in holdings)
    total_value = sum(h.total_value for h in holdings)
    
    helpers = get_template_helpers()
    context = {
        "request": request,
        "user": user,
        "holdings": [serialize_share(h) for h in holdings],
        "total_shares": total_shares,
        "total_value": total_value,
        "search": search,
        **helpers
    }
    return templates.TemplateResponse("admin/share_holdings.html", context)