
from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from ..session_auth import get_current_user
from ..db_utils import get_db

router = APIRouter()
templates = Jinja2Templates(directory="backend/templates")


@router.get("/client/dashboard", response_class=HTMLResponse)
def client_dashboard(request: Request, user: dict = Depends(get_current_user)):
    conn = get_db()
    deposits = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'deposit'", (user["id"],)).fetchone()[0]
    withdrawals = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'withdraw'", (user["id"],)).fetchone()[0]
    try:
        balance = float(deposits) - float(withdrawals)
    except Exception:
        balance = 0.0
    transactions = conn.execute("SELECT id, type, amount, timestamp FROM savings WHERE user_id = ? ORDER BY timestamp DESC", (user["id"],)).fetchall()
    loans = conn.execute("SELECT id, amount, term, status, timestamp FROM loans WHERE user_id = ? ORDER BY timestamp DESC", (user["id"],)).fetchall()
    conn.close()
    return templates.TemplateResponse("client/dashboard.html", {"request": request, "user": user, "balance": balance, "transactions": transactions, "loans": loans})


@router.get("/client/savings", response_class=HTMLResponse)
def view_savings(request: Request, user: dict = Depends(get_current_user)):
    conn = get_db()
    deposits = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'deposit'", (user["id"],)).fetchone()[0]
    withdrawals = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'withdraw'", (user["id"],)).fetchone()[0]
    try:
        balance = float(deposits) - float(withdrawals)
    except Exception:
        balance = 0.0
    transactions = conn.execute("SELECT id, type, amount, timestamp FROM savings WHERE user_id = ? ORDER BY timestamp DESC", (user["id"],)).fetchall()
    conn.close()
    return templates.TemplateResponse("client/savings.html", {"request": request, "user": user, "balance": balance, "transactions": transactions})


@router.post("/client/savings/deposit")
def deposit(request: Request, amount: float = Form(...), user: dict = Depends(get_current_user)):
    if amount <= 0:
        return templates.TemplateResponse("client/savings.html", {"request": request, "user": user, "error": "Amount must be positive"})
    conn = get_db()
    conn.execute("INSERT INTO savings (user_id, type, amount) VALUES (?, 'deposit', ?)", (user["id"], amount))
    conn.commit()
    conn.close()
    return RedirectResponse("/client/savings", status_code=303)


@router.post("/client/savings/withdraw")
def withdraw(request: Request, amount: float = Form(...), user: dict = Depends(get_current_user)):
    if amount <= 0:
        return templates.TemplateResponse("client/savings.html", {"request": request, "user": user, "error": "Amount must be positive"})
    conn = get_db()
    deposits = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'deposit'", (user["id"],)).fetchone()[0]
    withdrawals = conn.execute("SELECT COALESCE(SUM(amount),0) FROM savings WHERE user_id = ? AND type = 'withdraw'", (user["id"],)).fetchone()[0]
    try:
        balance = float(deposits) - float(withdrawals)
    except Exception:
        balance = 0.0
    if amount > balance:
        conn.close()
        return templates.TemplateResponse("client/savings.html", {"request": request, "user": user, "error": "Insufficient balance"})
    conn.execute("INSERT INTO savings (user_id, type, amount) VALUES (?, 'withdraw', ?)", (user["id"], amount))
    conn.commit()
    conn.close()
    return RedirectResponse("/client/savings", status_code=303)


@router.get("/client/loans", response_class=HTMLResponse)
def view_loans(request: Request, user: dict = Depends(get_current_user)):
    conn = get_db()
    loans_raw = conn.execute("SELECT id, amount, term, status, timestamp FROM loans WHERE user_id = ? ORDER BY timestamp DESC", (user["id"],)).fetchall()
    loans = []
    for l in loans_raw:
        repaid = conn.execute("SELECT COALESCE(SUM(amount),0) FROM loan_payments WHERE loan_id = ?", (l["id"],)).fetchone()[0] or 0.0
        try:
            outstanding = float(l["amount"]) - float(repaid)
        except Exception:
            outstanding = 0.0
        loans.append({
            "id": l["id"],
            "amount": l["amount"],
            "term": l["term"],
            "status": l["status"],
            "timestamp": l["timestamp"],
            "repaid": float(repaid),
            "outstanding": max(0.0, outstanding)
        })
    conn.close()
    return templates.TemplateResponse("client/loans.html", {"request": request, "user": user, "loans": loans})


@router.post("/client/loan/request")
def request_loan(request: Request, amount: float = Form(...), term: int = Form(default=12), user: dict = Depends(get_current_user)):
    if amount <= 0:
        return templates.TemplateResponse("client/loans.html", {"request": request, "user": user, "error": "Loan amount must be positive"})
    conn = get_db()
    conn.execute("INSERT INTO loans (user_id, amount, term, status) VALUES (?, ?, ?, 'pending')", (user["id"], amount, term))
    conn.commit()
    conn.close()
    return RedirectResponse("/client/loans", status_code=303)


@router.post("/client/loan/repay")
def repay_loan(request: Request, loan_id: int = Form(...), amount: float = Form(...), user: dict = Depends(get_current_user)):
    if amount <= 0:
        return templates.TemplateResponse("client/loans.html", {"request": request, "user": user, "error": "Payment must be positive"})
    conn = get_db()
    loan = conn.execute("SELECT id, user_id, amount, status FROM loans WHERE id = ?", (loan_id,)).fetchone()
    if not loan:
        conn.close()
        return templates.TemplateResponse("client/loans.html", {"request": request, "user": user, "error": "Loan not found"})
    if loan["user_id"] != user["id"]:
        conn.close()
        raise HTTPException(status_code=403, detail="Not authorized to repay this loan")
    # Allow repayments only for approved or partially paid loans
    if loan["status"] not in ("approved", "partial"):
        conn.close()
        return templates.TemplateResponse("client/loans.html", {"request": request, "user": user, "error": "Loan is not open for repayment"})
    repaid = conn.execute("SELECT COALESCE(SUM(amount),0) FROM loan_payments WHERE loan_id = ?", (loan_id,)).fetchone()[0] or 0.0
    try:
        outstanding = float(loan["amount"]) - float(repaid)
    except Exception:
        outstanding = 0.0
    if outstanding <= 0:
        conn.close()
        return RedirectResponse("/client/loans", status_code=303)
    pay_amount = float(amount)
    # prevent overpayment: cap to outstanding
    if pay_amount > outstanding:
        pay_amount = outstanding

    conn.execute("INSERT INTO loan_payments (loan_id, user_id, amount) VALUES (?, ?, ?)", (loan_id, user["id"], pay_amount))
    # update loan status if fully repaid
    new_repaid = conn.execute("SELECT COALESCE(SUM(amount),0) FROM loan_payments WHERE loan_id = ?", (loan_id,)).fetchone()[0] or 0.0
    try:
        new_outstanding = float(loan["amount"]) - float(new_repaid)
    except Exception:
        new_outstanding = 0.0
    if new_outstanding <= 0.001:
        conn.execute("UPDATE loans SET status = 'paid' WHERE id = ?", (loan_id,))
    else:
        conn.execute("UPDATE loans SET status = 'partial' WHERE id = ?", (loan_id,))

    # log payment
    try:
        conn.execute("INSERT INTO logs (user_id, action) VALUES (?, ?)", (user["id"], f"loan_payment:{loan_id}:{pay_amount}"))
    except Exception:
        pass

    conn.commit()
    conn.close()
    return RedirectResponse("/client/loans", status_code=303)
