from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
import hashlib
import os
import binascii
from fastapi import status
import sqlite3
import secrets
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    # Prefer passlib if available
    from passlib.context import CryptContext  # type: ignore
    from passlib.exc import PasswordSizeError, ValueError
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
except ImportError:
    # Lightweight fallback using PBKDF2-HMAC (not as feature rich as passlib)
    class SimpleCryptContext:
        def __init__(self, schemes=None, deprecated="auto"):
            self.iterations = 100000
            self.algorithm = "sha256"

        def hash(self, password):
            if isinstance(password, str):
                password = password.encode()
            salt = os.urandom(16)
            dk = hashlib.pbkdf2_hmac(self.algorithm, password, salt, self.iterations)
            return f"pbkdf2_{self.algorithm}${self.iterations}${binascii.hexlify(salt).decode()}${binascii.hexlify(dk).decode()}"

        def verify(self, password, hashed):
            try:
                parts = hashed.split('$')
                if not parts[0].startswith('pbkdf2_'):
                    return False
                algorithm = parts[0].split('_', 1)[1]
                iterations = int(parts[1])
                salt = binascii.unhexlify(parts[2])
                dk = binascii.unhexlify(parts[3])
                if isinstance(password, str):
                    password = password.encode()
                newdk = hashlib.pbkdf2_hmac(algorithm, password, salt, iterations)
                return secrets.compare_digest(newdk, dk)
            except Exception:
                return False

    pwd_context = SimpleCryptContext()

from .db_utils import get_db
from .session_auth import get_current_user as session_get_current_user

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))  # Stronger secret key
app.mount("/static", StaticFiles(directory="backend/static"), name="static")
templates = Jinja2Templates(directory="backend/templates")

# To avoid bcrypt's 72-byte truncation limit, pre-hash with SHA-256 before passing
# to the configured password hasher. This works whether we're using passlib/bcrypt
# or the SimpleCryptContext PBKDF2 fallback.
def hash_password(password: str) -> str:
    """
    Hash a password with pre-hashing to avoid bcrypt's 72-byte limit.
    First computes SHA-256 of the password, then hashes that with the configured context.
    """
    if not password:
        raise ValueError("Password cannot be empty")
    
    # Compute SHA-256 hex digest, then hash that with the pwd_context
    sha = hashlib.sha256(password.encode('utf-8')).hexdigest()
    try:
        return pwd_context.hash(sha)
    except Exception as e:
        logger.error(f"Password hashing failed: {e}")
        raise HTTPException(status_code=500, detail="Password hashing failed")

