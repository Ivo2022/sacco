#!/usr/bin/env python
"""Simple SQLite backup script"""
import os
import shutil
from datetime import datetime
from pathlib import Path

def backup_database():
    # Database path
    db_path = "backend/database/cheontec.db"
    backup_dir = "backups"
    
    if not os.path.exists(db_path):
        print("Database not found!")
        return
    
    # Create backup directory
    os.makedirs(backup_dir, exist_ok=True)
    
    # Create backup with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"cheontec_{timestamp}.db")
    
    # Copy database
    shutil.copy2(db_path, backup_path)
    print(f"✓ Database backed up to: {backup_path}")
    
    # Optional: Keep only last 30 backups
    backups = sorted(Path(backup_dir).glob("cheontec_*.db"))
    if len(backups) > 30:
        for old_backup in backups[:-30]:
            old_backup.unlink()
            print(f"Removed old backup: {old_backup}")

if __name__ == "__main__":
    backup_database()