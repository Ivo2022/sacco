# SHARES & DIVIDENDS SYSTEM - QUICK REFERENCE

## Current Status

**✅ IMPLEMENTED:**
- Share type management
- Member share subscriptions
- Share transfers between members
- Dividend declarations
- Dividend payments to members
- Transaction history tracking
- Multi-SACCO isolation
- Complete routes & templates

**❌ MISSING (Priority Order):**

### 🔴 CRITICAL (Phase 1)
1. **SACCO-level enable/disable** - Governance control
2. **Share withdrawal** - Member liquidity
3. **Template fix** - Bug in share.py line 57
4. **Consolidate dividends** - Remove duplicate code

### 🟡 IMPORTANT (Phase 2)
1. **Dividend reinvestment** - Auto-reinvest flag not used
2. **Manager analytics** - No share metrics visible
3. **UI/UX improvements** - Better forms and validation

### 🟢 NICE-TO-HAVE (Phase 3)
1. **Share approvals** - Manager approval workflow
2. **Share pricing** - Secondary market
3. **Advanced calculations** - Date-adjusted holdings
4. **Reporting** - Statements and audit reports

---

## Key Files

### Models
- **`backend/models/share.py`** (136 lines)
  - ShareType, Share, ShareTransaction, DividendDeclaration, DividendPayment

- **`backend/models/models.py`** (453 lines)
  - Sacco class (needs shares_enabled flag added at line ~48)
  - User class

### Services
- **`backend/services/share_service.py`** (235 lines)
  - create_share_type() ✅
  - subscribe_to_shares() ✅
  - transfer_shares() ✅
  - withdraw_shares() ❌ NEEDS ADDING
  - get_member_share_holdings() ✅
  - calculate_dividend_entitlement() ❌ NEEDS REMOVING (duplicate)
  - get_share_transaction_history() ✅

- **`backend/services/dividend_service.py`** (158 lines)
  - declare_dividend() ✅
  - calculate_dividend_for_member() ✅
  - pay_dividends() ✅
  - get_dividend_history() ✅

### Routes
- **`backend/routers/share.py`** (359 lines)
  - GET /shares/dashboard ✅
  - GET /shares/subscribe ✅
  - POST /shares/subscribe ✅
  - GET /shares/history ✅
  - GET /shares/withdraw ❌ NEEDS ADDING
  - POST /shares/withdraw ❌ NEEDS ADDING
  - **BUG:** Line 57 - incorrect TemplateResponse params

- **`backend/routers/dividend.py`** (246 lines)
  - GET /admin/dividends/declare ✅
  - POST /admin/dividends/declare ✅
  - POST /admin/dividends/{id}/pay ✅
  - GET /admin/dividends/history ✅
  - GET /dividends/entitlement ✅
  - GET /dividends/history ✅

### Dependencies
- **`backend/core/dependencies.py`**
  - get_current_user() ✅
  - require_role() ✅
  - require_manager() ✅
  - **NEEDS ADDING:**
    - require_shares_enabled()
    - require_dividends_enabled()

### Templates
```
✅ backend/templates/shares/
   ├── dashboard.html - Member holdings
   ├── subscribe.html - Purchase form
   ├── no_shares.html - Error page
   └── history.html - Transaction history

❌ NEEDS CREATING:
   └── withdraw.html - Withdrawal form

✅ backend/templates/dividends/
   ├── entitlement.html - Member calculation
   └── history.html - Payment history

✅ backend/templates/admin/
   ├── declare_dividend.html - Declaration form
   └── dividend_history.html - History view

❌ NEEDS CREATING:
   └── sacco_settings.html - Feature toggles
```

---

## Phase 1 Implementation Summary

### Task 1: SACCO Enable/Disable (2 hours)
**Files to modify:**
- `backend/models/models.py` - Add shares_enabled, dividends_enabled to Sacco
- `backend/core/dependencies.py` - Add 2 decorator functions
- `backend/routers/share.py` - Update 4 routes
- `backend/routers/dividend.py` - Update 2 routes
- Create `backend/routers/sacco_settings.py` - New settings routes
- Create `backend/templates/admin/sacco_settings.html` - New template

### Task 2: Share Withdrawal (4 hours)
**Files to modify:**
- `backend/services/share_service.py` - Add 2 functions
- `backend/routers/share.py` - Add 2 routes + imports
- Create `backend/templates/shares/withdraw.html` - New template

### Task 3: Template Fix (0.5 hours)
**Files to modify:**
- `backend/routers/share.py` - Line 57 only

### Task 4: Consolidate Dividends (1.5 hours)
**Files to modify:**
- `backend/services/share_service.py` - Delete 1 function
- `backend/routers/share.py` - Update imports

**Total Phase 1: 8 hours**

---

## Database Changes

### Sacco table
```sql
ALTER TABLE saccos ADD COLUMN shares_enabled BOOLEAN DEFAULT 0;
ALTER TABLE saccos ADD COLUMN dividends_enabled BOOLEAN DEFAULT 0;
```

### No other schema changes needed!
The models already support all Phase 1 functionality.

---

## Testing Approach

### Unit Tests
- Test each service function with valid/invalid inputs
- Test route permission checks
- Test calculations (refunds, dividends)

