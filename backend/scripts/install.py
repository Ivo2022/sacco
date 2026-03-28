# scripts/test_system.py
import os
import sys
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import importlib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from backend.core.database import Base, SessionLocal, engine, get_db, init_db
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
from backend.core.middleware import SACCOStatusMiddleware, TemplateHelpersMiddleware
from backend.models import (
    User, RoleEnum, Sacco, Saving, Loan, LoanPayment, 
    PendingDeposit, ExternalLoan, ExternalLoanPayment, Log,
    PaymentMethodEnum
)
from backend.services.user_service import create_user, get_password_hash, verify_password
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


# ============ NEW TESTS FOR REFACTORED STRUCTURE ============

def test_configuration_loading(result):
    """Test 1: Configuration loading"""
    print("\n" + "="*60)
    print("TEST 1: Configuration Loading")
    print("="*60)
    
    try:
        # Test settings are loaded
        assert settings.PROJECT_NAME == "SACCO Management System"
        assert settings.VERSION == "1.0.0"
        assert settings.SECRET_KEY is not None
        assert settings.LOCAL_OFFSET_HOURS == 3
        assert settings.TIMEZONE_NAME == "East Africa Time"
        
        result.add_pass("Configuration loaded successfully")
        return True
    except Exception as e:
        result.add_fail("Configuration loading", str(e))
        return False


def test_database_session_dependency(result):
    """Test 2: Database session dependency"""
    print("\n" + "="*60)
    print("TEST 2: Database Session Dependency")
    print("="*60)
    
    try:
        # Test get_db generator
        db_gen = get_db()
        db = next(db_gen)
        
        assert db is not None
        assert isinstance(db, Session)
        
        # Test that session works
        sql_result = db.execute(text("SELECT 1")).scalar()
        assert sql_result == 1
        
        db.close()
        
        result.add_pass("Database session dependency works")
        return True
    except Exception as e:
        result.add_fail("Database session dependency", str(e))
        return False


def test_template_helpers(result):
    """Test 3: Template helper functions"""
    print("\n" + "="*60)
    print("TEST 3: Template Helpers")
    print("="*60)
    
    try:
        # Test format_money
        assert format_money(1000) == "UGX 1,000.00"
        assert format_money(1234567.89) == "UGX 1,234,567.89"
        assert format_money(None) == "UGX 0.00"
        
        # Test format_date
        test_date = datetime(2024, 1, 15, 10, 30, 0)
        assert format_date(test_date) == "2024-01-15"
        assert format_date(test_date, '%Y/%m/%d') == "2024/01/15"
        
        # Test format_datetime
        assert format_datetime(test_date) == "2024-01-15 10:30:00"
        
        # Test format_percentage
        assert format_percentage(12.5) == "12.50%"
        assert format_percentage(7) == "7.00%"
        
        # Test format_local_time (basic)
        local_time = format_local_time(test_date)
        assert local_time is not None
        
        result.add_pass("All template helpers working correctly")
        return True
    except Exception as e:
        result.add_fail("Template helpers", str(e))
        return False


def test_jinja2_template_registration(result):
    """Test 4: Jinja2 template registration"""
    print("\n" + "="*60)
    print("TEST 4: Jinja2 Template Registration")
    print("="*60)
    
    try:
        # Create test templates
        templates = Jinja2Templates(directory="backend/templates")
        
        # Register helpers
        register_template_helpers(templates)
        
        # Check if globals were added
        assert 'money' in templates.env.globals
        assert 'local_time' in templates.env.globals
        assert 'date' in templates.env.globals
        assert 'datetime' in templates.env.globals
        assert 'percentage' in templates.env.globals
        assert 'now' in templates.env.globals
        
        # Check if filters were added
        assert 'money' in templates.env.filters
        assert 'local_time' in templates.env.filters
        assert 'date' in templates.env.filters
        
        result.add_pass("Jinja2 templates registered successfully")
        return True
    except Exception as e:
        result.add_fail("Jinja2 template registration", str(e))
        return False


