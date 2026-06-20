import sys
import os
from pathlib import Path

# Add the project root to sys.path so we can run this file directly if needed
sys.path.append(str(Path(__file__).resolve().parent.parent))

# =====================================================================
# --- CORE APP PRIVILEGE CONFIGURATIONS (Shared Security Source) ---
# =====================================================================

# Roles allowed to access the SQL analytical retrieval layer
ALLOWED_SQL_ROLES = {"billing_executive", "admin"}

# Document collection directory permissions mapped by user group
COLLECTION_PERMISSIONS = {
    "admin": ["general", "clinical", "nursing", "billing", "equipment"],
    "billing_executive": ["general", "billing"],
    "doctor": ["general", "clinical"],
    "nurse": ["general", "nursing"],
    "technician": ["general", "equipment"]
}

# Application mock credential database registry
USER_DATABASE = {
    "admin_user": {"password": "password123", "role": "admin"},
    "billing_user": {"password": "password123", "role": "billing_executive"},
    "doctor_user": {"password": "password123", "role": "doctor"},
    "nurse_user": {"password": "password123", "role": "nurse"},
    "tech_user": {"password": "password123", "role": "technician"}
}

# =====================================================================
# --- AUDIT COMPONENT EXECUTION LAYER (Component 3 Evaluator) ---
# =====================================================================
# Import your operational secure search engine directly from retrieval.hybrid_search
from retrieval.hybrid_search import execute_secure_hybrid_search

def run_automated_security_audit():
    """
    Component 3: Automated Security Evaluator Tool
    Runs deterministic multi-role cross-validation checks to audit the RBAC security.
    """
    print("=" * 60)
    print(" STARTING COMPONENT 3: AUTOMATED SECURITY EVALUATION ")
    print("=" * 60)
    
    test_query = "What is the correct IV cannula size for a paediatric patient under 5kg?"
    
    # Define our test matrix: (User Role, Expected Access Allowed True/False)
    security_test_matrix = [
        ("nurse", True),         # Authorized role (should find clinical docs)
        ("doctor", True),        # Authorized role (should find clinical docs)
        ("admin", True),         # Authorized master role (should find clinical docs)
        ("technician", False),   # Unauthorized role for ICU procedures (should be blocked)
        ("guest_user", False),   # Completely unprivileged role (should be blocked)
    ]
    
    failed_tests = 0
    
    for role, expected_allowed in security_test_matrix:
        print(f"\n[AUDIT] Auditing Query Request under Role Identity: '{role}'...")
        try:
            # Query the vector engine directly using the role parameter constraint
            retrieved_chunks = execute_secure_hybrid_search(
                user_query=test_query,
                user_role=role, top_k=3
            )
            
            access_granted = len(retrieved_chunks) > 0
            
            # Cross-verify database state against expected security thresholds
            if access_granted == expected_allowed:
                print(f" -> STATUS: PASS \u2705 (Access Granted: {access_granted}, Expected: {expected_allowed})")
                if access_granted:
                    print(f" -> Verified Allowed Source: {retrieved_chunks[0].metadata.get('source')}")
            else:
                print(f" -> STATUS: FAIL \u274c (Access Granted: {access_granted}, Expected: {expected_allowed})")
                failed_tests += 1
                
        except Exception as e:
            print(f" -> STATUS: CRASHED \ud83d\udca5 (Error: {e})")
            failed_tests += 1
            
    print("\n" + "=" * 60)
    print(" AUDIT SUMMARY ")
    print("=" * 60)
    if failed_tests == 0:
        print(" SUCCESS: All RBAC security vectors passed validation gates cleanly! \ud83c\udf89")
    else:
        print(f" WARNING: Security boundary breach identified. {failed_tests} tests failed.")
    print("=" * 60)

if __name__ == "__main__":
    run_automated_security_audit()
