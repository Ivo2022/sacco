# backend/scripts/init_db.py
"""
Initialize database with superadmin user
Run with: python -m backend.scripts.init_db
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file FIRST
from dotenv import load_dotenv

# Load .env from the project root
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path, override=True)
    print(f"✅ Loaded environment from {env_path}")
else:
    print(f"⚠️  .env file not found at {env_path}")

# Now import modules that depend on settings
from backend.core.database import SessionLocal
from backend.models import User, RoleEnum, SystemSetting
from backend.services.user_service import create_user, get_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength
    Returns (is_valid, error_message)
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    
    if not any(c in "!@#$%^&*()_+-=[]{}|;:,.<>?" for c in password):
        return False, "Password must contain at least one special character (!@#$%^&* etc.)"
    
    return True, ""


def create_superadmin():
    """Create superadmin user if it doesn't exist using .env configuration"""
    db = SessionLocal()
    
    try:
        # Check if superadmin already exists
        superadmin = db.query(User).filter(User.role == RoleEnum.SUPER_ADMIN).first()
        
        if superadmin:
            logger.info(f"Superadmin already exists: {superadmin.username} ({superadmin.email})")
            return
        
        logger.info("No superadmin found. Creating new superadmin from .env configuration...")
        
        # Get superadmin details from environment variables
        username = os.environ.get("SUPERADMIN_USERNAME")
        email = os.environ.get("SUPERADMIN_EMAIL")
        password = os.environ.get("SUPERADMIN_PASSWORD")
        full_name = os.environ.get("SUPERADMIN_FULL_NAME", "System Super Administrator")
        
        # Debug: Print loaded environment variables (without passwords)
        logger.info(f"SUPERADMIN_USERNAME from env: {username}")
        logger.info(f"SUPERADMIN_EMAIL from env: {email}")
        logger.info(f"SUPERADMIN_PASSWORD set: {'Yes' if password else 'No'}")
        
        # Validate all required environment variables are present
        missing_vars = []
        if not username:
            missing_vars.append("SUPERADMIN_USERNAME")
        if not email:
            missing_vars.append("SUPERADMIN_EMAIL")
        if not password:
            missing_vars.append("SUPERADMIN_PASSWORD")
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            logger.info("Please add them to your .env file:")
            logger.info("  SUPERADMIN_USERNAME=superadmin")
            logger.info("  SUPERADMIN_EMAIL=superadmin@cheontec.com")
            logger.info("  SUPERADMIN_PASSWORD=Admin123!")
            logger.info("  SUPERADMIN_FULL_NAME=System Super Administrator (optional)")
            logger.info("\nOr run with --test to create a test superadmin")
            return
        
        # Validate username
        if len(username) < 3:
            logger.error("Username must be at least 3 characters long")
            return
        
        # Validate email format
        if "@" not in email or "." not in email:
            logger.error(f"Invalid email format: {email}")
            return
        
        # Validate password strength
        is_valid, error_msg = validate_password_strength(password)
        if not is_valid:
            logger.error(f"Password validation failed: {error_msg}")
            return
        
        # Create superadmin user using user_service
        try:
            superadmin_user = create_user(
                db=db,
                email=email,
                password=password,
                role=RoleEnum.SUPER_ADMIN,
                sacco_id=None,
                full_name=full_name,
                username=username,
                is_staff=True,
                can_apply_for_loans=False,
                can_receive_dividends=False,
                requires_approval_for_loans=False,
                is_active=True,
                is_verified=True
            )
            
            logger.info("=" * 50)
            logger.info("✅ Superadmin created successfully!")
            logger.info(f"   Username: {username}")
            logger.info(f"   Email: {email}")
            logger.info(f"   Full Name: {full_name}")
            logger.info(f"   Role: SUPER_ADMIN")
            logger.info("=" * 50)
            
            # Create default system settings
            create_default_settings(db)
            
        except ValueError as e:
            logger.error(f"Failed to create superadmin: {e}")
            return
        
    except Exception as e:
        logger.error(f"Error creating superadmin: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def create_default_settings(db):
    """Create default system settings"""
    try:
        default_settings = [
            {"key": "site_name", "value": "SACCO Management System", "description": "Site name"},
            {"key": "site_description", "value": "Comprehensive SACCO Management Platform", "description": "Site description"},
            {"key": "default_interest_rate", "value": "12.0", "description": "Default loan interest rate (%)"},
            {"key": "max_loan_term_months", "value": "36", "description": "Maximum loan term in months"},
            {"key": "min_savings_for_loan", "value": "10000", "description": "Minimum savings required for loan"},
            {"key": "max_loan_amount", "value": "500000", "description": "Maximum loan amount"},
            {"key": "savings_interest_rate", "value": "5.0", "description": "Savings interest rate (%)"},
            {"key": "membership_fee", "value": "5000", "description": "Membership fee amount"},
            {"key": "enable_notifications", "value": "true", "description": "Enable email notifications"},
            {"key": "backup_enabled", "value": "true", "description": "Enable automatic backups"},
            {"key": "loan_approval_threshold", "value": "100000", "description": "Amount requiring manager approval"},
            {"key": "max_loan_to_savings_ratio", "value": "3.0", "description": "Maximum loan amount as multiple of savings"},
        ]
        
        created_count = 0
        for setting in default_settings:
            existing = db.query(SystemSetting).filter(SystemSetting.key == setting["key"]).first()
            if not existing:
                new_setting = SystemSetting(**setting)
                db.add(new_setting)
                created_count += 1
        
        db.commit()
        
        if created_count > 0:
            logger.info(f"✅ Created {created_count} default system settings")
        else:
            logger.info("Default system settings already exist")
            
    except Exception as e:
        logger.warning(f"Could not create default settings: {e}")


def create_test_superadmin():
    """Create a test superadmin for development (bypasses .env)"""
    db = SessionLocal()
    
    try:
        # Check if superadmin exists
        superadmin = db.query(User).filter(User.role == RoleEnum.SUPER_ADMIN).first()
        
        if superadmin:
            logger.info(f"Superadmin already exists: {superadmin.username}")
            return
        
        logger.info("Creating test superadmin for development...")
        
        # Test credentials
        test_username = "admin"
        test_email = "admin@cheontec.com"
        test_password = "Admin123!"
        test_full_name = "System Administrator"
        
        # Validate test password (should pass)
        is_valid, error_msg = validate_password_strength(test_password)
        if not is_valid:
            logger.error(f"Test password validation failed: {error_msg}")
            return
        
        # Create test superadmin using user_service
        try:
            test_user = create_user(
                db=db,
                email=test_email,
                password=test_password,
                role=RoleEnum.SUPER_ADMIN,
                sacco_id=None,
                full_name=test_full_name,
                username=test_username,
                is_staff=True,
                can_apply_for_loans=False,
                can_receive_dividends=False,
                requires_approval_for_loans=False,
                is_active=True,
                is_verified=True
            )
            
            logger.info("=" * 50)
            logger.info("✅ Test superadmin created!")
            logger.info(f"   Username: admin")
            logger.info(f"   Password: Admin123!")
            logger.info(f"   Email: admin@cheontec.com")
            logger.info(f"   Full Name: System Administrator")
            logger.info("=" * 50)
            logger.warning("⚠️  Remember to change these credentials in production!")
            
            # Create default system settings
            create_default_settings(db)
            
        except ValueError as e:
            logger.error(f"Failed to create test superadmin: {e}")
            return
        
    except Exception as e:
        logger.error(f"Error creating test superadmin: {e}")
        db.rollback()
    finally:
        db.close()


def update_superadmin_password():
    """Update existing superadmin password from .env"""
    db = SessionLocal()
    
    try:
        superadmin = db.query(User).filter(User.role == RoleEnum.SUPER_ADMIN).first()
        
        if not superadmin:
            logger.error("No superadmin found to update")
            return
        
        new_password = os.environ.get("SUPERADMIN_PASSWORD")
        
        if not new_password:
            logger.error("SUPERADMIN_PASSWORD not set in environment")
            return
        
        # Validate password strength
        is_valid, error_msg = validate_password_strength(new_password)
        if not is_valid:
            logger.error(f"Password validation failed: {error_msg}")
            return
        
        # Update password using the same hashing function
        superadmin.password_hash = get_password_hash(new_password)
        db.commit()
        
        logger.info("✅ Superadmin password updated successfully!")
        
    except Exception as e:
        logger.error(f"Error updating password: {e}")
        db.rollback()
    finally:
        db.close()


def show_superadmin_info():
    """Display superadmin information (without password)"""
    db = SessionLocal()
    
    try:
        superadmin = db.query(User).filter(User.role == RoleEnum.SUPER_ADMIN).first()
        
        if superadmin:
            logger.info("=" * 50)
            logger.info("Superadmin Information:")
            logger.info(f"  ID: {superadmin.id}")
            logger.info(f"  Username: {superadmin.username}")
            logger.info(f"  Email: {superadmin.email}")
            logger.info(f"  Full Name: {superadmin.full_name}")
            logger.info(f"  Role: {superadmin.role}")
            logger.info(f"  Active: {superadmin.is_active}")
            logger.info(f"  Verified: {superadmin.is_verified}")
            logger.info(f"  Staff: {superadmin.is_staff}")
            logger.info(f"  Created: {superadmin.created_at}")
            logger.info(f"  Last Login: {superadmin.last_login}")
            logger.info("=" * 50)
        else:
            logger.info("No superadmin found in database")
            
    except Exception as e:
        logger.error(f"Error fetching superadmin info: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Initialize database with superadmin")
    parser.add_argument("--test", action="store_true", help="Create test superadmin with default credentials")
    parser.add_argument("--force", action="store_true", help="Force creation even if superadmin exists")
    parser.add_argument("--update-password", action="store_true", help="Update superadmin password from .env")
    parser.add_argument("--show", action="store_true", help="Show superadmin information")
    
    args = parser.parse_args()
    
    logger.info("=" * 50)
    logger.info("Database Initialization Script")
    logger.info("=" * 50)
    
    if args.show:
        show_superadmin_info()
    elif args.update_password:
        update_superadmin_password()
    elif args.test:
        logger.info("Creating test superadmin...")
        create_test_superadmin()
    else:
        logger.info("Creating superadmin from .env...")
        create_superadmin()
    
    logger.info("=" * 50)
    logger.info("Initialization complete!")