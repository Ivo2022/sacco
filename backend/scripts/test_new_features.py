# backend/scripts/test_new_features.py
"""
Test script for new features - Smart Insights, Loan Intelligence, Notifications
Run with: python -m backend.scripts.test_new_features
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import SessionLocal
from models import User, Sacco, Saving, Loan, LoanPayment
from services.insights_service import InsightsService
from services.loan_intelligence import LoanIntelligenceService
from datetime import datetime, timedelta
import random

def create_test_data():
    """Create test data for demonstrating new features"""
    db = SessionLocal()
    
    try:
        # Get or create test SACCO
        sacco = db.query(Sacco).filter(Sacco.name == "Test SACCO").first()
        if not sacco:
            sacco = Sacco(
                name="Test SACCO",
                email="test@sacco.com",
                status="active"
            )
            db.add(sacco)
            db.commit()
            db.refresh(sacco)
            print(f"✓ Created test SACCO: {sacco.name}")
        
        # Create test members with different behaviors
        test_members = [
            {
                "email": "active_saver@test.com",
                "full_name": "Active Saver",
                "savings": [100000, 150000, 120000, 130000],  # Regular savings
                "loans": None
            },
            {
                "email": "inactive_saver@test.com",
                "full_name": "Inactive Saver",
                "savings": [50000],  # Only one saving, 45 days ago
                "loans": None
            },
            {
                "email": "good_borrower@test.com",
                "full_name": "Good Borrower",
                "savings": [200000, 250000, 300000],
                "loans": {
                    "amount": 500000,
                    "term": 6,
                    "payments": [85000, 85000, 85000, 85000]  # Regular payments
                }
            },
            {
                "email": "risky_borrower@test.com",
                "full_name": "Risky Borrower",
                "savings": [50000],
                "loans": {
                    "amount": 300000,
                    "term": 6,
                    "payments": [30000]  # Only one payment, overdue
                }
            }
        ]
        
        for member_data in test_members:
            # Create user
            user = db.query(User).filter(User.email == member_data["email"]).first()
            if not user:
                user = User(
                    email=member_data["email"],
                    full_name=member_data["full_name"],
                    username=member_data["email"].split("@")[0],
                    role="MEMBER",
                    sacco_id=sacco.id,
                    is_active=True,
                    is_approved=True
                )
                db.add(user)
                db.commit()
                db.refresh(user)
                print(f"✓ Created test member: {user.full_name}")
            
            # Add savings
            for i, amount in enumerate(member_data["savings"]):
                # Make older savings for inactive member
                days_ago = 45 if member_data["email"] == "inactive_saver@test.com" and i == 0 else i * 7
                saving = Saving(
                    sacco_id=sacco.id,
                    user_id=user.id,
                    type="deposit",
                    amount=amount,
                    payment_method="CASH",
                    timestamp=datetime.utcnow() - timedelta(days=days_ago)
                )
                db.add(saving)
            
            # Add loans
            if member_data["loans"]:
                loan = Loan(
                    sacco_id=sacco.id,
                    user_id=user.id,
                    amount=member_data["loans"]["amount"],
                    term=member_data["loans"]["term"],
                    status="approved",
                    interest_rate=12.0,
                    approved_at=datetime.utcnow() - timedelta(days=90)
                )
                loan.calculate_interest()
                db.add(loan)
                db.commit()
                db.refresh(loan)
                
                # Add loan payments
                for i, amount in enumerate(member_data["loans"]["payments"]):
                    # Make some payments overdue
                    days_ago = 15 if i == len(member_data["loans"]["payments"]) - 1 else i * 30
                    payment = LoanPayment(
                        loan_id=loan.id,
                        sacco_id=sacco.id,
                        user_id=user.id,
                        amount=amount,
                        payment_method="CASH",
                        timestamp=datetime.utcnow() - timedelta(days=days_ago)
                    )
                    db.add(payment)
        
        db.commit()
        print("\n✅ Test data created successfully!")
        
    except Exception as e:
        print(f"❌ Error creating test data: {e}")
        db.rollback()
    finally:
        db.close()

def test_insights():
    """Test Smart Insights Engine"""
    print("\n" + "="*60)
    print("TESTING: Smart Insights Engine")
    print("="*60)
    
    db = SessionLocal()
    try:
        sacco = db.query(Sacco).filter(Sacco.name == "Test SACCO").first()
        if not sacco:
            print("❌ Test SACCO not found. Run create_test_data() first.")
            return
        
        insights_service = InsightsService(db, sacco.id)
        
        # Test 1: Detect inactive savers
        print("\n📊 Test 1: Detecting Inactive Savers")
        inactive = insights_service.detect_inactive_savers(days_threshold=30)
        if inactive:
            print(f"✓ Found {len(inactive[0]['data'])} inactive savers")
            for saver in inactive[0]['data']:
                print(f"  - {saver['name']}: {saver['days_inactive']} days inactive")
        else:
            print("⚠ No inactive savers found (may need to adjust threshold)")
        
        # Test 2: Detect likely defaulters
        print("\n📊 Test 2: Detecting Likely Defaulters")
        defaulters = insights_service.detect_likely_defaulters()
        if defaulters:
            print(f"✓ Found {len(defaulters[0]['data'])} members at risk of default")
            for defaulter in defaulters[0]['data']:
                print(f"  - {defaulter['member_name']}: Risk Score {defaulter['risk_score']}")
                for reason in defaulter['reasons']:
                    print(f"    • {reason}")
        else:
            print("⚠ No defaulters detected")
        
        # Test 3: Get top savers
        print("\n📊 Test 3: Top Savers")
        top_savers = insights_service.get_top_savers(limit=5)
        if top_savers:
            print(f"✓ Top {len(top_savers[0]['data'])} savers:")
            for saver in top_savers[0]['data'][:3]:
                print(f"  - {saver['name']}: UGX {saver['total_savings']:,.2f}")
        
        # Test 4: Generate all insights
        print("\n📊 Test 4: Generating All Insights")
        all_insights = insights_service.generate_all_insights()
        print(f"✓ Generated {len(all_insights)} insights")
        for insight in all_insights:
            print(f"  - {insight['title']} ({insight['severity']})")
        
        # Test 5: Weekly summary
        print("\n📊 Test 5: Weekly Summary")
        summary = insights_service.generate_weekly_summary()
        print(f"✓ Weekly Summary Generated")
        print(f"  - Period: {summary['week_start'][:10]} to {summary['week_end'][:10]}")
        print(f"  - New Members: {summary['metrics']['new_members']}")
        print(f"  - New Savings: UGX {summary['metrics']['total_new_savings']:,.2f}")
        
        print("\n✅ Smart Insights tests completed!")
        
    except Exception as e:
        print(f"❌ Error testing insights: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def test_loan_intelligence():
    """Test Loan Intelligence System"""
    print("\n" + "="*60)
    print("TESTING: Loan Intelligence System")
    print("="*60)
    
    db = SessionLocal()
    try:
        # Get test users
        good_borrower = db.query(User).filter(User.email == "good_borrower@test.com").first()
        risky_borrower = db.query(User).filter(User.email == "risky_borrower@test.com").first()
        
        if not good_borrower or not risky_borrower:
            print("❌ Test users not found. Run create_test_data() first.")
            return
        
        loan_service = LoanIntelligenceService(db)
        
        # Test 1: Eligibility scoring
        print("\n📊 Test 1: Loan Eligibility Scoring")
        for user in [good_borrower, risky_borrower]:
            eligibility = loan_service.calculate_eligibility_score(user.id)
            print(f"\n  Member: {user.full_name}")
            print(f"  - Eligibility Score: {eligibility['score']}/100")
            print(f"  - Eligible: {'✓ Yes' if eligibility['eligible'] else '✗ No'}")
            if eligibility['eligible']:
                print(f"  - Max Loan Amount: UGX {eligibility['max_loan_amount']:,.2f}")
            print(f"  - Factors:")
            for factor in eligibility['factors'][:3]:
                print(f"    • {factor['factor']}: {factor['score']} points ({factor['value']})")
        
        # Test 2: Risk scoring for existing loans
        print("\n📊 Test 2: Loan Risk Scoring")
        loans = db.query(Loan).filter(Loan.user_id.in_([good_borrower.id, risky_borrower.id])).all()
        for loan in loans:
            risk = loan_service.calculate_risk_score(loan.id)
            print(f"\n  Loan #{loan.id} - {loan.user.full_name}")
            print(f"  - Risk Score: {risk['score']}/100")
            print(f"  - Risk Level: {risk['level'].upper()}")
            print(f"  - Risk Factors:")
            for factor in risk['factors'][:2]:
                print(f"    • {factor['factor']}: +{factor['risk_contribution']} points")
        
        # Test 3: Early warnings
        print("\n📊 Test 3: Early Warning System")
        sacco = db.query(Sacco).filter(Sacco.name == "Test SACCO").first()
        warnings = loan_service.get_early_warnings(sacco.id)
        print(f"✓ Found {len(warnings)} loans with early warnings")
        for warning in warnings[:3]:
            print(f"  - {warning['member_name']}: {warning['risk_level'].upper()} risk (Score: {warning['risk_score']})")
        
        # Test 4: Portfolio risk summary
        print("\n📊 Test 4: Portfolio Risk Summary")
        portfolio_risk = loan_service.get_loan_portfolio_risk_summary(sacco.id)
        print(f"  Total Loans: {portfolio_risk['total_loans']}")
        print(f"  Total Amount: UGX {portfolio_risk['total_amount']:,.2f}")
        print(f"  Risk Distribution:")
        for level, data in portfolio_risk['risk_distribution'].items():
            print(f"    - {level.upper()}: {data['count']} loans ({data['percentage']:.1f}%) - UGX {data['amount']:,.2f}")
        
        # Test 5: Generate repayment schedule
        print("\n📊 Test 5: Repayment Schedule Generation")
        if loans:
            test_loan = loans[0]
            schedule = loan_service.generate_repayment_schedule(test_loan.id)
            print(f"✓ Generated schedule for loan #{test_loan.id}")
            print(f"  Monthly Payment: UGX {schedule[0]['amount']:,.2f}" if schedule else "  No schedule generated")
            print(f"  Total Installments: {len(schedule)}")
        
        print("\n✅ Loan Intelligence tests completed!")
        
    except Exception as e:
        print(f"❌ Error testing loan intelligence: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

def test_api_endpoints():
    """Test API endpoints (requires running server)"""
    print("\n" + "="*60)
    print("TESTING: API Endpoints (Server Required)")
    print("="*60)
    print("""
    To test API endpoints manually:
    
    1. Start the server: uvicorn backend.main:app --reload
    
    2. Test endpoints using curl or browser:
    
    # Insights endpoints
    GET  http://localhost:8000/admin/insights/dashboard
    GET  http://localhost:8000/api/insights/alerts
    POST http://localhost:8000/api/insights/generate
    GET  http://localhost:8000/api/insights/weekly-summary
    GET  http://localhost:8000/api/insights/inactive-members?days=30
    GET  http://localhost:8000/api/insights/risk-analysis
    
    # Loan Intelligence endpoints
    GET  http://localhost:8000/api/loan/eligibility
    GET  http://localhost:8000/api/loan/early-warnings
    GET  http://localhost:8000/api/loan/portfolio-risk
    GET  http://localhost:8000/manager/loan-risk-dashboard
    """)

if __name__ == "__main__":
    print("\n" + "="*60)
    print("SACCO NEW FEATURES TEST SUITE")
    print("="*60)
    
    # Step 1: Create test data
    print("\n📝 Step 1: Creating test data...")
    create_test_data()
    
    # Step 2: Test Insights
    test_insights()
    
    # Step 3: Test Loan Intelligence
    test_loan_intelligence()
    
    # Step 4: API testing instructions
    test_api_endpoints()
    
    print("\n" + "="*60)
    print("✅ Testing completed!")
    print("="*60)
    print("\nNext steps:")
    print("1. Start the server: uvicorn backend.main:app --reload")
    print("2. Login as admin and visit: http://localhost:8000/admin/insights/dashboard")
    print("3. Visit: http://localhost:8000/manager/loan-risk-dashboard")
    print("4. Check the API endpoints listed above")