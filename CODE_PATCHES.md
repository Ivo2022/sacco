# Code Patches - Ready to Apply

## Patch 1: Fix Critical Payment Model Bug

**File**: `backend/routers/manager.py`  
**Lines**: 247-250  
**Severity**: CRITICAL

### Apply This Patch:

```diff
--- a/backend/routers/manager.py
+++ b/backend/routers/manager.py
@@ -244,7 +244,7 @@ def manager_dashboard(
         # Calculate total payable (principal + interest)
         interest = loan.amount * (loan.interest_rate / 100) * (loan.duration_months / 12)
         total_payable = loan.amount + interest
     
         # Get total payments made
-        total_paid = db.query(func.sum(Payment.amount)).filter(
-            Payment.loan_id == loan.id
+        total_paid = db.query(func.sum(LoanPayment.amount)).filter(
+            LoanPayment.loan_id == loan.id
         ).scalar() or 0
```

### Manual Fix Steps:
1. Open `backend/routers/manager.py`
2. Go to line 247
3. Change `Payment.amount` to `LoanPayment.amount`
4. Change `Payment.loan_id` to `LoanPayment.loan_id`
5. Save file

### Verification:
```bash
grep -n "Payment.amount\|Payment.loan_id" backend/routers/manager.py
# Should return: (no matches - if it does, the bug still exists)

# Try to import the module
python -c "from backend.routers import manager; print('✓ No import errors')"
```

---

## Patch 2: Remove Duplicate Function

**File**: `backend/routers/manager.py`  
**Lines**: 23-45 (DELETE)  
**Severity**: HIGH

### Apply This Patch:

Delete lines 23-45. These are the duplicate function definition:

```python
# DELETE THESE LINES (23-45):
def serialize_loan(loan: Loan) -> dict:
    """Serialize loan ORM object to dictionary with user info."""
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
        # Add user information
        "user": {
            "id": loan.user.id if loan.user else None,
            "full_name": loan.user.full_name if loan.user else None,
            "email": loan.user.email if loan.user else None,
            #"member_number": loan.user.member_number if loan.user else None
        } if loan.user else None
    }
```

Keep the second definition (lines 47-88).

### Verification:
```bash
grep -n "def serialize_loan" backend/routers/manager.py
# Should return exactly ONE match (line number will change after deletion)
```

---

## Patch 3: Fix Total Outstanding Calculation

**File**: `backend/routers/manager.py`  
**Lines**: 240-255  
**Severity**: HIGH

### Current (Broken):
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
    total_paid = db.query(func.sum(Payment.amount)).filter(  # BUG HERE
        Payment.loan_id == loan.id
    ).scalar() or 0

    # Calculate outstanding balance
    outstanding = total_payable - total_paid
    if outstanding > 0:
        total_outstanding += outstanding
```

### Fixed Version:
```python
# Get all loans with outstanding balance (active or overdue)
outstanding_loans = db.query(Loan).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(['active', 'overdue'])  # Changed from just 'active'
).all()

total_outstanding = 0
for loan in outstanding_loans:
    # Use pre-calculated total_payable instead of recalculating
    # total_payable = principal + interest (already in database)
    
    # Get total payments made
    total_paid = db.query(func.sum(LoanPayment.amount)).filter(  # FIXED: Payment -> LoanPayment
        LoanPayment.loan_id == loan.id
    ).scalar() or 0

    # Calculate outstanding balance
    outstanding = loan.total_payable - total_paid  # FIXED: Use stored value
    if outstanding > 0:
        total_outstanding += outstanding
```

### Alternative (Most Efficient):
```python
# Calculate total outstanding using pure SQL (no Python loop)
from sqlalchemy import case

# Get sum of all payments per loan
payments_per_loan = db.query(
    LoanPayment.loan_id,
    func.sum(LoanPayment.amount).label('total_paid')
).filter(
    LoanPayment.sacco_id == sacco_id
).group_by(LoanPayment.loan_id).subquery()

# Calculate outstanding for each loan and sum
outstanding_subquery = db.query(
    func.sum(
        case(
            (Loan.total_payable > func.coalesce(payments_per_loan.c.total_paid, 0),
             Loan.total_payable - func.coalesce(payments_per_loan.c.total_paid, 0)),
            else_=0
        )
    )
).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(['active', 'overdue'])
).outerjoin(
    payments_per_loan,
    Loan.id == payments_per_loan.c.loan_id
)

total_outstanding = outstanding_subquery.scalar() or 0
```

---

## Patch 4: Create Loan Status Enum

**Create New File**: `backend/core/loan_status.py`

```python
from enum import Enum

class LoanStatusEnum(str, Enum):
    """
    Standard loan status definitions.
    Use these constants throughout the application instead of hardcoded strings.
    """
    
    PENDING = "pending"           # Awaiting credit officer review
    APPROVED = "approved"         # Approved, waiting disbursement
    ACTIVE = "active"             # Disbursed, member is repaying
    COMPLETED = "completed"       # Fully repaid and closed
    OVERDUE = "overdue"           # Past due date with balance remaining
    REJECTED = "rejected"         # Denied by credit officer
    CANCELLED = "cancelled"       # Cancelled before disbursement


