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
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware

# Suppress SQLAlchemy relationship overlap warnings
warnings.filterwarnings("ignore", category=SAWarning, module="sqlalchemy.orm.relationships")

# Import core modules
from .core import (
    settings,
    init_db,
    SACCOStatusMiddleware,
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

# Create FastAPI application
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG
)

# =============================================================================
# MIDDLEWARE CONFIGURATION
# =============================================================================

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

# Session middleware
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    max_age=settings.SESSION_MAX_AGE,
    same_site="lax",          # important
    https_only=True           # 🔥 REQUIRED on Render (HTTPS)
)

# SACCO status middleware
app.add_middleware(SACCOStatusMiddleware)


# =============================================================================
# STATIC FILES CONFIGURATION
# =============================================================================

current_dir = Path(__file__).parent.absolute()
static_dir = current_dir / "static"
static_dir.mkdir(exist_ok=True)

logger.info(f"Static directory: {static_dir}")
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# =============================================================================
# TEMPLATES CONFIGURATION
# =============================================================================

templates_dir = current_dir / "templates"

if not templates_dir.exists():
    logger.error(f"Templates directory not found at {templates_dir}")
    raise RuntimeError(f"Templates directory missing: {templates_dir}")

logger.info(f"Templates directory: {templates_dir}")
template_files = list(templates_dir.glob("*.html"))
logger.info(f"Template files found: {[f.name for f in template_files]}")

# Create templates instance
templates = Jinja2Templates(directory=str(templates_dir))

# Production settings
templates.env.cache = None  # Disable Cache for now.
templates.env.auto_reload = settings.DEBUG  # Only auto-reload in debug mode

# Store templates in app state
app.state.templates = templates


# =============================================================================
# ROUTERS
# =============================================================================

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(superadmin.router, prefix="", tags=["Super Admin"])
app.include_router(manager.router, prefix="", tags=["SACCO Manager"])
app.include_router(member.router, prefix="", tags=["Member"])
app.include_router(accountant.router, prefix="", tags=["Accountant"])
app.include_router(credit_officer.router, prefix="", tags=["Credit Officer"])
app.include_router(switch_account.router, prefix="", tags=["Switch Account"])
app.include_router(home.router, tags=["Home"])


# =============================================================================
# APPLICATION LIFECYCLE EVENTS
# =============================================================================

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
        except Exception as e:
            logger.warning(f"Failed to create daily backup: {e}")
    
    logger.info("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on application shutdown"""
    logger.info(f"Shutting down {settings.PROJECT_NAME}")


# =============================================================================
# HEALTH CHECK ENDPOINTS
# =============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "debug": settings.DEBUG,
        "database": "sqlite" if settings.DATABASE_URL.startswith("sqlite:///") else "postgresql",
        "templates_loaded": len(template_files)
    }


@app.get("/debug/templates")
async def debug_templates():
    """Debug endpoint to check template availability"""
    return {
        "templates_dir": str(templates_dir),
        "exists": True,
        "files": [f.name for f in template_files],
        "base_exists": (templates_dir / "base.html").exists(),
        "template_count": len(template_files)
    }


@app.get("/debug/globals")
async def debug_globals():
    """Debug endpoint to check template globals"""
    return {
        "globals_count": len(app.state.templates.env.globals),
        "globals_keys": list(app.state.templates.env.globals.keys()),
        "cache_size": app.state.templates.env.cache_size,
        "auto_reload": app.state.templates.env.auto_reload
    }