### Integration Tests
- Full user journey: subscribe → withdraw → dividend
- Multi-SACCO isolation
- Feature flag enforcement

### Manual Tests
- Visit each route
- Submit forms
- Check database records
- Verify flash messages

---

## Enums & Constants

### ShareTransactionType
- SUBSCRIPTION
- TRANSFER
- **WITHDRAWAL** (model supports, code needs to create)
- DIVIDEND_REINVESTMENT (model supports, code doesn't process)

### ShareClass
- CLASS_A (voting shares)
- CLASS_B (non-voting shares)
- CLASS_C (employee shares)

### DividendStatus
- pending (declared, not yet paid)
- paid (payments processed)
- cancelled (if needed)

---

## Error Handling

### Existing validation
✅ Min/max shares enforcement
✅ Share type availability check
✅ SACCO isolation

### Missing validation
❌ Withdrawal quantity validation (needs)
❌ Share withdrawal when disabled (needs)
❌ Dividend access when disabled (needs)

---

## Future Enhancements Preview

### Phase 2 (10 hours)
- Dividend reinvestment automation
- Manager analytics dashboard
- UI/UX improvements

### Phase 3 (8+ hours)
- Share approval workflow
- Share pricing mechanism
- Advanced dividend calculations
- Comprehensive reporting

---

## Common Patterns Used

### Routes use pattern
```python
@router.post("/endpoint")
async def handler(
    request: Request,
    field: Type = Form(...),
    user: User = Depends(require_role),
    db: Session = Depends(get_db)
):
    try:
        # Call service function
        result = service_function(db, ...)
        
        # Log action
        create_log(db, action="ACTION", ...)
        
        # Flash message
        request.session["flash_message"] = "Success"
        
        return RedirectResponse(...)
    except Exception as e:
        request.session["flash_message"] = f"Error: {e}"
        return RedirectResponse(...)
```

### Service functions
```python
def operation(db: Session, ...) -> Model:
    # Get related records
    record = db.query(Model).filter(...).first()
    
    # Validate
    if not valid:
        raise ValueError("Reason")
    
    # Execute
    # Update related records
    # Create transaction records
    
    db.commit()
    db.refresh(record)
    
    return record
```

---

## Dependency Tree

```
User Request
    ↓
Route Handler
    ├── get_current_user (dependency)
    ├── require_shares_enabled (dependency) ← NEW
    ├── get_db (dependency)
    └── require_manager (dependency)
    
Route Handler
    ↓
Service Function
    ├── Query models
    ├── Validate
    ├── Modify database
    └── Return result

Service Function result
    ↓
Template Context
    ├── Serialized data
    ├── Flash messages
    └── Helpers
    
Template renders
    ↓
HTML to Browser
```

---

## SQL Queries for Testing

```sql
-- Share holdings
SELECT u.email, st.name, s.quantity, s.total_value 
FROM shares s 
JOIN users u ON s.user_id = u.id 
JOIN share_types st ON s.share_type_id = st.id;

-- Transactions
SELECT st.transaction_type, st.quantity, st.total_amount, st.transaction_date
FROM share_transactions st
WHERE st.user_id = ?
ORDER BY st.transaction_date DESC;

-- Dividends
SELECT dd.fiscal_year, dd.rate, dd.total_dividend_pool, dd.status
FROM dividend_declarations dd
WHERE dd.sacco_id = ?
ORDER BY dd.fiscal_year DESC;

-- Payments
SELECT u.email, dp.amount, dp.is_reinvested, dp.paid_at
FROM dividend_payments dp
JOIN users u ON dp.user_id = u.id
WHERE dp.sacco_id = ?;

-- SACCO settings
SELECT name, shares_enabled, dividends_enabled
FROM saccos;
```

---

## Common Issues & Solutions

### Issue: "Shares system is not enabled"
**Cause:** shares_enabled = 0 in Sacco  
**Solution:** Visit /admin/sacco-settings and enable

### Issue: Template not rendering
**Cause:** Incorrect TemplateResponse params  
**Solution:** Check line 57 in share.py router

### Issue: Dividend amount not calculated
**Cause:** Using share_service.calculate_dividend_entitlement instead of dividend_service version  
**Solution:** Remove duplicate, use dividend_service version

### Issue: Withdrawal fails
**Cause:** Function not implemented yet  
**Solution:** Complete Phase 1 implementation

---

## Performance Considerations

### Current
- Simple queries with join operations
- No N+1 problems observed
- Proper indexing on sacco_id, user_id

### Optimization opportunities (for future)
- Add database indexes on share_type_id
- Cache share_type details in member dashboard
- Batch dividend payment processing
- Add pagination to large result sets

---

## Security Considerations

### Multi-SACCO Isolation
✅ All queries filter by sacco_id
✅ User.sacco_id enforced via authentication
✅ Routes validate sacco ownership

### Permission Checks
✅ Member routes check user is authenticated
✅ Manager routes use require_manager dependency
✅ Feature flags prevent access when disabled

### Input Validation
✅ Form inputs validated in routes
✅ Service functions validate parameters
✅ Database constraints enforce rules

### Audit Trail
✅ All significant actions logged
✅ Timestamps recorded
✅ User ID captured with action

---

**Document Generated:** 2026-04-01  
**Maintenance Status:** Active  
**Last Updated:** Phase 1 Design Complete

