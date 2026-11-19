"""Lab 1: Assignment 2 -- Detect a Scheduling Conflict
Extends read_existing_schedule to return multiple busy days.
Checks for conflicts between unavailable days and busy days before finalizing,
explicitly reporting conflicts to the user instead of silently double-booking.
"""
import json

SIMULATED_ANSWERS = {
    "subjects": ["Data Structures", "Operating Systems", "AI Agents"],
    "hours_per_day": 2,
    "unavailable_days": ["Sunday", "Friday"], # Student chose Friday as unavailable
}

class ConflictDetectingStudyPlannerAgent:
    def __init__(self, existing_schedule):
        self.goal = {
            "subjects": None,
            "hours_per_day": None,
            "unavailable_days": None,
            "schedule_generated": False,
        }
        self.existing_schedule = existing_schedule
        self.plan = None
        self.conflicts = []
        self.log = []

    def satisfied(self):
        return self.goal["schedule_generated"] is True

    def next_step(self):
        for field in ("subjects", "hours_per_day", "unavailable_days"):
            if self.goal[field] is None:
                return ("ask", field)
        return ("generate_plan", None)

    def read_existing_schedule(self):
        return self.existing_schedule

    def detect_conflicts(self, busy_days, unavailable_days):
        """Detect if unavailable days clash with required study allocations or
        if busy days restrict the available study hours below target.
        """
        detected = []
        all_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        available_days = [d for d in all_days if d not in unavailable_days]
        
        # Check overlaps
        busy_on_available = [d for d in busy_days if d in available_days]
        if len(available_days) < len(self.goal["subjects"]):
            detected.append(
                f"Too few study days available ({len(available_days)}) to cover all {len(self.goal['subjects'])} subjects."
            )
        for bd in busy_days:
            if bd in busy_on_available:
                detected.append(
                    f"Warning: {bd} is flagged as busy in existing schedule. Agent must adjust time slot to 20:00-22:00."
                )
        return detected

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
                busy_info = self.read_existing_schedule()
                busy_days = busy_info.get("busy_days", [])
                self.log.append({
                    "iteration": len(self.log) + 1,
                    "planned": "read existing schedule and check conflicts",
                    "action": "tool call: read_existing_schedule()",
                    "observed": busy_info,
                    "stopped": False,
                })

                # Check conflict before finalizing
                self.conflicts = self.detect_conflicts(busy_days, self.goal["unavailable_days"])
                if self.conflicts:
                    self.log.append({
                        "iteration": len(self.log) + 1,
                        "planned": "flag scheduling conflicts to user",
                        "action": "conflict analysis report generated",
                        "observed": self.conflicts,
                        "stopped": False,
                    })

                self.plan = self._build_plan(busy_info)
                self.goal["schedule_generated"] = True
                self.log.append({
                    "iteration": len(self.log) + 1,
                    "planned": "generate schedule avoiding known conflicts",
                    "action": "built weekly plan with conflict resolution",
                    "observed": self.plan,
                    "stopped": True,
                    "stop_reason": "goal.schedule_generated is now True",
                })
        return self.plan

    def _build_plan(self, busy_slots):
        busy_days = busy_slots.get("busy_days", [])
        days = [d for d in
                ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                if d not in self.goal["unavailable_days"]]
        subjects = self.goal["subjects"]
        plan = {}
        for i, day in enumerate(days):
            subject = subjects[i % len(subjects)]
            slot = "17:00-19:00"
            is_busy = day in busy_days
            if is_busy:
                slot = "20:00-22:00 (Moved to late evening to avoid busy schedule)"
            plan[day] = {"subject": subject, "time": slot, "busy_day_adjusted": is_busy}
        return plan

if __name__ == "__main__":
    # Schedule now has two busy days: Wednesday and Friday
    existing_schedule = {"busy_days": ["Wednesday", "Friday"]}
    agent = ConflictDetectingStudyPlannerAgent(existing_schedule)

    print("=== Running Conflict-Detecting Planner ===")
    plan = agent.run()

    print("\n=== Detected Scheduling Notes / Conflicts ===")
    for c in agent.conflicts:
        print(f"  [FLAG] {c}")

    print("\n=== Generated Plan ===")
    print(json.dumps(plan, indent=2))
