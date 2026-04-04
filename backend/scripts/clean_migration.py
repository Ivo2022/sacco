import re
from pathlib import Path

def clean_sqlite_dump(input_file, output_file):
    print(f"Reading from: {input_file}")
    
    with open(input_file, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    # 1. Remove PRAGMA statements
    sql = re.sub(r'PRAGMA[^;]+;', '', sql, flags=re.IGNORECASE)
    
    # 2. Remove BEGIN/COMMIT TRANSACTION
    sql = re.sub(r'BEGIN TRANSACTION;', '', sql, flags=re.IGNORECASE)
    sql = re.sub(r'COMMIT;', '', sql, flags=re.IGNORECASE)
    
    # 3. Convert DATETIME to TIMESTAMP
    sql = re.sub(r'\bDATETIME\b', 'TIMESTAMP', sql, flags=re.IGNORECASE)
    
    # 4. Convert AUTOINCREMENT to SERIAL
    sql = re.sub(r'\bAUTOINCREMENT\b', 'SERIAL', sql, flags=re.IGNORECASE)
    
    # 5. Convert INTEGER PRIMARY KEY to SERIAL PRIMARY KEY
    sql = re.sub(r'INTEGER PRIMARY KEY', 'SERIAL PRIMARY KEY', sql, flags=re.IGNORECASE)
    
    # 6. Remove double quotes around identifiers
    sql = re.sub(r'"([^"]+)"', r'\1', sql)
    
    # 7. Convert SQLite datetime functions
    sql = re.sub(r"datetime\(([^)]+)\)", r"\1::TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(r"date\(([^)]+)\)", r"\1::DATE", sql, flags=re.IGNORECASE)
    
    # 8. Remove SQLite's sqlite_sequence references
    sql = re.sub(r"DELETE FROM sqlite_sequence[^;]+;", '', sql, flags=re.IGNORECASE)
    sql = re.sub(r"INSERT INTO sqlite_sequence[^;]+;", '', sql, flags=re.IGNORECASE)
    
    # 9. Convert last_insert_rowid() to LASTVAL()
    sql = re.sub(r'last_insert_rowid\(\)', 'LASTVAL()', sql, flags=re.IGNORECASE)
    
    # 10. Convert CURRENT_TIMESTAMP to NOW()
    sql = re.sub(r'CURRENT_TIMESTAMP', 'NOW()', sql, flags=re.IGNORECASE)
    
    # 11. Fix CREATE TABLE statements (add IF NOT EXISTS correctly)
    # Match: CREATE TABLE table_name or CREATE TABLE "table_name"
    sql = re.sub(
        r'CREATE TABLE (?:public\.)?([^\s(]+)',
        r'CREATE TABLE IF NOT EXISTS public.\1',
        sql,
        flags=re.IGNORECASE
    )
    
    # 12. Fix INSERT statements to use public schema
    sql = re.sub(
        r'INSERT INTO (?!public\.)([^\s(]+)',
        r'INSERT INTO public.\1',
        sql,
        flags=re.IGNORECASE
    )
    
    # 13. Remove any ON CONFLICT clauses (SQLite specific)
    sql = re.sub(r'ON CONFLICT\([^)]+\) DO NOTHING\s*;', ';', sql, flags=re.IGNORECASE)
    sql = re.sub(r'ON CONFLICT[^;]+;', ';', sql, flags=re.IGNORECASE)
    
    # 14. Remove SQLite-specific indexes
    sql = re.sub(r'CREATE INDEX "sqlite_autoindex[^"]+" ON.*$', '', sql, flags=re.IGNORECASE | re.MULTILINE)
    
    # 15. Handle DEFAULT CURRENT_TIMESTAMP
    sql = re.sub(r"DEFAULT CURRENT_TIMESTAMP", "DEFAULT NOW()", sql, flags=re.IGNORECASE)
    
    # Write the cleaned SQL
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(sql)
    
    # Split into schema and data files
    lines = sql.split('\n')
    schema_lines = []
    data_lines = []
    
    for line in lines:
        if line.strip().upper().startswith('INSERT INTO'):
            data_lines.append(line)
        elif line.strip().upper().startswith('CREATE TABLE'):
            schema_lines.append(line)
        elif line.strip() and not line.strip().startswith('--'):
            # Add other non-comment, non-empty lines to schema
            if line.strip():
                schema_lines.append(line)
    
    schema_file = output_file.replace('.sql', '_schema_only.sql')
    with open(schema_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(schema_lines))
    
    data_file = output_file.replace('.sql', '_data_only.sql')
    with open(data_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(data_lines))
    
    print(f"✅ Cleaned migration saved to {output_file}")
    print(f"✅ Schema only saved to {schema_file}")
    print(f"✅ Data only saved to {data_file}")
    print(f"\n📊 Statistics:")
    print(f"   - {len(schema_lines)} schema lines")
    print(f"   - {len(data_lines)} data lines")

if __name__ == "__main__":
    # Get the script's directory (backend/scripts)
    script_dir = Path(__file__).parent
    
    # Go up one level to backend, then into database
    backend_dir = script_dir.parent
    database_dir = backend_dir / 'database'
    
    # Set file paths
    input_path = database_dir / 'dump.sql'
    output_path = database_dir / 'cleaned_migration.sql'
    
    print(f"Looking for SQLite dump at: {input_path}")
    
    if not input_path.exists():
        print(f"Error: {input_path} not found!")
        print("First run: sqlite3 cheontec.db .dump > backend/database/dump.sql")
    else:
        clean_sqlite_dump(str(input_path), str(output_path))
    	
    if not input_path.exists():
        print(f"❌ Error: {input_path} not found!")
        print("\nFirst create the dump file:")
        print(f"  cd {database_dir}")
        print("  sqlite3 cheontec.db .dump > dump.sql")
    else:
        clean_sqlite_dump(str(input_path), str(output_path))
        print("\n📝 Next steps:")
        print("1. Drop existing tables if any:")
        print("   psql -U cheontec -d cheontec_db -c \"DROP SCHEMA public CASCADE; CREATE SCHEMA public;\"")
        print("\n2. Run schema first:")
        print(f"   psql -U cheontec -d cheontec_db -f {database_dir}/cleaned_migration_schema_only.sql")
        print("\n3. Then run data:")
        print(f"   psql -U cheontec -d cheontec_db -f {database_dir}/cleaned_migration_data_only.sql")