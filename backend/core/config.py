# backend/core/config.py
import os
import secrets
from typing import Optional, List, ClassVar
from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Application settings"""
    
    # Project info
    PROJECT_NAME: str = "SACCO Management System"
    VERSION: str = "1.0.0"
    
    # Security
    SECRET_KEY: str = os.environ.get("SESSION_SECRET") or secrets.token_hex(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    PROJECT_ROOT: ClassVar[Path] = Path(__file__).parent.parent.parent
    @property
    def DEFAULT_DB_PATH(self) -> Path:
        return self.PROJECT_ROOT / "backend" / "database" / "cheontec.db"
    
    @property
    def DATABASE_URL(self) -> str:
        # Create database directory if it doesn't exist
        self.DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return os.environ.get("DATABASE_URL", f"sqlite:///{self.DEFAULT_DB_PATH}")
    
    # Timezone
    LOCAL_OFFSET_HOURS: int = 3
    TIMEZONE_NAME: str = "East Africa Time"
    
    # File uploads
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10MB
    
    # Pagination
    ITEMS_PER_PAGE: int = 20
    
    # Session
    SESSION_MAX_AGE: int = 60 * 60 * 24 * 7  # 7 days
    SESSION_SECRET_KEY: str = os.environ.get("SESSION_SECRET_KEY") or secrets.token_hex(32)
    
    # Admin email for notifications
    ADMIN_EMAIL: Optional[str] = os.environ.get("ADMIN_EMAIL")
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ]
    
    # Email settings
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    
    # Debug mode
    DEBUG: bool = os.environ.get("DEBUG", "False").lower() == "true"
    ENVIRONMENT: str = os.environ.get("ENVIRONMENT", "development")
    
    # Account Creation Mode
    ALLOW_SELF_REGISTRATION: bool = os.environ.get("ALLOW_SELF_REGISTRATION", "True").lower() == "true"
    SELF_REGISTRATION_REQUIRES_APPROVAL: bool = os.environ.get("SELF_REGISTRATION_REQUIRES_APPROVAL", "True").lower() == "true"
    DEFAULT_MEMBER_STATUS: str = os.environ.get("DEFAULT_MEMBER_STATUS", "pending")  # pending, active
	
    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # Ignore extra fields from environment

# Create settings instance
settings = Settings()

# For backward compatibility, expose commonly used settings at module level
SECRET_KEY = settings.SECRET_KEY
DATABASE_URL = settings.DATABASE_URL
DEBUG = settings.DEBUG