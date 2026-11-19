"""Lab 10: Assignment 1 -- A Second Incident Type: DB Connection Pool Exhaustion
Diagnoses a distinct database incident with its own error signature,
deploy history, and metric elevation.
"""

DB_INCIDENT_LOGS = [
    {"ts": "11:10:00", "level": "INFO", "msg": "deploy completed: analytics-worker v1.8.0"},
    {"ts": "11:14:20", "level": "WARN", "msg": "DB pool active connections: 98/100"},
    {"ts": "11:15:00", "level": "ERROR", "msg": "FATAL: remaining connection slots are reserved for superuser connections"},
    {"ts": "11:15:30", "level": "ERROR", "msg": "ConnectionPoolTimeoutException: Timeout waiting for idle connection in pool"},
]

DB_DEPLOY_HISTORY = [
    {"ts": "11:10:00", "service": "analytics-worker", "version": "v1.8.0", "prev_version": "v1.7.9"}
]

DB_METRICS = {"baseline_error_rate": 0.1, "current_error_rate": 4.5}

def classify_severity(metrics):
    ratio = metrics["current_error_rate"] / metrics["baseline_error_rate"]
    if metrics["current_error_rate"] > 50:
        return "down"
    if ratio >= 2:
        return "degraded"
    return "early_warning"

def diagnose_db_incident(logs, deploys, metrics):
    severity = classify_severity(metrics)
    error_msgs = [l["msg"] for l in logs if l["level"] == "ERROR"]
    
    if any("connection" in m.lower() for m in error_msgs):
        root_cause = "Database connection pool exhaustion caused by unclosed connections in analytics-worker."
    else:
        root_cause = "General service failure."

    suspect = deploys[0]
    return {
        "incident_type": "DATABASE_POOL_EXHAUSTION",
        "affected_service": suspect["service"],
        "severity": severity,
        "root_cause_diagnosis": root_cause,
        "recommended_action": "rollback",
        "rollback_target": suspect["prev_version"],
        "requires_human_approval": True
    }

if __name__ == "__main__":
    report = diagnose_db_incident(DB_INCIDENT_LOGS, DB_DEPLOY_HISTORY, DB_METRICS)
    print("=== Database Connection Exhaustion Incident Report ===")
    for k, v in report.items():
        print(f"{k}: {v}")
