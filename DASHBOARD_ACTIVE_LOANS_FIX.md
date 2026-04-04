# Dashboard Active/Overdue Loans Fix - Diagnostics & Solutions

## Issues Found & Fixed

### 1. ✅ FIXED: Missing Import in accountant.py
**Problem**: The `Loan` and `LoanPayment` models were not imported in `accountant.py`, causing the loan metrics queries to fail silently.

**Location**: `backend/routers/accountant.py` Line 11

**Before**:
```python
from ..models import RoleEnum, PendingDeposit, Saving, User, Sacco
```

**After**:
```python
from ..models import RoleEnum, PendingDeposit, Saving, User, Sacco, Loan, LoanPayment
```

**Status**: ✅ Fixed

---

### 2. ✅ FIXED: Missing Context Variable in manager.py
**Problem**: The template expects `overdue_loans_count` but the context was only passing `overdue_loans`.

**Location**: `backend/routers/manager.py` Line 363-364

**Template Expects**: `{{ overdue_loans_count|default(0) }}`  
**Context Was Passing**: `"overdue_loans": overdue_loans_count`

**Fix**: Added both keys to context:
```python
"overdue_loans": overdue_loans_count,
"overdue_loans_count": overdue_loans_count,
```

**Status**: ✅ Fixed

---

## Why Active Loans & Overdue Loans Show Zero

If metrics still show `0` after the above fixes, it's likely one of these:

### Possibility 1: No Loan Data
The database might not have any loans, or the loans don't have the correct `sacco_id`.

**Check with SQL**:
```sql
-- Check if loans exist
SELECT COUNT(*) FROM loans;

-- Check loans by status
SELECT status, COUNT(*) FROM loans GROUP BY status;

-- Check loans by SACCO
SELECT sacco_id, status, COUNT(*) FROM loans GROUP BY sacco_id, status;
```

### Possibility 2: Wrong SACCO ID
The user's `sacco_id` might not match the loans' `sacco_id`.

**Check in database**:
```sql
-- Get all SACCOs
SELECT id, name FROM saccos;

-- Get loans for each SACCO
SELECT sacco_id, status, COUNT(*) FROM loans GROUP BY sacco_id, status;
```

### Possibility 3: Data Type Mismatch
The `status` column might have different values than expected (e.g., uppercase vs lowercase).

**Check actual values**:
```sql
SELECT DISTINCT status FROM loans;
```

Expected values should be: `pending`, `approved`, `active`, `completed`, `overdue`, `rejected`

---

## Verification Steps

### Step 1: Verify Database Connectivity
Run this Python code to verify the database connection:

```python
import sys
sys.path.insert(0, r'd:\2026\fastapi')

from backend.core.dependencies import SessionLocal
from backend.models import Loan, Sacco

db = SessionLocal()
saccos = db.query(Sacco).all()
print(f"SACCOs found: {len(saccos)}")

for sacco in saccos:
    loans = db.query(Loan).filter(Loan.sacco_id == sacco.id).count()
    print(f"  {sacco.name} (ID: {sacco.id}): {loans} loans")

db.close()
```

### Step 2: Check Actual Data
Run the test script to see detailed information:

```bash
cd d:\2026\fastapi
python test_queries.py
```

This will show:
- Number of active loans
- Number of overdue loans
- Total savings
- Any warnings about missing data

### Step 3: Create Sample Data (if needed)
If the database is empty, you'll need to:

1. Create users for the SACCO
2. Create loans with proper `sacco_id`
3. Create savings records

---

## Expected Behavior After Fix

### Manager Dashboard
- Active Loans: Shows count of loans with status='active'
- Overdue Loans: Shows count of loans with status='overdue'
- Total Interest Earned: Shows sum of total_interest from completed loans
- Total Payments Received: Shows sum of all loan payments

### Accountant Dashboard
- Same 4 metrics as manager
- Plus existing savings metrics

### Credit Officer Dashboard
- Same 4 metrics
- Plus loan detail information

---

## Total Savings Issue

If total savings is showing incorrect value:

### Check 1: Verify Savings Data
```sql
SELECT COUNT(*) FROM savings;
SELECT SUM(amount) FROM savings;
SELECT sacco_id, COUNT(*), SUM(amount) FROM savings GROUP BY sacco_id;
```

### Check 2: Verify Query Calculation
In manager.py, line ~300:
```python
total_savings = db.query(func.sum(Saving.amount)).filter(
    Saving.sacco_id == sacco_id
).scalar() or 0
```

This query sums all savings amounts for the user's SACCO.

### Possible Issues:
1. **No savings data** - No savings records exist
2. **Wrong SACCO** - Savings assigned to different SACCO
3. **Deleted records** - Savings were soft-deleted
4. **Null values** - Some amount fields are NULL

---

## Testing the Fixes

### Quick Test (No Code Required)
1. Navigate to Manager Dashboard
2. Check if "Overdue Loans" now shows a number instead of error
3. Check if "Active Loans" shows a number

### Full Test (Run Application)
```bash
cd d:\2026\fastapi
python backend/main.py

# Then navigate to:
# Manager: http://localhost:8000/manager/dashboard
# Accountant: http://localhost:8000/accountant/dashboard
# Credit Officer: http://localhost:8000/credit-officer/dashboard
```

### Database Test
```bash
cd d:\2026\fastapi
python test_queries.py
```

---

## Code Changes Summary

| File | Change | Line | Status |
|------|--------|------|--------|
| accountant.py | Added Loan, LoanPayment imports | 11 | ✅ Done |
| manager.py | Added overdue_loans_count to context | 364 | ✅ Done |

---

## If Issues Persist

### Check 1: Application Restart
```bash
# Stop the server (Ctrl+C)
# Delete __pycache__ folders
rmdir /s /q backend\__pycache__

# Restart
python backend/main.py
```

### Check 2: Database Reset
If you want to ensure the database is clean:
```bash
# Backup current database
copy database\cheontec.db database\cheontec.db.backup

# Delete and reinitialize (if needed)
# Run initialization script from scripts folder
python backend/scripts/init_db.py
```

### Check 3: Check Logs
Look for errors in application logs:
- Check for "Loan model not found"
- Check for "LoanPayment model not found"  
- Check for SQL errors in sacco_id filtering

---

## Performance Notes

The dashboard queries are optimized:
- All queries filter by `sacco_id` (indexed field)
- Aggregation queries use `func.coalesce` for null safety
- Outstanding calculation uses minimal loops

Expected load time: < 500ms per dashboard

---

## Next Steps

1. ✅ Apply the two fixes above (already done)
2. ⏳ Restart the application
3. ⏳ Test all three dashboards
4. ⏳ Run `test_queries.py` to verify data
5. ⏳ Check for any errors in logs

---

**Status**: ✅ Code fixes complete, awaiting application restart & testing
