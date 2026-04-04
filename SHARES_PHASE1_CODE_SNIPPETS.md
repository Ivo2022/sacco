# SHARES & DIVIDENDS - PHASE 1 COPY-PASTE CODE

This document contains exact code snippets ready to implement Phase 1 changes. Copy-paste directly into your files.

---

## 1. SACCO MODEL UPDATES

### File: `backend/models/models.py`

**Location: After line 47 (membership_fee field)**

**CODE TO ADD:**
```python
    # Shares & Dividends Feature Flags
    shares_enabled = Column(Boolean, default=False)  # Enable/disable shares system
    dividends_enabled = Column(Boolean, default=False)  # Enable/disable dividends system
```

**Full context (lines 35-65):**
```python
class Sacco(Base):
    __tablename__ = "saccos"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, nullable=True)
    phone = Column(String)
    address = Column(String)
    registration_no = Column(String)
    website = Column(String)
    status = Column(String, default='active')
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    membership_fee = Column(Float, default=50000)  # Add membership fee to Sacco model
    
    # Shares & Dividends Feature Flags
    shares_enabled = Column(Boolean, default=False)  # Enable/disable shares system
    dividends_enabled = Column(Boolean, default=False)  # Enable/disable dividends system
		
    # Referral fields
    referred_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    referral_commission_paid = Column(Float, default=0.0)

    # Relationships
    users = relationship("User", foreign_keys="[User.sacco_id]", back_populates="sacco", cascade="all, delete")
    savings = relationship("Saving", foreign_keys="[Saving.sacco_id]", back_populates="sacco", cascade="all, delete")
    loans = relationship("Loan", foreign_keys="[Loan.sacco_id]", back_populates="sacco", cascade="all, delete")
```

---

## 2. DEPENDENCIES UPDATES

### File: `backend/core/dependencies.py`

**Location: At the end of the file**

**CODE TO ADD:**
```python
def require_shares_enabled(
    request: Request = None,
    user: User = Depends(get_current_user) if get_current_user else None,
    db: Session = Depends(get_db) if get_db else None
) -> User:
    """Dependency to ensure shares feature is enabled for user's SACCO"""
    from fastapi import HTTPException
    if not user or not user.sacco or not user.sacco.shares_enabled:
        raise HTTPException(
            status_code=403,
            detail="Shares system is not enabled for your SACCO. Please contact your administrator."
        )
    return user


def require_dividends_enabled(
    request: Request = None,
    user: User = Depends(get_current_user) if get_current_user else None,
    db: Session = Depends(get_db) if get_db else None
) -> User:
    """Dependency to ensure dividends feature is enabled for user's SACCO"""
    from fastapi import HTTPException
    if not user or not user.sacco or not user.sacco.dividends_enabled:
        raise HTTPException(
            status_code=403,
            detail="Dividends system is not enabled for your SACCO. Please contact your administrator."
        )
    return user
```

---

## 3. SHARE SERVICE UPDATES

### File: `backend/services/share_service.py`

**Location: At the end of the file (after get_share_transaction_history)**

**IMPORTS TO ADD** (at top of file, in existing imports section):
```python
from datetime import datetime  # Add this if not already there
from ..models.share import ShareTransactionType  # Add if not already there
```

