# SHARES & DIVIDENDS SYSTEM - PHASE 1 IMPLEMENTATION GUIDE

**Phase:** 1 - Critical Fixes  
**Estimated Time:** 8 hours  
**Priority:** HIGH  
**Status:** Ready for Implementation

---

## OVERVIEW

Phase 1 implements 4 critical features that form the foundation for a complete shares and dividends system:

1. **SACCO-Level Enable/Disable** - Governance control
2. **Share Withdrawal/Redemption** - Member liquidity
3. **Fix Template Issues** - Bug fixes
4. **Consolidate Calculations** - Code cleanup

---

## IMPLEMENTATION TASK 1: SACCO SHARES ENABLE/DISABLE FEATURE

### **Objective**
Add capability for each SACCO to enable/disable the shares system, with automatic enforcement across all routes.

### **Changes Required**

#### **1.1 Update Sacco Model**

**File:** `backend/models/models.py`

**Add to Sacco class (after membership_fee field, line 48):**

```python
# Shares & Dividends Feature Flag
shares_enabled = Column(Boolean, default=False)  # Default disabled for governance
dividends_enabled = Column(Boolean, default=False)  # Separate control for dividends
```

**Why separate flags?** Some SACCOs may want shares without dividends, or vice versa.

#### **1.2 Create Database Migration**

**File:** Create new migration file (if using Alembic, otherwise manual SQL)

```sql
-- Add shares feature flags to saccos table
ALTER TABLE saccos ADD COLUMN shares_enabled BOOLEAN DEFAULT 0;
ALTER TABLE saccos ADD COLUMN dividends_enabled BOOLEAN DEFAULT 0;
```

**Alternative (if no migration system):** Execute directly in SQLite

```bash
sqlite3 database/cheontec.db "ALTER TABLE saccos ADD COLUMN shares_enabled BOOLEAN DEFAULT 0;"
sqlite3 database/cheontec.db "ALTER TABLE saccos ADD COLUMN dividends_enabled BOOLEAN DEFAULT 0;"
```

#### **1.3 Add Enable/Disable Utility Function**

**File:** `backend/core/dependencies.py`

**Add new function (at end of file):**

```python
def require_shares_enabled(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """Dependency to ensure shares feature is enabled for user's SACCO"""
    if not user.sacco or not user.sacco.shares_enabled:
        raise HTTPException(
            status_code=403,
            detail="Shares system is not enabled for your SACCO. Please contact your administrator."
        )
    return user


def require_dividends_enabled(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> User:
    """Dependency to ensure dividends feature is enabled for user's SACCO"""
    if not user.sacco or not user.sacco.dividends_enabled:
        raise HTTPException(
            status_code=403,
            detail="Dividends system is not enabled for your SACCO. Please contact your administrator."
        )
    return user
```

#### **1.4 Update Share Routes - Add Feature Checks**

**File:** `backend/routers/share.py`

**Update all member routes to require shares_enabled:**

**Line ~96 - Update share_dashboard route:**
```python
@router.get("/shares/dashboard")
async def share_dashboard(
    request: Request,
    user: User = Depends(require_shares_enabled),  # ADD THIS
    db: Session = Depends(get_db)
):
    """Display member's share portfolio"""
    # ... rest of function unchanged
```

**Line ~131 - Update share_subscription_form route:**
```python
@router.get("/shares/subscribe")
async def share_subscription_form(
    request: Request,
    user: User = Depends(require_shares_enabled),  # ADD THIS
    db: Session = Depends(get_db)
):
    """Display share subscription form"""
    # ... rest of function unchanged
```

**Line ~166 - Update subscribe_to_shares_route:**
```python
@router.post("/shares/subscribe")
async def subscribe_to_shares_route(
    request: Request,
    share_type_id: int = Form(...),
    quantity: int = Form(...),
    payment_method: str = Form(...),
    reference_number: str = Form(None),
    user: User = Depends(require_shares_enabled),  # ADD THIS
    db: Session = Depends(get_db)
):
    """Process share subscription"""
    # ... rest of function unchanged
```

