# Agentic AI Systems — All 14 Labs & Assignments

### School of Computer Science & Engineering | KLE Technological University

This repository contains complete, tested, offline-runnable Python implementations for all **14 Labs** and all **28 Graded Assignments** from the **Agentic AI Systems** course.

---

## Repository Structure

```text
Agentic-AI-Systems-Labs/
├── README.md
├── lab01_agent_vs_chatbot/
│   ├── reference.py          # Study Planner: Goal -> Plan -> Act -> Observe -> Revise loop
│   ├── assignment_1.py       # Two independent rounds of feedback mutating existing plan
│   └── assignment_2.py       # Pre-finalization conflict detection for busy days
├── lab02_tool_using_agent/
│   ├── reference.py          # Campus Data Assistant: calculator, read_csv, mock_events_api
│   ├── assignment_1.py       # Low turnout notification tool with trace justification
│   └── assignment_2.py       # 3-tool chain: CSV reader -> category filter -> calculator
├── lab03_skill_creation/
│   ├── reference.py          # Research Summary Skill: claim, evidence, limitation, takeaway
│   ├── assignment_1.py       # Multi-claim source detection & evidence-based selection
│   └── assignment_2.py       # Low-evidence input handling without fabrication
├── lab04_memory_and_retrieval/
│   ├── reference.py          # Project Assistant: short-term session vs long-term scoped memory
│   ├── assignment_1.py       # Topic isolation: zero cross-topic leakage (database vs hosting)
│   └── assignment_2.py       # Retention & staleness policy warning for aged records
├── lab05_mcp_connector/
│   ├── reference.py          # Mini MCP Server: resource vs tool & capability manifest
│   ├── assignment_1.py       # Dynamic capability discovery (list_files) without hardcoding
│   └── assignment_2.py       # Directory jail permission boundary (/safe/) with traversal tests
├── lab06_opencla_runtime/
│   ├── reference.py          # Mini Personal Agent Runtime: 6 OpenCLA runtime components
│   ├── assignment_1.py       # Per-user rate limiting (max 3 tasks) at interface boundary
│   └── assignment_2.py       # Failure escalation: human handoff after 2 consecutive errors
├── lab07_agentic_node_graph/
│   ├── reference.py          # Campus App Builder: graph execution & failure simulation
│   ├── assignment_1.py       # Security scan node inserted between builder and tester
│   └── assignment_2.py       # Retry limit: exactly 1 retry on builder before human escalation
├── lab08_parallel_swarm/
│   ├── reference.py          # Hackathon Planner: ThreadPool concurrent swarm & merge
│   ├── assignment_1.py       # 5th role (Marketing agent) & multi-agent budget conflict resolution
│   └── assignment_2.py       # Decentralized peer critique across all swarm roles
├── lab09_deep_research_agent/
│   ├── reference.py          # AI Topic Briefing: question -> extract -> compare -> synthesize
│   ├── assignment_1.py       # Substantive contradiction detection (S4 vs S1) with root causes
│   └── assignment_2.py       # Source quality tiers & transparent down-weighting in synthesis
├── lab10_cloud_ops_agent/
│   ├── reference.py          # Failed Deployment: diagnose, correlate, draft approval request
│   ├── assignment_1.py       # DB connection pool exhaustion diagnosis & error signature
│   └── assignment_2.py       # Bifurcated remediation: safe auto-fix vs gated rollback
├── lab11_agentic_sdlc_factory/
│   ├── reference.py          # SDLC Pipeline: stories -> design -> code -> test -> review -> release
│   ├── assignment_1.py       # Concurrent stories (CSV + JSON) with end-to-end lineage tracing
│   └── assignment_2.py       # Deliberate code bug caught by independent AC test suite
├── lab12_safety_governance/
│   ├── reference.py          # Guardrails: least privilege, eval gate, privacy scrub, rollback
│   ├── assignment_1.py       # Financial cost control ($500 cap) and anti-bypass check
│   └── assignment_2.py       # Mandatory re-evaluation gate after every 5 proposals
├── lab13_discipline_engineering/
│   ├── reference.py          # Mechanical Engineering: predictive vibration/temperature maintenance
│   ├── assignment_1.py       # Electrical Engineering: transformer load forecasting & safety gate
│   └── assignment_2.py       # Degradation trend escalation: 3 consecutive warnings trigger inspection
└── lab14_capstone_project/
    ├── reference.py          # Full Worklet: node graph, 3+ tools, skill, memory, trace, audit
    ├── assignment_1.py       # Multi-skill orchestration (triage vs password reset guidance)
    └── assignment_2.py       # 6-case evaluation suite including adversarial prompt injection defense
```

---

## How to Run

Every script is 100% self-contained and uses standard Python library modules (no third-party dependencies or external API keys needed).

```bash
# Run any reference file:
python lab01_agent_vs_chatbot/reference.py

# Run any assignment file:
python lab01_agent_vs_chatbot/assignment_1.py
python lab01_agent_vs_chatbot/assignment_2.py
```

---

## Quick Git Push Instructions

To push this entire folder to your personal GitHub repository:

```bash
cd "Agentic-AI-Systems-Labs"

# Initialize git repository
git init

# Add all files
git add .

# Initial commit
git commit -m "Add complete reference code and solutions for Labs 1 to 14"

# Set branch to main
git branch -M main

# Link to your remote GitHub repository
git remote add origin https://github.com/<YOUR_USERNAME>/<YOUR_REPO_NAME>.git

# Push
git push -u origin main
```
