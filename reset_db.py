# save as reset_db.py
import os
import sys
from passlib.context import CryptContext

# Add the parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from backend.database import engine, SessionLocal
from backend.models import Base, User, RoleEnum

# Use the same password context as your application
# This should match what's in your services.py
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return pwd_context.hash(password)

# Database file path
db_path = "backend/cheontec.db"

# Delete existing database if it exists
if os.path.exists(db_path):
    print(f"Deleting existing database: {db_path}")
    os.remove(db_path)
    print("Database deleted successfully")
else:
    print(f"No existing database found at {db_path}")

# Create new database with all tables
print("Creating new database with all tables...")
Base.metadata.create_all(bind=engine)
print("Database created successfully!")

# Create a test session to add initial data
db = SessionLocal()

print("\nCreating super admin user...")

# Create super admin user only
super_admin = User(
    full_name="System Administrator",
    email="admin@example.com",
    password_hash=hash_password("admin123"),
    role=RoleEnum.SUPER_ADMIN,
    is_active=True,
    password_reset_required=False
)
db.add(super_admin)
db.commit()
print(f"Created super admin: {super_admin.email} / admin123")

print("\nSuper admin created successfully!")

# Show summary
print("\n" + "="*50)
print("DATABASE RESET COMPLETE")
print("="*50)
print(f"Database: {db_path}")
print("\nSuper Admin Account:")
print(f"  Email: admin@example.com")
print(f"  Password: admin123")
print(f"  Role: SUPER_ADMIN")
print("\nYou can now start your application!")
print("="*50)

db.close()