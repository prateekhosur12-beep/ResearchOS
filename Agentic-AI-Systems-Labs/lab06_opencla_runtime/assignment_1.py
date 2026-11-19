"""Lab 6: Assignment 1 -- Add Per-User Rate Limiting
Enforces a maximum of 3 tasks per user per session inside receive_task (the interface layer)
without modifying run_task's core loop signature or dispatch logic.
The 4th task by the same user is rejected with a rate limit error.
"""
from datetime import datetime

def tool_word_count(text):
    return {"count": len(text.split())}

TOOLS = {"word_count": tool_word_count}

class Memory:
    def __init__(self):
        self._store = {}
    def scope(self, user):
        return self._store.setdefault(user, {})

class Audit:
    def __init__(self):
        self.entries = []
    def log(self, task, skill_name, tool_calls, result=None, error=None):
        self.entries.append({
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "task": task, "skill": skill_name, "tool_calls": tool_calls,
            "result": result, "error": error,
        })

class EchoSkill:
    def __init__(self, memory_scope):
        self.memory_scope = memory_scope
        self.tool_calls = []
    def execute(self, task):
        wc = TOOLS["word_count"](task["text"])
        self.tool_calls.append({"tool": "word_count", "output": wc})
        return f"Processed: {task['text']} ({wc['count']} words)"

SKILL_REGISTRY = {"echo": EchoSkill}

def select_skill(task):
    return task["skill"]

# Unchanged core loop
def run_task(task, user, memory, audit):
    skill_name = select_skill(task)
    skill_cls = SKILL_REGISTRY[skill_name]
    skill = skill_cls(memory.scope(user))
    try:
        result = skill.execute(task)
        audit.log(task, skill_name, skill.tool_calls, result=result)
        return result
    except Exception as e:
        audit.log(task, skill_name, skill.tool_calls, error=str(e))
        raise

# User quota tracking in the interface layer
USER_QUOTA = {}
MAX_TASKS_PER_SESSION = 3

def receive_task_with_rate_limit(task, user, memory, audit):
    """Enforces rate limit at the boundary before calling run_task."""
    current_count = USER_QUOTA.get(user, 0)
    if current_count >= MAX_TASKS_PER_SESSION:
        err_msg = f"RateLimitExceeded: User '{user}' exceeded limit of {MAX_TASKS_PER_SESSION} tasks per session."
        audit.log(task, task.get("skill", "unknown"), [], error=err_msg)
        raise PermissionError(err_msg)
    
    USER_QUOTA[user] = current_count + 1
    return run_task(task, user, memory, audit)

if __name__ == "__main__":
    memory, audit = Memory(), Audit()
    user = "alice"

    print("=== Submitting tasks for user 'alice' (Limit: 3) ===")
    for i in range(1, 4):
        res = receive_task_with_rate_limit({"skill": "echo", "text": f"Task number {i}"},
                                          user=user, memory=memory, audit=audit)
        print(f"Task {i} Success: {res} (Usage: {USER_QUOTA[user]}/{MAX_TASKS_PER_SESSION})")

    print("\n=== Attempting 4th task (Expect Rejection) ===")
    try:
        receive_task_with_rate_limit({"skill": "echo", "text": "Task number 4"},
                                      user=user, memory=memory, audit=audit)
    except PermissionError as e:
        print(f"Blocked as expected: {e}")

    print("\n=== Different user 'bob' can still run tasks ===")
    res_bob = receive_task_with_rate_limit({"skill": "echo", "text": "Bob's task"},
                                          user="bob", memory=memory, audit=audit)
    print(f"Bob's Task: {res_bob}")