**Line ~223 - Update share_transaction_history:**
```python
@router.get("/shares/history")
async def share_transaction_history(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, le=100),
    user: User = Depends(require_shares_enabled),  # ADD THIS
    db: Session = Depends(get_db)
):
    """View share transaction history"""
    # ... rest of function unchanged
```

#### **1.5 Update Dividend Routes - Add Feature Checks**

**File:** `backend/routers/dividend.py`

**Update member dividend routes:**

**Update `/dividends/entitlement` route:**
```python
@router.get("/dividends/entitlement")
async def dividend_entitlement(
    request: Request,
    fiscal_year: int = Query(None),
    user: User = Depends(require_dividends_enabled),  # ADD THIS
    db: Session = Depends(get_db)
):
    """View member's dividend entitlement"""
    # ... rest of function unchanged
```

**Update `/dividends/history` route:**
```python
@router.get("/dividends/history")
async def dividend_payment_history(
    request: Request,
    user: User = Depends(require_dividends_enabled),  # ADD THIS
    db: Session = Depends(get_db)
):
    """View member's dividend payment history"""
    # ... rest of function unchanged
```

#### **1.6 Create Admin Settings Route**

**File:** `backend/routers/admin.py` (or create new `backend/routers/sacco_settings.py`)

**Add new route to enable/disable shares:**

```python
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from ..core.dependencies import get_db, require_manager
from ..models import User, Sacco
from ..utils import create_log

router = APIRouter()

@router.get("/admin/sacco-settings")
async def sacco_settings(
    request: Request,
    user: User = Depends(require_manager),
    db: Session = Depends(get_db)
):
    """Display SACCO settings page"""
    templates = request.app.state.templates
    sacco = user.sacco
    
    from ..utils.helpers import get_template_helpers
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
        request.session["flash_message"] = f"Error updating settings: {str(e)}"
        request.session["flash_type"] = "danger"
    
    return RedirectResponse(url="/admin/sacco-settings", status_code=303)
```

#### **1.7 Create SACCO Settings Template**

**File:** `backend/templates/admin/sacco_settings.html`

```html
{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
    <div class="row">
        <div class="col-md-8 offset-md-2">
            <h1 class="mb-4">SACCO Settings</h1>
            
            <div class="card mb-3">
                <div class="card-header bg-primary text-white">
                    <h5 class="mb-0">SACCO Information</h5>
                </div>
                <div class="card-body">
                    <dl class="row">
                        <dt class="col-sm-3">SACCO Name:</dt>
                        <dd class="col-sm-9">{{ sacco.name }}</dd>
                        
                        <dt class="col-sm-3">Status:</dt>
                        <dd class="col-sm-9">
                            <span class="badge {% if sacco.status == 'active' %}badge-success{% else %}badge-danger{% endif %}">
                                {{ sacco.status|title }}
                            </span>
                        </dd>
                        
                        <dt class="col-sm-3">Membership Fee:</dt>
                        <dd class="col-sm-9">UGX {{ "{:,.2f}".format(sacco.membership_fee) }}</dd>
                    </dl>
                </div>
            </div>
            
            <!-- Shares System Toggle -->
            <div class="card mb-3">
                <div class="card-header bg-info text-white">
                    <h5 class="mb-0">Shares System</h5>
                </div>
                <div class="card-body">
                    <p class="text-muted mb-3">
                        Enable or disable the shares system for your SACCO. When disabled, members cannot 
                        subscribe to or manage shares.
                    </p>
                    
                    <form method="post" action="/admin/sacco-settings/toggle-shares" class="mb-3">
                        <div class="form-group d-flex align-items-center">
                            <span class="mr-3">
                                {% if sacco.shares_enabled %}
                                    <span class="badge badge-success">Currently ENABLED</span>
                                {% else %}
                                    <span class="badge badge-secondary">Currently DISABLED</span>
                                {% endif %}
                            </span>
                            <button type="submit" name="enabled" value="{% if sacco.shares_enabled %}false{% else %}true{% endif %}" 
                                    class="btn {% if sacco.shares_enabled %}btn-danger{% else %}btn-success{% endif %}">
                                {% if sacco.shares_enabled %}Disable Shares{% else %}Enable Shares{% endif %}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
            
            <!-- Dividends System Toggle -->
            <div class="card mb-3">
                <div class="card-header bg-info text-white">
                    <h5 class="mb-0">Dividends System</h5>
                </div>
                <div class="card-body">
                    <p class="text-muted mb-3">
                        Enable or disable the dividends system for your SACCO. When disabled, managers cannot 
                        declare dividends and members cannot view or receive dividend payments.
                    </p>
                    
                    <form method="post" action="/admin/sacco-settings/toggle-dividends" class="mb-3">
                        <div class="form-group d-flex align-items-center">
                            <span class="mr-3">
                                {% if sacco.dividends_enabled %}
                                    <span class="badge badge-success">Currently ENABLED</span>
                                {% else %}
                                    <span class="badge badge-secondary">Currently DISABLED</span>
                                {% endif %}
                            </span>
                            <button type="submit" name="enabled" value="{% if sacco.dividends_enabled %}false{% else %}true{% endif %}" 
                                    class="btn {% if sacco.dividends_enabled %}btn-danger{% else %}btn-success{% endif %}">
                                {% if sacco.dividends_enabled %}Disable Dividends{% else %}Enable Dividends{% endif %}
                            </button>
                        </div>
                    </form>
                </div>
            </div>
            
            <div class="alert alert-info">
                <strong>Note:</strong> Changes to these settings take effect immediately. Members will be unable to 
                access the disabled features.
            </div>
            
            <a href="/admin/dashboard" class="btn btn-secondary">Back to Dashboard</a>
        </div>
    </div>
</div>
{% endblock %}
```

