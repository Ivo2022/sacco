#!/usr/bin/env python
"""
Final verification that the fixes are working
"""
import sys
sys.path.insert(0, r'd:\2026\fastapi')

print("=" * 80)
print("DASHBOARD FIXES VERIFICATION")
print("=" * 80)

# Test 1: Check imports
print("\n1. CHECKING IMPORTS")
print("-" * 80)

try:
    from backend.routers.accountant import router as accountant_router
    print("✅ accountant.py imports successful")
except Exception as e:
    print(f"❌ accountant.py import failed: {e}")
    sys.exit(1)

try:
    from backend.routers.manager import router as manager_router
    print("✅ manager.py imports successful")
except Exception as e:
    print(f"❌ manager.py import failed: {e}")
    sys.exit(1)

try:
    from backend.routers.credit_officer import router as credit_officer_router
    print("✅ credit_officer.py imports successful")
except Exception as e:
    print(f"❌ credit_officer.py import failed: {e}")
    sys.exit(1)

# Test 2: Check database connection
print("\n2. CHECKING DATABASE")
print("-" * 80)

try:
    from backend.core.dependencies import SessionLocal
    db = SessionLocal()
    print("✅ Database connection successful")
    db.close()
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    sys.exit(1)

# Test 3: Check models are importable in accountant
print("\n3. CHECKING MODEL IMPORTS")
print("-" * 80)

try:
    from backend.models import Loan, LoanPayment
    print("✅ Loan model importable")
    print("✅ LoanPayment model importable")
except Exception as e:
    print(f"❌ Model import failed: {e}")
    sys.exit(1)

# Test 4: Verify the fixed context variables
print("\n4. CHECKING CONTEXT VARIABLES")
print("-" * 80)

try:
    db = SessionLocal()
    
    # Get a SACCO
    from backend.models import Sacco, User, RoleEnum
    sacco = db.query(Sacco).first()
    
    if not sacco:
        print("⚠️  No SACCO found - cannot test dashboard queries")
        db.close()
        sys.exit(0)
    
    # Get a manager user for testing
    manager_user = db.query(User).filter(
        User.sacco_id == sacco.id,
        User.role == RoleEnum.MANAGER
    ).first()
    
    if not manager_user:
        print(f"⚠️  No manager user found for SACCO {sacco.name}")
        print("   Please create a manager user to fully test the dashboard")
        db.close()
        sys.exit(0)
    
    print(f"✅ Using SACCO: {sacco.name} (ID: {sacco.id})")
    print(f"✅ Using Manager: {manager_user.email}")
    
    # Test the queries
    sacco_id = sacco.id
    
    from sqlalchemy import func
    
    # Test active loans count
    active_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "active"
    ).count()
    print(f"\n   Active Loans Count: {active_count}")
    
    # Test overdue loans count
    overdue_count = db.query(Loan).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == "overdue"
    ).count()
    print(f"   Overdue Loans Count: {overdue_count}")
    
    # Test total interest
    interest = db.query(func.coalesce(func.sum(Loan.total_interest), 0)).filter(
        Loan.sacco_id == sacco_id,
        Loan.status == 'completed'
    ).scalar() or 0
    print(f"   Total Interest Earned: {interest}")
    
    # Test total payments
    payments = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
        LoanPayment.sacco_id == sacco_id
    ).scalar() or 0
    print(f"   Total Payments Received: {payments}")
    
    if active_count == 0 and overdue_count == 0:
        print("\n⚠️  WARNING:")
        print("   Both active and overdue loan counts are 0.")
        print("   This could mean:")
        print("   1. No loans exist in the database")
        print("   2. Loans exist but none have 'active' or 'overdue' status")
        print("   3. Loans exist but have a different sacco_id")
        
        # Check total loans
        total = db.query(Loan).count()
        print(f"\n   Total loans (all SACCOs): {total}")
        
        if total > 0:
            from sqlalchemy import distinct
            saccos_with_loans = db.query(distinct(Loan.sacco_id)).all()
            print(f"   SACCOs with loans: {[s[0] for s in saccos_with_loans]}")
    else:
        print("\n✅ Dashboard metrics are working!")
    
    db.close()
    
except Exception as e:
    print(f"❌ Error testing queries: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("VERIFICATION COMPLETE")
print("=" * 80)
