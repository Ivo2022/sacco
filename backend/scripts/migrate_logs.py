# scripts/migrate_logs.py
"""
Script to find and migrate create_log calls to log_user_action
Run with: python -m scripts.migrate_logs
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

def find_create_log_calls(directory: Path) -> List[Tuple[Path, int, str]]:
    """Find all create_log calls in Python files"""
    results = []
    
    for py_file in directory.rglob("*.py"):
        if "env" in str(py_file) or "venv" in str(py_file):
            continue
            
        with open(py_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        for i, line in enumerate(lines, 1):
            if 'create_log(' in line and not line.strip().startswith('#'):
                results.append((py_file, i, line.strip()))
    
    return results

def generate_migration_suggestions(calls: List[Tuple[Path, int, str]]) -> List[str]:
    """Generate migration suggestions for create_log calls"""
    suggestions = []
    
    for file_path, line_num, line in calls:
        # Parse the create_log call
        pattern = r'create_log\(\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^,]+),\s*([^)]+)\)'
        match = re.search(pattern, line)
        
        if match:
            db_param = match.group(1).strip()
            action_param = match.group(2).strip()
            user_id_param = match.group(3).strip()
            sacco_id_param = match.group(4).strip()
            details_param = match.group(5).strip()
            
            suggestion = f"""
File: {file_path}:{line_num}
Current: {line}
Suggested: log_user_action(
    db={db_param},
    user={user_id_param},  # Make sure this is a User object
    action={action_param},
    details={details_param},
    ip_address=request.client.host if available
)
"""
            suggestions.append(suggestion)
    
    return suggestions

def main():
    """Main function to find and suggest migrations"""
    project_root = Path(__file__).parent.parent
    backend_dir = project_root / "backend"
    
    print("🔍 Finding all create_log calls...")
    calls = find_create_log_calls(backend_dir)
    
    print(f"📊 Found {len(calls)} create_log calls")
    
    if calls:
        print("\n📝 Migration suggestions:")
        print("=" * 80)
        
        suggestions = generate_migration_suggestions(calls)
        for suggestion in suggestions:
            print(suggestion)
            print("-" * 80)
    
    print("\n💡 Migration Tips:")
    print("1. Replace create_log with log_user_action")
    print("2. Make sure you have the User object available")
    print("3. Add ip_address=request.client.host if you have request object")
    print("4. The sacco_id is automatically detected from the user")
    print("5. Test each migration individually")

if __name__ == "__main__":
    main()