# Groupings for different reporting purposes
STATUS_GROUPS = {
    # For different report purposes
    "awaiting_action": [LoanStatusEnum.PENDING],
    "approved_not_disbursed": [LoanStatusEnum.APPROVED],
    "currently_active": [LoanStatusEnum.ACTIVE],
    "problem_loans": [LoanStatusEnum.OVERDUE],
    "completed": [LoanStatusEnum.COMPLETED],
    "closed": [LoanStatusEnum.COMPLETED, LoanStatusEnum.REJECTED, LoanStatusEnum.CANCELLED],
    
    # For financial calculations
    "disbursed": [LoanStatusEnum.ACTIVE, LoanStatusEnum.COMPLETED, LoanStatusEnum.APPROVED],
    "owed_balance": [LoanStatusEnum.ACTIVE, LoanStatusEnum.OVERDUE],
    "earning_interest": [LoanStatusEnum.ACTIVE, LoanStatusEnum.OVERDUE],
}


def is_valid_status(status: str) -> bool:
    """Check if a status string is valid."""
    return status in [s.value for s in LoanStatusEnum]
```

---

## Patch 5: Update Manager Dashboard to Use STATUS_GROUPS

**File**: `backend/routers/manager.py`  
**At Top**: Add import

```python
# Add to imports section
from ..core.loan_status import LoanStatusEnum, STATUS_GROUPS
```

**Line 199 (approx)**: Update pending_loans_count

```python
# BEFORE:
pending_loans_count = db.query(Loan).filter(
    Loan.sacco_id == sacco_id, Loan.status == "pending"
).count()

# AFTER:
pending_loans_count = db.query(Loan).filter(
    Loan.sacco_id == sacco_id, 
    Loan.status == LoanStatusEnum.PENDING
).count()
```

**Line 229**: Update total_disbursed

```python
# BEFORE:
total_disbursed = db.query(func.sum(Loan.amount)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(['active', 'completed', 'approved'])
).scalar() or 0

# AFTER:
total_disbursed = db.query(func.sum(Loan.amount)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(STATUS_GROUPS["disbursed"])
).scalar() or 0
```

**Line 240**: Update outstanding_loans filter

```python
# BEFORE:
outstanding_loans = db.query(Loan).filter(
    Loan.sacco_id == sacco_id,
    Loan.status == 'active'
).all()

# AFTER:
outstanding_loans = db.query(Loan).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(STATUS_GROUPS["owed_balance"])
).all()
```

---

## Patch 6: Update Admin Dashboard to Match

**File**: `backend/routers/sacco_admin.py`  
**Line 47**: Change outstanding_loans calculation

```python
# BEFORE:
outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status == 'approved'  # Wrong - should be owed_balance
).scalar() or 0.0

# AFTER:
from ..core.loan_status import STATUS_GROUPS

outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(STATUS_GROUPS["owed_balance"])
).scalar() or 0.0
```

---

## Patch 7: Create Test File

**Create New File**: `tests/test_data_sync.py`

```python
import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from backend.models import Loan, LoanPayment, User, Sacco, RoleEnum
from backend.services.statistics_service import get_sacco_statistics
from backend.core.loan_status import LoanStatusEnum, STATUS_GROUPS


@pytest.fixture
def test_db(db: Session):
    """Fixture providing a test database session"""
    return db


def test_payment_model_exists(test_db: Session):
    """Verify LoanPayment model exists and can be queried"""
    try:
        # Should not raise error
        test_db.query(LoanPayment).count()
        assert True
    except Exception as e:
        pytest.fail(f"LoanPayment model error: {e}")


