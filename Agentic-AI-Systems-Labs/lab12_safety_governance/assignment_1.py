"""Lab 12: Assignment 1 -- A Cost-Category Control
Adds cost estimation and financial budget gates.
Any remediation proposal whose estimated cost exceeds $500 is REJECTED
unless the finance_approved flag is explicitly True.
Includes an adversarial test attempting to bypass the check by omitting cost.
"""

class CostGatedChangeAgent:
    COST_THRESHOLD_USD = 500.0

    def propose_action_with_cost(self, action_name, estimated_cost_usd, rollback_plan, finance_approved=False):
        # Adversarial check: cost MUST be specified
        if estimated_cost_usd is None or not isinstance(estimated_cost_usd, (int, float)):
            return {
                "approved_for_request": False,
                "reason": "REJECTED: Cost estimate missing or invalid. Cost opacity is prohibited."
            }

        if estimated_cost_usd > self.COST_THRESHOLD_USD and not finance_approved:
            return {
                "approved_for_request": False,
                "reason": (f"REJECTED: Estimated cost (${estimated_cost_usd}) exceeds budget "
                           f"threshold (${self.COST_THRESHOLD_USD}) and lacks required finance_approved flag.")
            }

        return {
            "approved_for_request": True,
            "action": action_name,
            "cost": estimated_cost_usd,
            "rollback_plan": rollback_plan,
            "status": "FORWARDED_TO_OPS_APPROVAL"
        }

if __name__ == "__main__":
    agent = CostGatedChangeAgent()

    print("=== Case 1: Expensive Action ($1200) without Finance Approval ===")
    r1 = agent.propose_action_with_cost("Scale Cluster x10", estimated_cost_usd=1200.0,
                                       rollback_plan="Scale down", finance_approved=False)
    print(r1)
    assert r1["approved_for_request"] is False

    print("\n=== Case 2: Expensive Action ($1200) WITH Finance Approval ===")
    r2 = agent.propose_action_with_cost("Scale Cluster x10", estimated_cost_usd=1200.0,
                                       rollback_plan="Scale down", finance_approved=True)
    print(r2)
    assert r2["approved_for_request"] is True

    print("\n=== Adversarial Case 3: Omitting Cost Entirely (Bypass Attempt) ===")
    r3 = agent.propose_action_with_cost("Spin up GPU Fleet", estimated_cost_usd=None,
                                       rollback_plan="Terminate pods", finance_approved=False)
    print(r3)
    assert r3["approved_for_request"] is False
    print("\nConfirmed: Cost control and adversarial evasion defenses verified.")
