# FastAPI SACCO System - Data Synchronization Issues Report

## Executive Summary
This report documents critical data synchronization issues found in the FastAPI SACCO management system. These issues cause statistics displayed on different dashboards to be inconsistent and incorrect, leading to inaccurate financial reporting.

---

## Critical Issues Found

### 1. **UNDEFINED MODEL REFERENCE - `Payment` Model (CRITICAL)**

**Location**: `backend/routers/manager.py`, Lines 247-250

**Issue**:
```python
total_paid = db.query(func.sum(Payment.amount)).filter(
    Payment.loan_id == loan.id
).scalar() or 0
```

**Problem**:
- References a non-existent `Payment` model
- Should reference `LoanPayment` model instead
- This causes the total_outstanding calculation to FAIL with NameError
- Statistics displayed to managers are incorrect or undefined

**Impact**: 
- ❌ Manager dashboard crashes when calculating outstanding loans
- ❌ Total outstanding balance is incorrect
- ❌ Loan performance metrics are unreliable

**Fix Required**:
```python
# Change from:
total_paid = db.query(func.sum(Payment.amount)).filter(
    Payment.loan_id == loan.id
).scalar() or 0

# To:
total_paid = db.query(func.sum(LoanPayment.amount)).filter(
    LoanPayment.loan_id == loan.id
).scalar() or 0
```

---

### 2. **INCONSISTENT TOTAL OUTSTANDING CALCULATION**

**Location**: `backend/routers/manager.py`, Lines 240-255

**Issue**:
```python
# Gets all active loans, then manually loops to calculate outstanding
active_loans = db.query(Loan).filter(
    Loan.sacco_id == sacco_id,
    Loan.status == 'active'
).all()

total_outstanding = 0
for loan in active_loans:
    # Recalculates interest instead of using stored values
    interest = loan.amount * (loan.interest_rate / 100) * (loan.duration_months / 12)
    total_payable = loan.amount + interest
    # ... then references Payment model (undefined)
```

**Problems**:
1. Recalculates interest manually instead of using `Loan.total_interest` field
2. Uses `Payment` model which doesn't exist
3. Only counts ACTIVE loans, but database may have:
   - Approved loans (not yet disbursed)
   - Completed loans (still owed payments?)
   - Overdue loans (definitely owed)

**Comparison with Admin Dashboard** (`sacco_admin.py`, Lines 47-49):
```python
outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status == 'approved'  # Different status filter!
).scalar() or 0.0
```

**Impact**:
- ❌ Manager sees one total, Admin sees different total
- ❌ Doesn't account for overdue loans
- ❌ Doesn't use consistent calculation methodology

---

### 3. **DUPLICATE `serialize_loan()` FUNCTIONS**

**Location**: `backend/routers/manager.py`, Lines 23-88

**Issue**:
```python
# First definition (lines 23-45)
def serialize_loan(loan: Loan) -> dict:
    """Serialize loan ORM object to dictionary with user info."""
    return {
        "id": loan.id,
        "amount": loan.amount,
        # ... fields ...
    }

# Second definition (lines 47-88) - OVERWRITES THE FIRST!
def serialize_loan(loan: Loan) -> dict:
    """Serialize loan ORM object to dictionary with calculated fields."""
    # ... different implementation ...
```

**Problems**:
1. First function definition is completely ignored
2. Second function includes a nested function `calculate_monthly_payment`
3. Both have different return structures
4. Creates confusion about which fields are available in serialized loans

**Impact**:
- ❌ Data structure inconsistency
- ❌ First definition's logic is dead code
- ❌ Unclear which fields are available in templates

---

### 4. **MISSING SACCO_ID FILTER IN SOME QUERIES**

**Location**: `backend/routers/manager.py`, Lines 221-237

**Issue**:
```python
# These queries filter by sacco_id correctly:
total_interest_earned = db.query(func.sum(Loan.total_interest)).filter(
    Loan.sacco_id == sacco_id,  # ✓ Has sacco_id filter
    Loan.status.in_(['completed', 'active'])
).scalar() or 0

# But later:
total_loan_amount = db.query(func.sum(Loan.amount)).filter(
    Loan.sacco_id == sacco_id  # ✓ Has sacco_id
).scalar() or 0
```

