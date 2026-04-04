# Data Synchronization Fixes - Implementation Guide

## Overview
This guide provides step-by-step fixes for all data synchronization issues found in the FastAPI SACCO system.

---

## FIX #1: Replace Payment with LoanPayment (CRITICAL)

**File**: `backend/routers/manager.py`
**Lines**: 247-250
**Severity**: CRITICAL - Breaks manager dashboard

### Current Code:
```python
for loan in active_loans:
    # Calculate total payable (principal + interest)
    interest = loan.amount * (loan.interest_rate / 100) * (loan.duration_months / 12)
    total_payable = loan.amount + interest

    # Get total payments made
    total_paid = db.query(func.sum(Payment.amount)).filter(  # <-- WRONG MODEL
        Payment.loan_id == loan.id
    ).scalar() or 0
```

### Fixed Code:
```python
for loan in active_loans:
    # Calculate total payable (principal + interest)
    interest = loan.amount * (loan.interest_rate / 100) * (loan.duration_months / 12)
    total_payable = loan.amount + interest

    # Get total payments made
    total_paid = db.query(func.sum(LoanPayment.amount)).filter(  # <-- FIXED
        LoanPayment.loan_id == loan.id
    ).scalar() or 0
```

### Verification:
```bash
# Search for any remaining "Payment." references (excluding LoanPayment)
grep -n "Payment\\.amount\|Payment\\.loan_id" backend/routers/manager.py
# Should return: (none)
```

---

## FIX #2: Consolidate serialize_loan() Functions

**File**: `backend/routers/manager.py`
**Lines**: 23-88
**Severity**: HIGH - Creates confusion and dead code

### Current Problem:
Two definitions of `serialize_loan()` exist. The first is overwritten by the second.

### Solution: Remove the first definition and keep the second

```python
# DELETE LINES 23-45 (First definition)

# KEEP LINES 47-88 (Second definition)
def serialize_loan(loan: Loan) -> dict:
    """Serialize loan ORM object to dictionary with calculated fields."""
    
    # Calculate monthly payment
    def calculate_monthly_payment(amount, interest_rate, duration_months):
        if duration_months and duration_months > 0:
            monthly_rate = (interest_rate / 100) / 12
            if monthly_rate > 0:
                payment = amount * (monthly_rate * (1 + monthly_rate) ** duration_months) / ((1 + monthly_rate) ** duration_months - 1)
                return round(payment, 2)
            else:
                return round(amount / duration_months, 2)
        return amount
    
    return {
        "id": loan.id,
        "amount": loan.amount,
        "term": loan.term,
        "status": loan.status,
        "timestamp": loan.timestamp.isoformat() if loan.timestamp else None,
        "purpose": loan.purpose,
        "interest_rate": loan.interest_rate,
        "total_payable": loan.total_payable,
        "total_paid": loan.total_paid,
        "total_interest": loan.total_interest,
        "approved_by": loan.approved_by,
        "approved_at": loan.approved_at.isoformat() if loan.approved_at else None,
        "approval_notes": loan.approval_notes,
        "user_id": loan.user_id,
        "sacco_id": loan.sacco_id,
        "monthly_payment": calculate_monthly_payment(
            float(loan.amount) if loan.amount else 0,
            float(loan.interest_rate) if loan.interest_rate else 0,
            loan.term or 0
        ),
        # Add user information
        "user": {
            "id": loan.user.id if loan.user else None,
            "full_name": loan.user.full_name if loan.user else None,
            "email": loan.user.email if loan.user else None,
        } if loan.user else None
    }
```

### Verification:
```python
# Search for duplicate definitions
grep -n "def serialize_loan" backend/routers/manager.py
# Should return exactly ONE match
```

---

## FIX #3: Standardize total_outstanding Calculation

**File**: `backend/routers/manager.py`
**Lines**: 240-255
**Severity**: HIGH - Manager and admin see different figures