def test_middleware_existence(result):
    """Test 5: Middleware existence and structure"""
    print("\n" + "="*60)
    print("TEST 5: Middleware")
    print("="*60)
    
    try:
        # Test SACCOStatusMiddleware
        sacco_middleware = SACCOStatusMiddleware
        assert hasattr(sacco_middleware, 'dispatch')
        assert hasattr(sacco_middleware, 'PUBLIC_PATHS')
        assert isinstance(sacco_middleware.PUBLIC_PATHS, list)
        
        # Test TemplateHelpersMiddleware
        template_middleware = TemplateHelpersMiddleware
        assert hasattr(template_middleware, 'dispatch')
        
        result.add_pass("Middleware classes properly defined")
        return True
    except Exception as e:
        result.add_fail("Middleware", str(e))
        return False


def test_dependencies(result):
    """Test 6: Dependency functions - Updated for new roles"""
    print("\n" + "="*60)
    print("TEST 6: Dependencies")
    print("="*60)
    
    try:
        # Check that all dependency functions exist
        assert callable(get_current_user)
        assert callable(require_auth)
        assert callable(require_manager)
        assert callable(require_accountant)
        assert callable(require_credit_officer)
        assert callable(require_any_role)
        
        result.add_pass("All dependency functions defined")
        return True
    except Exception as e:
        result.add_fail("Dependencies", str(e))
        return False


def test_router_imports(result):
    """Test 7: Router imports - Updated for new structure"""
    print("\n" + "="*60)
    print("TEST 7: Router Imports")
    print("="*60)
    
    try:
        # Try importing all routers - Updated to reflect new role-based routers
        from backend.routers import auth, superadmin, manager, accountant, credit_officer, member, admin, home
        
        assert auth is not None
        assert superadmin is not None
        assert manager is not None
        assert accountant is not None
        assert credit_officer is not None
        assert member is not None
        assert admin is not None
        assert home is not None
        
        result.add_pass("All routers imported successfully")
        return True
    except Exception as e:
        result.add_fail("Router imports", str(e))
        return False


def test_app_creation(result):
    """Test 8: FastAPI app creation"""
    print("\n" + "="*60)
    print("TEST 8: FastAPI App Creation")
    print("="*60)
    
    try:
        # Import the app
        from backend.main import app
        
        assert app is not None
        assert app.title == "SACCO Management System"
        assert app.version == "1.0.0"
        
        # Check that routes are registered
        routes = [route.path for route in app.routes]
        assert "/health" in routes
        assert "/" in routes
        assert "/auth" in str(routes)
        
        result.add_pass("FastAPI app created with all routes")
        return True
    except Exception as e:
        result.add_fail("FastAPI app creation", str(e))
        return False


def test_startup_event(result, db):
    """Test 9: Startup event functionality"""
    print("\n" + "="*60)
    print("TEST 9: Startup Event")
    print("="*60)
    
    try:
        # Test that database is initialized
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        assert len(tables) > 0
        
        result.add_pass("Startup event initialized database")
        return True
    except Exception as e:
        result.add_fail("Startup event", str(e))
        return False


# ============ UPDATED TESTS WITH NEW ROLE STRUCTURE ============

def test_database_creation(result):
    """Test 10: Database and tables creation"""
    print("\n" + "="*60)
    print("TEST 10: Database and Table Creation")
    print("="*60)
    
    try:
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        expected_tables = ['users', 'saccos', 'savings', 'loans', 'loan_payments', 
                          'pending_deposits', 'external_loans', 'external_loan_payments', 'logs']
        
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
    """Test 11: Superadmin creation"""
    print("\n" + "="*60)
    print("TEST 11: Superadmin Creation")
    print("="*60)
    
    try:
        # Create superadmin
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
        
        # Verify superadmin exists
        admin = db.query(User).filter(User.email == "superadmin@cheontec.com").first()
        if not admin:
            result.add_fail("Superadmin creation", "User not found in database")
            return False
        
        if admin.role != RoleEnum.SUPER_ADMIN:
            result.add_fail("Superadmin role", f"Expected SUPER_ADMIN, got {admin.role}")
            return False
        
        result.add_pass("Superadmin created successfully")
        return True
    except Exception as e:
        result.add_fail("Superadmin creation", str(e))
        return False


