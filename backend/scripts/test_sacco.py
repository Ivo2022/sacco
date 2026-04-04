# Quick test in Python console
from backend.core.database import SessionLocal
from backend.models.models import Sacco, Log, User
from backend.utils.logger import log_user_action
from backend.core.dependencies import get_current_user

db = SessionLocal()

# Create a second SACCO
sacco2 = Sacco(
    name="Test SACCO 2",
    email="test2@example.com",
    phone="123456789"
)
db.add(sacco2)
db.commit()

# Create a log for the second SACCO (as super admin)
super_admin = db.query(User).filter(User.role == 'SUPER_ADMIN').first()
log_user_action(
    db=db,
    user=super_admin,
    action="TEST_ACTION",
    details="This log is for SACCO 2",
    ip_address="127.0.0.1",
    sacco_id=sacco2.id  # Force this log to be for SACCO 2
)

db.commit()

# Now check if the manager can see this log
manager = db.query(User).filter(User.id == 2).first()
from backend.utils.logger import get_logs_for_user
logs = get_logs_for_user(db, manager)

# Verify SACCO 2 log is NOT in the results
sacco2_logs = [l for l in logs if l.sacco_id == sacco2.id]
print(f"Manager sees SACCO 2 logs: {len(sacco2_logs)}")  # Should be 0