### Current Code (BROKEN):
```python
# Get all active loans
active_loans = db.query(Loan).filter(
    Loan.sacco_id == sacco_id,
    Loan.status == 'active'
).all()

total_outstanding = 0
for loan in active_loans:
    # Calculate total payable (principal + interest)
    interest = loan.amount * (loan.interest_rate / 100) * (loan.duration_months / 12)
    total_payable = loan.amount + interest

    # Get total payments made
    total_paid = db.query(func.sum(Payment.amount)).filter(  # <-- ERROR HERE
        Payment.loan_id == loan.id
    ).scalar() or 0

    # Calculate outstanding balance
    outstanding = total_payable - total_paid
    if outstanding > 0:
        total_outstanding += outstanding
```

### Option A: Use Database Calculation (RECOMMENDED)
```python
# Calculate total outstanding in database query
# Outstanding = loans that still have a balance due
outstanding_loans = db.query(Loan).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(['active', 'overdue'])  # Only currently owed loans
).all()

total_outstanding = 0
for loan in outstanding_loans:
    # Use pre-calculated totals from Loan model
    total_paid = db.query(func.sum(LoanPayment.amount)).filter(
        LoanPayment.loan_id == loan.id
    ).scalar() or 0
    
    # total_payable = principal + interest (already calculated)
    outstanding = loan.total_payable - total_paid
    if outstanding > 0:
        total_outstanding += outstanding
```

### Option B: Pure SQL (MOST EFFICIENT)
```python
# Create a subquery for total payments per loan
from sqlalchemy import and_

payments_subquery = db.query(
    LoanPayment.loan_id,
    func.sum(LoanPayment.amount).label('total_paid')
).filter(
    LoanPayment.sacco_id == sacco_id
).group_by(LoanPayment.loan_id).subquery()

# Use in main query
outstanding_query = db.query(
    func.sum(
        Loan.total_payable - func.coalesce(payments_subquery.c.total_paid, 0)
    )
).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(['active', 'overdue']),
    Loan.total_payable > func.coalesce(payments_subquery.c.total_paid, 0)
).outerjoin(
    payments_subquery,
    Loan.id == payments_subquery.c.loan_id
).scalar() or 0

total_outstanding = float(outstanding_query or 0)
```

### Update All References:
After fixing `total_outstanding`, ensure:

1. **Admin dashboard** uses same calculation
   - File: `backend/routers/sacco_admin.py`, Lines 47-49
   - Change `Loan.status == 'approved'` to `Loan.status.in_(['active', 'overdue'])`

2. **Statistics service** uses same calculation
   - File: `backend/services/statistics_service.py`
   - Check `get_sacco_statistics()` function

### Verification:
```python
# Run this test to verify consistency:
from sqlalchemy.orm import Session
from backend.models import Loan, LoanPayment
from sqlalchemy import func

def verify_outstanding_calculation(db: Session, sacco_id: int):
    """Verify outstanding calculation matches across all routes"""
    
    # Method 1: Manager dashboard calculation
    active_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(['active', 'overdue'])
    ).all()
    
    total_outstanding_method1 = 0
    for loan in active_loans:
        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        outstanding = loan.total_payable - total_paid
        if outstanding > 0:
            total_outstanding_method1 += outstanding
    
    # Method 2: Check against admin
    outstanding_admin = db.query(func.sum(Loan.amount)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'approved'
    ).scalar() or 0
    
    print(f"Manager calculation: {total_outstanding_method1}")
    print(f"Admin calculation: {outstanding_admin}")
    print(f"Match: {total_outstanding_method1 == outstanding_admin}")
    
    return total_outstanding_method1 == outstanding_admin
```

---

## FIX #4: Standardize Loan Status Filters

**Files**: Multiple routers
**Severity**: HIGH - Different views show different data

### Define Standard Status Groups

Create file: `backend/core/loan_status.py`

