import json
import sqlite3
from pathlib import Path

def export_sqlite_to_json():
    # Connect to SQLite
    db_path = Path(__file__).parent.parent / 'database' / 'cheontec.db'
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
    tables = [row[0] for row in cursor.fetchall()]
    
    # Export each table to JSON
    for table in tables:
        cursor.execute(f"SELECT * FROM {table}")
        rows = cursor.fetchall()
        
        if rows:
            data = [dict(row) for row in rows]
            output_file = Path(__file__).parent.parent / 'database' / f'{table}_export.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, default=str)
            print(f"✅ Exported {len(data)} rows from {table} to {output_file}")
    
    conn.close()
    print("\n✅ Export complete!")

if __name__ == "__main__":
    export_sqlite_to_json()