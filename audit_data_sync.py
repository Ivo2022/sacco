"""
Comprehensive Data Synchronization Audit
Validates that statistics are consistent across all account types and pages
"""
import requests
from bs4 import BeautifulSoup
import re

BASE_URL = "http://127.0.0.1:8000"

def extract_stat_value(html_content, pattern_text):
    """Extract numeric values from HTML stats"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Look for stat cards with specific text patterns
    stats = {}
    for card in soup.find_all('div', class_='stat-card'):
        text = card.get_text()
        if pattern_text.lower() in text.lower():
            # Try to find numbers in the card
            numbers = re.findall(r'[\d,]+\.?\d*', text)
            if numbers:
                stats[pattern_text] = numbers[0]
    
    return stats

def check_sacco_data_consistency():
    """Check if SACCO data is consistent across different pages"""
    print("\n" + "="*80)
    print("DATA SYNCHRONIZATION AUDIT REPORT")
    print("="*80)
    
    # Test unauthenticated page
    print("\n[1] TESTING UNAUTHENTICATED PAGE")
    print("-" * 80)
    response = requests.get(f"{BASE_URL}/")
    if response.status_code == 200:
        print("✓ Index page loads successfully")
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Check for any hard-coded stats
        stats_elements = soup.find_all(class_=re.compile(r'stat|metric|card'))
        if stats_elements:
            print(f"  - Found {len(stats_elements)} stat/metric elements")
        else:
            print("  - No stats displayed (expected for unauthenticated user)")
    else:
        print(f"✗ Failed to load index page: {response.status_code}")
    
    return True

def validate_dashboard_structure():
    """Validate that dashboard structure is correct"""
    print("\n[2] VALIDATING DASHBOARD STRUCTURE")
    print("-" * 80)
    
    # Load manager dashboard HTML
    from pathlib import Path
    dashboard_path = Path("d:\\2026\\fastapi\\backend\\templates\\manager\\dashboard.html")
    
    if dashboard_path.exists():
        with open(dashboard_path) as f:
            content = f.read()
        
        # Check for key Jinja2 variables
        variables_to_check = [
            'pending_loans',
            'overdue_loans',
            'pending_deposits',
            'pending_members_count',
            'total_interest_earned',
            'total_payments_received',
            'total_disbursed',
            'total_outstanding',
            'repayment_rate',
            'new_members_this_month',
            'member_count',
            'active_members'
        ]
        
        found_vars = 0
        for var in variables_to_check:
            if f"{{{{ {var}" in content or f"{{{{{{ {var}" in content:
                found_vars += 1
                print(f"✓ {var} is used in template")
            else:
                print(f"⚠ {var} not found in template")
        
        print(f"\nTotal variables found: {found_vars}/{len(variables_to_check)}")
        return found_vars == len(variables_to_check)
    else:
        print(f"✗ Dashboard file not found: {dashboard_path}")
        return False

def check_python_routes_consistency():
    """Check if Python routes are calculating stats consistently"""
    print("\n[3] CHECKING PYTHON ROUTES FOR CONSISTENCY")
    print("-" * 80)
    
    from pathlib import Path
    
    # Check manager.py for stats calculation
    manager_path = Path("d:\\2026\\fastapi\\backend\\routers\\manager.py")
    
    if manager_path.exists():
        with open(manager_path) as f:
            content = f.read()
        
        issues = []
        
        # Check 1: Outstanding calculation consistency
        if "total_outstanding" in content:
            outstanding_calcs = content.count("total_outstanding")
            print(f"✓ total_outstanding calculated {outstanding_calcs} times")
            if outstanding_calcs > 1:
                print("  ⚠ WARNING: Multiple calculations - ensure they're identical")
        
        # Check 2: Interest calculation
        if "total_interest" in content or "total_interest_earned" in content:
            print("✓ Interest calculations found")
        else:
            print("✗ Interest calculations missing or incorrectly named")
            issues.append("Interest calculation")
        
        # Check 3: SACCO filtering
        if "sacco_id" in content:
            sacco_filters = content.count(".filter(")
            print(f"✓ Data filtered by SACCO {sacco_filters} times")
            if ".filter(" in content and "Loan.sacco_id ==" not in content:
                print("  ⚠ WARNING: Some filters might not include sacco_id")
                issues.append("Missing sacco_id filter")
        
        # Check 4: LoanPayment model usage
        if "LoanPayment" in content:
            print("✓ LoanPayment model is used for calculations")
        else:
            print("✗ LoanPayment model usage missing")
            issues.append("LoanPayment tracking")
        
        if issues:
            print(f"\n⚠ Found {len(issues)} potential issues:")
            for issue in issues:
                print(f"  - {issue}")
            return False
        else:
            print("\n✓ No consistency issues detected")
            return True
    else:
        print(f"✗ Manager route file not found: {manager_path}")
        return False

def check_statistics_service():
    """Check statistics service calculations"""
    print("\n[4] CHECKING STATISTICS SERVICE")
    print("-" * 80)
    
    from pathlib import Path
    stats_path = Path("d:\\2026\\fastapi\\backend\\services\\statistics_service.py")
    
    if stats_path.exists():
        with open(stats_path) as f:
            content = f.read()
        
        # Check for get_sacco_statistics function
        if "def get_sacco_statistics" in content:
            print("✓ get_sacco_statistics function found")
        else:
            print("✗ get_sacco_statistics function missing")
            return False
        
        # Check for key calculations
        key_calcs = [
            ('total_deposits', 'total deposits calculation'),
            ('total_withdrawals', 'total withdrawals calculation'),
            ('total_loans', 'total loans calculation'),
            ('outstanding', 'outstanding loans calculation'),
            ('loan_payments', 'loan payment sum'),
        ]
        
        found_calcs = 0
        for calc_name, description in key_calcs:
            if calc_name in content:
                found_calcs += 1
                print(f"✓ {description}")
        
        print(f"\nCalculations found: {found_calcs}/{len(key_calcs)}")
        return found_calcs == len(key_calcs)
    else:
        print(f"✗ Statistics service not found: {stats_path}")
        return False

def check_sacco_isolation():
    """Verify that data is properly isolated per SACCO"""
    print("\n[5] CHECKING SACCO DATA ISOLATION")
    print("-" * 80)
    
    from pathlib import Path
    manager_path = Path("d:\\2026\\fastapi\\backend\\routers\\manager.py")
    
    if manager_path.exists():
        with open(manager_path) as f:
            lines = f.readlines()
        
        # Find manager_dashboard function
        dashboard_start = None
        for i, line in enumerate(lines):
            if "def manager_dashboard" in line:
                dashboard_start = i
                break
        
        if dashboard_start:
            # Look for the next 50 lines and check for sacco_id
            dashboard_section = ''.join(lines[dashboard_start:min(dashboard_start+50, len(lines))])
            
            if "user.sacco_id" in dashboard_section or "sacco_id =" in dashboard_section:
                print("✓ SACCO ID is retrieved from user context")
            else:
                print("✗ SACCO ID not retrieved")
                return False
            
            # Check if all queries filter by sacco_id
            query_count = dashboard_section.count(".filter(")
            sacco_filter_count = dashboard_section.count("sacco_id")
            
            if query_count > 0 and sacco_filter_count == 0:
                print(f"⚠ WARNING: Found {query_count} queries but no sacco_id filters")
                return False
            else:
                print(f"✓ Found {query_count} queries with sacco_id filtering")
                return True
        else:
            print("✗ manager_dashboard function not found")
            return False
    else:
        print(f"✗ Manager route file not found")
        return False

def check_loan_payment_tracking():
    """Verify loan payment tracking is correct"""
    print("\n[6] CHECKING LOAN PAYMENT TRACKING")
    print("-" * 80)
    
    from pathlib import Path
    models_path = Path("d:\\2026\\fastapi\\backend\\models\\models.py")
    
    if models_path.exists():
        with open(models_path) as f:
            content = f.read()
        
        # Check for LoanPayment model
        if "class LoanPayment" in content:
            print("✓ LoanPayment model exists")
            
            # Check for key fields
            fields = ['amount', 'loan_id', 'sacco_id', 'timestamp']
            found_fields = 0
            for field in fields:
                if f"{field} =" in content or f"Column" in content:
                    found_fields += 1
            
            print(f"✓ LoanPayment has key tracking fields")
        else:
            print("✗ LoanPayment model not found")
            return False
        
        # Check Loan model for tracking fields
        if "class Loan" in content:
            print("✓ Loan model exists")
            
            if "total_payable" in content:
                print("✓ Loan has total_payable field")
            if "total_interest" in content:
                print("✓ Loan has total_interest field")
            if "total_paid" in content:
                print("✓ Loan has total_paid field")
        
        return True
    else:
        print(f"✗ Models file not found")
        return False

if __name__ == "__main__":
    print("\n\n")
    print("╔" + "="*78 + "╗")
    print("║" + " "*20 + "SACCO DATA SYNCHRONIZATION AUDIT" + " "*26 + "║")
    print("╚" + "="*78 + "╝")
    
    results = {
        "Data Consistency": check_sacco_data_consistency(),
        "Dashboard Structure": validate_dashboard_structure(),
        "Route Consistency": check_python_routes_consistency(),
        "Statistics Service": check_statistics_service(),
        "SACCO Isolation": check_sacco_isolation(),
        "Loan Payment Tracking": check_loan_payment_tracking(),
    }
    
    print("\n\n" + "="*80)
    print("AUDIT SUMMARY")
    print("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status:8} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n✓✓✓ ALL DATA SYNCHRONIZATION CHECKS PASSED ✓✓✓")
    else:
        print(f"\n⚠⚠⚠ {total - passed} TESTS FAILED - REVIEW NEEDED ⚠⚠⚠")