```python
from enum import Enum

class LoanStatusEnum(str, Enum):
    """Standard loan status definitions"""
    PENDING = "pending"           # Awaiting credit officer review
    APPROVED = "approved"         # Approved by credit officer, waiting disbursement
    ACTIVE = "active"             # Disbursed, member is repaying
    COMPLETED = "completed"       # Fully repaid
    OVERDUE = "overdue"           # Past due date with balance
    REJECTED = "rejected"         # Denied by credit officer
    CANCELLED = "cancelled"       # Cancelled before disbursement

# Status groupings for reporting
STATUS_GROUPS = {
    "awaiting_action": [LoanStatusEnum.PENDING],
    "approved_not_disbursed": [LoanStatusEnum.APPROVED],
    "active_loans": [LoanStatusEnum.ACTIVE],
    "problem_loans": [LoanStatusEnum.OVERDUE],
    "completed": [LoanStatusEnum.COMPLETED],
    "closed": [LoanStatusEnum.COMPLETED, LoanStatusEnum.REJECTED, LoanStatusEnum.CANCELLED],
    "disbursed": [LoanStatusEnum.ACTIVE, LoanStatusEnum.COMPLETED, LoanStatusEnum.OVERDUE],
    "owed_balance": [LoanStatusEnum.ACTIVE, LoanStatusEnum.OVERDUE],
}
```

### Update All Filters

**File**: `backend/routers/manager.py`

```python
from ..core.loan_status import STATUS_GROUPS, LoanStatusEnum

# Change from:
total_disbursed = db.query(func.sum(Loan.amount)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(['active', 'completed', 'approved'])
).scalar() or 0

# To:
total_disbursed = db.query(func.sum(Loan.amount)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(STATUS_GROUPS["disbursed"])
).scalar() or 0

# Change from:
total_outstanding = # ... calculate for 'active' loans only

# To:
total_outstanding = # ... calculate for STATUS_GROUPS["owed_balance"] loans
```

**File**: `backend/routers/sacco_admin.py`

```python
# Change from:
outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status == 'approved'
).scalar() or 0.0

# To:
outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(STATUS_GROUPS["owed_balance"])
).scalar() or 0.0
```

### Verification:
```bash
# Ensure all routes use STATUS_GROUPS
grep -r "Loan.status ==" backend/routers/ | wc -l
# Should be 0 or only for backwards compatibility

grep -r "Loan.status.in_" backend/routers/ | wc -l
# All filters should use this pattern
```

---

## FIX #5: Use Pre-Calculated Loan Fields

**File**: `backend/models/models.py`
**Severity**: MEDIUM - Improves consistency and performance

### Verify Loan Model Has These Fields:

```python
class Loan(Base):
    __tablename__ = "loans"
    
    id = Column(Integer, primary_key=True)
    amount = Column(Float)                          # Principal
    interest_rate = Column(Float)                   # Annual interest rate
    term = Column(Integer)                          # Term in months
    duration_months = Column(Integer)               # Calculated or input
    
    # Pre-calculated totals (should be populated when loan is created)
    total_interest = Column(Float, default=0)       # Calculated interest
    total_payable = Column(Float, default=0)        # Principal + interest
    total_paid = Column(Float, default=0)           # Total payments received
    
    # Status tracking
    status = Column(String, default="pending")
    
    # Timestamps
    timestamp = Column(DateTime, default=datetime.utcnow)
    approved_at = Column(DateTime, nullable=True)
    
    # Relationships
    sacco_id = Column(Integer, ForeignKey("sacco.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    user = relationship("User", back_populates="loans")
```

### Never Recalculate - Always Use Stored Values:

**BEFORE** (WRONG):
```python
interest = loan.amount * (loan.interest_rate / 100) * (loan.duration_months / 12)
total_payable = loan.amount + interest
```

**AFTER** (RIGHT):
```python
# Use pre-calculated values
total_interest = loan.total_interest
total_payable = loan.total_payable
```

### Create Helper Function:

File: `backend/utils/loan_utils.py`