def test_sacco_creation(result, db):
    """Test 12: SACCO creation"""
    print("\n" + "="*60)
    print("TEST 12: SACCO Creation")
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
    """Test 13: Manager creation with linked member account"""
    print("\n" + "="*60)
    print("TEST 13: Manager Creation")
    print("="*60)
    
    try:
        # Create manager
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
        
        # Create linked member account
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
        
        # Link accounts
        manager.linked_member_account_id = member.id
        member.linked_admin_id = manager.id
        db.commit()
        
        # Verify manager permissions
        assert manager.can_approve_loans is True
        assert manager.can_manage_loans is True
        
        result.add_pass(f"Manager created: {manager.email} (ID: {manager.id})")
        result.add_pass(f"Linked member created: {member.email} (ID: {member.id})")
        result.add_pass(f"Manager permissions: can_approve_loans={manager.can_approve_loans}")
        return manager.id, member.id
    except Exception as e:
        result.add_fail("Manager creation", str(e))
        return None, None


def test_accountant_creation(result, db, sacco_id, manager_id):
    """Test 14: Accountant creation"""
    print("\n" + "="*60)
    print("TEST 14: Accountant Creation")
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
        
        # Create linked member for accountant
        member = create_user(
            db,
            email="accountant_member@test.com",
            password="Accountant123",
            role=RoleEnum.MEMBER,
            sacco_id=sacco_id,
            full_name="Test Accountant (Member)",
            username="test.accountant.member",
            is_staff=True,
            can_apply_for_loans=True
        )
        
        accountant.linked_member_account_id = member.id
        member.linked_admin_id = accountant.id
        db.commit()
        
        # Verify accountant permissions
        assert accountant.can_approve_deposits is True
        assert accountant.can_view_all_transactions is True
        
        result.add_pass(f"Accountant created: {accountant.email} (ID: {accountant.id})")
        result.add_pass(f"Accountant permissions: can_approve_deposits={accountant.can_approve_deposits}")
        return accountant.id
    except Exception as e:
        result.add_fail("Accountant creation", str(e))
        return None


def test_credit_officer_creation(result, db, sacco_id):
    """Test 15: Credit Officer creation"""
    print("\n" + "="*60)
    print("TEST 15: Credit Officer Creation")
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
        
        # Verify credit officer permissions
        assert credit_officer.can_manage_loans is True
        assert credit_officer.can_send_loan_reminders is True
        
        result.add_pass(f"Credit Officer created: {credit_officer.email} (ID: {credit_officer.id})")
        result.add_pass(f"Credit Officer permissions: can_manage_loans={credit_officer.can_manage_loans}")
        return credit_officer.id
    except Exception as e:
        result.add_fail("Credit Officer creation", str(e))
        return None


def test_member_creation(result, db, sacco_id):
    """Test 16: Regular member creation"""
    print("\n" + "="*60)
    print("TEST 16: Regular Member Creation")
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
        
        # Verify member permissions
        if member.can_apply_for_loans:
            result.add_pass("Member created with loan application permission")
        else:
            result.add_fail("Member creation", "Member does not have loan application permission")
        
        # Verify member cannot perform admin actions
        assert member.can_approve_loans is False
        assert member.can_approve_deposits is False
        assert member.can_manage_loans is False
        
        result.add_pass(f"Member created: {member.email} (ID: {member.id})")
        result.add_pass(f"Member admin permissions: can_approve_loans={member.can_approve_loans}")
        return member.id
    except Exception as e:
        result.add_fail("Member creation", str(e))
        return None


