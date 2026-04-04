import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from ..core import SessionLocal
from sqlalchemy import text

def reset_sequences():
    session = SessionLocal()
    
    # Get all tables with id columns
    result = session.execute(text("""
        SELECT 
            t.table_name,
            c.column_name
        FROM information_schema.tables t
        JOIN information_schema.columns c ON t.table_name = c.table_name
        WHERE t.table_schema = 'public'
            AND c.column_name = 'id'
            AND t.table_type = 'BASE TABLE'
        ORDER BY t.table_name
    """))
    
    tables = result.fetchall()
    
    for table_name, column_name in tables:
        try:
            # Get max id
            max_id = session.execute(text(f"SELECT COALESCE(MAX({column_name}), 1) FROM {table_name}")).scalar()
            
            # Reset sequence
            session.execute(text(f"""
                SELECT setval(pg_get_serial_sequence('{table_name}', '{column_name}'), {max_id})
            """))
            
            print(f"✅ Reset {table_name} sequence to {max_id}")
        except Exception as e:
            print(f"⚠️  Error resetting {table_name}: {e}")
    
    session.commit()
    session.close()
    print("\n✅ All sequences reset successfully!")

if __name__ == "__main__":
    reset_sequences()