```python
def calculate_loan_totals(principal: float, interest_rate: float, duration_months: int) -> dict:
    """
    Calculate total interest and total payable for a loan.
    
    This is the SINGLE SOURCE OF TRUTH for interest calculations.
    Use this when creating or updating loans.
    """
    if duration_months <= 0:
        return {"total_interest": 0, "total_payable": principal}
    
    # Calculate interest
    total_interest = principal * (interest_rate / 100) * (duration_months / 12)
    total_payable = principal + total_interest
    
    return {
        "total_interest": round(total_interest, 2),
        "total_payable": round(total_payable, 2)
    }

def get_loan_outstanding(loan: Loan, db: Session) -> float:
    """
    Get outstanding balance for a loan.
    Outstanding = Total Payable - Total Paid
    """
    from backend.models import LoanPayment
    from sqlalchemy import func
    
    total_paid = db.query(func.sum(LoanPayment.amount)).filter(
        LoanPayment.loan_id == loan.id
    ).scalar() or 0
    
    outstanding = loan.total_payable - total_paid
    return max(outstanding, 0)  # Never negative
```

### Update Loan Creation:

**File**: `backend/routers/member.py` or wherever loans are created

```python
from ..utils.loan_utils import calculate_loan_totals

# When creating a loan
loan_totals = calculate_loan_totals(
    principal=loan_amount,
    interest_rate=interest_rate,
    duration_months=loan_term
)

new_loan = Loan(
    amount=loan_amount,
    interest_rate=interest_rate,
    term=loan_term,
    duration_months=loan_term,
    total_interest=loan_totals["total_interest"],
    total_payable=loan_totals["total_payable"],
    status="pending",
    # ... other fields ...
)

db.add(new_loan)
db.commit()
```

---

## FIX #6: Implement Statistics Service Centralization

**File**: `backend/services/statistics_service.py`
**Severity**: HIGH - Ensures single source of truth

### Create Centralized Statistics Function:

```python
from sqlalchemy.orm import Session
from sqlalchemy import func
from ..models import Loan, LoanPayment, Saving, User, PendingDeposit, RoleEnum
from ..core.loan_status import STATUS_GROUPS, LoanStatusEnum
from typing import Dict, Any

def get_sacco_statistics(db: Session, sacco_id: int) -> Dict[str, Any]:
    """
    Get comprehensive statistics for a SACCO.
    
    This is the SINGLE SOURCE OF TRUTH for all dashboard statistics.
    All routes should use this function, not calculate separately.
    
    Returns:
        Dictionary with all calculated metrics
    """
    
    # ========== LOAN METRICS ==========
    pending_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == LoanStatusEnum.PENDING
    ).count()
    
    approved_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == LoanStatusEnum.APPROVED
    ).count()
    
    active_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == LoanStatusEnum.ACTIVE
    ).count()
    
    completed_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == LoanStatusEnum.COMPLETED
    ).count()
    
    overdue_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == LoanStatusEnum.OVERDUE
    ).count()
    
    rejected_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == LoanStatusEnum.REJECTED
    ).count()
    
    # ========== LOAN TOTALS ==========
    total_disbursed = db.query(func.coalesce(func.sum(Loan.amount), 0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(STATUS_GROUPS["disbursed"])
    ).scalar() or 0
    
    total_interest_earned = db.query(func.coalesce(func.sum(Loan.total_interest), 0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(STATUS_GROUPS["completed"])  # Only completed loans
    ).scalar() or 0
    
    total_payments_received = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.sacco_id == sacco_id
    ).scalar() or 0
    
    # Outstanding loans (current balance due)
    active_and_overdue_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(STATUS_GROUPS["owed_balance"])
    ).all()
    
    total_outstanding = 0
    for loan in active_and_overdue_loans:
        total_paid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        outstanding = loan.total_payable - total_paid
        total_outstanding += max(outstanding, 0)
    
    # ========== PERFORMANCE METRICS ==========
    if total_disbursed > 0:
        repayment_rate = (total_payments_received / total_disbursed) * 100
    else:
        repayment_rate = 0
    
    avg_interest_rate = db.query(func.coalesce(func.avg(Loan.interest_rate), 0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(STATUS_GROUPS["disbursed"])
    ).scalar() or 0
    
    # ========== SAVINGS METRICS ==========
    total_deposits = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.sacco_id == sacco_id,
        Saving.type == "deposit"
    ).scalar() or 0
    
    total_withdrawals = db.query(func.coalesce(func.sum(Saving.amount), 0)).filter(
        Saving.sacco_id == sacco_id,
        Saving.type == "withdrawal"
    ).scalar() or 0
    
    total_savings = total_deposits - total_withdrawals
    
    # ========== MEMBER METRICS ==========
    total_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER
    ).count()
    
    active_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_active == True
    ).count()
    
    pending_members = db.query(User).filter(
        User.sacco_id == sacco_id,
        User.role == RoleEnum.MEMBER,
        User.is_approved == False
    ).count()
    
    # ========== DEPOSIT METRICS ==========
    pending_deposits = db.query(PendingDeposit).filter(
        PendingDeposit.sacco_id == sacco_id,
        PendingDeposit.status == "pending"
    ).count()
    
    # Return comprehensive statistics
    return {
        # Loan counts
        "pending_loans": pending_loans,
        "approved_loans": approved_loans,
        "active_loans_count": active_loans,
        "completed_loans": completed_loans,
        "overdue_loans": overdue_loans,
        "rejected_loans": rejected_loans,
        
        # Loan totals
        "total_disbursed": float(total_disbursed),
        "total_outstanding": float(total_outstanding),
        "total_interest_earned": float(total_interest_earned),
        "total_payments_received": float(total_payments_received),
        "avg_interest_rate": round(float(avg_interest_rate), 2),
        "repayment_rate": round(repayment_rate, 2),
        
        # Savings
        "total_deposits": float(total_deposits),
        "total_withdrawals": float(total_withdrawals),
        "total_savings": float(total_savings),
        
        # Members
        "total_members": total_members,
        "active_members": active_members,
        "pending_members": pending_members,
        
        # Deposits
        "pending_deposits": pending_deposits,
    }
```

### Update Manager Dashboard to Use Service:

**File**: `backend/routers/manager.py`

```python
# OLD WAY (BROKEN - multiple separate queries):
total_interest_earned = db.query(...).scalar() or 0
total_disbursed = db.query(...).scalar() or 0
total_outstanding = # ... manual loop ...
# ... etc ...

# NEW WAY (CORRECT - single source of truth):
stats = get_sacco_statistics(db, sacco_id)

# Then use the returned values:
total_interest_earned = stats["total_interest_earned"]
total_disbursed = stats["total_disbursed"]
total_outstanding = stats["total_outstanding"]
# ... etc ...
```

### Verification:
```python
# Test that all dashboards return same values
from backend.services.statistics_service import get_sacco_statistics

db_session = next(get_db())
sacco_id = 1

stats = get_sacco_statistics(db_session, sacco_id)

# Manually query one value
manual_outstanding = db_session.query(...).scalar()

# Should match
assert stats["total_outstanding"] == manual_outstanding
```

---

## FIX #7: Add Payment Verification Workflow

**File**: Create `backend/models/payment_verification.py`
**Severity**: MEDIUM - Improves audit trail

### Add Verification Fields:

