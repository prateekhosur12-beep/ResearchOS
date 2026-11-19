"""Lab 8: Assignment 2 -- Distributed Critique
Replaces central critique() with decentralized peer critiques:
Each agent inspects the merged draft against its own domain invariants and returns objections.
The conflict log attributes each objection to the specific raising agent.
"""

def budget_critique(draft):
    objections = []
    total_cost = draft.get("venue_cost", 0) + draft.get("swag_cost", 0)
    cap = draft.get("budget_cap", 0)
    if total_cost > cap:
        objections.append({
            "raised_by": "budget_agent",
            "severity": "CRITICAL",
            "objection": f"Combined spending {total_cost} exceeds hard budget cap {cap}."
        })
    return objections

def logistics_critique(draft):
    objections = []
    if draft.get("expected_attendees", 0) > draft.get("venue_capacity", 0):
        objections.append({
            "raised_by": "logistics_agent",
            "severity": "HIGH",
            "objection": f"Expected attendees ({draft.get('expected_attendees')}) exceeds venue capacity ({draft.get('venue_capacity')})."
        })
    return objections

def judging_critique(draft):
    objections = []
    if draft.get("duration_hours", 0) < 12:
        objections.append({
            "raised_by": "judging_agent",
            "severity": "MEDIUM",
            "objection": "Hackathon duration under 12 hours is too short for meaningful project judging."
        })
    return objections

CRITIQUE_ROLES = [budget_critique, logistics_critique, judging_critique]

def run_distributed_critique(draft):
    all_objections = []
    for critique_fn in CRITIQUE_ROLES:
        objections = critique_fn(draft)
        all_objections.extend(objections)
    return all_objections

if __name__ == "__main__":
    # Draft with two distinct domain violations
    draft_plan = {
        "venue": "Lab B",
        "venue_cost": 20000,
        "swag_cost": 15000,
        "budget_cap": 30000,          # Budget violation: 35000 > 30000
        "expected_attendees": 150,
        "venue_capacity": 100,         # Logistics violation: 150 > 100
        "duration_hours": 24,          # Judging invariant satisfied
    }

    print("=== Running Distributed Critique Across Swarm Roles ===")
    objections = run_distributed_critique(draft_plan)
    
    for obj in objections:
        print(f"[{obj['severity']}] Raised By: {obj['raised_by']}")
        print(f"  Details: {obj['objection']}")

    assert len(objections) >= 2, "Expected objections from both budget and logistics!"
    print("\nConfirmed: Multiple roles independently raised domain-specific objections.")
