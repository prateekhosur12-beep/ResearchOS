"""Lab 10: Assignment 2 -- A Safe Auto-Remediation Path
Implements a bifurcated remediation path:
1. Low-risk action ('restart_single_pod') for WARNING-level transient memory leak -> AUTO-EXECUTED
2. High-risk action ('rollback') for ALARM/Degraded failure -> REQUIRES HUMAN APPROVAL
"""

def risk_level(action):
    HIGH_RISK = {"rollback", "scale_cluster", "truncate_db"}
    LOW_RISK = {"restart_single_pod", "flush_local_cache", "send_slack_alert"}
    if action in HIGH_RISK:
        return "high"
    if action in LOW_RISK:
        return "low"
    return "unknown"

def remediate_incident(scenario):
    action = scenario["proposed_action"]
    risk = risk_level(action)

    if risk == "low":
        # Safe auto-remediation path
        return {
            "scenario": scenario["name"],
            "severity": scenario["severity"],
            "action": action,
            "risk": risk,
            "auto_executed": True,
            "execution_status": f"SUCCESS: '{action}' executed automatically without human intervention."
        }
    else:
        # High risk requires human approval gate
        return {
            "scenario": scenario["name"],
            "severity": scenario["severity"],
            "action": action,
            "risk": risk,
            "auto_executed": False,
            "execution_status": "BLOCKED: Awaiting mandatory human signoff before execution."
        }

if __name__ == "__main__":
    # Case 1: Low-risk transient warning
    sc1 = {"name": "Transient Pod Memory Spike", "severity": "WARNING", "proposed_action": "restart_single_pod"}
    res1 = remediate_incident(sc1)
    print("=== Case 1: Low-Risk Action ===")
    print(res1)
    assert res1["auto_executed"] is True, "Low risk action must auto-execute!"

    # Case 2: High-risk rollback
    sc2 = {"name": "Production NullPointerException", "severity": "DEGRADED", "proposed_action": "rollback"}
    res2 = remediate_incident(sc2)
    print("\n=== Case 2: High-Risk Action ===")
    print(res2)
    assert res2["auto_executed"] is False, "High risk action must NEVER auto-execute!"
    print("\nConfirmed: Policy cleanly separates safe auto-remediation from gated operations.")