def test_deposit_initiation(result, db, member_id, sacco_id):
    """Test 17: Deposit initiation"""
    print("\n" + "="*60)
    print("TEST 17: Deposit Initiation")
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
    """Test 18: Deposit approval by accountant"""
    print("\n" + "="*60)
    print("TEST 18: Deposit Approval")
    print("="*60)
    
    try:
        pending = db.query(PendingDeposit).filter(PendingDeposit.id == pending_id).first()
        if not pending:
            result.add_fail("Deposit approval", "Pending deposit not found")
            return False
        
        # Create savings record
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
        
        # Update pending deposit
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
    """Test 19: Loan request"""
    print("\n" + "="*60)
    print("TEST 19: Loan Request")
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
        result.add_pass(f"  Interest: UGX {loan.total_interest:,.2f}")
        result.add_pass(f"  Total Payable: UGX {loan.total_payable:,.2f}")
        return loan.id
    except Exception as e:
        result.add_fail("Loan request", str(e))
        return None


def test_loan_approval_by_manager(result, db, loan_id, manager_id):
    """Test 20: Loan approval by manager"""
    print("\n" + "="*60)
    print("TEST 20: Loan Approval by Manager")
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


def test_loan_approval_by_credit_officer(result, db, manager_id, credit_officer_id, sacco_id):
    """Test 20b: Loan approval by credit officer (alternative)"""
    print("\n" + "="*60)
    print("TEST 20b: Loan Approval by Credit Officer")
    print("="*60)
    
    try:
        # Create a new loan for credit officer to approve
        loan = Loan(
            sacco_id=sacco_id,
            user_id=manager_id,  # Using manager's linked member account
            amount=50000,
            term=6,
            interest_rate=12.0,
            purpose="Credit officer test",
            status="pending"
        )
        loan.calculate_interest()
        db.add(loan)
        db.commit()
        
        # Credit officer approves
        loan.status = "approved"
        loan.approved_by = credit_officer_id
        loan.approved_at = datetime.now(timezone.utc)
        db.commit()
        
        result.add_pass(f"Loan approved by Credit Officer: UGX {loan.amount:,.2f}")
        return True
    except Exception as e:
        result.add_fail("Loan approval by credit officer", str(e))
        return False


def test_loan_payment(result, db, loan_id, member_id, sacco_id):
    """Test 21: Loan payment"""
    print("\n" + "="*60)
    print("TEST 21: Loan Payment")
    print("="*60)
    
    try:
        loan = db.query(Loan).filter(Loan.id == loan_id).first()
        if not loan:
            result.add_fail("Loan payment", "Loan not found")
            return False
        
        payment_amount = loan.calculate_monthly_payment()
        
        # Create loan payment
        payment = LoanPayment(
            loan_id=loan_id,
            sacco_id=sacco_id,
            user_id=member_id,
            amount=payment_amount,
            payment_method="SAVINGS"
        )
        db.add(payment)
        
        # Update loan total paid
        loan.total_paid = payment_amount
        
        db.commit()
        
        result.add_pass(f"Loan payment recorded: UGX {payment_amount:,.2f}")
        return True
    except Exception as e:
        result.add_fail("Loan payment", str(e))
        return False


