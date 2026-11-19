"""Lab 14: Capstone Project Studio -- Integrated Mini System
Reference Implementation
Compact worklet ("Campus Help-Desk Agent") combining node graph, 3+ tools,
reusable skill, memory design, prompt log, execution trace, evaluation,
safety control, and limitations roadmap.
"""
from datetime import datetime

FAQ_DB = {"wifi": "Connect to 'Campus-Secure' and log in with your student ID."}
TICKET_DB = []

def tool_search_faq(query):
    for k, v in FAQ_DB.items():
        if k in query.lower():
            return {"found": True, "answer": v}
    return {"found": False}

def tool_create_ticket(issue):
    ticket_id = f"T-{len(TICKET_DB) + 1:03d}"
    TICKET_DB.append({"id": ticket_id, "issue": issue, "status": "open"})
    return {"ticket_id": ticket_id}

def tool_check_ticket_status(ticket_id):
    for t in TICKET_DB:
        if t["id"] == ticket_id:
            return t
    return {"error": "not found"}

def triage_skill(issue_text):
    faq_result = tool_search_faq(issue_text)
    if faq_result["found"]:
        return {"resolution": "faq", "answer": faq_result["answer"]}
    ticket = tool_create_ticket(issue_text)
    return {"resolution": "escalated", "ticket_id": ticket["ticket_id"]}

class CapstoneMemory:
    def __init__(self):
        self.session = {}
        self.history = []

    def record(self, user, issue, outcome):
        entry = {"user": user, "issue": issue, "outcome": outcome,
                 "date": datetime.now().isoformat(timespec="seconds")}
        self.history.append(entry)
        self.session["last_issue"] = issue

def node_graph_run(user, issue, memory, audit_log, prompt_log):
    prompt_log.append({"stage": "intake", "input": issue})
    if not issue.strip():
        audit_log.append({"stage": "intake", "result": "rejected: empty issue"})
        return {"rejected": True, "reason": "empty issue text"}

    outcome = triage_skill(issue)
    prompt_log.append({"stage": "triage", "output": outcome})

    if outcome["resolution"] == "faq":
        response = outcome["answer"]
    else:
        response = f"Ticket {outcome['ticket_id']} created; support will follow up."

    memory.record(user, issue, outcome)
    audit_log.append({"stage": "complete", "user": user, "issue": issue, "outcome": outcome})
    return {"rejected": False, "response": response, "outcome": outcome}

def run_evaluation():
    cases = [
        ("How do I connect to wifi?", "faq"),
        ("My laptop charger is broken", "escalated"),
    ]
    memory, audit_log, prompt_log = CapstoneMemory(), [], []
    results = []
    for issue, expected in cases:
        result = node_graph_run("eval_user", issue, memory, audit_log, prompt_log)
        actual = result["outcome"]["resolution"]
        results.append({"issue": issue, "expected": expected, "actual": actual,
                        "passed": actual == expected})
    return results

if __name__ == "__main__":
    memory, audit_log, prompt_log = CapstoneMemory(), [], []
    print("=== Run 1: FAQ match ===")
    print(node_graph_run("alice", "How do I connect to wifi on campus?", memory, audit_log, prompt_log))
    print("\n=== Run 2: Escalation (no FAQ match) ===")
    print(node_graph_run("bob", "My laptop charger is broken", memory, audit_log, prompt_log))
    print("\n=== Run 3: Safety control rejects empty input ===")
    print(node_graph_run("carol", "   ", memory, audit_log, prompt_log))
    print("\n=== Evaluation ===")
    for r in run_evaluation():
        print(f"  [{'PASS' if r['passed'] else 'FAIL'}] {r['issue']} -> {r['actual']}")
