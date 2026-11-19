"""Lab 12: Assignment 2 -- Mandatory Re-Evaluation After N Proposals
Tracks proposal counts. Forces re-evaluation after every 5 proposals.
The 6th proposal is blocked with an expiration error until evaluate() is called again.
"""

class ReEvaluationAgent:
    MAX_PROPOSALS_PER_EVAL = 5

    def __init__(self):
        self.proposals_since_eval = 0
        self.eval_pass_rate = None

    def evaluate(self):
        # Simulated diagnostic regression test suite
        self.eval_pass_rate = 0.95
        self.proposals_since_eval = 0
        print(f"[EVALUATION RUN] Pass rate: {self.eval_pass_rate*100}%. Quota reset to {self.MAX_PROPOSALS_PER_EVAL} proposals.")
        return True

    def propose(self, action_name):
        if self.eval_pass_rate is None or self.proposals_since_eval >= self.MAX_PROPOSALS_PER_EVAL:
            return {
                "success": False,
                "error": (f"PROPOSAL BLOCKED: Evaluation expired! {self.proposals_since_eval} proposals made "
                          f"since last evaluation. Re-evaluation mandatory before proposing further actions.")
            }
        
        self.proposals_since_eval += 1
        return {
            "success": True,
            "proposal_number": self.proposals_since_eval,
            "action": action_name,
            "status": "SUBMITTED"
        }

if __name__ == "__main__":
    agent = ReEvaluationAgent()
    agent.evaluate()

    print("\n=== Submitting 5 Proposals Within Evaluation Window ===")
    for i in range(1, 6):
        res = agent.propose(f"Patch config item {i}")
        print(f"Proposal {i}: {res['success']} (Usage: {agent.proposals_since_eval}/5)")

    print("\n=== Submitting 6th Proposal (Should Be Blocked) ===")
    res_6 = agent.propose("Patch config item 6")
    print(res_6)
    assert res_6["success"] is False, "6th proposal must be blocked!"

    print("\n=== Re-evaluating Agent ===")
    agent.evaluate()
    res_after_reval = agent.propose("Patch config item 6 (Post Re-Eval)")
    print("Post-Eval Proposal:", res_after_reval)
    assert res_after_reval["success"] is True, "Proposal after re-evaluation must succeed!"
