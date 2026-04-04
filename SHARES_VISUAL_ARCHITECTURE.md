# SHARES & DIVIDENDS SYSTEM - VISUAL ARCHITECTURE GUIDE

---

## CURRENT STATE (BEFORE PHASE 1)

```
┌─────────────────────────────────────────────────────────────┐
│                    SACCO MEMBER PORTAL                      │
└─────────────────────────────────────────────────────────────┘
                              ▼
    ┌──────────────┬──────────────────┬──────────────┐
    ▼              ▼                  ▼              ▼
  SHARES       DIVIDENDS          LOANS          SAVINGS
  ✅ Buy        ✅ View            ✅ Full       ✅ Full
  ❌ Sell       ✅ History         ✅ Full       ✅ Full
  ❌ Withdraw   ❌ Can't control if disabled
  
  └─ Backend Routes (359 lines)
  └─ Service Functions (235 lines)
  └─ Database Models (136 lines)
  └─ Templates (8 files)

  ⚠️  ISSUES:
      • No SACCO-level control
      • Members can't withdraw
      • Duplicate code
      • Template bug
```

---

## PHASE 1 CHANGES (AFTER IMPLEMENTATION)

```
┌─────────────────────────────────────────────────────────────┐
│                    SACCO ADMIN PANEL                        │
│                   [NEW SETTINGS PAGE]                       │
└─────────────────────────────────────────────────────────────┘
    Shares System:  [Disabled  ▼] [Enable] ← NEW CONTROL
    Dividends:      [Enabled   ▼] [Disable]← NEW CONTROL


┌─────────────────────────────────────────────────────────────┐
│                    SACCO MEMBER PORTAL                      │
└─────────────────────────────────────────────────────────────┘
                              ▼
    ┌──────────────┬──────────────────┬──────────────┐
    ▼              ▼                  ▼              ▼
  SHARES       DIVIDENDS          LOANS          SAVINGS
  ✅ Buy        ✅ View            ✅ Full       ✅ Full
  ✅ Sell[NEW]  ✅ History         ✅ Full       ✅ Full
  ✅ Withdraw   ✅ Only if enabled
  
  Enhanced Features:
  └─ Withdrawal form [NEW] 
  └─ Route guards [NEW]
  └─ Service functions [NEW]
  └─ Clean codebase [IMPROVED]
  
  ✅ ISSUES FIXED:
      ✅ SACCO-level control
      ✅ Members can withdraw
      ✅ No duplicate code
      ✅ Template fixed
```

---

## DATA FLOW - SHARE SUBSCRIPTION

### BEFORE & AFTER (Same for subscription, different for withdrawal)

```
┌──────────────┐
│   Member     │
└──────┬───────┘
       │ GET /shares/subscribe
       ▼
┌──────────────────────────────────────┐
│  Form: Select Type, Quantity          │
│  [NEW] Hidden: Check shares_enabled   │
└──────┬───────────────────────────────┘
       │ POST /shares/subscribe
       ▼
┌──────────────────────────────────────┐
│  Route Handler (share.py)             │
│  [NEW] require_shares_enabled check   │
│  ├─ Get user, db, form data           │
│  └─ Call subscribe_to_shares()        │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Service Layer (share_service.py)     │
│  subscribe_to_shares()                │
│  ├─ Validate min/max quantities       │
│  ├─ Create Share record               │
│  ├─ Create ShareTransaction record    │
│  └─ Return Share object               │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Database                             │
│  ├─ shares table (updated)            │
│  ├─ share_transactions (new record)   │
│  └─ logs table (audit trail)          │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Response to Member                   │
│  ├─ Redirect to /shares/dashboard     │
│  ├─ Flash: "Success message"          │
│  └─ Show updated holdings             │
└──────────────────────────────────────┘
```

---

## DATA FLOW - SHARE WITHDRAWAL [NEW]