```python
from sqlalchemy import Column, Integer, DateTime, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from . import Base

class LoanPaymentVerification(Base):
    """Audit trail for loan payment verification"""
    __tablename__ = "loan_payment_verifications"
    
    id = Column(Integer, primary_key=True)
    payment_id = Column(Integer, ForeignKey("loan_payments.id"), unique=True)
    
    # Verification status
    is_verified = Column(Boolean, default=False)
    verification_timestamp = Column(DateTime, nullable=True)
    verified_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Dispute tracking
    is_disputed = Column(Boolean, default=False)
    dispute_reason = Column(String, nullable=True)
    dispute_timestamp = Column(DateTime, nullable=True)
    dispute_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Reversal tracking
    is_reversed = Column(Boolean, default=False)
    reversal_reason = Column(String, nullable=True)
    reversal_timestamp = Column(DateTime, nullable=True)
    reversal_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    # Relationships
    payment = relationship("LoanPayment", back_populates="verification")
    verified_by = relationship("User", foreign_keys=[verified_by_user_id])
    disputed_by = relationship("User", foreign_keys=[dispute_by_user_id])
    reversed_by = relationship("User", foreign_keys=[reversal_by_user_id])

```

### Update Calculations to Only Count Verified Payments:

```python
# OLD WAY (counts all payments):
total_paid = db.query(func.sum(LoanPayment.amount)).filter(
    LoanPayment.loan_id == loan.id
).scalar() or 0

# NEW WAY (only count verified, non-disputed, non-reversed):
from backend.models import LoanPaymentVerification

total_paid = db.query(func.sum(LoanPayment.amount)).join(
    LoanPaymentVerification
).filter(
    LoanPayment.loan_id == loan.id,
    LoanPaymentVerification.is_verified == True,
    LoanPaymentVerification.is_disputed == False,
    LoanPaymentVerification.is_reversed == False
).scalar() or 0
```

---

## FIX #8: Timezone Consistency

**File**: `backend/core/config.py`
**Severity**: LOW - But important for accuracy

### Set Standard Timezone:

```python
from datetime import timezone, timedelta
import pytz

# Define standard timezone for the system
SYSTEM_TIMEZONE = pytz.timezone('UTC')  # or 'Africa/Kampala' for Uganda
APP_TIMEZONE_OFFSET = timedelta(hours=3)  # EAT - East Africa Time

def get_system_now():
    """Get current time in system timezone"""
    from datetime import datetime
    return datetime.now(SYSTEM_TIMEZONE)

def convert_to_system_tz(dt):
    """Convert datetime to system timezone"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=SYSTEM_TIMEZONE)
    return dt.astimezone(SYSTEM_TIMEZONE)
```

### Update All datetime.utcnow() Calls:

```python
# OLD:
from datetime import datetime
month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

# NEW:
from backend.core.config import get_system_now
month_start = get_system_now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
```

---

## Testing & Validation

### Create Test File: `tests/test_data_sync.py`

