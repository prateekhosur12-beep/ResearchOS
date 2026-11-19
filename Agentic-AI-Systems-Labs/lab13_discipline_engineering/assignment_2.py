"""Lab 13: Assignment 2 -- Escalate on a Trend, Not Just a Threshold
Extends the Mechanical agent so that 3 consecutive WARNING-level readings
(even if none reach ALARM) automatically escalate from continue_monitoring
to schedule_preventative_inspection.
"""

# Log where values stay in WARNING band (2.8 - 4.4 mm/s) but never hit ALARM (>= 4.5 mm/s)
PERSISTENT_WARNING_LOG = [
    {"t": 0, "vibration_mm_s": 2.0, "temp_c": 60}, # NORMAL
    {"t": 1, "vibration_mm_s": 3.0, "temp_c": 71}, # WARNING 1
    {"t": 2, "vibration_mm_s": 3.4, "temp_c": 72}, # WARNING 2
    {"t": 3, "vibration_mm_s": 3.8, "temp_c": 74}, # WARNING 3 (Persistent!)
]

THRESHOLDS = {"vibration_warn": 2.8, "vibration_alarm": 4.5, "temp_warn": 70, "temp_alarm": 80}

def classify_reading(r):
    if r["vibration_mm_s"] >= THRESHOLDS["vibration_alarm"] or r["temp_c"] >= THRESHOLDS["temp_alarm"]:
        return "ALARM"
    if r["vibration_mm_s"] >= THRESHOLDS["vibration_warn"] or r["temp_c"] >= THRESHOLDS["temp_warn"]:
        return "WARNING"
    return "NORMAL"

def trend_escalation_agent(log):
    conditions = [classify_reading(entry) for entry in log]
    latest_condition = conditions[-1]

    # Check for 3 consecutive warnings
    consecutive_warnings = 0
    for c in reversed(conditions):
        if c == "WARNING":
            consecutive_warnings += 1
        else:
            break

    if latest_condition == "ALARM":
        action = "CRITICAL_SHUTDOWN_RECOMMENDED"
    elif consecutive_warnings >= 3:
        action = f"ESCALATE_TO_SCHEDULED_INSPECTION (Triggered by {consecutive_warnings} consecutive WARNING states)"
    elif latest_condition == "WARNING":
        action = "CONTINUE_MONITORING_WITH_INCREASED_SAMPLING"
    else:
        action = "CONTINUE_NORMAL_MONITORING"

    return {
        "conditions_history": conditions,
        "consecutive_warnings": consecutive_warnings,
        "action": action
    }

if __name__ == "__main__":
    result = trend_escalation_agent(PERSISTENT_WARNING_LOG)
    print("=== Trend-Based Degradation Escalation ===")
    print("Conditions History:    ", result["conditions_history"])
    print("Consecutive Warnings:  ", result["consecutive_warnings"])
    print("Action Taken:          ", result["action"])

    assert "ESCALATE_TO_SCHEDULED_INSPECTION" in result["action"]
    print("\nConfirmed: Three consecutive warnings successfully escalated to inspection.")
