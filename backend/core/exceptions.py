"""
Custom exceptions for the application
"""

class SACCOException(Exception):
    """Base exception for SACCO application"""
    pass

class AuthenticationError(SACCOException):
    """Authentication related errors"""
    pass

class AuthorizationError(SACCOException):
    """Authorization related errors"""
    pass

class DatabaseError(SACCOException):
    """Database related errors"""
    pass

class ValidationError(SACCOException):
    """Validation related errors"""
    pass