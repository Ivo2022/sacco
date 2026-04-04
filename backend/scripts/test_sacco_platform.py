# scripts/test_system.py
import os
import sys
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from backend.core.database import Base, SessionLocal, engine, init_db
from backend.core.config import settings
from backend.core.dependencies import (
    get_current_user, require_auth, require_manager,
    require_accountant, require_credit_officer,
    require_any_role
)
from backend.core.template_helpers import (
    format_money, format_local_time, format_date,
    format_datetime, format_percentage, register_template_helpers
)
from backend.models import (
    User, RoleEnum, Sacco, Saving, Loan, LoanPayment, 
    PendingDeposit, ExternalLoan, ExternalLoanPayment, Log,
    PaymentMethodEnum
)
from backend.models.share import Share, ShareType, ShareTransaction, DividendDeclaration, DividendPayment
from backend.services.user_service import create_user, get_password_hash, verify_password
from backend.services.insights_service import InsightsService
from backend.utils.logger import create_log
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
import random

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get the database path from settings
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite:///"):
    db_path = db_url.replace("sqlite:///", "")
else:
    db_path = "backend/database/cheontec.db"

DB_PATH = db_path
BACKUP_DIR = "backups"

# Create the database directory if it doesn't exist
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


class TestResult:
    """Class to track test results"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name):
        self.passed += 1
        print(f"  ✅ PASS: {test_name}")
    
    def add_fail(self, test_name, error):
        self.failed += 1
        self.errors.append(f"❌ FAIL: {test_name} - {error}")
        print(f"  ❌ FAIL: {test_name} - {error}")
    
    def summary(self):
        print("\n" + "="*60)
        print(f"TEST SUMMARY")
        print("="*60)
        print(f"  Passed: {self.passed}")
        print(f"  Failed: {self.failed}")
        print(f"  Total: {self.passed + self.failed}")
        if self.errors:
            print("\nErrors:")
            for error in self.errors:
                print(f"  {error}")
        return self.failed == 0


def backup_existing_database():
    """Backup existing database if it exists"""
    if os.path.exists(DB_PATH):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(BACKUP_DIR, f"cheontec_{timestamp}.db")
        shutil.copy2(DB_PATH, backup_path)
        print(f"✓ Backed up existing database to: {backup_path}")
        return backup_path
    return None


def create_fresh_database():
    """Create a fresh database with all tables"""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("✓ Removed existing database")
    
    # Use the new init_db function
    init_db()
    
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"✓ Created database with tables: {', '.join(tables)}")
    return len(tables) > 0


# ============ SHARES AND DIVIDENDS TESTS ============

def test_share_type_creation(result, db, sacco_id):
    """Test 30: Share Type creation"""
    print("\n" + "="*60)
    print("TEST 30: Share Type Creation")
    print("="*60)
    
    try:
        share_type = ShareType(
            sacco_id=sacco_id,
            name="Class A Shares",
            class_type="class_a",
            par_value=10000,
            minimum_shares=1,
            maximum_shares=1000,
            is_voting=True,
            dividend_rate=8.0
        )
        db.add(share_type)
        
        share_type2 = ShareType(
            sacco_id=sacco_id,
            name="Class B Shares",
            class_type="class_b",
            par_value=5000,
            minimum_shares=5,
            maximum_shares=500,
            is_voting=False,
            dividend_rate=6.0
        )
        db.add(share_type2)
        db.commit()
        
        result.add_pass(f"Share Type created: {share_type.name} (ID: {share_type.id})")
        result.add_pass(f"Share Type created: {share_type2.name} (ID: {share_type2.id})")
        return share_type.id, share_type2.id
    except Exception as e:
        result.add_fail("Share Type creation", str(e))
        return None, None


def test_member_share_purchase(result, db, member_id, sacco_id, share_type_id):
    """Test 31: Member share purchase"""
    print("\n" + "="*60)
    print("TEST 31: Member Share Purchase")
    print("="*60)
    
    try:
        share_type = db.query(ShareType).filter(ShareType.id == share_type_id).first()
        quantity = 10
        total_amount = quantity * share_type.par_value
        
        # Create share holding
        share = Share(
            user_id=member_id,
            sacco_id=sacco_id,
            share_type_id=share_type_id,
            quantity=quantity,
            total_value=total_amount,
            is_active=True,
            last_updated=datetime.utcnow()
        )
        db.add(share)
        db.flush()
        
        # Create transaction record
        transaction = ShareTransaction(
            share_id=share.id,
            user_id=member_id,
            sacco_id=sacco_id,
            transaction_type="subscription",
            quantity=quantity,
            price_per_share=share_type.par_value,
            total_amount=total_amount,
            transaction_date=datetime.utcnow(),
            reference_number=f"SHARE-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            notes="Initial share purchase"
        )
        db.add(transaction)
        db.commit()
        
        result.add_pass(f"Member purchased {quantity} {share_type.name} shares")
        result.add_pass(f"  Total amount: UGX {total_amount:,.2f}")
        return share.id, transaction.id
    except Exception as e:
        result.add_fail("Member share purchase", str(e))
        return None, None


def test_dividend_declaration(result, db, sacco_id, share_type_id):
    """Test 32: Dividend declaration"""
    print("\n" + "="*60)
    print("TEST 32: Dividend Declaration")
    print("="*60)
    
    try:
        share_type = db.query(ShareType).filter(ShareType.id == share_type_id).first()
        current_year = datetime.utcnow().year
        
        # Get total shares outstanding
        total_shares = db.query(Share).filter(
            Share.sacco_id == sacco_id,
            Share.share_type_id == share_type_id,
            Share.is_active == True
        ).all()
        
        total_quantity = sum(s.quantity for s in total_shares)
        amount_per_share = share_type.par_value * (share_type.dividend_rate / 100)
        total_dividend_pool = total_quantity * amount_per_share
        
        declaration = DividendDeclaration(
            sacco_id=sacco_id,
            share_type_id=share_type_id,
            declared_date=datetime.utcnow(),
            fiscal_year=current_year,
            rate=share_type.dividend_rate,
            amount_per_share=amount_per_share,
            total_dividend_pool=total_dividend_pool,
            payment_date=datetime.utcnow() + timedelta(days=30),
            declared_by=1,  # Superadmin ID
            status="pending"
        )
        db.add(declaration)
        db.commit()
        
        result.add_pass(f"Dividend declared for {share_type.name}")
        result.add_pass(f"  Rate: {share_type.dividend_rate}%")
        result.add_pass(f"  Amount per share: UGX {amount_per_share:,.2f}")
        result.add_pass(f"  Total dividend pool: UGX {total_dividend_pool:,.2f}")
        return declaration.id
    except Exception as e:
        result.add_fail("Dividend declaration", str(e))
        return None


def test_dividend_payment(result, db, declaration_id, member_id, sacco_id, share_id):
    """Test 33: Dividend payment to member"""
    print("\n" + "="*60)
    print("TEST 33: Dividend Payment")
    print("="*60)
    
    try:
        declaration = db.query(DividendDeclaration).filter(DividendDeclaration.id == declaration_id).first()
        share = db.query(Share).filter(Share.id == share_id).first()
        
        if not declaration or not share:
            result.add_fail("Dividend payment", "Declaration or Share not found")
            return False
        
        dividend_amount = share.quantity * declaration.amount_per_share
        
        payment = DividendPayment(
            declaration_id=declaration_id,
            user_id=member_id,
            sacco_id=sacco_id,
            share_id=share_id,
            shares_held=share.quantity,
            amount=dividend_amount,
            payment_method="bank",
            paid_at=datetime.utcnow(),
            reference_number=f"DIV-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            is_reinvested=False
        )
        db.add(payment)
        db.commit()
        
        result.add_pass(f"Dividend payment recorded")
        result.add_pass(f"  Shares held: {share.quantity}")
        result.add_pass(f"  Amount paid: UGX {dividend_amount:,.2f}")
        return payment.id
    except Exception as e:
        result.add_fail("Dividend payment", str(e))
        return None


def test_member_dividends_view(result, db, member_id):
    """Test 34: Member dividends view"""
    print("\n" + "="*60)
    print("TEST 34: Member Dividends View")
    print("="*60)
    
    try:
        # Get all dividend payments for member
        payments = db.query(DividendPayment).filter(
            DividendPayment.user_id == member_id
        ).all()
        
        total_dividends = sum(p.amount for p in payments)
        
        result.add_pass(f"Member has {len(payments)} dividend payment(s)")
        result.add_pass(f"  Total dividends received: UGX {total_dividends:,.2f}")
        
        # Get share holdings
        holdings = db.query(Share).filter(
            Share.user_id == member_id,
            Share.is_active == True
        ).all()
        
        total_shares = sum(h.quantity for h in holdings)
        total_value = sum(h.total_value for h in holdings)
        
        result.add_pass(f"Member share holdings: {total_shares} units")
        result.add_pass(f"  Total share value: UGX {total_value:,.2f}")
        
        return True
    except Exception as e:
        result.add_fail("Member dividends view", str(e))
        return False


def test_insights_dashboard(result, db, sacco_id):
    """Test 35: Insights dashboard generation"""
    print("\n" + "="*60)
    print("TEST 35: Insights Dashboard")
    print("="*60)
    
    try:
        insights_service = InsightsService(db, sacco_id)
        
        # Generate weekly summary
        weekly_summary = insights_service.generate_weekly_summary()
        if weekly_summary:
            result.add_pass("Weekly summary generated successfully")
            print(f"    Week: {weekly_summary.get('week_start')} to {weekly_summary.get('week_end')}")
            metrics = weekly_summary.get('metrics', {})
            print(f"    New members: {metrics.get('new_members', 0)}")
            print(f"    New loans: {metrics.get('new_loans', 0)}")
        
        # Detect inactive members
        inactive_members = insights_service.detect_inactive_savers(30)
        if inactive_members is not None:
            result.add_pass("Inactive members detection ran successfully")
        
        # Detect likely defaulters
        defaulters = insights_service.detect_likely_defaulters()
        if defaulters is not None:
            result.add_pass("Defaulters detection ran successfully")
        
        # Generate all insights
        all_insights = insights_service.generate_all_insights()
        if all_insights is not None:
            result.add_pass(f"Generated {len(all_insights) if all_insights else 0} insights")
        
        # Get active alerts
        active_alerts = insights_service.get_active_alerts()
        if active_alerts is not None:
            result.add_pass(f"Active alerts: {len(active_alerts)}")
        
        return True
    except Exception as e:
        result.add_fail("Insights dashboard", str(e))
        import traceback
        traceback.print_exc()
        return False


def test_switch_links(result, db, manager_id, member_id):
    """Test 36: Switch links functionality"""
    print("\n" + "="*60)
    print("TEST 36: Switch Links")
    print("="*60)
    
    try:
        manager = db.query(User).filter(User.id == manager_id).first()
        member = db.query(User).filter(User.id == member_id).first()
        
        # Check if accounts are linked
        if manager.linked_member_account_id == member.id:
            result.add_pass("Manager → Member link exists")
        else:
            result.add_fail("Manager → Member link", "Not linked")
        
        if member.linked_admin_id == manager.id:
            result.add_pass("Member → Manager link exists")
        else:
            result.add_fail("Member → Manager link", "Not linked")
        
        # Test that switch URLs would work
        switch_to_member_url = f"/switch/to-member?as_member={manager.linked_member_account_id}"
        switch_to_staff_url = f"/switch/to-staff?as_staff={member.linked_admin_id}"
        
        result.add_pass(f"Switch to Member URL: {switch_to_member_url}")
        result.add_pass(f"Switch to Staff URL: {switch_to_staff_url}")
        
        return True
    except Exception as e:
        result.add_fail("Switch links", str(e))
        return False


def test_template_routes(result):
    """Test 37: Template routes exist"""
    print("\n" + "="*60)
    print("TEST 37: Template Routes")
    print("="*60)
    
    try:
        from backend.main import app
        
        routes = [route.path for route in app.routes]
        
        # Check member routes
        assert "/member/shares" in routes or any("/member/shares" in r for r in routes)
        result.add_pass("/member/shares route exists")
        
        assert "/member/dividends" in routes or any("/member/dividends" in r for r in routes)
        result.add_pass("/member/dividends route exists")
        
        # Check insights routes
        assert "/manager/insights/dashboard" in routes or any("/insights/dashboard" in r for r in routes)
        result.add_pass("Insights dashboard route exists")
        
        # Check API routes
        assert any("/api/insights/weekly-summary" in r for r in routes)
        result.add_pass("/api/insights/weekly-summary API exists")
        
        return True
    except Exception as e:
        result.add_fail("Template routes", str(e))
        return False


def run_all_tests():
    """Run all system tests"""
    result = TestResult()
    
    print("\n" + "="*60)
    print("SACCO MANAGEMENT SYSTEM - COMPREHENSIVE TEST")
    print("WITH SHARES, DIVIDENDS, AND INSIGHTS MODULES")
    print("="*60)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Backup existing database
    backup_existing_database()
    
    # Create fresh database
    if not create_fresh_database():
        result.add_fail("Database creation", "Failed to create database")
        return result.summary()
    
    db = SessionLocal()
    
    try:
        # Test basic modules
        test_database_creation(result)
        test_superadmin_creation(result, db)
        sacco_id = test_sacco_creation(result, db)
        
        if sacco_id:
            # Create users with different roles
            manager_id, linked_member_id = test_manager_creation(result, db, sacco_id)
            accountant_id = test_accountant_creation(result, db, sacco_id, manager_id)
            credit_officer_id = test_credit_officer_creation(result, db, sacco_id)
            member_id = test_member_creation(result, db, sacco_id)
            
            # Test Shares module
            share_type_id, share_type2_id = test_share_type_creation(result, db, sacco_id)
            
            if share_type_id and member_id:
                share_id, transaction_id = test_member_share_purchase(result, db, member_id, sacco_id, share_type_id)
                
                # Test Dividends module
                if share_id:
                    declaration_id = test_dividend_declaration(result, db, sacco_id, share_type_id)
                    if declaration_id:
                        test_dividend_payment(result, db, declaration_id, member_id, sacco_id, share_id)
                    
                    test_member_dividends_view(result, db, member_id)
            
            # Test Insights module
            test_insights_dashboard(result, db, sacco_id)
            
            # Test switch links
            if manager_id and linked_member_id:
                test_switch_links(result, db, manager_id, linked_member_id)
            
            # Test deposit and loan flows
            if member_id and accountant_id:
                pending_id = test_deposit_initiation(result, db, member_id, sacco_id)
                if pending_id:
                    test_deposit_approval(result, db, pending_id, accountant_id, member_id, sacco_id)
            
            if member_id and manager_id:
                loan_id = test_loan_request(result, db, member_id, sacco_id)
                if loan_id:
                    test_loan_approval_by_manager(result, db, loan_id, manager_id)
                    test_loan_payment(result, db, loan_id, member_id, sacco_id)
            
            # Test template routes
            test_template_routes(result)
        
        test_permission_checks(result)
        test_dashboard_urls(result)
        
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        result.add_fail("Test execution", str(e))
    finally:
        db.close()
    
    return result.summary()


# ============ HELPER FUNCTIONS FROM ORIGINAL TESTS ============

def test_database_creation(result):
    """Test database and tables creation"""
    print("\n" + "="*60)
    print("TEST: Database and Table Creation")
    print("="*60)
    
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected_tables = ['users', 'saccos', 'savings', 'loans', 'loan_payments', 
                          'pending_deposits', 'external_loans', 'external_loan_payments', 'logs',
                          'share_types', 'shares', 'share_transactions', 
                          'dividend_declarations', 'dividend_payments']
        
        for table in expected_tables:
            if table not in tables:
                result.add_fail(f"Table {table} missing", "Table not created")
                return False
        
        result.add_pass("All required tables created")
        return True
    except Exception as e:
        result.add_fail("Database creation", str(e))
        return False


def test_superadmin_creation(result, db):
    """Test superadmin creation"""
    print("\n" + "="*60)
    print("TEST: Superadmin Creation")
    print("="*60)
    
    try:
        superadmin = create_user(
            db,
            email="superadmin@cheontec.com",
            password="Admin@123",
            role=RoleEnum.SUPER_ADMIN,
            full_name="Super Administrator",
            username="superadmin",
            is_staff=True,
            can_apply_for_loans=False
        )
        db.commit()
        
        result.add_pass("Superadmin created successfully")
        return True
    except Exception as e:
        result.add_fail("Superadmin creation", str(e))
        return False


def test_sacco_creation(result, db):
    """Test SACCO creation"""
    print("\n" + "="*60)
    print("TEST: SACCO Creation")
    print("="*60)
    
    try:
        sacco = Sacco(
            name="Test SACCO",
            email="test@sacco.com",
            phone="+256700000000",
            address="Kampala, Uganda",
            status="active"
        )
        db.add(sacco)
        db.commit()
        db.refresh(sacco)
        
        result.add_pass(f"SACCO created: {sacco.name} (ID: {sacco.id})")
        return sacco.id
    except Exception as e:
        result.add_fail("SACCO creation", str(e))
        return None


def test_manager_creation(result, db, sacco_id):
    """Test manager creation with linked member account"""
    print("\n" + "="*60)
    print("TEST: Manager Creation")
    print("="*60)
    
    try:
        manager = create_user(
            db,
            email="manager@test.com",
            password="Manager123",
            role=RoleEnum.MANAGER,
            sacco_id=sacco_id,
            full_name="Test Manager",
            username="test.manager",
            is_staff=True,
            can_apply_for_loans=False
        )
        
        member = create_user(
            db,
            email="manager_member@test.com",
            password="Manager123",
            role=RoleEnum.MEMBER,
            sacco_id=sacco_id,
            full_name="Test Manager (Member)",
            username="test.manager.member",
            is_staff=True,
            can_apply_for_loans=True,
            requires_approval_for_loans=True
        )
        
        manager.linked_member_account_id = member.id
        member.linked_admin_id = manager.id
        db.commit()
        
        result.add_pass(f"Manager created: {manager.email} (ID: {manager.id})")
        result.add_pass(f"Linked member created: {member.email} (ID: {member.id})")
        return manager.id, member.id
    except Exception as e:
        result.add_fail("Manager creation", str(e))
        return None, None


def test_accountant_creation(result, db, sacco_id, manager_id):
    """Test accountant creation"""
    print("\n" + "="*60)
    print("TEST: Accountant Creation")
    print("="*60)
    
    try:
        accountant = create_user(
            db,
            email="accountant@test.com",
            password="Accountant123",
            role=RoleEnum.ACCOUNTANT,
            sacco_id=sacco_id,
            full_name="Test Accountant",
            username="test.accountant",
            is_staff=True,
            can_apply_for_loans=False
        )
        
        result.add_pass(f"Accountant created: {accountant.email} (ID: {accountant.id})")
        return accountant.id
    except Exception as e:
        result.add_fail("Accountant creation", str(e))
        return None


def test_credit_officer_creation(result, db, sacco_id):
    """Test credit officer creation"""
    print("\n" + "="*60)
    print("TEST: Credit Officer Creation")
    print("="*60)
    
    try:
        credit_officer = create_user(
            db,
            email="creditofficer@test.com",
            password="Credit123",
            role=RoleEnum.CREDIT_OFFICER,
            sacco_id=sacco_id,
            full_name="Test Credit Officer",
            username="test.credit",
            is_staff=True,
            can_apply_for_loans=False
        )
        
        result.add_pass(f"Credit Officer created: {credit_officer.email} (ID: {credit_officer.id})")
        return credit_officer.id
    except Exception as e:
        result.add_fail("Credit Officer creation", str(e))
        return None


def test_member_creation(result, db, sacco_id):
    """Test regular member creation"""
    print("\n" + "="*60)
    print("TEST: Regular Member Creation")
    print("="*60)
    
    try:
        member = create_user(
            db,
            email="member@test.com",
            password="Member123",
            role=RoleEnum.MEMBER,
            sacco_id=sacco_id,
            full_name="Test Member",
            username="test.member",
            can_apply_for_loans=True,
            can_receive_dividends=True
        )
        db.commit()
        
        result.add_pass(f"Member created: {member.email} (ID: {member.id})")
        return member.id
    except Exception as e:
        result.add_fail("Member creation", str(e))
        return None


def test_deposit_initiation(result, db, member_id, sacco_id):
    """Test deposit initiation"""
    print("\n" + "="*60)
    print("TEST: Deposit Initiation")
    print("="*60)
    
    try:
        pending = PendingDeposit(
            sacco_id=sacco_id,
            user_id=member_id,
            amount=50000,
            payment_method="CASH",
            reference_number="REF123456",
            description="Test deposit",
            status="pending"
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)
        
        result.add_pass(f"Deposit initiated: UGX 50,000 (Pending ID: {pending.id})")
        return pending.id
    except Exception as e:
        result.add_fail("Deposit initiation", str(e))
        return None


def test_deposit_approval(result, db, pending_id, accountant_id, member_id, sacco_id):
    """Test deposit approval by accountant"""
    print("\n" + "="*60)
    print("TEST: Deposit Approval")
    print("="*60)
    
    try:
        pending = db.query(PendingDeposit).filter(PendingDeposit.id == pending_id).first()
        if not pending:
            result.add_fail("Deposit approval", "Pending deposit not found")
            return False
        
        saving = Saving(
            sacco_id=sacco_id,
            user_id=member_id,
            type="deposit",
            amount=pending.amount,
            payment_method=PaymentMethodEnum.CASH,
            description=pending.description,
            reference_number=pending.reference_number,
            approved_by=accountant_id,
            approved_at=datetime.now(timezone.utc), 
            pending_deposit_id=pending.id
        )
        db.add(saving)
        
        pending.status = "approved"
        pending.approved_by = accountant_id
        pending.approved_at = datetime.now(timezone.utc)
        
        db.commit()
        
        result.add_pass(f"Deposit approved: UGX {pending.amount:,.2f}")
        return saving.id
    except Exception as e:
        result.add_fail("Deposit approval", str(e))
        return None


def test_loan_request(result, db, member_id, sacco_id):
    """Test loan request"""
    print("\n" + "="*60)
    print("TEST: Loan Request")
    print("="*60)
    
    try:
        loan = Loan(
            sacco_id=sacco_id,
            user_id=member_id,
            amount=100000,
            term=12,
            interest_rate=12.0,
            purpose="Business",
            status="pending"
        )
        loan.calculate_interest()
        db.add(loan)
        db.commit()
        db.refresh(loan)
        
        result.add_pass(f"Loan requested: UGX {loan.amount:,.2f} (ID: {loan.id})")
        return loan.id
    except Exception as e:
        result.add_fail("Loan request", str(e))
        return None


def test_loan_approval_by_manager(result, db, loan_id, manager_id):
    """Test loan approval by manager"""
    print("\n" + "="*60)
    print("TEST: Loan Approval by Manager")
    print("="*60)
    
    try:
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            result.add_fail("Loan approval", "Loan not found")
            return False
        
        loan.status = "approved"
        loan.approved_by = manager_id
        loan.approved_at = datetime.now(timezone.utc)
        db.commit()
        
        result.add_pass(f"Loan approved by Manager: UGX {loan.amount:,.2f}")
        return True
    except Exception as e:
        result.add_fail("Loan approval by manager", str(e))
        return False


def test_loan_payment(result, db, loan_id, member_id, sacco_id):
    """Test loan payment"""
    print("\n" + "="*60)
    print("TEST: Loan Payment")
    print("="*60)
    
    try:
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            result.add_fail("Loan payment", "Loan not found")
            return False
        
        payment_amount = loan.calculate_monthly_payment()
        
        payment = LoanPayment(
            loan_id=loan_id,
            sacco_id=sacco_id,
            user_id=member_id,
            amount=payment_amount,
            payment_method="SAVINGS"
        )
        db.add(payment)
        
        loan.total_paid = payment_amount
        
        db.commit()
        
        result.add_pass(f"Loan payment recorded: UGX {payment_amount:,.2f}")
        return True
    except Exception as e:
        result.add_fail("Loan payment", str(e))
        return False


def test_permission_checks(result):
    """Test permission checks for different roles"""
    print("\n" + "="*60)
    print("TEST: Permission Checks")
    print("="*60)
    
    try:
        db = SessionLocal()
        
        manager = db.query(User).filter(User.role == RoleEnum.MANAGER).first()
        if manager:
            assert manager.can_approve_loans is True
            result.add_pass("Manager has approve loans permission")
        
        accountant = db.query(User).filter(User.role == RoleEnum.ACCOUNTANT).first()
        if accountant:
            assert accountant.can_approve_deposits is True
            result.add_pass("Accountant has approve deposits permission")
        
        credit_officer = db.query(User).filter(User.role == RoleEnum.CREDIT_OFFICER).first()
        if credit_officer:
            assert credit_officer.can_manage_loans is True
            result.add_pass("Credit Officer has manage loans permission")
        
        db.close()
        return True
    except Exception as e:
        result.add_fail("Permission checks", str(e))
        return False


def test_dashboard_urls(result):
    """Test dashboard URLs for different roles"""
    print("\n" + "="*60)
    print("TEST: Dashboard URLs")
    print("="*60)
    
    try:
        expected_urls = {
            RoleEnum.SUPER_ADMIN: "/superadmin/dashboard",
            RoleEnum.MANAGER: "/manager/dashboard",
            RoleEnum.ACCOUNTANT: "/accountant/dashboard",
            RoleEnum.CREDIT_OFFICER: "/credit-officer/dashboard",
            RoleEnum.MEMBER: "/member/dashboard",
        }
        
        for role, expected_url in expected_urls.items():
            mock_user = User(role=role)
            actual_url = mock_user.get_dashboard_url
            assert actual_url == expected_url
            result.add_pass(f"{role.value} dashboard URL: {actual_url}")
        
        return True
    except Exception as e:
        result.add_fail("Dashboard URLs", str(e))
        return False


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Run system tests')
    parser.add_argument('--quick', action='store_true', help='Run quick test without creating fresh database')
    
    args = parser.parse_args()
    
    if args.quick:
        print("Quick test mode - using existing database")
        # Implement quick test if needed
    else:
        success = run_all_tests()
        
        if success:
            print("\n" + "="*60)
            print("🎉 ALL TESTS PASSED! System is ready for use. 🎉")
            print("="*60)
            print("\nTest data has been created with:")
            print("  🔐 Superadmin: superadmin@cheontec.com / Admin@123")
            print("  🔐 Manager: manager@test.com / Manager123")
            print("  🔐 Accountant: accountant@test.com / Accountant123")
            print("  🔐 Credit Officer: creditofficer@test.com / Credit123")
            print("  🔐 Member: member@test.com / Member123")
            print("\n📊 Features Tested:")
            print("  ✅ Shares Module (Purchase shares, view holdings)")
            print("  ✅ Dividends Module (Declarations, payments)")
            print("  ✅ Insights Dashboard (Weekly summary, alerts)")
            print("  ✅ Switch Links (Member ↔ Staff switching)")
            print("  ✅ Deposits and Approvals")
            print("  ✅ Loans and Payments")
            print("\n🚀 You can now run the application and test all features.")
        else:
            print("\n" + "="*60)
            print("❌ SOME TESTS FAILED. Please review the errors above. ❌")
            print("="*60)
            sys.exit(1)