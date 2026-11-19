"""Lab 13: Assignment 1 -- Add a Second Domain: Electrical Load Forecasting & Fault Triage
Applies the agentic pattern to Electrical Engineering:
Monitors transformer load percentage and winding temperature.
Strict safety gate: ALARM feeder trips are never automated and require chief electrical engineer approval.
"""

ELECTRICAL_SENSOR_LOG = [
    {"hour": 14, "load_kva_pct": 78, "oil_temp_c": 62, "phase_unbalance_pct": 1.2},
    {"hour": 15, "load_kva_pct": 86, "oil_temp_c": 71, "phase_unbalance_pct": 1.8},
    {"hour": 16, "load_kva_pct": 94, "oil_temp_c": 79, "phase_unbalance_pct": 2.5},
    {"hour": 17, "load_kva_pct": 108, "oil_temp_c": 92, "phase_unbalance_pct": 4.1},
]

GRID_THRESHOLDS = {
    "load_warn_pct": 85, "load_alarm_pct": 100,
    "temp_warn_c": 75, "temp_alarm_c": 90
}

def classify_grid_state(reading):
    if reading["load_kva_pct"] >= GRID_THRESHOLDS["load_alarm_pct"] or reading["oil_temp_c"] >= GRID_THRESHOLDS["temp_alarm_c"]:
        return "ALARM"
    if reading["load_kva_pct"] >= GRID_THRESHOLDS["load_warn_pct"] or reading["oil_temp_c"] >= GRID_THRESHOLDS["temp_warn_c"]:
        return "WARNING"
    return "NORMAL"

def electrical_safety_gate(state):
    # Industrial safety invariant: Agent cannot trip grid substation breaker without human engineer
    if state == "ALARM":
        return {
            "recommended_action": "REQUEST_MANUAL_FEEDER_TRIP_AND_LOAD_SHED",
            "auto_execute": False,
            "requires_role": "Chief Electrical Engineer"
        }
    elif state == "WARNING":
        return {
            "recommended_action": "DISPATCH_COOLING_BANK_AND_ALERT_OPERATOR",
            "auto_execute": False,
            "requires_role": "Substation Operator"
        }
    return {"recommended_action": "NORMAL_TELEMETRY_LOGGING", "auto_execute": True}

def electrical_triage_agent():
    latest = ELECTRICAL_SENSOR_LOG[-1]
    state = classify_grid_state(latest)
    safety = electrical_safety_gate(state)

    return {
        "domain": "Electrical Engineering -- Substation Transformer Monitoring",
        "reading": latest,
        "classification": state,
        "safety_decision": safety,
        "evaluation_standard": "IEEE C57.91 Guide for Loading Mineral-Oil-Immersed Transformers"
    }

if __name__ == "__main__":
    report = electrical_triage_agent()
    print("=== Electrical Grid Triage Agent Output ===")
    for k, v in report.items():
        print(f"{k}: {v}")
    
    assert report["safety_decision"]["auto_execute"] is False, "ALARM action must not auto-execute!"
    print("\nConfirmed: Substation safety interlock enforced; human authorization mandatory.")