**CODE TO ADD:**
```python
def withdraw_shares(
    db: Session,
    user_id: int,
    share_type_id: int,
    quantity: int,
    withdrawal_reason: str = None,
    bank_details: dict = None
) -> ShareTransaction:
    """
    Withdraw/redeem shares for a member
    
    Args:
        db: Database session
        user_id: Member ID
        share_type_id: Type of shares to withdraw
        quantity: Number of shares to withdraw
        withdrawal_reason: Reason for withdrawal (optional)
        bank_details: Bank account for refund (optional)
    
    Returns:
        ShareTransaction record of the withdrawal
    
    Raises:
        ValueError: If insufficient shares or invalid share
    """
    # Get member's share holding
    share = db.query(Share).filter(
        Share.user_id == user_id,
        Share.share_type_id == share_type_id,
        Share.is_active == True
    ).first()
    
    if not share:
        raise ValueError(f"No active share holdings found for share type {share_type_id}")
    
    if share.quantity < quantity:
        raise ValueError(
            f"Insufficient shares. You have {share.quantity} shares but requested {quantity} withdrawal."
        )
    
    # Get share type for par value
    share_type = db.query(ShareType).filter(
        ShareType.id == share_type_id
    ).first()
    
    if not share_type:
        raise ValueError("Share type not found")
    
    # Calculate refund value based on current total_value
    value_per_share = share.total_value / share.quantity if share.quantity > 0 else share_type.par_value
    refund_amount = quantity * value_per_share
    
    # Create withdrawal transaction
    transaction = ShareTransaction(
        share_id=share.id,
        user_id=user_id,
        sacco_id=share.sacco_id,
        transaction_type=ShareTransactionType.WITHDRAWAL,
        quantity=-quantity,  # Negative for withdrawal
        price_per_share=value_per_share,
        total_amount=-refund_amount,  # Negative (outgoing)
        payment_method=bank_details.get("payment_method", "bank_transfer") if bank_details else "bank_transfer",
        reference_number=bank_details.get("reference_number") if bank_details else None,
        notes=f"Share withdrawal. Reason: {withdrawal_reason or 'Not specified'}"
    )
    db.add(transaction)
    
    # Update member's share holding
    share.quantity -= quantity
    share.total_value -= refund_amount
    
    # If no shares left, mark as inactive
    if share.quantity == 0:
        share.is_active = False
    
    # Update timestamp
    share.last_updated = datetime.utcnow()
    
    db.commit()
    db.refresh(transaction)
    
    return transaction


def get_withdrawal_options(db: Session, user_id: int, sacco_id: int) -> list:
    """
    Get all shares available for withdrawal
    
    Returns:
        List of shares with details suitable for withdrawal form
    """
    shares = db.query(Share).filter(
        Share.user_id == user_id,
        Share.sacco_id == sacco_id,
        Share.is_active == True,
        Share.quantity > 0
    ).all()
    
    options = []
    for share in shares:
        if share.share_type:
            options.append({
                "id": share.id,
                "share_type_id": share.share_type_id,
                "share_type_name": share.share_type.name,
                "quantity_available": share.quantity,
                "total_value": share.total_value,
                "value_per_share": share.total_value / share.quantity if share.quantity > 0 else 0,
                "class_type": share.share_type.class_type.value if share.share_type.class_type else None
            })
    
    return options
```

**CODE TO DELETE** (lines ~182-200):
Find and delete the `calculate_dividend_entitlement()` function completely. It looks like:
```python
def calculate_dividend_entitlement(db: Session, user_id: int, fiscal_year: int) -> dict:
    """Calculate dividend entitlement for a member"""
    # ... approximately 20 lines ...
```

---

## 4. SHARE ROUTES UPDATES

### File: `backend/routers/share.py`

**LOCATION 1: Update imports (lines 17-23)**

**BEFORE:**
```python
from ..services.share_service import (
    create_share_type,
    subscribe_to_shares,
    transfer_shares,
    get_member_share_holdings,
    calculate_dividend_entitlement,
    get_share_transaction_history
)
```

**AFTER:**
```python
from ..services.share_service import (
    create_share_type,
    subscribe_to_shares,
    transfer_shares,
    withdraw_shares,
    get_withdrawal_options,
    get_member_share_holdings,
    get_share_transaction_history
)
from ..core.dependencies import require_shares_enabled, require_dividends_enabled
```

**LOCATION 2: Fix line 96 (share_dashboard route)**

**BEFORE:**
```python
@router.get("/shares/dashboard")
async def share_dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
```

**AFTER:**
```python
@router.get("/shares/dashboard")
async def share_dashboard(
    request: Request,
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
```

**LOCATION 3: Fix line 131 (share_subscription_form route)**

**BEFORE:**
```python
@router.get("/shares/subscribe")
async def share_subscription_form(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
```

**AFTER:**
```python
@router.get("/shares/subscribe")
async def share_subscription_form(
    request: Request,
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
```

**LOCATION 4: Fix line 57 (TemplateResponse call)**

**BEFORE:**
```python
    return templates.TemplateResponse(request, "shares/subscribe.html", context)
```

**AFTER:**
```python
    return templates.TemplateResponse("shares/subscribe.html", context)
```

**LOCATION 5: Fix line 166 (subscribe_to_shares_route)**

**BEFORE:**
```python
@router.post("/shares/subscribe")
async def subscribe_to_shares_route(
    request: Request,
    share_type_id: int = Form(...),
    quantity: int = Form(...),
    payment_method: str = Form(...),
    reference_number: str = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
```

**AFTER:**
```python
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
```

