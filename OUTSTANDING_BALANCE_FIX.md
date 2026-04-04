# Outstanding Balance Calculation Fix - Member Loans

## Issue Identified ❌

The outstanding balance calculation in the member loans view was **excluding interest** and only calculating:
```python
outstanding = loan.amount - repaid
```

This meant that the outstanding balance only reflected principal minus payments, ignoring the accrued interest that should be paid.

## Solution Applied ✅

Updated the `get_user_loans_with_repayment()` function in `backend/routers/member.py` (line 159) to properly calculate outstanding balance:

### Before (WRONG):
```python
outstanding = max(0.0, loan.amount - repaid)
```

### After (CORRECT):
```python
# Outstanding = total_payable (principal + interest) - repaid
outstanding = max(0.0, loan.total_payable - repaid)
```

## What Changed

- **File**: `backend/routers/member.py`
- **Function**: `get_user_loans_with_repayment()`
- **Line**: 159
- **Change**: Now uses `loan.total_payable` instead of `loan.amount`

## Impact

✅ **Outstanding balance now correctly includes**:
- Principal amount
- Accrued interest
- Minus total payments made

✅ **Affects**:
- Member loans view (`/member/loans`)
- Member dashboard outstanding summary
- Member dashboard active loans outstanding
- All notifications related to outstanding balance
- Maximum payment amount validation in the repayment form

## Example

**Scenario**: 
- Loan principal: UGX 10,000
- Interest rate: 10% annually
- Term: 12 months
- Total payable: UGX 11,000
- Payments made: UGX 3,000

**Before Fix**:
- Outstanding = 10,000 - 3,000 = **UGX 7,000** ❌ (Missing interest)

**After Fix**:
- Outstanding = 11,000 - 3,000 = **UGX 8,000** ✅ (Includes interest)

## Consistency Note

This fix aligns with:
- ✅ The `total_payable` field already stored in the Loan model
- ✅ The audit recommendations (Fix #5 in FIX_IMPLEMENTATION_GUIDE.md)
- ✅ Financial best practices (always include interest in outstanding balance)
- ✅ The manager/admin dashboards which also use `total_payable`

## Testing

To verify the fix works:

1. Create a test loan with:
   - Principal: 10,000
   - Interest rate: 10%
   - Term: 12 months

2. Make a payment of 5,000

3. View the member loans page

4. Verify outstanding balance = 11,000 - 5,000 = **6,000** ✅

---

**Fix Applied**: April 3, 2026  
**Status**: ✅ Complete  
**Tested**: Ready for testing
