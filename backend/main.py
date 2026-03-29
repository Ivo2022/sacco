# backend/main.py
"""
SACCO Management System - Main Application Entry Point
"""
import os
import logging
import warnings
from pathlib import Path
from datetime import date
import shutil

from sqlalchemy.exc import SAWarning
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Suppress SQLAlchemy relationship overlap warnings
warnings.filterwarnings("ignore", category=SAWarning, module="sqlalchemy.orm.relationships")

# Import core modules
from .core import (
    settings,
    init_db,
    SACCOStatusMiddleware,
    TemplateHelpersMiddleware,
    register_template_helpers
)
from .core.database import get_db_session

# Import models and schemas
from .models import User
from .schemas import RoleEnum

# Import routers
from .routers import (
    auth,
    superadmin,
    manager,
    member,
    accountant,
    credit_officer,
    switch_account,
    home
)

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Debug database connection info
logger.info(f"Database URL: {settings.DATABASE_URL}")
if settings.DATABASE_URL.startswith("sqlite:///"):
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    logger.info(f"Database file exists: {os.path.exists(db_path)}")

# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG
)

# CORS configuration
origins = [
    "https://www.api.cheontec.com",
    "https://api.cheontec.com",
    "http://localhost:8000",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE
)
app.add_middleware(SACCOStatusMiddleware)

# Setup static files - with absolute path handling for Render
current_dir = Path(__file__).parent.absolute()
static_dir = current_dir / "static"
static_dir.mkdir(exist_ok=True)

# Log paths for debugging on Render
logger.info(f"Current directory: {current_dir}")
logger.info(f"Static directory: {static_dir}")
logger.info(f"Static directory exists: {static_dir.exists()}")

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Setup templates - with absolute path and error handling for Render
templates_dir = current_dir / "templates"
logger.info(f"Templates directory: {templates_dir}")
logger.info(f"Templates directory exists: {templates_dir.exists()}")

# List template files for debugging
if templates_dir.exists():
    template_files = list(templates_dir.glob("*.html"))
    logger.info(f"Template files found: {[f.name for f in template_files]}")
else:
    logger.error(f"Templates directory NOT FOUND at {templates_dir}")

# Create templates instance with auto-reload disabled for production
templates = Jinja2Templates(
    directory=str(templates_dir)
)

# Disable template caching temporarily to debug
templates.env.cache_size = 0

# Store templates in app state for access in routers
app.state.templates = templates

# Register template helpers
register_template_helpers(templates)

# Include routers with prefixes
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(superadmin.router, prefix="", tags=["Super Admin"])
app.include_router(manager.router, prefix="", tags=["SACCO Manager"])
app.include_router(member.router, prefix="", tags=["Member"])
app.include_router(accountant.router, prefix="", tags=["Accountant"])
app.include_router(credit_officer.router, prefix="", tags=["Credit Officer"])
app.include_router(switch_account.router, prefix="", tags=["Switch Account"])
app.include_router(home.router, tags=["Home"])


@app.on_event("startup")
async def startup_event():
    """Initialize application on startup"""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.VERSION}")
    
    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise
    
    # Check for superadmin existence
    try:
        db = get_db_session()
        try:
            superadmin_count = db.query(User).filter(
                User.role == RoleEnum.SUPER_ADMIN
            ).count()
            
            if superadmin_count == 0:
                logger.warning(
                    "No superadmin exists! Create one with:\n"
                    "python -m backend.scripts.init_db"
                )
            else:
                logger.info(f"Found {superadmin_count} superadmin(s) in database")
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error checking superadmin: {e}")
    
    # Auto-backup daily for SQLite only
    if settings.DATABASE_URL.startswith("sqlite:///"):
        try:
            backup_dir = Path("backups")
            backup_dir.mkdir(exist_ok=True)
            
            backup_file = backup_dir / f"auto_backup_{date.today()}.db"
            db_path = settings.DATABASE_URL.replace("sqlite:///", "")
            
            if not backup_file.exists() and os.path.exists(db_path):
                shutil.copy2(db_path, backup_file)
                logger.info(f"Daily backup created: {backup_file}")
            elif backup_file.exists():
                logger.debug(f"Backup already exists for today: {backup_file}")
        except Exception as e:
            logger.warning(f"Failed to create daily backup: {e}")
    
    logger.info("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info(f"Shutting down {settings.PROJECT_NAME}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "debug": settings.DEBUG,
        "templates_dir": str(templates_dir),
        "templates_exist": templates_dir.exists()
    }


# Debug endpoint to check template availability
@app.get("/debug/templates")
async def debug_templates():
    """Debug endpoint to check template loading"""
    if templates_dir.exists():
        template_files = list(templates_dir.glob("*.html"))
        return {
            "templates_dir": str(templates_dir),
            "exists": True,
            "files": [f.name for f in template_files],
            "base_exists": (templates_dir / "base.html").exists()
        }
    else:
        return {
            "templates_dir": str(templates_dir),
            "exists": False,
            "error": "Templates directory not found"
        }