**LOCATION 6: Fix line 223 (share_transaction_history route)**

**BEFORE:**
```python
@router.get("/shares/history")
async def share_transaction_history(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
```

**AFTER:**
```python
@router.get("/shares/history")
async def share_transaction_history(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    user: User = Depends(require_shares_enabled),
    db: Session = Depends(get_db)
):
```

**LOCATION 7: Add two new routes (at end of file before any manager routes)**

```python
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
```

---

## 5. DIVIDEND ROUTES UPDATES

### File: `backend/routers/dividend.py`

**LOCATION 1: Update imports (top of file)**

Add to imports:
```python
from ..core.dependencies import require_dividends_enabled
```

**LOCATION 2: Update /dividends/entitlement route (around line 200)**

**BEFORE:**
```python
@router.get("/dividends/entitlement")
async def dividend_entitlement(
    request: Request,
    fiscal_year: int = Query(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
```

**AFTER:**
```python
@router.get("/dividends/entitlement")
async def dividend_entitlement(
    request: Request,
    fiscal_year: int = Query(None),
    user: User = Depends(require_dividends_enabled),
    db: Session = Depends(get_db)
):
```

**LOCATION 3: Update /dividends/history route (around line 224)**

**BEFORE:**
```python
@router.get("/dividends/history")
async def dividend_payment_history(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
```

**AFTER:**
```python
@router.get("/dividends/history")
async def dividend_payment_history(
    request: Request,
    user: User = Depends(require_dividends_enabled),
    db: Session = Depends(get_db)
):
```

---

## 6. NEW FILE: SACCO SETTINGS ROUTER

### File: `backend/routers/sacco_settings.py` (CREATE NEW FILE)

**FULL FILE CONTENT:**
```python
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
```

**THEN: Register router in main.py**

In `backend/main.py`, find the router includes section and add:
```python
from .routers import sacco_settings
# ...
app.include_router(sacco_settings.router)
```

---

## 7. NEW FILE: SACCO SETTINGS TEMPLATE

### File: `backend/templates/admin/sacco_settings.html` (CREATE NEW FILE)

**FULL FILE CONTENT:** See SHARES_PHASE1_IMPLEMENTATION.md section "2.7 Create SACCO Settings Template"

(Too long to include here, but the template code is in that file)

---

## 8. NEW FILE: WITHDRAWAL TEMPLATE

### File: `backend/templates/shares/withdraw.html` (CREATE NEW FILE)

**FULL FILE CONTENT:** See SHARES_PHASE1_IMPLEMENTATION.md section "2.3 Create Withdrawal Template"

(Too long to include here, but the template code is in that file)

---

## DATABASE MIGRATION

Execute these SQL commands in SQLite:

```sql
-- Add feature flags to saccos table
ALTER TABLE saccos ADD COLUMN shares_enabled BOOLEAN DEFAULT 0;
ALTER TABLE saccos ADD COLUMN dividends_enabled BOOLEAN DEFAULT 0;

-- Verify columns were added
SELECT id, name, shares_enabled, dividends_enabled FROM saccos LIMIT 5;

-- Optional: Enable shares for all existing SACCOs (safer to keep disabled)
-- UPDATE saccos SET shares_enabled = 1, dividends_enabled = 1;
```

---

## QUICK CHECKLIST

- [ ] Add columns to Sacco model (models.py)
- [ ] Add dependencies (dependencies.py)
- [ ] Add withdraw_shares + get_withdrawal_options to share_service.py
- [ ] Remove calculate_dividend_entitlement from share_service.py
- [ ] Update share.py imports
- [ ] Update share.py routes (change require_shares_enabled + template fix)
- [ ] Add withdrawal routes to share.py
- [ ] Create sacco_settings.py router
- [ ] Create sacco_settings.html template
- [ ] Create withdraw.html template
- [ ] Update dividend.py dependencies
- [ ] Run database migration
- [ ] Register sacco_settings router in main.py
- [ ] Test all routes
- [ ] Run unit tests
- [ ] Deploy

---

## TESTING ONE-LINER

After implementing, test with:

```bash
# Test member can view dashboard
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/shares/dashboard

# Test withdrawal form renders
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/shares/withdraw

# Check database
sqlite3 database/cheontec.db "SELECT id, shares_enabled, dividends_enabled FROM saccos LIMIT 3;"
```

---

**Ready to implement! Follow this file + SHARES_PHASE1_IMPLEMENTATION.md for detailed guidance.**

