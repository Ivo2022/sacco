#!/usr/bin/env python
"""Test script to check dashboard metrics data"""

import sqlite3
import sys

def main():
    db_path = "database/cheontec.db"
    try:
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        
        print("=" * 60)
        print("DASHBOARD DATA CHECK")
        print("=" * 60)
        
        # Check loans
        print("\n1. LOAN STATISTICS")
        print("-" * 60)
        c.execute("SELECT COUNT(*) FROM loan")
        total = c.fetchone()[0]
        print(f"   Total Loans: {total}")
        
        c.execute("SELECT status, COUNT(*) FROM loan GROUP BY status")
        by_status = c.fetchall()
        for status, count in by_status:
            print(f"   - {status}: {count}")
        
        # Check if there are any active or overdue loans
        c.execute("SELECT COUNT(*) FROM loan WHERE status = 'active'")
        active = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM loan WHERE status = 'overdue'")
        overdue = c.fetchone()[0]
        
        print(f"\n   Active Loans: {active}")
        print(f"   Overdue Loans: {overdue}")
        
        # Check SACCOs
        print("\n2. SACCO INFORMATION")
        print("-" * 60)
        c.execute("SELECT COUNT(*) FROM sacco")
        sacco_total = c.fetchone()[0]
        print(f"   Total SACCOs: {sacco_total}")
        
        c.execute("SELECT id, name FROM sacco")
        saccos = c.fetchall()
        for sacco_id, sacco_name in saccos:
            c.execute("SELECT COUNT(*) FROM loan WHERE sacco_id = ? AND status = 'active'", (sacco_id,))
            active_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM loan WHERE sacco_id = ? AND status = 'overdue'", (sacco_id,))
            overdue_count = c.fetchone()[0]
            print(f"   {sacco_name} (ID: {sacco_id})")
            print(f"      - Active: {active_count}, Overdue: {overdue_count}")
        
        # Check Saving table for total_savings
        print("\n3. SAVINGS STATISTICS")
        print("-" * 60)
        c.execute("SELECT COUNT(*) FROM saving")
        savings_count = c.fetchone()[0]
        print(f"   Total Savings Records: {savings_count}")
        
        c.execute("SELECT SUM(amount) FROM saving")
        total_savings = c.fetchone()[0]
        print(f"   Total Savings Amount: {total_savings if total_savings else 0}")
        
        c.execute("SELECT sacco_id, SUM(amount) FROM saving GROUP BY sacco_id")
        savings_by_sacco = c.fetchall()
        print("\n   By SACCO:")
        for sacco_id, amount in savings_by_sacco:
            c.execute("SELECT name FROM sacco WHERE id = ?", (sacco_id,))
            sacco_name = c.fetchone()
            sacco_name = sacco_name[0] if sacco_name else "Unknown"
            print(f"      {sacco_name} (ID: {sacco_id}): {amount}")
        
        # Check Users (managers, accountants)
        print("\n4. USER INFORMATION")
        print("-" * 60)
        c.execute("SELECT role, COUNT(*) FROM user GROUP BY role")
        users_by_role = c.fetchall()
        for role, count in users_by_role:
            print(f"   {role}: {count}")
        
        c.execute("SELECT sacco_id, COUNT(*) FROM user WHERE sacco_id IS NOT NULL GROUP BY sacco_id")
        users_by_sacco = c.fetchall()
        print("\n   Users by SACCO:")
        for sacco_id, count in users_by_sacco:
            c.execute("SELECT name FROM sacco WHERE id = ?", (sacco_id,))
            sacco_name = c.fetchone()
            sacco_name = sacco_name[0] if sacco_name else "Unknown"
            print(f"      {sacco_name} (ID: {sacco_id}): {count}")
        
        # Sample loan data
        print("\n5. SAMPLE LOAN DATA")
        print("-" * 60)
        c.execute("SELECT id, sacco_id, amount, status, total_payable FROM loan LIMIT 3")
        samples = c.fetchall()
        if samples:
            for loan_id, sacco_id, amount, status, total_payable in samples:
                print(f"   Loan {loan_id}:")
                print(f"      SACCO: {sacco_id}, Amount: {amount}, Status: {status}")
                print(f"      Total Payable: {total_payable}")
        else:
            print("   No loans found")
        
        print("\n" + "=" * 60)
        conn.close()
        
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
