"""Lab 2: Assignment 2 -- A Three-Tool Chain
Adds a category field to CSV data and implements a 3-step tool chain:
1. read_csv: fetch raw rows
2. filter_rows: filter rows by category and validate non-empty
3. calculator: compute average over filtered subset
"""
import csv
import io

CATEGORIZED_CSV = """event,category,signups
AI Club Talk,technical,12
Hackathon Kickoff,technical,9
Robotics Demo,technical,15
GenAI Workshop,technical,7
Capstone Expo,technical,20
Career Panel,social,11
Campus Picnic,social,45
Board Games Night,social,25"""

def calculator(operation, values):
    if operation == "average":
        if not values:
            return {"error": "no values supplied"}
        return {"result": sum(values) / len(values)}
    if operation == "sum":
        return {"result": sum(values)}
    return {"error": f"unsupported operation: {operation}"}

def read_csv(source_text=CATEGORIZED_CSV):
    reader = csv.DictReader(io.StringIO(source_text.strip()))
    rows = list(reader)
    if not rows:
        return {"error": "empty file", "rows": [], "row_count": 0}
    return {"rows": rows, "row_count": len(rows)}

def filter_rows(rows, category):
    """Filters events by category and validates that the result is non-empty."""
    filtered = [r for r in rows if r.get("category", "").lower() == category.lower()]
    if not filtered:
        return {"error": f"no records found for category '{category}'", "filtered_rows": []}
    return {"filtered_rows": filtered, "count": len(filtered)}

TOOLS = {
    "read_csv": read_csv,
    "filter_rows": filter_rows,
    "calculator": calculator,
}

class ThreeToolChainAssistant:
    def __init__(self):
        self.trace = []

    def _call(self, tool_name, reason, **kwargs):
        result = TOOLS[tool_name](**kwargs)
        entry = {"tool": tool_name, "reason": reason, "input": kwargs, "output": result}
        self.trace.append(entry)
        if "error" in result:
            raise RuntimeError(f"{tool_name} failed: {result['error']}")
        return result

    def answer_category_average(self, category):
        # Step 1: Read CSV
        csv_data = self._call("read_csv", "Fetch raw event records with category information")
        
        # Step 2: Filter by category and validate
        filtered_data = self._call(
            "filter_rows",
            f"Filter dataset down to '{category}' events only and validate non-empty",
            rows=csv_data["rows"],
            category=category
        )
        
        # Extract numerical column from validated filtered subset
        values = [int(r["signups"]) for r in filtered_data["filtered_rows"]]
        
        # Step 3: Compute average using calculator
        avg_result = self._call(
            "calculator",
            f"Compute mathematical average for {len(values)} '{category}' events",
            operation="average",
            values=values
        )
        
        return (f"Average sign-ups for '{category}' events: {avg_result['result']:.2f} "
                f"(computed across {filtered_data['count']} matching events).")

if __name__ == "__main__":
    assistant = ThreeToolChainAssistant()
    query = "What's the average sign-up for technical events only?"
    print(f"Question: {query}")
    answer = assistant.answer_category_average("technical")
    print(f"Answer:   {answer}\n")

    print("=== Trace of 3-Tool Chain ===")
    for i, t in enumerate(assistant.trace, 1):
        print(f"{i}. Tool: {t['tool']}")
        print(f"   Reason: {t['reason']}")
        print(f"   Output: {t['output']}")
