"""Lab 7: Assignment 2 -- Add a Retry Limit to the Builder Node
Modifies the graph execution to allow the builder node exactly 1 retry upon failure.
Demonstrates:
  (a) Builder fails once, retries, and succeeds.
  (b) Builder fails twice and escalates to human instead of retrying a third time.
"""

def requirement_node(state):
    state["requirements"] = ["login", "events"]
    return state

def builder_step(state, attempt_number):
    """Simulates builder behavior across attempts."""
    fail_attempts = state.get("fail_attempts", 0)
    if attempt_number <= fail_attempts:
        state["build_ok"] = False
        state["error"] = f"Compilation failed on attempt {attempt_number}"
    else:
        state["build_ok"] = True
        state["code"] = "event_app.py"
        state["error"] = None
    return state

def run_graph_with_builder_retry(fail_attempts):
    state = {"fail_attempts": fail_attempts, "requirements": ["login", "events"]}
    trace = []
    
    # Builder execution with max 1 retry (total 2 attempts)
    max_retries = 1
    attempt = 1
    build_successful = False

    while attempt <= 1 + max_retries:
        state = builder_step(state, attempt)
        trace.append({
            "node": "builder",
            "attempt": attempt,
            "success": state["build_ok"],
            "error": state.get("error")
        })
        if state["build_ok"]:
            build_successful = True
            break
        attempt += 1

    if not build_successful:
        trace.append({
            "node": "builder",
            "action": "ESCALATE_TO_HUMAN",
            "reason": f"Builder failed {attempt-1} consecutive times (exceeded max_retries={max_retries})."
        })
    else:
        trace.append({
            "node": "tester",
            "action": "PROCEED_TO_TESTS",
            "status": "ready"
        })

    return trace

if __name__ == "__main__":
    print("=== Scenario A: Fails Once, Retries, and Succeeds ===")
    trace_a = run_graph_with_builder_retry(fail_attempts=1)
    for t in trace_a:
        print(t)

    print("\n=== Scenario B: Fails Twice, Exceeds Limit, Escalates to Human ===")
    trace_b = run_graph_with_builder_retry(fail_attempts=2)
    for t in trace_b:
        print(t)