def test_external_loan_creation(result, db, sacco_id, member_id):
    """Test 22: External loan creation"""
    print("\n" + "="*60)
    print("TEST 22: External Loan Creation")
    print("="*60)
    
    try:
        external_loan = ExternalLoan(
            sacco_id=sacco_id,
            borrower_name="External Borrower",
            borrower_contact="+256712345678",
            borrower_national_id="EXT123456",
            amount=200000,
            term=6,
            interest_rate=15.0,
            purpose="Personal",
            collateral_description="Land title",
            collateral_value=500000,
            guarantor_id=member_id,
            status="pending"
        )
        external_loan.calculate_interest()
        db.add(external_loan)
        db.commit()
        db.refresh(external_loan)
        
        result.add_pass(f"External loan created: UGX {external_loan.amount:,.2f} (ID: {external_loan.id})")
        result.add_pass(f"  Interest: UGX {external_loan.total_interest:,.2f}")
        result.add_pass(f"  Total Payable: UGX {external_loan.total_payable:,.2f}")
        return external_loan.id
    except Exception as e:
        result.add_fail("External loan creation", str(e))
        return None


def test_external_loan_approval(result, db, external_loan_id, manager_id):
    """Test 23: External loan approval"""
    print("\n" + "="*60)
    print("TEST 23: External Loan Approval")
    print("="*60)
    
    try:
        external_loan = db.query(ExternalLoan).filter(ExternalLoan.id == external_loan_id).first()
        if not external_loan:
            result.add_fail("External loan approval", "Loan not found")
            return False
        
        external_loan.status = "approved"
        external_loan.approved_by = manager_id
        external_loan.approved_at = datetime.now(timezone.utc)
        db.commit()
        
        result.add_pass(f"External loan approved: UGX {external_loan.amount:,.2f}")
        return True
    except Exception as e:
        result.add_fail("External loan approval", str(e))
        return False


def test_external_loan_payment(result, db, external_loan_id):
    """Test 24: External loan payment"""
    print("\n" + "="*60)
    print("TEST 24: External Loan Payment")
    print("="*60)
    
    try:
        external_loan = db.query(ExternalLoan).filter(ExternalLoan.id == external_loan_id).first()
        if not external_loan:
            result.add_fail("External loan payment", "Loan not found")
            return False
        
        payment_amount = external_loan.calculate_monthly_payment()
        
        payment = ExternalLoanPayment(
            external_loan_id=external_loan_id,
            amount=payment_amount,
            payment_method="CASH",
            reference_number="EXT-PAY-001",
            notes="First payment"
        )
        db.add(payment)
        
        external_loan.total_paid = payment_amount
        db.commit()
        
        result.add_pass(f"External loan payment recorded: UGX {payment_amount:,.2f}")
        return True
    except Exception as e:
        result.add_fail("External loan payment", str(e))
        return False


def test_audit_log(result, db, user_id, sacco_id):
    """Test 25: Audit log creation"""
    print("\n" + "="*60)
    print("TEST 25: Audit Log Creation")
    print("="*60)
    
    try:
        log = Log(
            user_id=user_id,
            sacco_id=sacco_id,
            action="TEST_ACTION",
            details="Test audit log entry",
            ip_address="127.0.0.1"
        )
        db.add(log)
        db.commit()
        
        result.add_pass("Audit log created")
        return True
    except Exception as e:
        result.add_fail("Audit log creation", str(e))
        return False


def test_permission_checks(result):
    """Test 26: Permission checks for new roles"""
    print("\n" + "="*60)
    print("TEST 26: Permission Checks")
    print("="*60)
    
    try:
        from backend.models import User, RoleEnum
        from backend.core.database import SessionLocal
        
        db = SessionLocal()
        
        try:
            # Test Manager permissions
            manager = db.query(User).filter(User.role == RoleEnum.MANAGER).first()
            if manager:
                assert manager.can_approve_loans is True
                assert manager.can_manage_loans is True
                result.add_pass("Manager has correct permissions")
            else:
                result.add_fail("Manager permissions", "No manager found")
            
            # Test Accountant permissions
            accountant = db.query(User).filter(User.role == RoleEnum.ACCOUNTANT).first()
            if accountant:
                assert accountant.can_approve_deposits is True
                assert accountant.can_view_all_transactions is True
                result.add_pass("Accountant has correct permissions")
            else:
                result.add_fail("Accountant permissions", "No accountant found")
            
            # Test Credit Officer permissions
            credit_officer = db.query(User).filter(User.role == RoleEnum.CREDIT_OFFICER).first()
            if credit_officer:
                assert credit_officer.can_manage_loans is True
                assert credit_officer.can_send_loan_reminders is True
                result.add_pass("Credit Officer has correct permissions")
            else:
                result.add_fail("Credit Officer permissions", "No credit officer found")
            
            # Test Member permissions
            member = db.query(User).filter(User.role == RoleEnum.MEMBER).first()
            if member:
                assert member.can_apply_for_loans is True
                assert member.can_approve_loans is False
                result.add_pass("Member has correct permissions")
            else:
                result.add_fail("Member permissions", "No member found")
            
            result.add_pass("All permission checks completed")
            return True
        finally:
            db.close()
            
    except Exception as e:
        result.add_fail("Permission checks", str(e))
        import traceback
        traceback.print_exc()
        return False


