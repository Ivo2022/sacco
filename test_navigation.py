"""
Test script to verify navigation rendering for different user roles
"""
import requests
from bs4 import BeautifulSoup

BASE_URL = "http://127.0.0.1:8000"

def check_navbar_structure(html_content, role):
    """Check if navbar is present in the HTML"""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Check for navbar
    navbar = soup.find('nav', class_='navbar')
    has_navbar = navbar is not None
    
    # Check for sidebar
    sidebar = soup.find('div', class_='sidebar-desktop')
    has_sidebar = sidebar is not None
    
    # Check for offcanvas (mobile sidebar)
    offcanvas = soup.find('div', class_='offcanvas')
    has_offcanvas = offcanvas is not None
    
    # Check for mobile menu button
    mobile_button = soup.find('button', attrs={'data-bs-target': '#sidebarMenu'})
    has_mobile_button = mobile_button is not None
    
    # Check content-area-with-sidebar class
    content_area = soup.find('div', class_='content-area')
    has_sidebar_margin = content_area and 'content-area-with-sidebar' in content_area.get('class', [])
    
    return {
        'role': role,
        'has_navbar': has_navbar,
        'has_sidebar': has_sidebar,
        'has_offcanvas': has_offcanvas,
        'has_mobile_button': has_mobile_button,
        'has_sidebar_margin': has_sidebar_margin,
    }

def test_unauthenticated_page():
    """Test the index page without authentication"""
    print("\n" + "="*70)
    print("Testing UNAUTHENTICATED PAGE (no login)")
    print("="*70)
    
    response = requests.get(f"{BASE_URL}/", allow_redirects=True)
    if response.status_code == 200:
        result = check_navbar_structure(response.text, "UNAUTHENTICATED")
        print(f"✓ Page loaded successfully")
        print(f"  - Navbar present: {result['has_navbar']}")
        print(f"  - Sidebar desktop: {result['has_sidebar']} (should be False)")
        print(f"  - Offcanvas mobile: {result['has_offcanvas']} (should be False)")
        print(f"  - Mobile menu button: {result['has_mobile_button']} (should be False)")
        print(f"  - Content has sidebar margin: {result['has_sidebar_margin']} (should be False)")
        
        # Verify expectations
        assert result['has_navbar'] == True, "Navbar should be present for all users"
        assert result['has_sidebar'] == False, "Sidebar should NOT be present for unauthenticated users"
        assert result['has_offcanvas'] == False, "Offcanvas should NOT be present for unauthenticated users"
        assert result['has_mobile_button'] == False, "Mobile button should NOT be present for unauthenticated users"
        print("✓ All checks passed for unauthenticated page")
        return True
    else:
        print(f"✗ Failed to load page: {response.status_code}")
        return False

if __name__ == "__main__":
    print("\n" + "="*70)
    print("NAVIGATION RENDERING TEST SUITE")
    print("="*70)
    
    success = test_unauthenticated_page()
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    if success:
        print("""
✓ UNAUTHENTICATED PAGE: All checks passed!
  - Navbar renders correctly
  - No sidebar for unauthenticated users
  - No mobile menu button for unauthenticated users

NOTE: To fully test authenticated navigation:
1. Create test accounts (Manager, Member, Accountant, Credit Officer)
2. Log in with each role
3. Verify:
   - MANAGER: sidebar + offcanvas + navbar
   - OTHER roles: navbar only
""")
    else:
        print("✗ TEST FAILED - Please check server logs")
