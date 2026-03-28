# add_log_details.py
import sqlite3

db_path = "cheontec.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check existing columns
cursor.execute("PRAGMA table_info(logs)")
columns = [col[1] for col in cursor.fetchall()]

if "details" not in columns:
    cursor.execute("ALTER TABLE logs ADD COLUMN details VARCHAR(500)")
    print("✓ Added details column to logs")

if "ip_address" not in columns:
    cursor.execute("ALTER TABLE logs ADD COLUMN ip_address VARCHAR(45)")
    print("✓ Added ip_address column to logs")

conn.commit()
conn.close()
print("Log table updated!")