def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.
    First pre-hashes with SHA-256 to match the hash_password function.
    """
    if not password or not hashed_password:
        return False
    
    # Compute SHA-256 hex digest, then verify with the pwd_context
    sha = hashlib.sha256(password.encode('utf-8')).hexdigest()
    try:
        return pwd_context.verify(sha, hashed_password)
    except Exception as e:
        logger.error(f"Password verification failed: {e}")
        return False

@app.on_event("startup")
def startup():
    conn = get_db()
    conn.row_factory = sqlite3.Row  # Ensure we get dictionary-like rows

    # Create users table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT 0
        )
    """)

    # Add commonly requested member fields if they don't exist (safe to run repeatedly)
    columns_to_add = [
        ("full_name", "TEXT"),
        ("email", "TEXT"),
        ("phone", "TEXT"),
        ("id_number", "TEXT"),
        ("member_number", "TEXT")
    ]
    
    for col_name, col_type in columns_to_add:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            # Column already exists
            pass

    # Create logs table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Create savings table (transactions)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS savings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Create loans table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL NOT NULL,
            term INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Create loan payments table to track repayments
    conn.execute("""
        CREATE TABLE IF NOT EXISTS loan_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            loan_id INTEGER,
            user_id INTEGER,
            amount REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(loan_id) REFERENCES loans(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    conn.commit()
    conn.close()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/register")
def register_get(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
def register_post(request: Request,
                  username: str = Form(...),
                  password: str = Form(...),
                  password_confirm: str = Form(...),
                  full_name: str = Form(None),
                  email: str = Form(None),
                  phone: str = Form(None),
                  id_number: str = Form(None),
                  member_number: str = Form(None),
                  initial_deposit: float = Form(0.0)):
    
    # Input validation
    if not username or not password:
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "Username and password are required"
        })
    
    # validate password confirmation
    if password != password_confirm:
        return templates.TemplateResponse("register.html", {
            "request": request, 
            "error": "Passwords do not match"
        })

    conn = get_db()
    conn.row_factory = sqlite3.Row
    
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

        hashed_password = hash_password(password)

        # Only the first user gets admin privileges
        is_admin = 1 if user_count == 0 else 0
        
        cursor = conn.execute(
            "INSERT INTO users (username, password, is_admin) VALUES (?, ?, ?)",
            (username, hashed_password, is_admin)
        )
        conn.commit()
        
        # Update extra profile fields
        conn.execute(
            """UPDATE users SET 
               full_name = ?, email = ?, phone = ?, id_number = ?, member_number = ? 
               WHERE username = ?""",
            (full_name, email, phone, id_number, member_number, username)
        )
        conn.commit()

        # If the registrant provided an initial deposit, create a savings record
        if initial_deposit and float(initial_deposit) > 0:
            row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
            if row:
                user_id = row["id"]
                conn.execute(
                    "INSERT INTO savings (user_id, type, amount) VALUES (?, 'deposit', ?)", 
                    (user_id, float(initial_deposit))
                )
                conn.execute(
                    "INSERT INTO logs (user_id, action) VALUES (?, ?)", 
                    (user_id, "initial_deposit")
                )
                conn.commit()
                
        return RedirectResponse("/login", status_code=303)
        
    except sqlite3.IntegrityError:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Username already exists"
        })
    except ValueError as e:
        logger.error(f"Password error during registration: {e}")
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "Password is too long or invalid"
        })
    except Exception as e:
        logger.error(f"Unexpected error during registration: {e}")
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error": "An unexpected error occurred"
        })
    finally:
        conn.close()

@app.get("/login")
def login_get(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    conn = get_db()
    conn.row_factory = sqlite3.Row
    
    try:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        
        if not user:
            return templates.TemplateResponse("login.html", {
                "request": request, 
                "error": "Invalid credentials"
            })
        
        if verify_password(password, user["password"]):
            # Convert row to dict for session storage
            user_dict = dict(user)
            request.session["user"] = user_dict
            
            conn.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", 
                        (user["id"], "login"))
            conn.commit()
            
            # Redirect users based on role
            if user["is_admin"]:
                return RedirectResponse("/admin/dashboard", status_code=303)
            return RedirectResponse("/client/dashboard", status_code=303)
        
        return templates.TemplateResponse("login.html", {
            "request": request, 
            "error": "Invalid credentials"
        })
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "An error occurred during login"
        })
    finally:
        conn.close()

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)

def get_current_user(request: Request):
    # kept for backward compat if other modules import from main
    return session_get_current_user(request)

def _log_action(conn, user_id: int, action: str):
    try:
        conn.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", (user_id, action))
        conn.commit()
    except Exception as e:
        logger.error(f"Failed to log action: {e}")

def _get_balance(conn, user_id: int) -> float:
    try:
        deposits = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'deposit'", 
            (user_id,)
        ).fetchone()[0]
        withdrawals = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'withdraw'", 
            (user_id,)
        ).fetchone()[0]
        return float(deposits) - float(withdrawals)
    except Exception as e:
        logger.error(f"Failed to calculate balance: {e}")
        return 0.0

from .routers import public as public_router, client as client_router, admin as admin_router

# Mount routers
app.include_router(public_router.router)
app.include_router(client_router.router)
app.include_router(admin_router.router)