#### **1.8 Update Admin Menu/Navigation**

**File:** `backend/templates/base.html` or relevant admin layout template

Add link to SACCO settings:
```html
<a class="dropdown-item" href="/admin/sacco-settings">
    <i class="fas fa-cog"></i> SACCO Settings
</a>
```

### **Testing Task 1**

**Test Cases:**

```
✓ CASE 1: shares_enabled = False blocks all share routes
  - Attempt GET /shares/dashboard → 403 error
  - Attempt GET /shares/subscribe → 403 error
  - Attempt POST /shares/subscribe → 403 error
  - Attempt GET /shares/history → 403 error

✓ CASE 2: dividends_enabled = False blocks dividend routes
  - Attempt GET /dividends/entitlement → 403 error
  - Attempt GET /dividends/history → 403 error

✓ CASE 3: Manager can toggle shares_enabled
  - Visit /admin/sacco-settings
  - Click Enable Shares button
  - Verify shares_enabled = True in database
  - Now share routes work

✓ CASE 4: Manager can toggle dividends_enabled
  - Visit /admin/sacco-settings
  - Click Enable Dividends button
  - Verify dividends_enabled = True in database
  - Now dividend routes work

✓ CASE 5: Multiple SACCOs independent
  - Create SACCO A with shares_enabled = True
  - Create SACCO B with shares_enabled = False
  - Member from A can access shares
  - Member from B cannot access shares
```

---

## IMPLEMENTATION TASK 2: SHARE WITHDRAWAL/REDEMPTION

### **Objective**
Allow members to withdraw shares and receive refund based on current value.

### **Changes Required**

#### **2.1 Create Withdrawal Service Function**

**File:** `backend/services/share_service.py`

**Add new function (at end of file):**

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

**Important:** Add import at top of file:
```python
from datetime import datetime
```

#### **2.2 Add Routes for Withdrawal**

**File:** `backend/routers/share.py`

**Add two new routes (after share_transaction_history route):**

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

**Required imports** at top of share.py:
```python
from ..services.share_service import (
    create_share_type,
    subscribe_to_shares,
    transfer_shares,
    withdraw_shares,  # ADD THIS
    get_withdrawal_options,  # ADD THIS
    get_member_share_holdings,
    calculate_dividend_entitlement,
    get_share_transaction_history
)
```

#### **2.3 Create Withdrawal Template**

**File:** `backend/templates/shares/withdraw.html`

