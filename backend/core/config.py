# backend/core/config.py
import os
import secrets
from typing import Optional, List, ClassVar, Union
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator, ValidationInfo

class Settings(BaseSettings):
    """Application settings with production safety"""
    
    # Project info
    PROJECT_NAME: str = "SACCO Management System"
    VERSION: str = "1.0.0"
    
    # Security - NO FALLBACKS in production
    SECRET_KEY: Optional[str] = None
    SESSION_SECRET_KEY: Optional[str] = None
    
    @field_validator("SECRET_KEY", "SESSION_SECRET_KEY")
    @classmethod
    def validate_secrets(cls, v: Optional[str], info: ValidationInfo) -> str:
        """Validate secrets exist in production"""
        env = os.environ.get("ENVIRONMENT", "development")
        
        if env == "production" and (not v or len(str(v)) < 32):
            raise ValueError(f"{info.field_name} must be set to at least 32 characters in production")
        
        if not v and env != "production":
            return secrets.token_hex(32)
        
        return v
    
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # Database
    PROJECT_ROOT: ClassVar[Path] = Path(__file__).parent.parent.parent
    DATABASE_URL: str = ""
    
    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str, info: ValidationInfo) -> str:
        """Validate database URL is set"""
        env = os.environ.get("ENVIRONMENT", "development")
        
        if not v and env == "production":
            raise ValueError("DATABASE_URL must be set in production environment")
        
        if v and v.startswith("postgres://"):
            db_path = v.replace("postgres://", "postgresql://")
            db_dir = Path(db_path).parent
            if db_dir:
                db_dir.mkdir(parents=True, exist_ok=True)
        
        return v or "sqlite:///./backend/database/cheontec.db"
    
    # PostgreSQL pool settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = 3600
    DB_POOL_PRE_PING: bool = True  # Important for Render's managed PostgreSQ
    
    # Timezone
    LOCAL_OFFSET_HOURS: int = 3
    TIMEZONE_NAME: str = "East Africa Time"
    
    # File uploads
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024
    
    # Pagination
    ITEMS_PER_PAGE: int = 20
    
    # Session
    SESSION_MAX_AGE: int = 60 * 60 * 24 * 7
    
    # Admin email for notifications
    ADMIN_EMAIL: Optional[str] = None
    
    # CORS - Use a simpler approach
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000,http://localhost:8000"
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list"""
        if not self.BACKEND_CORS_ORIGINS:
            return ["http://localhost:3000", "http://localhost:8000"]
        
        # Split by comma and clean up
        origins = [origin.strip() for origin in self.BACKEND_CORS_ORIGINS.split(",") if origin.strip()]
        return origins if origins else ["http://localhost:3000", "http://localhost:8000"]
    
    # Email settings
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: Optional[int] = None
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: Optional[str] = None
    
    # Environment
    DEBUG: bool = False
    ENVIRONMENT: str = "development"
    
    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v):
        """Parse DEBUG from environment"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)
    
    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"
    
    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"
    
    # Account Creation Mode
    ALLOW_SELF_REGISTRATION: bool = True
    SELF_REGISTRATION_REQUIRES_APPROVAL: bool = True
    DEFAULT_MEMBER_STATUS: str = "pending"
    
    @field_validator("ALLOW_SELF_REGISTRATION", "SELF_REGISTRATION_REQUIRES_APPROVAL", mode="before")
    @classmethod
    def parse_bool_settings(cls, v):
        """Parse boolean settings from environment"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


# Create settings instance
settings = Settings()

# For backward compatibility
SECRET_KEY = settings.SECRET_KEY
DATABASE_URL = settings.DATABASE_URL
DEBUG = settings.DEBUG