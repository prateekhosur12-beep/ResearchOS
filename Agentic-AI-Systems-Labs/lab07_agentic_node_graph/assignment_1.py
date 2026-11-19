"""Lab 7: Assignment 1 -- Add a Security-Scan Node
Inserts a 'security_scan' node between 'builder' and 'tester'.
Node checks for vulnerability-free code before allowing progression to testing.
Simulates both a success run and a failure run where the security scan flags an issue.
"""

class Node:
    def __init__(self, name, owner, success_fn, on_success, on_fail):
        self.name = name
        self.owner = owner
        self.success_fn = success_fn
        self.on_success = on_success
        self.on_fail = on_fail

def requirement_node(state):
    state["requirements"] = ["user login", "event listing", "RSVP button"]
    return state

def planner_node(state):
    state["tasks"] = {req: f"task_for({req})" for req in state["requirements"]}
    return state

def builder_node(state):
    state["build_ok"] = True
    state["code"] = "app.py generated"
    return state

def security_scan_node(state):
    """Scan code for hardcoded secrets, SQL injection, and OWASP top 10."""
    if state.get("force_security_fail"):
        state["security_clean"] = False
        state["vulnerabilities_found"] = ["Hardcoded API key detected on line 12"]
        return state
    state["security_clean"] = True
    state["vulnerabilities_found"] = []
    return state

def tester_node(state):
    state["tests_passed"] = state.get("security_clean", False)
    return state

def reviewer_node(state):
    state["review_clean"] = state.get("tests_passed", False)
    return state

def human_gate_node(state):
    state["human_signoff"] = state.get("review_clean", False)
    return state

GRAPH_WITH_SECURITY = [
    Node("requirement", "requirement_agent",
         lambda s: len(s.get("requirements", [])) >= 3,
         requirement_node, "escalate_to_human"),
    Node("planner", "planner_agent",
         lambda s: all(r in s.get("tasks", {}) for r in s.get("requirements", [])),
         planner_node, "return_to_requirement"),
    Node("builder", "builder_agent",
         lambda s: s.get("build_ok", False),
         builder_node, "retry_build"),
    # Newly inserted security-scan node
    Node("security_scan", "security_agent",
         lambda s: s.get("security_clean", False),
         security_scan_node,
         "quarantine_artifact_and_open_security_patch_ticket"),
    Node("tester", "tester_agent",
         lambda s: s.get("tests_passed", False),
         tester_node, "route_back_to_builder"),
    Node("reviewer", "reviewer_agent",
         lambda s: s.get("review_clean", False),
         reviewer_node, "route_back_to_builder"),
    Node("human_gate", "human",
         lambda s: s.get("human_signoff", False),
         human_gate_node, "return_to_planner"),
]

def simulate_pipeline(force_security_fail=False):
    state = {"force_security_fail": force_security_fail}
    trace = []
    for node in GRAPH_WITH_SECURITY:
        state = node.on_success(state)
        ok = node.success_fn(state)
        trace.append({"node": node.name, "owner": node.owner, "success": ok,
                      "state_after": {k: v for k, v in state.items() if k != "force_security_fail"}})
        if not ok:
            trace.append({"node": node.name, "failure_behavior_triggered": node.on_fail})
            break
    return trace

if __name__ == "__main__":
    print("=== 1. SUCCESS PATH (Security Scan Passes) ===")
    for step in simulate_pipeline(force_security_fail=False):
        print(f"  Node: {step.get('node')} | Success: {step.get('success', False)}")

    print("\n=== 2. FAILURE PATH (Security Scan Catches Vulnerability) ===")
    for step in simulate_pipeline(force_security_fail=True):
        print(f"  {step}")