```html
{% extends "base.html" %}

{% block content %}
<div class="container mt-4">
    <div class="row">
        <div class="col-md-8 offset-md-2">
            <h1 class="mb-4">Withdraw Shares</h1>
            
            <div class="card">
                <div class="card-body">
                    <form method="post" action="/shares/withdraw">
                        
                        <div class="form-group">
                            <label for="share_type_id" class="font-weight-bold">Select Share Type to Withdraw <span class="text-danger">*</span></label>
                            <select class="form-control" id="share_type_id" name="share_type_id" required onchange="updateAvailableShares()">
                                <option value="">-- Choose a share type --</option>
                                {% for option in withdrawal_options %}
                                <option value="{{ option.share_type_id }}" 
                                        data-quantity="{{ option.quantity_available }}"
                                        data-value-per-share="{{ option.value_per_share }}"
                                        data-total-value="{{ option.total_value }}">
                                    {{ option.share_type_name }} 
                                    (Available: {{ option.quantity_available }} shares @ UGX {{ "{:,.2f}".format(option.value_per_share) }} each)
                                </option>
                                {% endfor %}
                            </select>
                            <small class="form-text text-muted">You can only withdraw from shares you currently hold.</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="available_shares" class="font-weight-bold">Available Shares</label>
                            <input type="text" class="form-control" id="available_shares" disabled placeholder="Select a share type">
                        </div>
                        
                        <div class="form-group">
                            <label for="quantity" class="font-weight-bold">Quantity to Withdraw <span class="text-danger">*</span></label>
                            <input type="number" class="form-control" id="quantity" name="quantity" 
                                   min="1" placeholder="Enter quantity" required onchange="calculateRefund()">
                            <small class="form-text text-muted">Minimum 1 share</small>
                        </div>
                        
                        <div class="form-group">
                            <label for="refund_amount" class="font-weight-bold">Estimated Refund Amount</label>
                            <div class="input-group">
                                <div class="input-group-prepend">
                                    <span class="input-group-text">UGX</span>
                                </div>
                                <input type="text" class="form-control" id="refund_amount" disabled placeholder="0.00">
                            </div>
                            <small class="form-text text-muted">Based on current share value</small>
                        </div>
                        
                        <hr>
                        
                        <div class="form-group">
                            <label for="reason" class="font-weight-bold">Reason for Withdrawal</label>
                            <textarea class="form-control" id="reason" name="reason" rows="3" placeholder="Optional: Tell us why you're withdrawing"></textarea>
                        </div>
                        
                        <div class="form-group">
                            <label for="payment_method" class="font-weight-bold">Refund Payment Method</label>
                            <select class="form-control" id="payment_method" name="payment_method">
                                <option value="bank_transfer">Bank Transfer</option>
                                <option value="mobile_money">Mobile Money</option>
                                <option value="cash">Cash Pickup</option>
                                <option value="credit_account">Credit to Savings Account</option>
                            </select>
                        </div>
                        
                        <div class="form-group">
                            <label for="reference_number" class="font-weight-bold">Reference Number (Optional)</label>
                            <input type="text" class="form-control" id="reference_number" name="reference_number" 
                                   placeholder="e.g., Bank account, mobile number, etc.">
                        </div>
                        
                        <div class="alert alert-info">
                            <strong>Important:</strong>
                            <ul class="mb-0">
                                <li>Once withdrawn, you will no longer hold these shares</li>
                                <li>You will not be eligible for dividends on withdrawn shares</li>
                                <li>Refund processing may take 1-3 business days</li>
                            </ul>
                        </div>
                        
                        <div class="form-group">
                            <button type="submit" class="btn btn-danger btn-lg btn-block">
                                <i class="fas fa-sign-out-alt"></i> Withdraw Shares
                            </button>
                        </div>
                        
                        <a href="/shares/dashboard" class="btn btn-secondary btn-block">Cancel</a>
                    </form>
                </div>
            </div>
        </div>
    </div>
</div>

<script>
function updateAvailableShares() {
    const select = document.getElementById('share_type_id');
    const option = select.options[select.selectedIndex];
    const available = option.dataset.quantity || 0;
    document.getElementById('available_shares').value = available;
    document.getElementById('quantity').max = available;
    calculateRefund();
}

function calculateRefund() {
    const select = document.getElementById('share_type_id');
    const option = select.options[select.selectedIndex];
    const valuePerShare = parseFloat(option.dataset['valuePerShare']) || 0;
    const quantity = parseInt(document.getElementById('quantity').value) || 0;
    
    const refundAmount = valuePerShare * quantity;
    document.getElementById('refund_amount').value = refundAmount.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}
</script>
{% endblock %}
```

