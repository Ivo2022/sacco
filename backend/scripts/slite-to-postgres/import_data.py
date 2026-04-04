import json
import sys
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ..core import settings
from ..core import engine
from ..models import models, membership, share, insights, notification


def import_data():
    print(f"Connecting to: {settings.DATABASE_URL}")
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    # Map table names to model classes
    model_map = {
        'saccos': models.Sacco,  # Adjust model name if different
        'users': models.User,
        'pending_deposits': models.PendingDeposit,
        'loans': models.Loan,
        'logs': models.Log,
        'share_types': share.ShareType,
        'insight_logs': insights.InsightLog,
        'weekly_summaries': insights.WeeklySummary,
        'savings': models.Saving,
        'loan_payments': models.LoanPayment,
        'shares': share.Share,
        'dividend_declarations': share.DividendDeclaration,
        'share_transactions': share.ShareTransaction,
        'dividend_payments': share.DividendPayment,
    }
    
    database_dir = Path(__file__).parent.parent / 'database'
    
    # Import in order (respect foreign keys)
    import_order = [
        'saccos',
        'users', 
        'share_types',
        'pending_deposits',
        'loans',
        'savings',
        'shares',
        'dividend_declarations',
        'loan_payments',
        'share_transactions',
        'dividend_payments',
        'logs',
        'insight_logs',
        'weekly_summaries',
    ]
    
    for table_name in import_order:
        json_file = database_dir / f'{table_name}_export.json'
        
        if not json_file.exists():
            print(f"⚠️  No export file for {table_name}, skipping...")
            continue
        
        if table_name not in model_map:
            print(f"⚠️  No model found for {table_name}, skipping...")
            continue
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not data:
            print(f"📭 No data for {table_name}")
            continue
        
        model_class = model_map[table_name]
        
        # Clear existing data
        session.query(model_class).delete()
        session.commit()
        
        # Insert new data
        for row in data:
            # Convert string dates to datetime objects
            for key, value in row.items():
                if value and isinstance(value, str):
                    # Check if it looks like a datetime
                    if any(key_word in key.lower() for key_word in ['date', 'time', 'timestamp', 'created_at', 'updated_at', 'paid_at', 'approved_at']):
                        try:
                            # Try to parse ISO format datetime
                            row[key] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                        except:
                            pass  # Keep as string if not a date
            
            # Create model instance
            obj = model_class(**row)
            session.add(obj)
        
        session.commit()
        print(f"✅ Imported {len(data)} rows into {table_name}")
    
    print("\n✅ Import complete!")

if __name__ == "__main__":
    import_data()