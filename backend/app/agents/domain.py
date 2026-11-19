"""Discipline-specific research rules (Lab 13).

Domain packs are *data*, not code paths: adding a discipline means adding an entry
here, and every downstream skill/agent picks it up without modification.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True)
class DomainProfile:
    key: str
    label: str
    description: str
    evaluation_metrics: list[str] = field(default_factory=list)
    baseline_expectations: list[str] = field(default_factory=list)
    representative_datasets: list[str] = field(default_factory=list)
    reproducibility_checklist: list[str] = field(default_factory=list)
    venue_hints: list[str] = field(default_factory=list)
    formatting_standard: str = "IEEE"
    manuscript_rules: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


CS_AI = DomainProfile(
    key="computer_science",
    label="Computer Science / Artificial Intelligence",
    description=(
        "Empirical or systems research in computing. Claims must be tied to datasets, "
        "baselines, metrics and reproducible configurations."
    ),
    evaluation_metrics=[
        "Accuracy / Precision / Recall / F1",
        "mIoU or mAP for detection and segmentation",
        "AUC-ROC for imbalanced classification",
        "BLEU / ROUGE / BERTScore for generation",
        "Retrieval recall@k, nDCG, MRR for RAG systems",
        "Inference latency, throughput, memory footprint",
        "Statistical significance over ≥3 seeds (mean ± std)",
    ],
    baseline_expectations=[
        "Compare against at least one strong published baseline on the same dataset split",
        "Include an ablation isolating each proposed component",
        "Report the compute budget and hardware used",
        "Report failure cases and negative results, not only best runs",
    ],
    representative_datasets=[
        "Public benchmarks appropriate to the subfield (e.g. ImageNet, COCO, BEIR, MMLU)",
        "Domain datasets with documented licensing and splits",
    ],
    reproducibility_checklist=[
        "Code repository link with an explicit license",
        "Pinned dependency versions and random seeds",
        "Exact train/validation/test split definition",
        "Model checkpoints or the recipe to reproduce them",
        "Hardware and wall-clock budget",
    ],
    venue_hints=[
        "IEEE Transactions on Neural Networks and Learning Systems",
        "ACM Computing Surveys",
        "IEEE Access",
        "Pattern Recognition / Neurocomputing / Expert Systems with Applications",
        "Topical conferences: NeurIPS, ICML, ICLR, CVPR, ACL, KDD",
    ],
    formatting_standard="IEEE",
    manuscript_rules=[
        "No experimental numbers may be stated unless they come from a cited source.",
        "Every claim about prior work must carry a citation to a retrieved record.",
        "Proposed experiments must name the dataset, metric and baseline.",
        "Related work must be organised thematically, not as a paper-by-paper list.",
    ],
)

GENERIC = DomainProfile(
    key="generic",
    label="General Research",
    description="Discipline-neutral defaults for topics outside the configured packs.",
    evaluation_metrics=["Primary outcome measure defined by the study design"],
    baseline_expectations=["Compare against the established state of the art"],
    representative_datasets=["Documented, citable data sources"],
    reproducibility_checklist=["Data availability statement", "Method transparency"],
    venue_hints=["Peer-reviewed venues indexed in the retrieved records"],
    formatting_standard="APA",
    manuscript_rules=["Claims must be traceable to a cited source."],
)



def _pack(
    key: str,
    label: str,
    description: str,
    metrics: list[str],
    baselines: list[str],
    datasets: list[str],
    reproducibility: list[str],
    venues: list[str],
    formatting: str,
    rules: list[str],
) -> DomainProfile:
    return DomainProfile(
        key=key,
        label=label,
        description=description,
        evaluation_metrics=metrics,
        baseline_expectations=baselines,
        representative_datasets=datasets,
        reproducibility_checklist=reproducibility,
        venue_hints=venues,
        formatting_standard=formatting,
        manuscript_rules=rules,
    )


AGRICULTURE = _pack(
    "agriculture",
    "Agriculture / Precision Farming",
    "Field, remote-sensing and modelling research on crops, soil and water. Claims must "
    "name the region, season, crop and validation protocol.",
    [
        "Yield prediction error: RMSE / MAE / MAPE against measured yield",
        "R² and Nash-Sutcliffe efficiency (NSE) for crop and hydrological models",
        "Irrigation water productivity (kg yield per m³ water)",
        "Classification accuracy / F1 for crop, disease or stress detection",
        "IoU for field-boundary and parcel segmentation",
    ],
    [
        "Compare against a local agronomic baseline or official district yield statistics",
        "Compare against a simple weather-only or NDVI-only regression before claiming gains",
        "Report performance separately per crop and per agro-climatic zone",
    ],
    [
        "Sentinel-2 / Landsat surface reflectance time series",
        "Open agronomic trial data and national yield statistics for the study region",
        "Soil survey datasets with documented resolution and provenance",
    ],
    [
        "Crop, cultivar, region and season defined explicitly",
        "Sensor, revisit interval and cloud-masking procedure stated",
        "Train/test split by season or by field (never random pixel splits)",
        "Code and trained weights released with the paper",
    ],
    [
        "Computers and Electronics in Agriculture",
        "Agricultural Water Management",
        "Remote Sensing (MDPI) / ISPRS Journal of Photogrammetry",
        "Field Crops Research",
        "Precision Agriculture (Springer)",
    ],
    "APA",
    [
        "Agronomic claims must name crop, region and season; global claims need multi-region evidence.",
        "No yield or water-saving numbers may be stated without a cited source or reported experiment.",
        "Remote-sensing inputs must be described with sensor, resolution and date range.",
    ],
)

HEALTHCARE = _pack(
    "healthcare",
    "Healthcare / Clinical Informatics",
    "Clinical and health-services research. Evidence grading, cohort definition and "
    "regulatory constraints dominate what counts as a contribution.",
    [
        "Sensitivity, specificity, PPV/NPV and AUC with confidence intervals",
        "Calibration (Brier score, calibration slope) alongside discrimination",
        "Clinical utility: decision-curve analysis or net reclassification",
        "Time-to-event measures (hazard ratios, Kaplan-Meier) where relevant",
    ],
    [
        "Compare against current clinical standard of care or a published risk score",
        "Report external validation on an independent cohort",
        "Include a sample-size or power justification",
    ],
    [
        "Public clinical datasets with documented access terms (e.g. MIMIC, eICU, PhysioNet)",
        "Institutional cohorts with ethics approval references",
        "Registry data with version and extraction date",
    ],
    [
        "Ethics approval / data-use agreement stated",
        "Cohort inclusion-exclusion criteria and flow diagram",
        "Pre-registered analysis plan where applicable",
        "Missing-data handling and confounding control described",
    ],
    [
        "Journal of the American Medical Informatics Association",
        "The Lancet Digital Health",
        "npj Digital Medicine",
        "IEEE Journal of Biomedical and Health Informatics",
        "BMC Medical Informatics and Decision Making",
    ],
    "APA",
    [
        "Never state a clinical outcome without a cited study or reported trial result.",
        "Distinguish statistical association from clinical benefit.",
        "Patient data must be described at the aggregate level only.",
    ],
)

CYBERSECURITY = _pack(
    "cybersecurity",
    "Cybersecurity / Privacy",
    "Security, privacy and cryptography research. Threat model and adversarial "
    "evaluation are as important as the metric itself.",
    [
        "Detection rate at a fixed false-positive rate; ROC-AUC",
        "Attack success rate under an explicit adversary model",
        "Computational and communication overhead (ms, KB, gas)",
        "Formal security properties (IND-CPA, unforgeability) where claimed",
    ],
    [
        "Compare against a published detector or protocol on the same dataset",
        "Evaluate against adaptive adversaries, not only static attack sets",
        "Report performance on concept-drifted or newer attack families",
    ],
    [
        "Public intrusion-detection corpora (e.g. CIC-IDS, UNSW-NB15) with version notes",
        "Standard cryptographic test vectors",
        "Blockchain testnets with stated consensus and block parameters",
    ],
    [
        "Threat model written explicitly (attacker capability, goal, knowledge)",
        "Dataset generation procedure and labelling rules",
        "Reproducible environment (container image or pinned dependencies)",
    ],
    [
        "IEEE Transactions on Information Forensics and Security",
        "Computers & Security",
        "Journal of Cybersecurity (Oxford)",
        "USENIX Security / ACM CCS / IEEE S&P (conferences)",
    ],
    "IEEE",
    [
        "Never claim security without a stated threat model and evaluation.",
        "Distinguish a prototype evaluation from a production deployment.",
        "Do not assert compliance with a standard without citing its clause.",
    ],
)

ROBOTICS = _pack(
    "robotics",
    "Robotics / Autonomous Systems",
    "Perception, planning and control research. Real-world validity depends on "
    "platform, environment and safety evaluation.",
    [
        "Task success rate and intervention count",
        "Localisation error (ATE/RPE) and map quality",
        "Path length, time-to-goal and collision rate",
        "Control tracking error and settling time",
    ],
    [
        "Compare against a classical planner/controller baseline",
        "Report performance across at least two environments or platforms",
        "Include failure-mode analysis and recovery behaviour",
    ],
    [
        "Public robotics datasets and simulation benchmarks (e.g. KITTI, nuScenes, Habitat)",
        "Platform specifications and sensor calibration",
        "Sim-to-real transfer protocol",
    ],
    [
        "Hardware, sensors and calibration described",
        "Simulation configuration and randomisation ranges",
        "Safety and human-interaction protocol stated",
    ],
    [
        "IEEE Transactions on Robotics",
        "IEEE Robotics and Automation Letters",
        "Journal of Field Robotics",
        "ICRA / IROS / RSS (conferences)",
    ],
    "IEEE",
    [
        "Never report a success rate without stating trials, environment and conditions.",
        "Simulation-only results must be labelled as such.",
        "Safety claims require an explicit hazard analysis.",
    ],
)

ENERGY = _pack(
    "energy",
    "Renewable Energy / Storage",
    "Energy systems and materials research. Round-trip efficiency, degradation and "
    "lifecycle economics frame the contribution.",
    [
        "Round-trip efficiency (%) and energy/power density (Wh/kg, W/kg)",
        "Capacity retention and degradation rate per cycle",
        "Levelised cost of storage (LCOS) or cost per kWh",
        "Lifecycle impacts (kg CO2e per kWh) where claimed",
    ],
    [
        "Compare against commercial or literature cell/chemistry baselines",
        "Report ageing over >=500 cycles where feasible",
        "State measurement standard and test conditions (C-rate, temperature)",
    ],
    [
        "Public battery datasets and standard test protocols",
        "Material characterisation data with instrument details",
        "Grid or load profiles for system-level studies",
    ],
    [
        "Cell chemistry, format and test protocol stated",
        "Measurement uncertainty and instrument calibration",
        "Second-life or recycling assumptions made explicit",
    ],
    [
        "Journal of Power Sources",
        "Journal of Energy Storage",
        "Applied Energy",
        "Renewable and Sustainable Energy Reviews",
        "IEEE Transactions on Sustainable Energy",
    ],
    "APA",
    [
        "Never state an efficiency or cost figure without a cited source or measured result.",
        "Distinguish laboratory cell performance from pack- or system-level performance.",
        "Recycling and second-life claims must state the boundary of the assessment.",
    ],
)

CLIMATE = _pack(
    "climate",
    "Climate / Environmental Science",
    "Climate and environmental research. Uncertainty quantification, scenario choice "
    "and spatial scale are central to any claim.",
    [
        "Bias and RMSE against observations or reanalysis",
        "Skill scores (e.g. Brier skill score, Taylor diagram metrics)",
        "Trend significance with uncertainty intervals",
        "Scenario-conditional projections with ensemble spread",
    ],
    [
        "Compare against observational reference or reanalysis products",
        "Use multi-model ensembles rather than a single model",
        "Report uncertainty explicitly, not only central estimates",
    ],
    [
        "CMIP / ERA5 / satellite products with version and citation",
        "Station observations with quality-control notes",
    ],
    [
        "Model version, forcing scenario and resolution stated",
        "Calibration/validation periods defined",
        "Data and code availability statement",
    ],
    [
        "Nature Climate Change / Nature Sustainability",
        "Environmental Research Letters",
        "Journal of Climate",
        "Climatic Change",
    ],
    "APA",
    [
        "Every projection must name its scenario, period and model ensemble.",
        "Do not present a single-model result as a consensus.",
        "Distinguish detection of change from attribution of cause.",
    ],
)

EDUCATION = _pack(
    "education",
    "Education / Learning Sciences",
    "Educational research. Study design, sampling and ethics determine what can be "
    "inferred about learning.",
    [
        "Learning gain (pre/post effect size, Cohen's d)",
        "Assessment reliability and validity evidence",
        "Engagement and retention measures",
        "Qualitative coding reliability where applicable",
    ],
    [
        "Compare against a business-as-usual control condition",
        "Report effect sizes with confidence intervals, not only p-values",
        "Describe the population and sampling strategy",
    ],
    [
        "Institutional course data with ethics approval",
        "Public learning datasets with documented consent terms",
    ],
    [
        "Ethics approval and consent procedure",
        "Instrument and rubric documentation",
        "Attrition and missing-data handling",
    ],
    [
        "Computers & Education",
        "British Journal of Educational Technology",
        "IEEE Transactions on Learning Technologies",
        "International Journal of Educational Technology in Higher Education",
    ],
    "APA",
    [
        "Never generalise a single-course result to all learners.",
        "Distinguish measured learning gains from self-reported perception.",
        "Student data must be aggregated and de-identified.",
    ],
)

ECONOMICS = _pack(
    "economics",
    "Economics / Social Science",
    "Economic and social research. Identification strategy matters more than the "
    "number of observations.",
    [
        "Effect size with confidence intervals (elasticities, treatment effects)",
        "Model fit and out-of-sample forecast error (RMSE, MAE)",
        "Robustness across alternative specifications",
        "Welfare or policy-relevant summary measures",
    ],
    [
        "Compare against an identified baseline or a naive forecasting benchmark",
        "Report robustness checks and placebo tests",
        "Justify the identification strategy explicitly",
    ],
    [
        "Official statistics with release version",
        "Administrative microdata with access terms",
        "Survey data with weighting and sample design notes",
    ],
    [
        "Data source, vintage and revision stated",
        "Identification assumptions spelled out and tested",
        "Replication package with code and derived data",
    ],
    [
        "American Economic Review / AEJ: Applied",
        "Journal of Development Economics",
        "World Development",
        "Technological Forecasting and Social Change",
    ],
    "APA",
    [
        "Never state a causal effect without an identification strategy.",
        "Distinguish correlation, prediction and causation.",
        "Policy claims must state the population and period they apply to.",
    ],
)

NETWORKS = _pack(
    "networks",
    "Computer Networks / Distributed Systems",
    "Networking and distributed-systems research. Workload, topology and failure "
    "assumptions define the validity of any performance claim.",
    [
        "Throughput, goodput and latency percentiles (p50/p95/p99)",
        "Packet loss and jitter under stated load",
        "Control-plane convergence time and overhead",
        "Resource cost (CPU, memory, energy per node)",
    ],
    [
        "Compare against a deployed protocol or a strong published system",
        "Evaluate under realistic and adversarial network conditions",
        "Report tail latency, not only averages",
    ],
    [
        "Public network traces or emulated topologies with parameters",
        "Testbed description with hardware and link characteristics",
        "Simulation configuration files",
    ],
    [
        "Topology, link parameters and workload generator described",
        "Repeat counts and variance reported",
        "Artifact evaluation package where possible",
    ],
    [
        "IEEE/ACM Transactions on Networking",
        "Computer Networks (Elsevier)",
        "IEEE Transactions on Network and Service Management",
        "SIGCOMM / NSDI / CoNEXT (conferences)",
    ],
    "IEEE",
    [
        "Never report throughput without workload and topology.",
        "Simulation results must be labelled as simulation.",
        "Distinguish prototype measurements from production deployment.",
    ],
)

DOMAINS: dict[str, DomainProfile] = {
    CS_AI.key: CS_AI,
    AGRICULTURE.key: AGRICULTURE,
    HEALTHCARE.key: HEALTHCARE,
    CYBERSECURITY.key: CYBERSECURITY,
    ROBOTICS.key: ROBOTICS,
    ENERGY.key: ENERGY,
    CLIMATE.key: CLIMATE,
    EDUCATION.key: EDUCATION,
    ECONOMICS.key: ECONOMICS,
    NETWORKS.key: NETWORKS,
    GENERIC.key: GENERIC,
}

ALIASES = {
    "cs": "computer_science",
    "ai": "computer_science",
    "artificial intelligence": "computer_science",
    "machine learning": "computer_science",
    "computer science": "computer_science",
    "cse": "computer_science",
    "computer networks": "networks",
    "networking": "networks",
    "distributed systems": "networks",
    "agriculture": "agriculture",
    "agri": "agriculture",
    "precision agriculture": "agriculture",
    "farming": "agriculture",
    "healthcare": "healthcare",
    "health": "healthcare",
    "medicine": "healthcare",
    "medical": "healthcare",
    "clinical": "healthcare",
    "cybersecurity": "cybersecurity",
    "security": "cybersecurity",
    "privacy": "cybersecurity",
    "blockchain": "cybersecurity",
    "robotics": "robotics",
    "robots": "robotics",
    "autonomous systems": "robotics",
    "energy": "energy",
    "renewable energy": "energy",
    "battery": "energy",
    "storage": "energy",
    "climate": "climate",
    "climate science": "climate",
    "environment": "climate",
    "education": "education",
    "learning sciences": "education",
    "economics": "economics",
    "social science": "economics",
    "default": "generic",
    "auto": "generic",
    "other": "generic",
}

#: Keyword → domain routing used when the caller does not pick a pack explicitly.
_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "computer_science": (
        "neural", "deep learning", "machine learning", "yolo", "transformer", "llm",
        "large language model", "algorithm", "dataset", "computer vision", "segmentation",
        "classification", "detection", "reinforcement learning", "graph neural",
        "retrieval-augmented", "embedding",
    ),
    "agriculture": (
        "crop", "yield", "irrigation", "soil", "agricultur", "farm", "precision farming",
        "harvest", "fertilizer", "agronom", "sentinel-2", "ndvi",
    ),
    "healthcare": (
        "clinical", "patient", "medical", "health", "diagnos", "hospital", "tumor",
        "disease", "ehr", "biomedic",
    ),
    "cybersecurity": (
        "security", "attack", "privacy", "cryptograph", "blockchain", "authentication",
        "intrusion", "malware", "zero-knowledge", "identity",
    ),
    "robotics": (
        "robot", "manipulat", "slam", "autonomous", "drone", "uav", "navigation",
        "lidar", "actuator",
    ),
    "energy": (
        "battery", "batteries", "energy storage", "photovoltaic", "solar", "wind",
        "renewable", "recycling", "second-life", "lithium", "grid",
    ),
    "climate": (
        "climate", "emission", "carbon", "temperature rise", "precipitation",
        "hydrolog", "ecosystem", "environment",
    ),
    "education": (
        "student", "learning outcome", "curriculum", "classroom", "pedagog",
        "education", "teacher",
    ),
    "economics": (
        "economic", "market", "policy", "finance", "trade", "labour", "labor",
        "pricing", "welfare",
    ),
    "networks": (
        "network", "5g", "6g", "sdn", "tcp", "routing", "latency", "edge computing",
        "distributed system", "wireless",
    ),
}


def get_domain(key: str | None) -> DomainProfile:
    if not key:
        return CS_AI
    k = key.strip().lower()
    k = ALIASES.get(k, k)
    return DOMAINS.get(k, CS_AI if "comput" in k or "artificial" in k else GENERIC)


def list_domains() -> list[dict[str, Any]]:
    return [d.as_dict() for d in DOMAINS.values()]


def detect_domain(topic: str, instructions: str = "") -> str:
    """Route a topic to a pack by keyword evidence. Returns ``generic`` when unsure."""
    text = f"{topic} {instructions}".lower()
    scores: dict[str, int] = {}
    for key, hints in _DOMAIN_HINTS.items():
        score = sum(1 for h in hints if h in text)
        if score:
            scores[key] = score
    if not scores:
        return "computer_science" if any(
            k in text for k in ("neural", "deep learning", "algorithm", "model", "dataset")
        ) else "generic"
    return max(scores.items(), key=lambda kv: kv[1])[0]


def resolve_domain(key: str | None, topic: str = "", instructions: str = "") -> str:
    """Turn a user-supplied domain (or 'auto') into a real pack key."""
    cleaned = (key or "").strip().lower()
    if cleaned in ("", "auto", "detect", "default"):
        return detect_domain(topic, instructions)
    alias = ALIASES.get(cleaned, cleaned)
    return alias if alias in DOMAINS else detect_domain(topic, instructions)