```
┌──────────────┐
│   Member     │
└──────┬───────┘
       │ GET /shares/withdraw [NEW]
       ▼
┌──────────────────────────────────────┐
│  Route: withdrawal_form()             │
│  ├─ Check require_shares_enabled      │
│  ├─ Call get_withdrawal_options()     │
│  └─ Render withdraw.html form         │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Form: Select Share, Qty, Reason      │
│  ├─ Share Type dropdown               │
│  ├─ Quantity input (validated)        │
│  ├─ Reason textarea                   │
│  ├─ Payment method selection          │
│  └─ JavaScript calc: Refund amount    │
└──────┬───────────────────────────────┘
       │ POST /shares/withdraw [NEW]
       ▼
┌──────────────────────────────────────┐
│  Route: process_withdrawal()          │
│  ├─ Check require_shares_enabled      │
│  ├─ Validate quantity > 0             │
│  ├─ Check sufficient balance          │
│  └─ Call withdraw_shares()            │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Service: withdraw_shares() [NEW]     │
│  ├─ Get Share record                  │
│  ├─ Calculate value per share         │
│  ├─ Create WITHDRAWAL transaction     │
│  ├─ Update Share quantity/value       │
│  ├─ Mark inactive if qty = 0          │
│  └─ Commit to DB                      │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Database Updates                     │
│  ├─ shares.quantity (decreased)       │
│  ├─ shares.total_value (decreased)    │
│  ├─ shares.is_active (maybe false)    │
│  ├─ share_transactions (new record)   │
│  │   └─ type: WITHDRAWAL              │
│  │   └─ amount: negative (outgoing)   │
│  └─ logs (audit trail)                │
└──────┬───────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  Response to Member                   │
│  ├─ Redirect to /shares/dashboard     │
│  ├─ Flash: "Withdrawn X shares"       │
│  │        "Refund: UGX 5,000,000"     │
│  └─ Show updated holdings (decreased) │
└──────────────────────────────────────┘
```

---

## SACCO SETTINGS FLOW [NEW]

```
┌──────────────────────┐
│   SACCO Manager      │
└──────┬───────────────┘
       │ GET /admin/sacco-settings [NEW]
       ▼
┌────────────────────────────────────────────┐
│  Route: sacco_settings()                   │
│  ├─ Check require_manager                  │
│  └─ Render sacco_settings.html [NEW]       │
└──────┬─────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────┐
│  Settings Page [NEW TEMPLATE]              │
│  ┌──────────────────────────────────────┐  │
│  │ Shares System:                       │  │
│  │ Currently: [DISABLED]               │  │
│  │ [Enable Shares Button]              │  │
│  └──────────────────────────────────────┘  │
│  ┌──────────────────────────────────────┐  │
│  │ Dividends System:                    │  │
│  │ Currently: [ENABLED]                │  │
│  │ [Disable Dividends Button]          │  │
│  └──────────────────────────────────────┘  │
└──────┬─────────────────────────────────────┘
       │ POST /admin/sacco-settings/toggle-shares [NEW]
       ▼
┌────────────────────────────────────────────┐
│  Route: toggle_shares()                    │
│  ├─ Get SACCO from user                    │
│  ├─ Set shares_enabled = True/False        │
│  ├─ Commit to database                     │
│  ├─ Log action with timestamp              │
│  └─ Redirect with flash message            │
└──────┬─────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────┐
│  Database                                  │
│  saccos table                              │
│  ├─ id, name, email, ...                   │
│  ├─ shares_enabled = 1 [NEW]               │
│  ├─ dividends_enabled = 0 [NEW]            │
│  └─ Last modified timestamp                │
└──────┬─────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────┐
│  Result: Shares enabled for entire SACCO   │
│  ├─ All members can now:                   │
│  │  ├─ See /shares/dashboard               │
│  │  ├─ Use /shares/subscribe               │
│  │  ├─ Use /shares/withdraw                │
│  │  └─ Use /shares/history                 │
│  └─ All members blocked if disabled        │
└────────────────────────────────────────────┘
```

---

## DEPENDENCY CHAIN

### BEFORE Phase 1
```
Route Handler
    ▼
get_current_user() ← Only check
    ▼
Service Function
    ▼
Database
```