While most queries have sacco_id filters, inconsistencies could lead to:
- Data from other SACCOs leaking into reports
- Multi-tenant isolation failures

**Impact**:
- ⚠️ Risk of cross-SACCO data leakage
- ⚠️ Incorrect statistics if multiple SACCOs in system

---

### 5. **DIFFERENT TOTAL_DISBURSED CALCULATION ACROSS ROUTES**

**Manager.py** (Line 229-237):
```python
total_disbursed = db.query(func.sum(Loan.amount)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status.in_(['active', 'completed', 'approved'])
).scalar() or 0
```

**Sacco_admin.py** (Line 47-49):
```python
outstanding_loans = db.query(func.coalesce(func.sum(Loan.amount), 0.0)).filter(
    Loan.sacco_id == sacco_id,
    Loan.status == 'approved'
).scalar() or 0.0
```

**Problem**:
- Different status filters
- Different null-handling (`or 0` vs `coalesce`)
- Manager shows total for active+completed+approved
- Admin shows only approved loans as "outstanding"

**Impact**:
- ❌ Managers and admins see completely different figures
- ❌ Impossible to verify financial reports
- ❌ Confusing for stakeholders

---

### 6. **INTEREST CALCULATION INCONSISTENCY**

**Manager.py** (Line 243-244):
```python
# Recalculates interest manually
interest = loan.amount * (loan.interest_rate / 100) * (loan.duration_months / 12)
total_payable = loan.amount + interest
```

**Loan Model** (should be stored):
```python
# Should have:
Loan.total_interest  # Pre-calculated
Loan.total_payable   # Pre-calculated
```

**Problem**:
- Manager route recalculates instead of trusting database values
- What if `duration_months` is NULL?
- What if interest calculation method changed since loan creation?

**Impact**:
- ❌ Historical interest calculations won't match
- ❌ Reports change if calculation logic changes
- ❌ Audit trail is compromised

---

### 7. **UNTRACKED PAYMENT STATUS**

**Location**: Multiple routes access `LoanPayment` but no validation of:
- Is the payment actually credited to the loan?
- What if payment.loan_id doesn't match?
- What if payment is marked as disputed/reversed?

**Missing Fields** in loan payment tracking:
- payment_status (pending/confirmed/disputed/reversed)
- is_verified
- verification_timestamp
- verified_by_user_id

**Impact**:
- ⚠️ Payments might be counted multiple times
- ⚠️ Disputed/reversed payments still counted
- ⚠️ No audit trail for payment verification

---

### 8. **STATISTICS SERVICE DISCREPANCIES**

**Location**: `backend/services/statistics_service.py`

**Questions**:
1. Does `get_sacco_statistics()` calculate the same metrics as manager dashboard?
2. Are results cached or fresh?
3. Does it use same date ranges?
4. Same loan status filters?

**Impact**:
- ⚠️ Potentially returning cached/stale data
- ⚠️ Different calculations in different parts of system

---

### 9. **30-DAY TRANSACTION CALCULATION**

**Location**: `backend/routers/manager.py`, Lines 278-287

```python
thirty_days_ago = datetime.utcnow() - timedelta(days=30)
transactions_30d_orm = db.query(Saving).filter(
    Saving.sacco_id == sacco_id,
    Saving.timestamp >= thirty_days_ago
).all()
total_deposits_30d = sum(t.amount for t in transactions_30d_orm if t.type == "deposit")
total_withdrawals_30d = sum(t.amount for t in transactions_30d_orm if t.type == "withdrawal")
```

**Issues**:
1. Uses `utcnow()` - may be inconsistent with user's timezone
2. Fetches ALL records then filters in Python (inefficient)
3. Uses string comparison `t.type == "deposit"` instead of enum