### **Testing Task 2**

```
✓ CASE 1: Display withdrawal form with available shares
  - Visit /shares/withdraw
  - See list of shares member holds
  - Shows quantity available and value per share

✓ CASE 2: Quantity validation
  - Try quantity = 0 → Validation error
  - Try quantity > available → Error message
  - Try quantity within range → Accepted

✓ CASE 3: Refund calculation
  - Select share type
  - Enter quantity
  - Refund amount updates correctly (qty × price_per_share)

✓ CASE 4: Process withdrawal
  - Complete form and submit
  - Verify transaction created
  - Verify share quantity reduced
  - Verify share marked inactive if quantity = 0
  - Member redirected to dashboard
  - Transaction appears in history

✓ CASE 5: Dividend eligibility
  - Withdraw shares on Day 1
  - Declare dividend on Day 2
  - Member should NOT receive dividend on withdrawn shares
```

---

## IMPLEMENTATION TASK 3: FIX TEMPLATE RESPONSE ISSUE

### **Objective**
Fix incorrect TemplateResponse parameter order in share.py

### **Change Required**

**File:** `backend/routers/share.py`

**Line ~57 - BEFORE:**
```python
return templates.TemplateResponse(request, "shares/subscribe.html", context)
```

**Line ~57 - AFTER:**
```python
return templates.TemplateResponse("shares/subscribe.html", context)
```

The `request` is already in the context dict, no need to pass it separately.

### **Testing Task 3**

```
✓ CASE 1: Subscribe form renders without error
  - Visit /shares/subscribe
  - Page loads successfully
  - Form displays properly
  - No template errors in console
```

---

## IMPLEMENTATION TASK 4: CONSOLIDATE DIVIDEND CALCULATIONS

### **Objective**
Remove duplicate dividend calculation function from share_service.py

### **Changes Required**

#### **4.1 Remove from share_service.py**

**File:** `backend/services/share_service.py`

**Lines 182-200 - DELETE:**
```python
def calculate_dividend_entitlement(db: Session, user_id: int, fiscal_year: int) -> dict:
    """Calculate dividend entitlement for a member"""
    holdings = get_member_share_holdings(db, user_id)
    
    total_dividend = 0
    breakdown = []
    
    for holding in holdings:
        dividend_amount = holding["total_value"] * (holding["dividend_rate"] / 100)
        total_dividend += dividend_amount
        
        breakdown.append({
            "share_type": holding["share_type_name"],
            "value": holding["total_value"],
            "rate": holding["dividend_rate"],
            "dividend": dividend_amount
        })
    
    return {
        "total_dividend": total_dividend,
        "breakdown": breakdown,
        "fiscal_year": fiscal_year
    }
```

#### **4.2 Update imports in share.py router**

**File:** `backend/routers/share.py`

**Lines 17-23 - BEFORE:**
```python
from ..services.share_service import (
    create_share_type,
    subscribe_to_shares,
    transfer_shares,
    get_member_share_holdings,
    calculate_dividend_entitlement,  # REMOVE THIS
    get_share_transaction_history
)
```

**Lines 17-23 - AFTER:**
```python
from ..services.share_service import (
    create_share_type,
    subscribe_to_shares,
    transfer_shares,
    withdraw_shares,  # ADD THIS
    get_withdrawal_options,  # ADD THIS
    get_member_share_holdings,
    get_share_transaction_history
)
```

#### **4.3 Verify no other uses**

Search codebase for `calculate_dividend_entitlement` usage:

