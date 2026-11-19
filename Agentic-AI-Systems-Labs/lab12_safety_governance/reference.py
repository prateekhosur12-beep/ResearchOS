"""Lab 12: Safety, Evaluation, and Governance -- Guardrails for a Production-Change Agent
Reference Implementation
Implements all six controls from Concept 12 and rejects actions if evidence is missing.
"""

REGRESSION_SUITE_RESULT = {"passed": 9, "total": 10}

class ProdChangeAgent:
    permissions = {"can_write": "staging_only"}

    def __init__(self):
        self.audit_log = []
        self.evaluated = False

    def evaluate(self):
        pass_rate = REGRESSION_SUITE_RESULT["passed"] / REGRESSION_SUITE_RESULT["total"]
        self.evaluated = pass_rate >= 0.8
        self._log("evaluation", {"pass_rate": pass_rate, "passed_gate": self.evaluated})
        return self.evaluated

    def _log(self, step, data):
        self.audit_log.append({"step": step, "data": data})

    def propose_change(self, diagnosis, action, rollback_plan, privacy_scrubbed):
        if not self.evaluated:
            self._log("propose_change", {"rejected": True, "reason": "agent not evaluated"})
            return {"rejected": True, "reason": "Evaluation gate not passed; cannot propose changes."}
        if self.permissions["can_write"] != "staging_only":
            raise PermissionError("Agent must not hold direct production write access.")
        if not privacy_scrubbed:
            self._log("propose_change", {"rejected": True, "reason": "unscrubbed customer data in input"})
            return {"rejected": True, "reason": "Diagnostic input was not privacy-scrubbed; rejecting."}
        if not rollback_plan:
            self._log("propose_change", {"rejected": True, "reason": "no rollback plan supplied"})
            return {"rejected": True, "reason": "No rollback plan defined; rejecting proposal."}

        request = {
            "diagnosis": diagnosis,
            "proposed_action": action,
            "rollback_plan": rollback_plan,
            "category": "production",
            "requires_approval": True,
        }
        self._log("approval_requested", request)
        return request

    def apply_after_approval(self, request, human_decision):
        self._log("human_decision", {"decision": human_decision})
        if human_decision != "approved":
            return {"applied": False, "reason": "not approved by human"}
        return {"applied": False,
                "handed_off_to": "privileged_deploy_process",
                "note": "This agent never holds production write access; a separate "
                        "privileged process performs the actual apply step."}

if __name__ == "__main__":
    agent = ProdChangeAgent()
    print("=== Control 2: Evaluation gate ===")
    print(f"Evaluated and passed: {agent.evaluate()}")
    print("\n=== Attempt 1: missing rollback plan ===")
    print(agent.propose_change(
        diagnosis="Config X causes memory leak.",
        action="revert config X",
        rollback_plan=None,
        privacy_scrubbed=True,
    ))
    print("\n=== Attempt 2: unscrubbed customer data ===")
    print(agent.propose_change(
        diagnosis="Config X causes memory leak.",
        action="revert config X",
        rollback_plan="Revert to v3.",
        privacy_scrubbed=False,
    ))
    print("\n=== Attempt 3: valid proposal ===")
    req = agent.propose_change(
        diagnosis="Config X causes memory leak.",
        action="revert config X",
        rollback_plan="Revert to v3.",
        privacy_scrubbed=True,
    )
    print(req)
    print("\n=== Human approves ===")
    print(agent.apply_after_approval(req, human_decision="approved"))
    print("\n=== Adversarial test: agent attempts direct production write ===")
    try:
        agent.permissions["can_write"] = "production"
        agent.propose_change("test", "test", "test", True)
    except PermissionError as e:
        print(f"Blocked as expected: {e}")
