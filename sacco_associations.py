"""
# save as fix_sacco_associations.py
from backend.database import SessionLocal
from backend.models import User, Sacco

db = SessionLocal()

# Get the first SACCO (or create one if none exists)
sacco = db.query(Sacco).first()
if not sacco:
    print("No SACCO found! Creating one...")
    sacco = Sacco(name="Default SACCO", email="default@sacco.org")
    db.add(sacco)
    db.commit()
    db.refresh(sacco)

print(f"Using SACCO: {sacco.name} (ID: {sacco.id})")

# Update all users without sacco_id to belong to this SACCO
users_updated = db.query(User).filter(User.sacco_id.is_(None)).update(
    {User.sacco_id: sacco.id},
    synchronize_session=False
)

db.commit()
print(f"Updated {users_updated} users to belong to SACCO {sacco.id}")

# Verify
users = db.query(User).all()
for user in users:
    print(f"User: {user.email}, Role: {user.role}, SACCO ID: {user.sacco_id}")

db.close()
"""


# create_test_loan.py
import sqlite3
from datetime import datetime

conn = sqlite3.connect('backend/cheontec.db')
cursor = conn.cursor()

# Get member ID
cursor.execute("SELECT id FROM users WHERE email = 'peter@cheontec.com'")
member = cursor.fetchone()

if member:
    member_id = member[0]
    
    # Create a test loan request
    cursor.execute("""
        INSERT INTO loans (user_id, amount, term, status, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (member_id, 50000.00, 12, 'pending', datetime.now().isoformat()))
    
    conn.commit()
    print(f"Test loan created for member ID {member_id}")
    
    # Verify
    cursor.execute("SELECT id, amount, status FROM loans WHERE user_id = ?", (member_id,))
    loans = cursor.fetchall()
    for loan in loans:
        print(f"  Loan #{loan[0]}: Amount={loan[1]}, Status={loan[2]}")
else:
    print("Member not found!")

conn.close()