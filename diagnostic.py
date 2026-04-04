"""
Diagnostic script to check dashboard data and issues
"""
import sys
sys.path.insert(0, r'd:\2026\fastapi')

from backend.core.dependencies import SessionLocal
from backend.models import Loan, LoanPayment, Saving, Sacco, User, RoleEnum
from sqlalchemy import func

def check_database():
    db = SessionLocal()
    
    print("=" * 80)
    print("DASHBOARD DATA DIAGNOSTIC")
    print("=" * 80)
    
    try:
        # 1. Check SACCOs
        print("\n1. SACCO INFORMATION")
        print("-" * 80)
        saccos = db.query(Sacco).all()
        print(f"Total SACCOs: {len(saccos)}")
        for sacco in saccos:
            print(f"\n  SACCO: {sacco.name} (ID: {sacco.id})")
            
            # Check loans for this SACCO
            active = db.query(Loan).filter(
                Loan.sacco_id == sacco.id,
                Loan.status == "active"
            ).count()
            overdue = db.query(Loan).filter(
                Loan.sacco_id == sacco.id,
                Loan.status == "overdue"
            ).count()
            total = db.query(Loan).filter(Loan.sacco_id == sacco.id).count()
            
            print(f"    Loans: Total={total}, Active={active}, Overdue={overdue}")
            
            # Check savings
            savings_total = db.query(func.sum(Saving.amount)).filter(
                Saving.sacco_id == sacco.id
            ).scalar() or 0
            print(f"    Total Savings: {savings_total}")
            
            # Check users
            managers = db.query(User).filter(
                User.sacco_id == sacco.id,
                User.role == RoleEnum.MANAGER
            ).count()
            accountants = db.query(User).filter(
                User.sacco_id == sacco.id,
                User.role == RoleEnum.ACCOUNTANT
            ).count()
            print(f"    Users: Managers={managers}, Accountants={accountants}")
        
        # 2. Check loan statuses
        print("\n2. LOAN STATUS DISTRIBUTION")
        print("-" * 80)
        statuses = db.query(Loan.status, func.count(Loan.id)).group_by(Loan.status).all()
        for status, count in statuses:
            print(f"  {status}: {count}")
        
        # 3. Check sample loans
        print("\n3. SAMPLE LOAN DATA")
        print("-" * 80)
        sample_loans = db.query(Loan).limit(5).all()
        if sample_loans:
            for loan in sample_loans:
                print(f"\n  Loan ID: {loan.id}")
                print(f"    SACCO ID: {loan.sacco_id}")
                print(f"    User ID: {loan.user_id}")
                print(f"    Amount: {loan.amount}")
                print(f"    Status: {loan.status}")
                print(f"    Total Payable: {loan.total_payable}")
                print(f"    Total Interest: {loan.total_interest}")
                
                # Check payments
                payments = db.query(LoanPayment).filter(
                    LoanPayment.loan_id == loan.id
                ).all()
                print(f"    Payments: {len(payments)}")
                if payments:
                    total_paid = sum(p.amount for p in payments)
                    print(f"      Total Paid: {total_paid}")
        else:
            print("  No loans found in database!")
        
        # 4. Check savings details
        print("\n4. SAVINGS DATA")
        print("-" * 80)
        total_savings = db.query(func.sum(Saving.amount)).scalar() or 0
        savings_count = db.query(Saving).count()
        print(f"Total Savings Records: {savings_count}")
        print(f"Total Savings Amount: {total_savings}")
        
        # 5. Test queries manually
        print("\n5. MANUAL QUERY TESTS")
        print("-" * 80)
        if saccos:
            sacco = saccos[0]
            print(f"\nTesting queries for SACCO: {sacco.name} (ID: {sacco.id})")
            
            # Test active loans count
            active_count = db.query(Loan).filter(
                Loan.sacco_id == sacco.id,
                Loan.status == "active"
            ).count()
            print(f"  Active loans count: {active_count}")
            
            # Test overdue loans count
            overdue_count = db.query(Loan).filter(
                Loan.sacco_id == sacco.id,
                Loan.status == "overdue"
            ).count()
            print(f"  Overdue loans count: {overdue_count}")
            
            # Test total interest earned
            interest = db.query(func.coalesce(func.sum(Loan.total_interest), 0)).filter(
                Loan.sacco_id == sacco.id,
                Loan.status == 'completed'
            ).scalar() or 0
            print(f"  Total interest earned: {interest}")
            
            # Test total payments
            payments = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
                LoanPayment.sacco_id == sacco.id
            ).scalar() or 0
            print(f"  Total payments received: {payments}")
            
            # Test total savings
            savings = db.query(func.sum(Saving.amount)).filter(
                Saving.sacco_id == sacco.id
            ).scalar() or 0
            print(f"  Total savings: {savings}")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    check_database()
