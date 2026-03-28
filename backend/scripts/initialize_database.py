#!/usr/bin/env python
"""
Simple database initialization script
Creates database tables and superadmin account only
Run this to set up a fresh installation
"""

import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect
from backend.core.database import Base, engine, init_db
from backend.core.config import settings
from backend.models import User, RoleEnum
from backend.services.user_service import create_user
from backend.core.database import SessionLocal
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_database_path():
    """Get the database file path from settings"""
    db_url = settings.DATABASE_URL
    if db_url.startswith("sqlite:///"):
        return db_url.replace("sqlite:///", "")
    return "backend/database/cheontec.db"


def create_superadmin(db):
    """Create superadmin account if it doesn't exist"""
    superadmin_email = "superadmin@cheontec.com"
    superadmin_password = "Admin@123"
    
    # Check if superadmin already exists
    existing = db.query(User).filter(
        User.email == superadmin_email,
        User.role == RoleEnum.SUPER_ADMIN
    ).first()
    
    if existing:
        logger.info(f"Superadmin already exists: {existing.email}")
        return existing
    
    # Check if user exists with this email but different role
    user = db.query(User).filter(User.email == superadmin_email).first()
    if user:
        # Update to superadmin
        user.role = RoleEnum.SUPER_ADMIN
        user.is_staff = True
        db.commit()
        logger.info(f"Updated existing user {superadmin_email} to superadmin role")
        return user
    
    # Create new superadmin
    try:
        superadmin = create_user(
            db,
            email=superadmin_email,
            password=superadmin_password,
            role=RoleEnum.SUPER_ADMIN,
            full_name="Super Administrator",
            username="superadmin",
            is_staff=True,
            can_apply_for_loans=False
        )
        db.commit()
        logger.info(f"✓ Superadmin created successfully: {superadmin_email}")
        return superadmin
    except Exception as e:
        logger.error(f"Failed to create superadmin: {e}")
        db.rollback()
        raise


def main():
    """Main initialization function"""
    print("\n" + "="*60)
    print("SACCO MANAGEMENT SYSTEM - DATABASE INITIALIZATION")
    print("="*60)
    
    db_path = get_database_path()
    print(f"\nDatabase path: {db_path}")
    
    # Check if database already exists
    db_exists = os.path.exists(db_path)
    if db_exists:
        print(f"⚠ Database already exists at: {db_path}")
        response = input("Do you want to backup and recreate? (y/N): ").strip().lower()
        
        if response == 'y':
            # Backup existing database
            from datetime import datetime
            backup_dir = "backups"
            os.makedirs(backup_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"cheontec_{timestamp}.db")
            
            import shutil
            shutil.copy2(db_path, backup_path)
            print(f"✓ Database backed up to: {backup_path}")
            
            # Remove old database
            os.remove(db_path)
            print("✓ Removed existing database")
            db_exists = False
        else:
            print("Keeping existing database...")
    
    # Create fresh database if it doesn't exist
    if not db_exists:
        print("\nCreating database tables...")
        init_db()
        
        # Verify tables were created
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        print(f"✓ Created tables: {', '.join(tables)}")
    else:
        print("\nUsing existing database...")
    
    # Create superadmin
    print("\n" + "-"*40)
    print("Creating Superadmin Account")
    print("-"*40)
    
    db = SessionLocal()
    try:
        superadmin = create_superadmin(db)
        
        print("\n" + "="*60)
        print("INITIALIZATION COMPLETE!")
        print("="*60)
        print("\nSuperadmin credentials:")
        print("  Email: superadmin@cheontec.com")
        print("  Password: Admin@123")
        print("\nYou can now run the application and log in with these credentials.")
        print("\nTo create additional users (Manager, Accountant, Credit Officer, Members):")
        print("  1. Log in as superadmin")
        print("  2. Use the admin interface to create other users")
        print("  3. Or use the manager dashboard to create staff accounts")
        
    except Exception as e:
        logger.error(f"Initialization failed: {e}")
        return 1
    finally:
        db.close()
    
    return 0


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Initialize SACCO database')
    parser.add_argument('--force', action='store_true', help='Force recreate database without confirmation')
    args = parser.parse_args()
    
    # Override confirmation if --force flag is used
    if args.force:
        # Temporarily modify main to skip confirmation
        import builtins
        original_input = builtins.input
        builtins.input = lambda prompt: 'y'
        
        sys.exit(main())
    else:
        sys.exit(main())