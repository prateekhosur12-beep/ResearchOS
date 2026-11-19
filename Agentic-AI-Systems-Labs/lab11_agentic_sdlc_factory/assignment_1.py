"""Lab 11: Assignment 1 -- A Second, Concurrent Story
Runs two stories side-by-side: US-1 (CSV Export) and US-2 (JSON Export).
Maintains explicit lineage linking every design, code, and test artifact to its owning story.
"""

MULTI_REQUEST = "Add data export: Support both CSV export (US-1) and JSON API export (US-2)."

def requirement_agent(request):
    return [
        {
            "id": "US-1",
            "feature": "CSV Export",
            "acceptance_criteria": ["returns comma-separated string", "contains header"],
        },
        {
            "id": "US-2",
            "feature": "JSON Export",
            "acceptance_criteria": ["returns valid json list of dicts", "preserves data types"],
        }
    ]

def design_agent(story):
    return {
        "story_id": story["id"],
        "architecture": f"Handler for {story['feature']}",
        "component_name": f"{story['id'].lower()}_serializer"
    }

def coding_agent(design, story):
    if story["id"] == "US-1":
        def export_csv(data):
            header = ",".join(data[0].keys())
            rows = ["\n".join([header] + [",".join(str(v) for v in row.values()) for row in data])]
            return rows[0]
        return {"story_id": story["id"], "fn": export_csv}
    else:
        import json
        def export_json(data):
            return json.dumps(data)
        return {"story_id": story["id"], "fn": export_json}

def testing_agent(story):
    """Test authored solely against acceptance criteria."""
    def test_runner(fn):
        sample = [{"id": 1, "name": "Item A"}]
        out = fn(sample)
        if story["id"] == "US-1":
            passed = "id,name" in out and "Item A" in out
        else:
            passed = '"name": "Item A"' in out
        return [{"test": f"AC verification for {story['id']}", "passed": passed}]
    return test_runner

if __name__ == "__main__":
    stories = requirement_agent(MULTI_REQUEST)
    lineage_records = []

    for s in stories:
        sid = s["id"]
        dsg = design_agent(s)
        code = coding_agent(dsg, s)
        tester = testing_agent(s)
        test_out = tester(code["fn"])

        lineage_records.append({
            "story": sid,
            "design": dsg["component_name"],
            "code": code["fn"].__name__,
            "tests_passed": test_out[0]["passed"],
        })

    print("=== Multi-Story Lineage Matrix ===")
    print(f"{'Story ID':<10} | {'Design Component':<20} | {'Code Handler':<15} | {'Tests Status':<12}")
    print("-" * 65)
    for row in lineage_records:
        status = "PASSED" if row['tests_passed'] else "FAILED"
        print(f"{row['story']:<10} | {row['design']:<20} | {row['code']:<15} | {status:<12}")

    print("\nConfirmed: Each story retains an independent traceable lineage graph.")