### AFTER Phase 1
```
Route Handler
    ▼
require_shares_enabled() [NEW]
    ├─ Check user exists (get_current_user)
    ├─ Check user.sacco exists
    └─ Check sacco.shares_enabled == True
    ▼
Service Function
    ▼
Database
```

---

## FILE RELATIONSHIPS

```
┌─────────────────────────────────────────────────────────┐
│ backend/models/models.py                                │
│  class Sacco                                            │
│  ├─ shares_enabled [NEW]                                │
│  └─ dividends_enabled [NEW]                             │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│ backend/core/dependencies.py                            │
│  require_shares_enabled() [NEW]                         │
│  require_dividends_enabled() [NEW]                      │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│ backend/routers/share.py                                │
│  GET /shares/dashboard [UPDATED]                        │
│  POST /shares/subscribe [UPDATED]                       │
│  GET /shares/withdraw [NEW]                             │
│  POST /shares/withdraw [NEW]                            │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│ backend/services/share_service.py                       │
│  subscribe_to_shares() [EXISTING]                       │
│  withdraw_shares() [NEW]                                │
│  get_withdrawal_options() [NEW]                         │
│  calculate_dividend_entitlement() [DELETED]             │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│ backend/models/share.py                                 │
│  class Share                                            │
│  class ShareTransaction (uses WITHDRAWAL type)          │
└─────────────────────────────────────────────────────────┘


┌─────────────────────────────────────────────────────────┐
│ backend/routers/sacco_settings.py [NEW FILE]            │
│  GET /admin/sacco-settings [NEW]                        │
│  POST /admin/sacco-settings/toggle-shares [NEW]         │
│  POST /admin/sacco-settings/toggle-dividends [NEW]      │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│ backend/templates/admin/sacco_settings.html [NEW]       │
│  Settings form with toggle buttons                      │
└─────────────────────────────────────────────────────────┘
```

---

## DATABASE SCHEMA CHANGES

### BEFORE
```
saccos table
├── id (PK)
├── name
├── email
├── phone
├── address
├── registration_no
├── website
├── status
├── created_at
├── membership_fee
├── referred_by_id (FK)
└── referral_commission_paid
```

### AFTER (Phase 1)
```
saccos table
├── id (PK)
├── name
├── email
├── phone
├── address
├── registration_no
├── website
├── status
├── created_at
├── membership_fee
├── referred_by_id (FK)
├── referral_commission_paid
├── shares_enabled [NEW] ← Boolean, default=False
└── dividends_enabled [NEW] ← Boolean, default=False

shares table ← NO CHANGES (uses existing structure)
share_types table ← NO CHANGES
share_transactions table ← NO CHANGES (uses existing WITHDRAWAL type)
```

---

## ROUTE STRUCTURE - BEFORE & AFTER

### Member Routes - BEFORE
```
GET  /shares/dashboard          (show holdings)
GET  /shares/subscribe          (form)
POST /shares/subscribe          (process) ⚠️ NO FEATURE CHECK
GET  /shares/history            (transactions)
GET  /dividends/entitlement     (calculation) ⚠️ NO FEATURE CHECK
GET  /dividends/history         (payments)
```

### Member Routes - AFTER (Phase 1)
```
GET  /shares/dashboard          (show holdings) ✅ FEATURE CHECK
GET  /shares/subscribe          (form) ✅ FEATURE CHECK
POST /shares/subscribe          (process) ✅ FEATURE CHECK
GET  /shares/withdraw [NEW]     (form) ✅ FEATURE CHECK
POST /shares/withdraw [NEW]     (process) ✅ FEATURE CHECK
GET  /shares/history            (transactions) ✅ FEATURE CHECK
GET  /dividends/entitlement     (calculation) ✅ FEATURE CHECK
GET  /dividends/history         (payments) ✅ FEATURE CHECK
```

### Manager Routes - NEW (Phase 1)
```
GET  /admin/sacco-settings      (settings page) [NEW]
POST /admin/sacco-settings/toggle-shares [NEW]
POST /admin/sacco-settings/toggle-dividends [NEW]
```

---

## ERROR FLOW - SHARES DISABLED

