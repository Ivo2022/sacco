import sys
import os
from pathlib import Path

# Get the backend directory (parent of scripts)
script_dir = Path(__file__).resolve().parent
backend_dir = script_dir.parent
project_root = backend_dir.parent

# Add both backend and project root to path
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(backend_dir))

# Now try importing
try:
    from backend.core.config import settings
    from backend.database.session import engine
    from backend.database import models
except ImportError:
    # Fallback for when running from different locations
    os.chdir(backend_dir)
    from ..core import settings
    from ..core import engine
    from ..models import models, membership, share, insights, notification

def create_tables():
    print(f"Project root: {project_root}")
    print(f"Backend dir: {backend_dir}")
    print(f"Database URL: {settings.DATABASE_URL}")
    print("\nCreating all tables...")
    
    # Drop all tables first (clean slate)
    print("Dropping existing tables...")
    models.Base.metadata.drop_all(bind=engine)
    print("✅ Dropped existing tables")
    
    # Create all tables
    print("Creating new tables...")
    models.Base.metadata.create_all(bind=engine)
    print("✅ Created all tables")
    
    print("\n✅ Tables created successfully!")

if __name__ == "__main__":
    create_tables()