def test_account_switching(result, db, manager_id, member_id):
    """Test 27: Account switching between admin and member"""
    print("\n" + "="*60)
    print("TEST 27: Account Switching")
    print("="*60)
    
    try:
        manager = db.query(User).filter(User.id == manager_id).first()
        member = db.query(User).filter(User.id == member_id).first()
        
        if manager.linked_member_account_id != member.id:
            result.add_fail("Account linking", "Manager not linked to member")
            return False
        
        if member.linked_admin_id != manager.id:
            result.add_fail("Account linking", "Member not linked to manager")
            return False
        
        # Test dashboard URLs for different roles
        assert manager.get_dashboard_url == "/manager/dashboard"
        assert member.get_dashboard_url == "/member/dashboard"
        
        result.add_pass("Accounts properly linked")
        result.add_pass("Switching would work via /switch-to-member and /switch-to-admin")
        return True
    except Exception as e:
        result.add_fail("Account switching", str(e))
        return False


def test_dashboard_urls(result):
    """Test 28: Dashboard URLs for different roles"""
    print("\n" + "="*60)
    print("TEST 28: Dashboard URLs")
    print("="*60)
    
    try:
        from backend.models import User, RoleEnum
        
        # Test each role's dashboard URL
        expected_urls = {
            RoleEnum.SUPER_ADMIN: "/superadmin/dashboard",
            RoleEnum.MANAGER: "/manager/dashboard",
            RoleEnum.ACCOUNTANT: "/accountant/dashboard",
            RoleEnum.CREDIT_OFFICER: "/credit-officer/dashboard",
            RoleEnum.MEMBER: "/member/dashboard",
        }
        
        for role, expected_url in expected_urls.items():
            # Create a mock user with this role
            mock_user = User(role=role)
            actual_url = mock_user.get_dashboard_url
            assert actual_url == expected_url, f"Expected {expected_url}, got {actual_url}"
            result.add_pass(f"{role.value} dashboard URL: {actual_url}")
        
        result.add_pass("All dashboard URLs are correct")
        return True
    except Exception as e:
        result.add_fail("Dashboard URLs", str(e))
        return False


def test_error_handling(result):
    """Test 29: Error handling and exceptions"""
    print("\n" + "="*60)
    print("TEST 29: Error Handling")
    print("="*60)
    
    try:
        from backend.core.exceptions import (
            SACCOException, AuthenticationError, 
            AuthorizationError, DatabaseError, ValidationError
        )
        
        # Test exception inheritance
        assert issubclass(AuthenticationError, SACCOException)
        assert issubclass(AuthorizationError, SACCOException)
        assert issubclass(DatabaseError, SACCOException)
        assert issubclass(ValidationError, SACCOException)
        
        result.add_pass("Exception hierarchy properly defined")
        return True
    except Exception as e:
        result.add_fail("Error handling", str(e))
        return False


