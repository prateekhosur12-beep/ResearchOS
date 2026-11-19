"""Lab 8: Assignment 1 -- Add a Fifth Role: Marketing
Adds marketing_agent proposing publicity costs.
Extends critique() to check total cost (venue + marketing) against total budget cap,
logging and resolving multi-agent financial conflicts using budget_over_preference.
"""
from concurrent.futures import ThreadPoolExecutor

def research_agent(goal):
    return {"role": "research", "output": "Past events favored a 24-hour format with themed tracks."}

def logistics_agent(goal):
    return {"role": "logistics", "output": {"venue": "Grand Hall", "venue_cost": 22000, "date": "Saturday"}}

def budget_agent(goal):
    return {"role": "budget", "output": {"total_cap": 30000}}

def judging_agent(goal):
    return {"role": "judging", "output": "Judge on innovation, technical depth, and demo quality."}

def marketing_agent(goal):
    """Fifth role: proposes multi-channel campus publicity campaign."""
    return {"role": "marketing", "output": {"campaign": "Sponsored ads & banners", "marketing_cost": 12000}}

ROLES_WITH_MARKETING = {
    "research": research_agent,
    "logistics": logistics_agent,
    "budget": budget_agent,
    "judging": judging_agent,
    "marketing": marketing_agent,
}

def run_swarm():
    with ThreadPoolExecutor(max_workers=len(ROLES_WITH_MARKETING)) as pool:
        futures = {name: pool.submit(fn, "Plan Hackathon") for name, fn in ROLES_WITH_MARKETING.items()}
        return {name: f.result() for name, f in futures.items()}

def merge(outputs):
    return {
        "venue": outputs["logistics"]["output"]["venue"],
        "venue_cost": outputs["logistics"]["output"]["venue_cost"],
        "marketing_cost": outputs["marketing"]["output"]["marketing_cost"],
        "total_requested": outputs["logistics"]["output"]["venue_cost"] + outputs["marketing"]["output"]["marketing_cost"],
        "budget_cap": outputs["budget"]["output"]["total_cap"],
    }

def critique(draft):
    conflicts = []
    total = draft["total_requested"]
    cap = draft["budget_cap"]
    if total > cap:
        conflicts.append({
            "conflict": "total_cost_exceeds_budget_cap",
            "roles_involved": ["logistics", "marketing", "budget"],
            "total_requested": total,
            "budget_cap": cap,
            "overage": total - cap
        })
    return conflicts

def resolve(conflict):
    if conflict["conflict"] == "total_cost_exceeds_budget_cap":
        # Rule: Budget cap is rigid. Pro-rate marketing budget or cap it to remainder.
        return {
            "rule_applied": "budget_over_preference",
            "resolution": (f"Cap marketing at {conflict['budget_cap'] - 22000} (reduced from 12000) "
                           f"so combined expenses equal budget cap of {conflict['budget_cap']}.")
        }
    return {"resolution": "No action"}

if __name__ == "__main__":
    outputs = run_swarm()
    draft = merge(outputs)
    print("=== 5-Role Swarm Draft ===")
    print(draft)

    conflicts = critique(draft)
    print("\n=== Critique Results ===")
    conflict_log = []
    for c in conflicts:
        res = resolve(c)
        conflict_log.append({**c, **res})
        print(f"Conflict: {c['conflict']} (Overage: {c['overage']})")
        print(f"Resolution: {res['resolution']}")

    print("\n=== Final Swarm Conflict Report Artifact ===")
    for entry in conflict_log:
        print(entry)
