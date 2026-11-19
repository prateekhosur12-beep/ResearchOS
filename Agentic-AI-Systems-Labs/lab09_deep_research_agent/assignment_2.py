"""Lab 9: Assignment 2 -- Weight Sources by Quality
Assigns quality tiers to sources (peer-reviewed > independent benchmark > vendor blog).
Uses tiers in synthesize() to decide which claim to favor in contradictions,
while explicitly disclosing that lower-tier claims were down-weighted rather than omitted.
"""

TIERED_SOURCES = [
    {"id": "S1", "tier": "peer-reviewed paper", "tier_weight": 3,
     "claim": "RAG reduces hallucination rate by 41% on domain QA.",
     "evidence": "200 held-out medical questions.", "limitation": "Single domain."},
    {"id": "S2", "tier": "vendor engineering blog", "tier_weight": 1,
     "claim": "RAG eliminates 95% of all factual errors in production.",
     "evidence": "Marketing whitepaper without public test data.", "limitation": "Vendor self-interest bias."},
]

def synthesize_weighted(sources):
    lines = []
    lines.append("=== Quality-Weighted Research Synthesis ===")
    
    # Sort sources by tier weight descending
    sorted_sources = sorted(sources, key=lambda s: s["tier_weight"], reverse=True)
    
    primary = sorted_sources[0]
    secondary = sorted_sources[1]
    
    lines.append(f"Primary Finding (Favored): [{primary['id']}] {primary['claim']}")
    lines.append(f"  Justification: Grounded in Tier-{primary['tier_weight']} source ({primary['tier']}).")
    lines.append(f"\nSecondary Finding (Down-weighted): [{secondary['id']}] {secondary['claim']}")
    lines.append(f"  Disclosure: Down-weighted from 95% down to 41% due to Tier-{secondary['tier_weight']} classification ({secondary['tier']}) and lack of independent peer validation.")
    
    return "\n".join(lines)

if __name__ == "__main__":
    summary = synthesize_weighted(TIERED_SOURCES)
    print(summary)
