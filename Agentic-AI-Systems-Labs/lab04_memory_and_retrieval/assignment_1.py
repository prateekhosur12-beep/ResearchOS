"""Lab 4: Assignment 1 -- A Second, Isolated Topic
Adds a second topic ('hosting') alongside 'database'.
Demonstrates that topic-scoped retrieval guarantees zero cross-topic leakage.
"""
from dataclasses import dataclass
from datetime import date

@dataclass
class MemoryRecord:
    topic: str
    fact: str
    date: str
    source: str = "memory"

class IsolatedProjectMemory:
    def __init__(self):
        self.records = []
        self.allowed_writers = {"team_lead"}

    def retrieve(self, topic):
        # Strict topic boundary filter
        return [r for r in self.records if r.topic.lower() == topic.lower()]

    def write(self, record, user_role):
        if user_role not in self.allowed_writers:
            raise PermissionError(f"role '{user_role}' is not permitted to write memory")
        self.records.append(record)

class MultiTopicProjectAssistant:
    def __init__(self, memory):
        self.memory = memory

    def answer(self, topic, question):
        hits = self.memory.retrieve(topic)
        if not hits:
            return f"[session] No stored decision on '{topic}' yet."
        latest = hits[-1]
        return f"[memory, topic='{topic}', dated {latest.date}] {latest.fact}"

if __name__ == "__main__":
    memory = IsolatedProjectMemory()
    
    # Store decisions for two separate topics
    memory.write(
        MemoryRecord(topic="database", fact="we chose PostgreSQL with connection pooling", date="2026-07-03"),
        user_role="team_lead"
    )
    memory.write(
        MemoryRecord(topic="hosting", fact="we chose AWS ECS Fargate with multi-AZ", date="2026-07-04"),
        user_role="team_lead"
    )

    assistant = MultiTopicProjectAssistant(memory)

    print("=== Querying Topic: 'database' ===")
    ans_db = assistant.answer("database", "What is our architecture choice?")
    print(ans_db)

    print("\n=== Querying Topic: 'hosting' ===")
    ans_host = assistant.answer("hosting", "What is our architecture choice?")
    print(ans_host)

    # Verification of zero leakage
    assert "ECS" not in ans_db and "Fargate" not in ans_db, "Leakage from 'hosting' into 'database'!"
    assert "PostgreSQL" not in ans_host, "Leakage from 'database' into 'hosting'!"
    print("\nConfirmed: Zero cross-topic leakage between 'database' and 'hosting'.")
