"""Lab 14: Assignment 1 -- Add a Second Reusable Skill: Password Reset Guidance
Adds password_reset_skill alongside triage_skill.
The node graph inspects the issue text and dynamically routes to password_reset_skill
or triage_skill, demonstrating multi-skill orchestration.
"""

def tool_check_account_status(user_id):
    accounts = {"alice123": "active", "bob_locked": "locked"}
    return accounts.get(user_id, "unknown")

def triage_skill(issue_text):
    return {"resolution": "general_ticket", "details": f"Ticket logged for: {issue_text}"}

def password_reset_skill(issue_text, user_id):
    """Reusable skill for credential handling with strict verification constraints."""
    status = tool_check_account_status(user_id)
    if status == "locked":
        return {
            "resolution": "identity_verification_required",
            "instructions": "Your account is locked due to security policy. Please present physical ID at the Registrar's desk."
        }
    return {
        "resolution": "self_service_link",
        "instructions": "A secure password reset link has been dispatched to your primary university email on file."
    }

def routed_helpdesk_agent(user_id, issue_text):
    text_lower = issue_text.lower()
    
    # Intent classification for routing
    auth_keywords = ["password", "login", "reset", "forgot password", "unlock", "locked", "sign in"]
    if any(k in text_lower for k in auth_keywords):
        skill_used = "password_reset_skill"
        result = password_reset_skill(issue_text, user_id)
    else:
        skill_used = "triage_skill"
        result = triage_skill(issue_text)

    return {
        "user": user_id,
        "input_issue": issue_text,
        "routed_skill": skill_used,
        "result": result
    }

if __name__ == "__main__":
    print("=== Case 1: Password Query Routes to password_reset_skill ===")
    r1 = routed_helpdesk_agent("alice123", "I forgot my portal password")
    print(r1)
    assert r1["routed_skill"] == "password_reset_skill"

    print("\n=== Case 2: General Issue Routes to triage_skill ===")
    r2 = routed_helpdesk_agent("bob456", "The library printer is out of paper")
    print(r2)
    assert r2["routed_skill"] == "triage_skill"

    print("\n=== Case 3: Locked Account Constraint Triggered ===")
    r3 = routed_helpdesk_agent("bob_locked", "My account is locked and I cannot sign in")
    print(r3)
    assert r3["result"]["resolution"] == "identity_verification_required"