```bash
grep -r "calculate_dividend_entitlement" backend/
```

Should only find references in dividend_service.py. If found elsewhere, update imports.

### **Testing Task 4**

```
✓ CASE 1: No import errors
  - Restart FastAPI server
  - Check console for import errors
  - All routes load without errors

✓ CASE 2: Dividend calculations still work
  - Member views entitlement at /dividends/entitlement
  - Calculation is correct
  - Uses declared dividend rates (not share_type.dividend_rate)
```

---

## INTEGRATION TESTING - ALL TASKS

**Full User Journey Test:**

```
1. SACCO Admin Setup
   □ Visit /admin/sacco-settings
   □ Enable Shares system
   □ Enable Dividends system

2. Member Share Subscription
   □ Visit /shares/subscribe
   □ Select share type, enter quantity
   □ Submit subscription
   □ Verify on /shares/dashboard

3. Member Share Withdrawal
   □ Visit /shares/withdraw
   □ Select shares to withdraw
   □ Verify refund calculation
   □ Submit withdrawal
   □ Verify transaction in history

4. Manager Dividend Declaration
   □ Visit /admin/dividends/declare
   □ Declare dividend at 10% rate
   □ Verify total pool calculation

5. Process Dividend Payments
   □ Click pay on declaration
   □ Verify DividendPayment records created
   □ Verify amounts calculated correctly

6. Member Views Dividends
   □ Visit /dividends/entitlement
   □ See calculated entitlement
   □ Check payment history at /dividends/history

7. Disable Shares
   □ Admin disables shares_enabled
   □ Member tries /shares/dashboard
   □ Verify 403 error displayed
```

---

## DATABASE QUERIES TO VERIFY

After completing all tasks, run these queries to verify:

```sql
-- 1. Verify Sacco table has new columns
SELECT id, name, shares_enabled, dividends_enabled FROM saccos LIMIT 5;

-- 2. Verify shares for member
SELECT s.id, st.name, s.quantity, s.total_value, s.is_active 
FROM shares s 
JOIN share_types st ON s.share_type_id = st.id 
WHERE s.user_id = 1;

-- 3. Verify withdrawal transactions exist
SELECT * FROM share_transactions 
WHERE transaction_type = 'WITHDRAWAL' 
LIMIT 5;

-- 4. Verify dividend payments
SELECT * FROM dividend_payments LIMIT 5;

-- 5. Verify logs created
SELECT action, details FROM logs 
WHERE action IN ('SACCO_SETTING_CHANGED', 'SHARE_WITHDRAWAL') 
LIMIT 5;
```

---

## DEPLOYMENT CHECKLIST

- [ ] Backup database before migration
- [ ] Create database migration files (or manual ALTER TABLE)
- [ ] Run migration on development database
- [ ] Run all unit tests
- [ ] Run integration tests
- [ ] Code review of changes
- [ ] Update API documentation
- [ ] Deploy to staging
- [ ] Test in staging environment
- [ ] Deploy to production
- [ ] Monitor error logs for issues
- [ ] Notify admins to enable shares/dividends as needed

---

## ROLLBACK PLAN

If issues arise:

1. **To disable features without code changes:**
   ```sql
   UPDATE saccos SET shares_enabled = 0, dividends_enabled = 0;
   ```

2. **To remove database columns (if needed):**
   ```sql
   -- SQLite doesn't support DROP COLUMN easily
   -- Would require table recreation
   -- Better to just leave columns and not use them
   ```

3. **To revert code changes:**
   ```bash
   git revert [commit-hash]
   ```

---

## SUCCESS CRITERIA

Phase 1 is complete when:

✅ SACCO can enable/disable shares system  
✅ SACCO can enable/disable dividends system  
✅ Routes are protected by feature flags  
✅ Members can withdraw shares  
✅ Withdrawal calculations are correct  
✅ Transactions are recorded properly  
✅ Template rendering works correctly  
✅ Duplicate code is removed  
✅ All tests pass  
✅ No errors in production logs  

---

**Next Phase:** Phase 2 - Important Enhancements (Dividend Reinvestment, Analytics, UI/UX)

