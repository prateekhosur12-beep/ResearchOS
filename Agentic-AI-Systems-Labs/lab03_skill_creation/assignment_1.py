"""Lab 3: Assignment 1 -- Handle a Multi-Claim Source
Adds a third article with multiple competing claims (e.g. cost reduction vs latency).
Extends apply_research_summary_skill to detect competing claims, select the most
evidence-supported claim, and explicitly record the selection rationale.
"""

ARTICLE_C = {
    "title": "Model Quantization and Serving Economics in Production",
    "text": (
        "In production benchmarks, 4-bit quantization reduced cloud hosting costs by 48% across 100,000 requests with rigorous telemetry. "
        "Separately, an informal developer poll suggested developer satisfaction improved slightly. "
        "The study was conducted only on FP16 base models and did not evaluate non-transformer architectures."
    ),
    "candidate_claims": [
        {"claim": "4-bit quantization reduced cloud hosting costs by 48%", "evidence_strength": "High (100,000 requests with rigorous telemetry)"},
        {"claim": "Developer satisfaction improved slightly", "evidence_strength": "Low (informal poll without metrics)"}
    ]
}

def apply_multi_claim_summary_skill(article):
    text = article["text"]
    sentences = [s.strip() for s in text.split(".") if s.strip()]

    candidates = article.get("candidate_claims", [])
    if candidates:
        # Rank by evidence strength
        selected = max(candidates, key=lambda c: "High" in c["evidence_strength"])
        claim = selected["claim"]
        evidence = selected["evidence_strength"]
        selection_note = f"Selected claim '{claim}' over {len(candidates)-1} competing claim(s) due to stronger empirical evidence."
    else:
        claim = sentences[0]
        evidence = sentences[1] if len(sentences) > 1 else "not stated in source"
        selection_note = "Single claim identified from source."

    limitation = next((s for s in sentences if "only" in s.lower()
                        or "did not evaluate" in s.lower()
                        or "may not generalize" in s.lower()), "not stated in source")
    
    takeaway = f"Undergraduate takeaway: {claim.rstrip('.')} (evidence-backed)."

    return {
        "claim": claim,
        "evidence": evidence,
        "selection_note": selection_note,
        "limitation": limitation,
        "takeaway": takeaway,
    }

if __name__ == "__main__":
    out_c = apply_multi_claim_summary_skill(ARTICLE_C)
    print(f"=== Multi-Claim Summary: {ARTICLE_C['title']} ===")
    print(f"Claim:          {out_c['claim']}")
    print(f"Evidence:       {out_c['evidence']}")
    print(f"Selection Note: {out_c['selection_note']}")
    print(f"Limitation:     {out_c['limitation']}")
    print(f"Takeaway:       {out_c['takeaway']}")