def run_all_tests():
    """Run all system tests"""
    result = TestResult()
    
    print("\n" + "="*60)
    print("SACCO MANAGEMENT SYSTEM - COMPREHENSIVE TEST (REFACTORED VERSION)")
    print("WITH MANAGER, ACCOUNTANT, CREDIT_OFFICER ROLES")
    print("="*60)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Backup existing database
    backup_existing_database()
    
    # Create fresh database
    if not create_fresh_database():
        result.add_fail("Database creation", "Failed to create database")
        return result.summary()
    
    # Test new core modules first
    test_configuration_loading(result)
    test_database_session_dependency(result)
    test_template_helpers(result)
    test_jinja2_template_registration(result)
    test_middleware_existence(result)
    test_dependencies(result)
    test_router_imports(result)
    test_app_creation(result)
    test_error_handling(result)
    
    db = SessionLocal()
    
    try:
        # Test startup event
        test_startup_event(result, db)
        
        # Run original tests
        test_database_creation(result)
        test_superadmin_creation(result, db)
        sacco_id = test_sacco_creation(result, db)
        
        if sacco_id:
            manager_id, linked_member_id = test_manager_creation(result, db, sacco_id)
            accountant_id = test_accountant_creation(result, db, sacco_id, manager_id)
            credit_officer_id = test_credit_officer_creation(result, db, sacco_id)
            member_id = test_member_creation(result, db, sacco_id)
            
            if member_id:
                pending_id = test_deposit_initiation(result, db, member_id, sacco_id)
                if pending_id and accountant_id:
                    test_deposit_approval(result, db, pending_id, accountant_id, member_id, sacco_id)
                
                loan_id = test_loan_request(result, db, member_id, sacco_id)
                if loan_id and manager_id:
                    test_loan_approval_by_manager(result, db, loan_id, manager_id)
                    test_loan_payment(result, db, loan_id, member_id, sacco_id)
                
                # Test credit officer loan approval
                if credit_officer_id:
                    test_loan_approval_by_credit_officer(result, db, manager_id, credit_officer_id, sacco_id)
                
                external_loan_id = test_external_loan_creation(result, db, sacco_id, member_id)
                if external_loan_id and manager_id:
                    test_external_loan_approval(result, db, external_loan_id, manager_id)
                    test_external_loan_payment(result, db, external_loan_id)
            
            if manager_id and linked_member_id:
                test_account_switching(result, db, manager_id, linked_member_id)
            
            test_audit_log(result, db, manager_id or 1, sacco_id)
        
        test_permission_checks(result)
        test_dashboard_urls(result)  # Remove the db argument here
        
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        result.add_fail("Test execution", str(e))
    finally:
        db.close()
    
    return result.summary()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Run system tests')
    parser.add_argument('--quick', action='store_true', help='Run quick test without creating fresh database')
    
    args = parser.parse_args()
    
    if args.quick:
        print("Quick test mode - using existing database")
        # You can implement quick test here
    else:
        success = run_all_tests()
        
        if success:
            print("\n" + "="*60)
            print("🎉 ALL TESTS PASSED! System is ready for use. 🎉")
            print("="*60)
            print("\nTest data has been created with:")
            print("  Superadmin: superadmin@cheontec.com / Admin@123")
            print("  Manager: manager@test.com / Manager123")
            print("  Accountant: accountant@test.com / Accountant123")
            print("  Credit Officer: creditofficer@test.com / Credit123")
            print("  Member: member@test.com / Member123")
            print("\nRole Permissions:")
            print("  Manager: Can Manage all sacco operations and approve loans")
            print("  Accountant: Can approve deposits, view all transactions")
            print("  Credit Officer: Can manage loans, send loan reminders")
            print("  Member: Can apply for loans, make deposits, view own account")
            print("\nYou can now run the application and log in with these credentials.")
        else:
            print("\n" + "="*60)
            print("❌ SOME TESTS FAILED. Please review the errors above. ❌")
            print("="*60)
            sys.exit(1)