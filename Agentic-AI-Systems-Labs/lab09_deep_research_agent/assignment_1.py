"""Lab 9: Assignment 1 -- Add a Directly Contradicting Source
Adds source S4 that directly contradicts S1's hallucination-reduction findings.
Updates compare() and synthesize() to report a genuine contradiction (not a gap)
and states plausible reasons for the discrepancy.
"""

SOURCES_WITH_CONTRADICTION = [
    {"id": "S1", "type": "peer-reviewed paper", "date": "2026-02",
     "claim": "RAG reduces hallucination rate by 41% on domain QA vs non-retrieval baseline.",
     "evidence": "200 held-out questions from a medical knowledge base.",
     "limitation": "Single-domain medical Q&A; fixed retrieval corpus."},
    {"id": "S4", "type": "independent conference paper", "date": "2026-06",
     "claim": "RAG showed no statistically significant reduction in hallucinations (<2% change) in multi-turn legal QA.",
     "evidence": "Empirical evaluation on 1,500 legal case queries with contradictory precedents.",
     "limitation": "Tested only legal case law where retrieved passages frequently had conflicting interpretations."},
]

def compare_contradictions(sources):
    conflicts = []
    # Identify conflict between S1 and S4
    s1 = next(s for s in sources if s["id"] == "S1")
    s4 = next(s for s in sources if s["id"] == "S4")
    
    conflicts.append({
        "type": "GENUINE_CONTRADICTION",
        "sources": ["S1", "S4"],
        "summary": "Direct disagreement on RAG hallucination reduction efficacy (S1 reports -41%, S4 reports <2% delta).",
        "plausible_reasons": [
            "Domain difference: structured medical facts (S1) vs ambiguous legal precedents (S4).",
            "Query format: single-turn QA (S1) vs multi-turn conversational reasoning (S4).",
            "Corpus noise: S4 evaluated conflicting source passages which confuses retrieval augmentation."
        ]
    })
    return conflicts

def synthesize_with_conflict(sources, conflicts):
    lines = []
    lines.append("=== Executive Briefing: Contradiction Analysis ===")
    for s in sources:
        lines.append(f"[{s['id']} | {s['type']}] {s['claim']} (Evidence: {s['evidence']})")
    
    lines.append("\n=== Identified Substantive Conflict ===")
    for c in conflicts:
        lines.append(f"Conflict between {c['sources']}: {c['summary']}")
        lines.append("Plausible explanatory factors:")
        for r in c["plausible_reasons"]:
            lines.append(f"  * {r}")
    return "\n".join(lines)

if __name__ == "__main__":
    conflicts = compare_contradictions(SOURCES_WITH_CONTRADICTION)
    brief = synthesize_with_conflict(SOURCES_WITH_CONTRADICTION, conflicts)
    print(brief)