def test_total_outstanding_calculation(test_db: Session):
    """Test that total outstanding is calculated correctly"""
    
    # Create test SACCO
    sacco = Sacco(name="Test SACCO", created_at=datetime.utcnow())
    test_db.add(sacco)
    test_db.flush()
    
    # Create test user
    user = User(
        email="test@test.com",
        full_name="Test User",
        sacco_id=sacco.id,
        role=RoleEnum.MEMBER,
        is_active=True,
        is_approved=True,
        created_at=datetime.utcnow()
    )
    test_db.add(user)
    test_db.flush()
    
    # Create test loan: 10000 principal, 1000 interest
    loan = Loan(
        amount=10000,
        interest_rate=10,
        term=12,
        duration_months=12,
        total_interest=1000,
        total_payable=11000,
        status=LoanStatusEnum.ACTIVE,
        user_id=user.id,
        sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    test_db.add(loan)
    test_db.flush()
    
    # Add 5000 in payments
    payment = LoanPayment(
        amount=5000,
        loan_id=loan.id,
        sacco_id=sacco.id,
        timestamp=datetime.utcnow()
    )
    test_db.add(payment)
    test_db.commit()
    
    # Get statistics
    stats = get_sacco_statistics(test_db, sacco.id)
    
    # Outstanding should be 11000 - 5000 = 6000
    assert stats["total_outstanding"] == 6000, \
        f"Expected outstanding 6000, got {stats['total_outstanding']}"


def test_no_payment_model_reference():
    """Verify no code references non-existent Payment model"""
    import os
    
    # Search for Payment. references in Python files
    search_files = [
        "backend/routers/manager.py",
        "backend/routers/sacco_admin.py",
        "backend/routers/admin.py",
    ]
    
    for filepath in search_files:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()
                # Look for Payment.amount, Payment.loan_id, etc.
                # But exclude LoanPayment references
                lines = content.split('\n')
                for i, line in enumerate(lines, 1):
                    if 'Payment.' in line and 'LoanPayment' not in line:
                        # This is a bad reference
                        pytest.fail(f"{filepath}:{i} references non-existent Payment model: {line.strip()}")


def test_no_duplicate_serialize_loan():
    """Verify serialize_loan is defined only once"""
    import os
    
    filepath = "backend/routers/manager.py"
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            lines = f.readlines()
            count = sum(1 for line in lines if line.strip().startswith('def serialize_loan'))
            assert count == 1, f"Found {count} definitions of serialize_loan, expected 1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

## Patch 8: Create Statistics Service

**Create New File**: `backend/services/statistics_service.py`

```python
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Dict, Any
from ..models import Loan, LoanPayment, Saving, User, PendingDeposit, RoleEnum
from ..core.loan_status import STATUS_GROUPS, LoanStatusEnum


def get_sacco_statistics(db: Session, sacco_id: int) -> Dict[str, Any]:
    """
    Get comprehensive statistics for a SACCO.
    
    This is the SINGLE SOURCE OF TRUTH for all dashboard statistics.
    All routes should use this function to ensure consistency.
    
    Args:
        db: SQLAlchemy session
        sacco_id: SACCO ID to get statistics for
        
    Returns:
        Dictionary with all calculated metrics
    """
    
    # ========== LOAN COUNTS BY STATUS ==========
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
    
    # ========== LOAN FINANCIAL TOTALS ==========
    
    # Total disbursed (active + completed + approved)
    total_disbursed = db.query(func.coalesce(func.sum(Loan.amount), 0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(STATUS_GROUPS["disbursed"])
    ).scalar() or 0
    
    # Total interest earned (only from completed loans)
    total_interest_earned = db.query(func.coalesce(func.sum(Loan.total_interest), 0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == LoanStatusEnum.COMPLETED
    ).scalar() or 0
    
    # Total payments received
    total_payments_received = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.sacco_id == sacco_id
    ).scalar() or 0
    
    # Average interest rate
    avg_interest_rate = db.query(func.coalesce(func.avg(Loan.interest_rate), 0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(STATUS_GROUPS["disbursed"])
    ).scalar() or 0
    
    # Calculate total outstanding (balance still owed)
    outstanding_loans = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status.in_(STATUS_GROUPS["owed_balance"])
    ).all()
    
    total_outstanding = 0
    for loan in outstanding_loans:
        # Get total paid for this loan
        total_paid = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.loan_id == loan.id
        ).scalar() or 0
        
        # Calculate outstanding balance
        outstanding = loan.total_payable - total_paid
        if outstanding > 0:
            total_outstanding += outstanding
    
    # ========== PERFORMANCE METRICS ==========
    
    # Calculate repayment rate
    if total_disbursed > 0:
        repayment_rate = (total_payments_received / total_disbursed) * 100
    else:
        repayment_rate = 0
    
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
    
    # ========== RETURN ALL STATISTICS ==========
    
    return {
        # Loan counts
        "pending_loans": pending_loans,
        "approved_loans": approved_loans,
        "active_loans_count": active_loans,
        "completed_loans": completed_loans,
        "overdue_loans": overdue_loans,
        "rejected_loans": rejected_loans,
        
        # Loan financials
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

---

## How to Apply These Patches

### Option 1: Manual (Line by Line)
1. Open each file mentioned
2. Find the lines specified
3. Make the changes shown in the "AFTER" code
4. Save the file

### Option 2: Git Apply (If Using Git)
```bash
# Save the patches to a file and apply them
git apply < patches.diff
```

### Option 3: IDE Find/Replace
1. Use editor find/replace feature
2. Find: `Payment.amount`
3. Replace with: `LoanPayment.amount`
4. Repeat for other strings

---

## Testing Patches

After applying each patch:

```bash
# Test imports work
python -c "from backend.routers import manager; print('✓ manager.py imports')"
python -c "from backend.routers import sacco_admin; print('✓ sacco_admin.py imports')"

# Run tests
pytest tests/test_data_sync.py -v

# Check for errors
python -m py_compile backend/routers/manager.py
python -m py_compile backend/routers/sacco_admin.py
```

---

**Total Patches**: 8  
**Estimated Time**: 2-3 hours  
**Priority**: CRITICAL (Patches 1-3), HIGH (Patches 4-6), MEDIUM (Patches 7-8)