```
Member visits /shares/dashboard
              │
              ▼
┌────────────────────────────────┐
│ require_shares_enabled         │
│ Dependency Check               │
│ ├─ user.sacco.shares_enabled?  │
│ └─ Result: FALSE               │
└──────────┬──────────────────────┘
           │
           ▼
┌────────────────────────────────┐
│ HTTPException(403)             │
│ "Shares system is not enabled  │
│  for your SACCO"               │
└──────────┬──────────────────────┘
           │
           ▼
┌────────────────────────────────┐
│ Error Page Shown to Member     │
│                                │
│ [403 Forbidden]                │
│ Shares system not enabled      │
│ Contact your administrator     │
└────────────────────────────────┘
```

---

## CALCULATION EXAMPLES

### Share Withdrawal Calculation

```
Member has:
  ├─ Share Type: "Regular Shares"
  ├─ Quantity: 100 shares
  ├─ Total Value: 50,000,000 UGX
  └─ Value per share: 500,000 UGX

Member wants to withdraw: 25 shares

Calculation:
  └─ Refund = 25 × 500,000 = 12,500,000 UGX

After withdrawal:
  ├─ Quantity: 75 shares (decreased)
  ├─ Total Value: 37,500,000 UGX (decreased)
  └─ Transaction recorded: WITHDRAWAL, -25, -12,500,000
```

### Transaction Record (Database)

```
share_transactions table:
┌────┬──────┬──────┬──┬────────────┬──────────┬────────┬──────────────┐
│ id │ type │ user │  │ quantity   │ per_share│ amount │ date         │
├────┼──────┼──────┼──┼────────────┼──────────┼────────┼──────────────┤
│ 1  │SUBS  │   1  │  │ +100       │ 500,000  │+50M    │ 2026-03-01   │
│ 2  │WITH  │   1  │  │ -25        │ 500,000  │-12.5M  │ 2026-04-01   │
└────┴──────┴──────┴──┴────────────┴──────────┴────────┴──────────────┘

Result:
  Net position: 75 shares @ 37.5M UGX
  Audit trail: Complete history
  Accounting: Balanced
```

---

## PHASE PROGRESSION

```
CURRENT (Before Phase 1)
├─ Members can buy shares ✅
├─ Members can transfer ✅
├─ Managers can declare dividends ✅
├─ Members can receive dividends ✅
├─ [SACCO cannot disable] ❌
├─ [Members cannot withdraw] ❌
├─ [Duplicate code] ❌
└─ [Template bug] ❌

                    ▼ 8 HOURS WORK

AFTER PHASE 1
├─ Members can buy shares ✅
├─ Members can transfer ✅
├─ Members can withdraw ✅ NEW
├─ Managers can declare dividends ✅
├─ Members can receive dividends ✅
├─ [SACCO can enable/disable] ✅ NEW
├─ [No duplicate code] ✅
└─ [Templates fixed] ✅

                    ▼ 10 HOURS WORK

AFTER PHASE 2
├─ [Dividend reinvestment] ✅ NEW
├─ [Manager analytics] ✅ NEW
├─ [Better UI/UX] ✅ NEW
└─ All Phase 1 features ✅

                    ▼ 8+ HOURS WORK

AFTER PHASE 3
├─ [Share approval workflow] ✅
├─ [Share pricing mechanism] ✅
├─ [Advanced calculations] ✅
├─ [Comprehensive reports] ✅
└─ All Phase 1-2 features ✅
```

---

## SUCCESS METRICS

### Before Phase 1
- ❌ Members locked into shares (no liquidity)
- ❌ SACCO has no control (always enabled)
- ❌ Technical debt (duplicate code)
- ⚠️ User experience issues (template bug)

### After Phase 1
- ✅ Members can withdraw (liquidity)
- ✅ SACCO controls feature (governance)
- ✅ Clean codebase (no debt)
- ✅ Smooth UX (fixed templates)
- 🚀 Ready for Phase 2

### Measurement
```
Test Coverage: 100% of new code
Error Rate: < 0.1%
User Satisfaction: ++ (more options)
Technical Debt: Reduced
```

---

**This visual guide complements the detailed documentation. Use together for complete understanding.**

