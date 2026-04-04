import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ..core import SessionLocal
from sqlalchemy import text

def verify_migration():
    session = SessionLocal()
    
    # Get row counts for all tables
    result = session.execute(text("""
        SELECT 
            t.tablename,
            n.n_live_tup as row_count
        FROM pg_tables t
        LEFT JOIN pg_stat_user_tables n ON t.tablename = n.relname
        WHERE t.schemaname = 'public'
        ORDER BY t.tablename
    """))
    
    print("\n📊 Table row counts in PostgreSQL:")
    print("-" * 50)
    total = 0
    for row in result:
        count = row.row_count if row.row_count else 0
        print(f"  {row.tablename}: {count} rows")
        total += count
    print("-" * 50)
    print(f"  TOTAL: {total} rows")
    
    # Test specific tables
    print("\n🔍 Sample data verification:")
    
    # Check users
    users = session.execute(text("SELECT username, email FROM users LIMIT 3"))
    for user in users:
        print(f"  User: {user[0]} - {user[1]}")
    
    # Check saccos
    saccos = session.execute(text("SELECT name FROM saccos"))
    for sacco in saccos:
        print(f"  SACCO: {sacco[0]}")
    
    session.close()
    print("\n✅ Verification complete!")

if __name__ == "__main__":
    verify_migration()