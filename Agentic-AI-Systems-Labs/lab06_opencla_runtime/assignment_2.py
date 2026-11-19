"""Lab 6: Assignment 2 -- Escalate After Two Failures
Uses the audit log to count prior errors for a (user, skill) pair.
If a skill fails twice in one session, a third attempt immediately escalates to a human
rather than re-running the failing skill.
"""
from datetime import datetime

class Memory:
    def __init__(self):
        self._store = {}
    def scope(self, user):
        return self._store.setdefault(user, {})

class Audit:
    def __init__(self):
        self.entries = []
    def log(self, task, skill_name, user, tool_calls, result=None, error=None):
        self.entries.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "user": user, "task": task, "skill": skill_name,
            "tool_calls": tool_calls, "result": result, "error": error,
        })
    def count_failures(self, user, skill_name):
        return sum(1 for e in self.entries if e["user"] == user and e["skill"] == skill_name and e["error"] is not None)

class FlakyNetworkSkill:
    def __init__(self, memory_scope):
        self.memory_scope = memory_scope
        self.tool_calls = []
    def execute(self, task):
        # Always fails to simulate repeated service failure
        raise ConnectionError("Gateway timeout: remote server unreachable")

SKILL_REGISTRY = {"flaky_network": FlakyNetworkSkill}

def run_task(task, user, memory, audit):
    skill_name = task["skill"]
    skill_cls = SKILL_REGISTRY[skill_name]
    skill = skill_cls(memory.scope(user))
    try:
        result = skill.execute(task)
        audit.log(task, skill_name, user, skill.tool_calls, result=result)
        return result
    except Exception as e:
        audit.log(task, skill_name, user, skill.tool_calls, error=str(e))
        raise

def receive_task_with_escalation(task, user, memory, audit):
    skill_name = task["skill"]
    prior_failures = audit.count_failures(user, skill_name)
    
    if prior_failures >= 2:
        escalation_ticket = {
            "escalated": True,
            "reason": f"Skill '{skill_name}' failed {prior_failures} times for user '{user}'. Auto-escalated to human engineer.",
            "status": "HUMAN_ESCALATION_QUEUED",
        }
        audit.log(task, skill_name, user, [], result=escalation_ticket)
        return escalation_ticket

    return run_task(task, user, memory, audit)

if __name__ == "__main__":
    memory, audit = Memory(), Audit()
    user = "uday"
    task = {"skill": "flaky_network", "target": "https://api.internal/service"}

    print("=== Attempt 1: First Failure ===")
    try:
        receive_task_with_escalation(task, user, memory, audit)
    except ConnectionError as e:
        print(f"Attempt 1 caught error: {e}")

    print("\n=== Attempt 2: Second Failure ===")
    try:
        receive_task_with_escalation(task, user, memory, audit)
    except ConnectionError as e:
        print(f"Attempt 2 caught error: {e}")

    print("\n=== Attempt 3: Automatic Escalation to Human ===")
    outcome = receive_task_with_escalation(task, user, memory, audit)
    print("Outcome:", outcome)

    assert outcome.get("escalated") is True, "Must escalate on 3rd attempt!"
    print("\nConfirmed: Re-execution suppressed and escalated to human after two failures.")
