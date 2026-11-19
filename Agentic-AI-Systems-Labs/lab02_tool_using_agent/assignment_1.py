"""Lab 2: Assignment 1 -- Add a Notification Tool with Justified Use
Adds send_notification(message) which only drafts a notification message.
When the computed average sign-ups fall below a defined threshold (e.g. 15),
the agent calls this tool to draft a low-turnout notice and records the justification in the trace.
"""
import csv
import io

SIGNUPS_CSV = """event,signups
AI Club Talk,12
Hackathon Kickoff,9
Robotics Demo,15
GenAI Workshop,7
Capstone Expo,20
Career Panel,11"""

def calculator(operation, values):
    if operation == "average":
        if not values:
            return {"error": "no values supplied"}
        return {"result": sum(values) / len(values)}
    if operation == "sum":
        return {"result": sum(values)}
    return {"error": f"unsupported operation: {operation}"}

def read_csv(source_text=SIGNUPS_CSV):
    reader = csv.DictReader(io.StringIO(source_text.strip()))
    rows = list(reader)
    if not rows:
        return {"error": "empty file", "rows": [], "row_count": 0}
    return {"rows": rows, "row_count": len(rows)}

def send_notification(message):
    """Drafts a notification message. Does NOT send externally."""
    return {
        "status": "drafted",
        "notification_text": message,
        "dispatched": False,
        "note": "Draft saved for human review; no external network send performed."
    }

TOOLS = {
    "calculator": calculator,
    "read_csv": read_csv,
    "send_notification": send_notification
}

class NotifyingCampusAssistant:
    TURNOUT_THRESHOLD = 15.0  # Alert if average attendance is below 15

    def __init__(self):
        self.trace = []

    def _call(self, tool_name, reason, **kwargs):
        result = TOOLS[tool_name](**kwargs)
        entry = {"tool": tool_name, "reason": reason, "input": kwargs, "output": result}
        self.trace.append(entry)
        if "error" in result:
            raise RuntimeError(f"{tool_name} failed: {result['error']}")
        return result

    def answer(self, question):
        q = question.lower()
        if "average" in q or "sign" in q:
            csv_result = self._call("read_csv", "Extracting attendance figures from CSV")
            values = [int(r["signups"]) for r in csv_result["rows"]]
            avg_result = self._call("calculator", "Compute average sign-ups across events",
                                    operation="average", values=values)
            avg = avg_result["result"]
            resp = f"Average signups per event: {avg:.2f}."

            # Check threshold and call notification tool if turnout is low
            if avg < self.TURNOUT_THRESHOLD:
                draft_msg = f"Low turnout notice: Average signups ({avg:.2f}) fell below target ({self.TURNOUT_THRESHOLD})."
                notif = self._call(
                    "send_notification",
                    f"Computed average ({avg:.2f}) < threshold ({self.TURNOUT_THRESHOLD}); drafting alert for organizers",
                    message=draft_msg
                )
                resp += f" [ALERT DRAFTED]: {notif['notification_text']}"
            return resp
        return "Unsupported question."

if __name__ == "__main__":
    assistant = NotifyingCampusAssistant()
    question = "What is the average student sign-up count, and is an alert needed?"
    print(f"Q: {question}")
    answer = assistant.answer(question)
    print(f"A: {answer}\n")

    print("=== Execution Trace with Tool Call Justification ===")
    for idx, t in enumerate(assistant.trace, 1):
        print(f"Step {idx}:")
        print(f"  Tool:   {t['tool']}")
        print(f"  Reason: {t['reason']}")
        print(f"  Input:  {t['input']}")
        print(f"  Output: {t['output']}")