```python
import pytest
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

from backend.models import Loan, LoanPayment, User, Sacco, RoleEnum
from backend.services.statistics_service import get_sacco_statistics
from backend.routers.manager import manager_dashboard
from backend.routers.sacco_admin import sacco_dashboard


def test_total_outstanding_consistency(db: Session):
    """Test that total_outstanding is calculated consistently"""
    
    # Create test SACCO
    sacco = Sacco(name="Test SACCO", created_at=datetime.utcnow())
    db.add(sacco)
    db.flush()
    
    # Create test user
    user = User(
        email="test@example.com",
        full_name="Test User",
        sacco_id=sacco.id,
        role=RoleEnum.MEMBER,
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.flush()
    
    # Create test loan
    loan = Loan(
        amount=10000,
        interest_rate=10,
        term=12,
        duration_months=12,
        total_interest=1000,
        total_payable=11000,
        status="active",
        user_id=user.id,
        sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    db.add(loan)
    db.flush()
    
    # Create payment
    payment = LoanPayment(
        amount=5000,
        loan_id=loan.id,
        sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    db.add(payment)
    db.commit()
    
    # Get statistics
    stats = get_sacco_statistics(db, sacco.id)
    
    # Outstanding should be 11000 - 5000 = 6000
    assert stats["total_outstanding"] == 6000, \
        f"Expected outstanding 6000, got {stats['total_outstanding']}"
    
    # Total disbursed should include this active loan
    assert stats["total_disbursed"] >= 10000, \
        f"Expected disbursed >= 10000, got {stats['total_disbursed']}"


def test_total_disbursed_consistency(db: Session):
    """Test that total_disbursed uses correct status filters"""
    
    sacco = Sacco(name="Test SACCO 2", created_at=datetime.utcnow())
    db.add(sacco)
    db.flush()
    
    user = User(
        email="test2@example.com",
        full_name="Test User 2",
        sacco_id=sacco.id,
        role=RoleEnum.MEMBER,
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.flush()
    
    # Create loans with different statuses
    active_loan = Loan(
        amount=1000, interest_rate=10, term=12, duration_months=12,
        total_interest=100, total_payable=1100,
        status="active", user_id=user.id, sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    
    completed_loan = Loan(
        amount=2000, interest_rate=10, term=12, duration_months=12,
        total_interest=200, total_payable=2200,
        status="completed", user_id=user.id, sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    
    pending_loan = Loan(
        amount=500, interest_rate=10, term=12, duration_months=12,
        total_interest=50, total_payable=550,
        status="pending", user_id=user.id, sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    
    db.add_all([active_loan, completed_loan, pending_loan])
    db.commit()
    
    stats = get_sacco_statistics(db, sacco.id)
    
    # Total disbursed should include active + completed + approved (not pending)
    # So should be 1000 + 2000 = 3000
    assert stats["total_disbursed"] == 3000, \
        f"Expected disbursed 3000, got {stats['total_disbursed']}"


def test_repayment_rate_calculation(db: Session):
    """Test that repayment rate is calculated correctly"""
    
    sacco = Sacco(name="Test SACCO 3", created_at=datetime.utcnow())
    db.add(sacco)
    db.flush()
    
    user = User(
        email="test3@example.com",
        full_name="Test User 3",
        sacco_id=sacco.id,
        role=RoleEnum.MEMBER,
        is_active=True,
        is_approved=True
    )
    db.add(user)
    db.flush()
    
    # Create loan with 1000 total payable
    loan = Loan(
        amount=1000, interest_rate=0, term=12, duration_months=12,
        total_interest=0, total_payable=1000,
        status="active", user_id=user.id, sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    db.add(loan)
    db.flush()
    
    # Add 500 in payments (50% repayment rate)
    payment = LoanPayment(
        amount=500,
        loan_id=loan.id,
        sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    db.add(payment)
    db.commit()
    
    stats = get_sacco_statistics(db, sacco.id)
    
    # Repayment rate should be 50%
    assert stats["repayment_rate"] == 50.0, \
        f"Expected repayment rate 50%, got {stats['repayment_rate']}%"


# Run tests with: pytest tests/test_data_sync.py -v
```

### Run Tests:

```bash
cd /d/2026/fastapi
python -m pytest tests/test_data_sync.py -v
```

---

## Implementation Checklist

- [ ] Fix #1: Replace Payment with LoanPayment
- [ ] Fix #2: Remove duplicate serialize_loan() function
- [ ] Fix #3: Standardize total_outstanding calculation
- [ ] Fix #4: Create loan status enum and update all filters
- [ ] Fix #5: Ensure loan model uses pre-calculated fields
- [ ] Fix #6: Implement centralized statistics service
- [ ] Fix #7: Add payment verification workflow (optional)
- [ ] Fix #8: Standardize timezone usage (optional)
- [ ] Run data sync tests
- [ ] Test manager dashboard loads without errors
- [ ] Test admin dashboard shows consistent figures
- [ ] Verify all SACCOs see only their own data
- [ ] Create reconciliation report
- [ ] Document all changes in changelog

---

## Rollback Plan

If issues occur after implementing these fixes:

1. Revert to previous git commit
2. Keep the test file - it helps identify issues
3. Implement fixes one at a time, testing after each
4. Get stakeholder approval before production deployment

---

Generated: 2024
For: FastAPI SACCO Management System
