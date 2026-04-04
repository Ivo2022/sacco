import psycopg2
from psycopg2.extras import execute_values
import sys
from pathlib import Path
from sqlalchemy import create_engine
# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from ..core import settings
from ..core import engine
from ..models import models, membership, share, insights, notification

# Render PostgreSQL connection (update with your credentials)
RENDER_DB_URL = "postgresql://cheontec:cEx1YZruJCXRWeqMAnDbYa7wEQGAOt1G@dpg-d78ip62dbo4c7386fuvg-a.oregon-postgres.render.com/cheontec_db?sslmode=require"

# Define migration order (parent tables first, child tables last)
MIGRATION_ORDER = [
    'saccos',
    'users',
    'share_types',
    'membership_applications',
    'membership_fees',
    'alert_rules',
    'system_settings',
    'savings',
    'shares',
    'dividend_declarations',
    'loans',
    'pending_deposits',
    'referral_commissions',
    'loan_payments',
    'share_transactions',
    'dividend_payments',
    'external_loans',
    'external_loan_payments',
    'logs',
    'insight_logs',
    'weekly_summaries',
]

def create_tables_on_render():
    """Step 1: Create all tables on Render"""
    print("📋 Creating tables on Render...")
    
    render_engine = create_engine(RENDER_DB_URL)
    
    # Just create tables - don't drop since they don't exist
    models.Base.metadata.create_all(bind=render_engine)
    print("✅ Tables created successfully!")
    
    return render_engine

def get_table_data(local_cursor, table):
    """Get data from local table"""
    try:
        local_cursor.execute(f"SELECT * FROM {table}")
        rows = local_cursor.fetchall()
        
        if not rows:
            return None, None
        
        # Get column names
        local_cursor.execute(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = '{table}' 
            ORDER BY ordinal_position
        """)
        columns = [col[0] for col in local_cursor.fetchall()]
        
        return columns, rows
    except Exception as e:
        print(f"  ⚠️  Error reading {table}: {e}")
        return None, None

def reset_sequences():
    """Step 3: Reset all sequences on Render"""
    print("\n🔄 Resetting sequences...")
    
    render_conn = psycopg2.connect(RENDER_DB_URL)
    render_cursor = render_conn.cursor()
    
    render_cursor.execute("""
        SELECT tablename FROM pg_tables WHERE schemaname = 'public'
    """)
    tables = render_cursor.fetchall()
    
    for (table,) in tables:
        try:
            render_cursor.execute(f"""
                SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table}), 1)
                )
            """)
            print(f"  ✓ Reset {table} sequence")
        except Exception as e:
            pass  # Table might not have id column
    
    render_conn.commit()
    render_cursor.close()
    render_conn.close()
    print("✅ Sequences reset!")

def migrate_data_force():
    """Force migration by temporarily removing foreign keys"""
    print("\n📊 Starting data migration (forcing foreign keys off)...")
    
    # Local connection
    local_conn = psycopg2.connect(
        host="localhost",
        database="cheontec_db",
        user="cheontec",
        password="Admin123"
    )
    local_cursor = local_conn.cursor()
    
    # Render connection
    render_conn = psycopg2.connect(RENDER_DB_URL)
    render_cursor = render_conn.cursor()
    
    # Get all foreign key constraints
    render_cursor.execute("""
        SELECT conname, conrelid::regclass::text 
        FROM pg_constraint 
        WHERE contype = 'f'
    """)
    constraints = render_cursor.fetchall()
    
    # Drop all foreign key constraints
    print("Dropping foreign key constraints...")
    for conname, table_name in constraints:
        try:
            render_cursor.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT {conname}")
            print(f"  Dropped {conname} on {table_name}")
        except Exception as e:
            print(f"  Failed to drop {conname}: {e}")
    
    render_conn.commit()
    
    # Get all tables with data from local
    local_cursor.execute("""
        SELECT tablename FROM pg_tables 
        WHERE schemaname = 'public' 
        AND tablename NOT LIKE 'pg_%'
        ORDER BY tablename
    """)
    tables = [row[0] for row in local_cursor.fetchall()]
    
    # Migrate data
    for table in tables:
        print(f"\n📦 Migrating {table}...")
        
        local_cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = local_cursor.fetchone()[0]
        
        if count == 0:
            print(f"  No data, skipping")
            continue
        
        # Get columns
        local_cursor.execute(f"""
            SELECT column_name FROM information_schema.columns 
            WHERE table_name = '{table}' 
            ORDER BY ordinal_position
        """)
        columns = [col[0] for col in local_cursor.fetchall()]
        
        # Get data
        local_cursor.execute(f"SELECT * FROM {table}")
        rows = local_cursor.fetchall()
        
        # Insert
        try:
            render_cursor.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
            
            placeholders = ','.join(['%s'] * len(columns))
            insert_query = f"INSERT INTO {table} ({','.join(columns)}) VALUES %s"
            data = [tuple(row) for row in rows]
            
            execute_values(render_cursor, insert_query, data)
            render_conn.commit()
            print(f"  ✅ Migrated {len(rows)} rows")
        except Exception as e:
            print(f"  ❌ Error: {e}")
            render_conn.rollback()
    
    # Recreate foreign keys using SQLAlchemy
    print("\nRecreating foreign key constraints...")
    from ..core import settings
    from ..core import engine
    from ..models import models, membership, share, insights, notification
    
    render_engine = create_engine(RENDER_DB_URL)
    models.Base.metadata.create_all(bind=render_engine)
    print("✅ Constraints recreated!")
    
    local_cursor.close()
    local_conn.close()
    render_cursor.close()
    render_conn.close()
    
    print("\n✅ Migration complete!")

def verify_migration():
    """Step 4: Verify migration"""
    print("\n🔍 Verifying migration...")
    
    render_conn = psycopg2.connect(RENDER_DB_URL)
    render_cursor = render_conn.cursor()
    
    # Corrected query - use relname instead of tablename
    render_cursor.execute("""
        SELECT 
            relname as table_name,
            n_live_tup as row_count
        FROM pg_stat_user_tables
        ORDER BY relname
    """)
    
    total = 0
    tables_with_data = []
    for table, count in render_cursor.fetchall():
        if count and count > 0:
            print(f"  {table}: {count} rows")
            total += count
            tables_with_data.append(table)
    
    render_cursor.close()
    render_conn.close()
    
    print(f"\n📊 Total rows: {total}")
    print(f"📋 Tables with data: {len(tables_with_data)}")
    
    if total == 0:
        print("\n⚠️  WARNING: No data found in any table!")
    else:
        print("\n✅ Verification complete!")

if __name__ == "__main__":
    print("🚀 Starting migration to Render PostgreSQL")
    print("=" * 50)
    
    # Step 1: Create tables
    create_tables_on_render()
    
    # Step 2: Migrate data
    migrate_data_force()
    
    # Step 3: Reset sequences
    reset_sequences()
    
    # Step 4: Verify
    verify_migration()
    
    print("\n" + "=" * 50)
    print("✅ Migration to Render complete!")