**Better Implementation**:
```python
total_deposits_30d = db.query(func.sum(Saving.amount)).filter(
    Saving.sacco_id == sacco_id,
    Saving.type == 'deposit',
    Saving.timestamp >= thirty_days_ago
).scalar() or 0
```

---

## Data Sync Cross-Check Matrix

| Metric | Manager Dashboard | Admin Dashboard | Sacco Admin | Statistics Service | Consistency |
|--------|------------------|-----------------|-------------|-------------------|-------------|
| Total Disbursed | active+completed+approved | - | approved only | ? | ❌ NO |
| Outstanding Loans | Manual calculation (broken) | Same as approved | - | ? | ❌ NO |
| Total Interest | from Loan.total_interest | - | - | ? | ⚠️ UNCLEAR |
| Total Payments | from LoanPayment sum | - | - | ? | ⚠️ UNCLEAR |
| Member Count | Filtered by SACCO_ID | Not multi-tenant | By SACCO_ID | ? | ⚠️ PARTIAL |
| Deposit Totals | Sum(Saving.amount) | Sum(Saving.amount) | - | ? | ✓ SAME METHOD |

---

## Recommended Fixes (Priority Order)

### PRIORITY 1 - CRITICAL (Do Immediately)
1. **Fix `Payment` → `LoanPayment` reference** in manager.py line 247
2. **Consolidate total_outstanding calculation** - use consistent method everywhere
3. **Fix duplicate serialize_loan() functions** - keep only one implementation

### PRIORITY 2 - HIGH (Do Before Next Release)
4. **Standardize loan status filters** across all routes:
   - Define enum for valid loan statuses: PENDING, APPROVED, ACTIVE, COMPLETED, OVERDUE, REJECTED
   - Use consistently everywhere
   
5. **Move calculations to database** - don't recalculate in Python:
   - Use SQL SUM/AVG functions
   - Store pre-calculated totals in Loan model
   
6. **Implement Statistics Service Consistency**:
   - All dashboard data should come from single statistics service
   - Services should cache results with known TTL
   - Clear cache on any loan/payment updates

### PRIORITY 3 - MEDIUM (Do in Next Sprint)
7. **Add payment verification workflow**:
   - Payment must be explicitly verified before counting
   - Audit trail for all payment status changes
   
8. **Audit all SACCO_ID filters** - ensure multi-tenant isolation
9. **Timezone consistency** - use consistent timezone across system
10. **Add data validation tests** - verify dashboard stats against raw data

---

## Testing Checklist

After applying fixes, verify:

- [ ] Manager dashboard loads without errors
- [ ] Manager dashboard totals match admin dashboard totals
- [ ] Outstanding loans = Active + Overdue (not completed)
- [ ] Total disbursed = Active + Approved + Completed
- [ ] Total payments sum matches LoanPayment table
- [ ] 30-day metrics are in correct date range
- [ ] All SACCOs see only their own data
- [ ] Loan payment flows don't double-count
- [ ] Statistics service returns consistent results
- [ ] All dashboard metrics match API endpoints

---

## Long-Term Improvements

1. **Create Data Warehouse Schema**:
   - Pre-calculated fact tables for metrics
   - Dimensional tables for dimensions
   - ETL pipeline to sync data

2. **Implement Event Sourcing**:
   - Track all changes to loans/payments
   - Rebuild state from events
   - Audit trail is inherent

3. **Add Real-Time Monitoring**:
   - Alert on data inconsistencies
   - Monitor calculation differences
   - Track metric changes over time

4. **Create Reconciliation Reports**:
   - Daily: Compare manager vs admin totals
   - Weekly: Verify loan book against payments
   - Monthly: Reconcile with bank statements

---

## Questions for Development Team

1. What is the intended meaning of each loan status?
2. Should "outstanding" include approved loans not yet disbursed?
3. Are payments immediately counted or need verification?
4. What timezone should system use for all calculations?
5. Should statistics be cached? If so, what TTL?
6. Are there other loan status values besides the documented ones?

---

Generated: 2024
System: FastAPI SACCO Management Platform
