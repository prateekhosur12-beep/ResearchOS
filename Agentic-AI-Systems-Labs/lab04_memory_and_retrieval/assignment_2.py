"""Lab 4: Assignment 2 -- A Staleness / Retention Policy
Implements a retention_days threshold and staleness check.
If a retrieved record is older than the configured threshold, the assistant warns
the user that the decision may be outdated before presenting it.
"""
from dataclasses import dataclass
from datetime import datetime, date, timedelta

@dataclass
class MemoryRecord:
    topic: str
    fact: str
    date: str
    source: str = "memory"

class RetentionAwareProjectMemory:
    def __init__(self, retention_days=30):
        self.records = []
        self.retention_days = retention_days

    def retrieve(self, topic):
        return [r for r in self.records if r.topic == topic]

    def write(self, record):
        self.records.append(record)

class RetentionAwareAssistant:
    def __init__(self, memory):
        self.memory = memory

    def answer(self, topic, reference_date=None):
        if reference_date is None:
            reference_date = date.today()
            
        hits = self.memory.retrieve(topic)
        if not hits:
            return f"[session] No record found for '{topic}'."
            
        latest = hits[-1]
        record_date = datetime.strptime(latest.date, "%Y-%m-%d").date()
        age_days = (reference_date - record_date).days

        if age_days > self.memory.retention_days:
            warning = (f"[WARNING: Decision is {age_days} days old (exceeds {self.memory.retention_days}d retention policy) "
                       f"and may be stale! Please review before relying on it.]")
            return f"{warning}\n[memory, dated {latest.date}] {latest.fact}"
        
        return f"[FRESH: {age_days}d old] [memory, dated {latest.date}] {latest.fact}"

if __name__ == "__main__":
    memory = RetentionAwareProjectMemory(retention_days=30)
    
    # Fresh record: 5 days old
    ref_today = date(2026, 7, 15)
    memory.write(MemoryRecord(topic="cache", fact="use Redis v7", date="2026-07-10"))
    
    # Old record: 90 days old
    memory.write(MemoryRecord(topic="monitoring", fact="use Datadog free tier", date="2026-04-15"))

    assistant = RetentionAwareAssistant(memory)

    print("=== Fresh Record Test (Cache) ===")
    print(assistant.answer("cache", reference_date=ref_today))

    print("\n=== Stale Record Test (Monitoring) ===")
    print(assistant.answer("monitoring", reference_date=ref_today))
