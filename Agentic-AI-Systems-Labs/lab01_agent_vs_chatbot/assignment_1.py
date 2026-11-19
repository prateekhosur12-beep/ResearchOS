"""Lab 1: Assignment 1 -- Two Rounds of Feedback
Extends the reference agent to accept two independent rounds of feedback.
Both revisions mutate the same plan object, producing separate revise iterations
without regenerating the plan from scratch.
"""
import json

SIMULATED_ANSWERS = {
    "subjects": ["Data Structures", "Operating Systems", "AI Agents"],
    "hours_per_day": 2,
    "unavailable_days": ["Sunday"],
}

ROUND_1_FEEDBACK = "Move Tuesday's session to the evening."
ROUND_2_FEEDBACK = "Also make Friday's session shorter, only one hour (17:00-18:00)."

class MultiRoundStudyPlannerAgent:
    def __init__(self, existing_schedule):
        self.goal = {
            "subjects": None,
            "hours_per_day": None,
            "unavailable_days": None,
            "schedule_generated": False,
        }
        self.existing_schedule = existing_schedule
        self.plan = None
        self.log = []

    def satisfied(self):
        return self.goal["schedule_generated"] is True

    def next_step(self):
        for field in ("subjects", "hours_per_day", "unavailable_days"):
            if self.goal[field] is None:
                return ("ask", field)
        return ("generate_plan", None)

    def read_existing_schedule(self):
        result = self.existing_schedule
        if "error" in result:
            raise RuntimeError(f"tool error: {result['error']}")
        return result

    def run(self):
        while not self.satisfied():
            step, arg = self.next_step()
            if step == "ask":
                answer = SIMULATED_ANSWERS[arg]
                self.goal[arg] = answer
                self.log.append({
                    "iteration": len(self.log) + 1,
                    "planned": f"ask for {arg}",
                    "action": f"asked user for {arg}",
                    "observed": answer,
                    "stopped": False,
                })
            elif step == "generate_plan":
                busy = self.read_existing_schedule()
                self.log.append({
                    "iteration": len(self.log) + 1,
                    "planned": "read existing schedule before generating plan",
                    "action": "tool call: read_existing_schedule()",
                    "observed": busy,
                    "stopped": False,
                })
                self.plan = self._build_plan(busy)
                self.goal["schedule_generated"] = True
                self.log.append({
                    "iteration": len(self.log) + 1,
                    "planned": "generate schedule from gathered requirements",
                    "action": "built weekly plan",
                    "observed": self.plan,
                    "stopped": True,
                    "stop_reason": "goal.schedule_generated is now True",
                })
        return self.plan

    def _build_plan(self, busy_slots):
        days = [d for d in
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                if d not in self.goal["unavailable_days"]]
        subjects = self.goal["subjects"]
        plan = {}
        for i, day in enumerate(days):
            subject = subjects[i % len(subjects)]
            slot = "17:00-19:00"
            if day in busy_slots.get("busy_days", []):
                slot = "20:00-22:00"
            plan[day] = {"subject": subject, "time": slot}
        return plan

    def revise(self, feedback, round_num=1):
        """Mutate existing plan object upon receiving feedback.
        Demonstrates in-place mutation across multiple independent rounds.
        """
        self.log.append({
            "iteration": len(self.log) + 1,
            "planned": f"apply user feedback round {round_num} to existing plan",
            "action": f"feedback received: '{feedback}'",
            "observed": None,
            "stopped": False,
        })

        f_lower = feedback.lower()
        # Round 1 handling: Tuesday evening
        if "tuesday" in f_lower and "evening" in f_lower:
            if "Tuesday" in self.plan:
                self.plan["Tuesday"]["time"] = "20:00-22:00"

        # Round 2 handling: Friday shorter 1 hour
        if "friday" in f_lower and ("shorter" in f_lower or "one hour" in f_lower or "17:00-18:00" in f_lower):
            if "Friday" in self.plan:
                self.plan["Friday"]["time"] = "17:00-18:00"
                self.plan["Friday"]["note"] = "reduced to 1 hour per round 2 feedback"

        self.log.append({
            "iteration": len(self.log) + 1,
            "planned": f"confirm revised plan round {round_num}",
            "action": f"mutated existing plan for round {round_num} (not regenerated from scratch)",
            "observed": self.plan,
            "stopped": True,
            "stop_reason": f"revision round {round_num} applied in-place",
        })
        return self.plan

if __name__ == "__main__":
    existing_schedule = {"busy_days": ["Wednesday"]}
    agent = MultiRoundStudyPlannerAgent(existing_schedule)

    print("=== 1. Initial Plan Generation ===")
    initial_plan = agent.run()
    print(json.dumps(initial_plan, indent=2))

    print("\n=== 2. Round 1 Feedback ===")
    plan_after_r1 = agent.revise(ROUND_1_FEEDBACK, round_num=1)
    print(f"Feedback: {ROUND_1_FEEDBACK}")
    print(json.dumps(plan_after_r1, indent=2))

    print("\n=== 3. Round 2 Feedback ===")
    plan_after_r2 = agent.revise(ROUND_2_FEEDBACK, round_num=2)
    print(f"Feedback: {ROUND_2_FEEDBACK}")
    print(json.dumps(plan_after_r2, indent=2))

    print("\n=== 4. Full Iteration Log (Showing Both Revisions in-place) ===")
    for entry in agent.log:
        print(f"Iteration {entry['iteration']}: {entry['planned']} -> {entry['action']} (stopped={entry['stopped']})")
