"""
Test script to verify dashboard queries and add sample data if needed
"""
import sys
sys.path.insert(0, r'd:\2026\fastapi')

from backend.core.dependencies import SessionLocal
from backend.models import Loan, LoanPayment, Saving, Sacco, User, RoleEnum
from sqlalchemy import func, text

def test_queries():
    db = SessionLocal()
    
    print("=" * 80)
    print("TESTING DASHBOARD QUERIES")
    print("=" * 80)
    
    try:
        # Get first SACCO
        sacco = db.query(Sacco).first()
        if not sacco:
            print("\nERROR: No SACCO found in database!")
            print("Please create a SACCO first.")
            db.close()
            return
        
        sacco_id = sacco.id
        print(f"\nTesting with SACCO: {sacco.name} (ID: {sacco_id})")
        
        # Test 1: Count loans by status
        print("\n1. Testing Loan Counts")
        print("-" * 80)
        
        # Raw SQL to verify table structure
        print("\nChecking Loan table columns...")
        result = db.execute(text("PRAGMA table_info(loans)")).fetchall()
        print("Columns: " + ", ".join([col[1] for col in result]))
        
        # Test active loans
        active_query = db.query(Loan).filter(
            Loan.sacco_id == sacco_id,
            Loan.status == "active"
        )
        active_count = active_query.count()
        print(f"\nActive loans for SACCO {sacco_id}: {active_count}")
        if active_count > 0:
            print("  Sample active loans:")
            for loan in active_query.limit(2).all():
                print(f"    ID: {loan.id}, Amount: {loan.amount}, Status: {loan.status}")
        
        # Test overdue loans
        overdue_query = db.query(Loan).filter(
            Loan.sacco_id == sacco_id,
            Loan.status == "overdue"
        )
        overdue_count = overdue_query.count()
        print(f"\nOverdue loans for SACCO {sacco_id}: {overdue_count}")
        if overdue_count > 0:
            print("  Sample overdue loans:")
            for loan in overdue_query.limit(2).all():
                print(f"    ID: {loan.id}, Amount: {loan.amount}, Status: {loan.status}")
        
        # Test 2: Test aggregation queries
        print("\n2. Testing Aggregation Queries")
        print("-" * 80)
        
        # Test interest earned
        interest = db.query(func.coalesce(func.sum(Loan.total_interest), 0)).filter(
            Loan.sacco_id == sacco_id,
            Loan.status == 'completed'
        ).scalar() or 0
        print(f"\nTotal interest earned (completed): {interest}")
        
        # Test payments received
        payments = db.query(func.coalesce(func.sum(LoanPayment.amount), 0)).filter(
            LoanPayment.sacco_id == sacco_id
        ).scalar() or 0
        print(f"Total payments received: {payments}")
        
        # Test savings
        savings = db.query(func.sum(Saving.amount)).filter(
            Saving.sacco_id == sacco_id
        ).scalar() or 0
        print(f"Total savings: {savings}")
        
        # Test 3: Check if there are ANY loans at all
        print("\n3. Overall Loan Statistics")
        print("-" * 80)
        
        total_loans = db.query(Loan).count()
        print(f"\nTotal loans (all SACCOs): {total_loans}")
        
        loans_this_sacco = db.query(Loan).filter(Loan.sacco_id == sacco_id).count()
        print(f"Total loans (SACCO {sacco_id}): {loans_this_sacco}")
        
        if loans_this_sacco == 0:
            print("\n⚠️  WARNING: No loans found for this SACCO!")
            print("   The dashboard will show 0 for all loan metrics.")
            
            # Check if loans exist for other SACCOs
            all_loans_by_sacco = db.query(Loan.sacco_id, func.count(Loan.id)).group_by(Loan.sacco_id).all()
            if all_loans_by_sacco:
                print("\n  Loans by SACCO:")
                for sacco_id_found, count in all_loans_by_sacco:
                    print(f"    SACCO {sacco_id_found}: {count} loans")
        
        # Test 4: Check savings data
        print("\n4. Savings Statistics")
        print("-" * 80)
        
        total_savings = db.query(Saving).count()
        print(f"\nTotal savings records (all SACCOs): {total_savings}")
        
        savings_this_sacco = db.query(Saving).filter(Saving.sacco_id == sacco_id).count()
        print(f"Total savings records (SACCO {sacco_id}): {savings_this_sacco}")
        
        if savings_this_sacco == 0:
            print("\n⚠️  WARNING: No savings records found for this SACCO!")
            print("   Total savings will show 0 on the dashboard.")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    test_queries()
