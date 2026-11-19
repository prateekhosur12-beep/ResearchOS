"""Deterministic abstract-text analysis.

Used by every skill as the no-LLM path. Everything produced here is an *extraction*
from the retrieved abstract — never an inference about work the paper did not
report. Callers label these outputs accordingly.
"""

from __future__ import annotations

import re
from typing import Any

METHOD_SIGNALS: dict[str, list[str]] = {
    "survey": ["survey", "review", "overview", "systematic literature"],
    "transformer": ["transformer", "self-attention", "bert", "gpt", "vision transformer"],
    "cnn": ["cnn", "convolutional", "resnet", "yolo", "u-net", "vgg"],
    "federated": ["federated", "privacy-preserving", "differential privacy"],
    "reinforcement": ["reinforcement learning", "policy gradient", "q-learning", "ppo"],
    "rag": ["retrieval-augmented", "retrieval augmented", "rag pipeline"],
    "gnn": ["graph neural", "gnn", "graph convolution"],
    "diffusion": ["diffusion model", "denoising diffusion"],
    "llm": ["large language model", "llm", "foundation model"],
    "transfer": ["transfer learning", "fine-tun", "pre-trained"],
    "optimization": ["genetic algorithm", "particle swarm", "bayesian optimization"],
    "statistical": ["regression", "classification", "clustering", "statistical"],
}

DATASET_PATTERNS = [
    r"\b([A-Z][A-Za-z0-9\-]{2,}(?:[- ][A-Z][A-Za-z0-9]{1,})*)\s+(?:dataset|benchmark|corpus)",
    r"\b(?:dataset|benchmark|corpus)\s+(?:called|named)\s+([A-Z][A-Za-z0-9\-]+)",
]

KNOWN_DATASETS = [
    "ImageNet", "COCO", "CIFAR-10", "CIFAR-100", "MNIST", "Cityscapes", "KITTI", "Pascal VOC",
    "SQuAD", "GLUE", "MMLU", "RAGAS", "BEIR", "MS MARCO", "ChestX-ray14", "MIMIC-III",
    "MIMIC-IV", "BraTS", "ISIC", "ADE20K", "nuScenes", "BDD100K", "RDD2022", "Kaggle",
    "PhysioNet", "UCI", "SVHN", "OpenImages", "TextVQA", "HotpotQA", "Natural Questions",
]

LIMITATION_MARKERS = [
    "limitation", "limited to", "drawback", "shortcoming", "future work", "remains challenging",
    "does not address", "we do not", "cannot", "lack of", "constrained by", "fails to",
    "open problem", "not yet", "still an open", "under-explored", "underexplored",
]

PROBLEM_MARKERS = [
    "challenge", "problem", "difficult", "however", "bottleneck", "poor performance",
    "suffer", "issue", "hard to", "remains", "critical",
]

FINDING_MARKERS = [
    "results show", "we show", "experiments show", "outperform", "improve", "achiev",
    "demonstrate", "increase", "reduce", "gain", "accuracy", "f1", "%",
]

METRIC_PATTERNS = [
    "accuracy", "precision", "recall", "f1", "f1-score", "auc", "roc", "map", "miou",
    "bleu", "rouge", "perplexity", "latency", "throughput", "psnr", "ssim", "wer", "cer",
    "recall@k", "ndcg", "mrr", "dice", "iou", "hit rate", "false positive rate",
]


def sentences(text: str | None) -> list[str]:
    if not text:
        return []
    cleaned = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", cleaned)
    return [p.strip() for p in parts if len(p.strip()) > 25]


def first_match(sents: list[str], markers: list[str], limit: int = 2) -> list[str]:
    hits = []
    for s in sents:
        low = s.lower()
        if any(m in low for m in markers):
            hits.append(s)
        if len(hits) >= limit:
            break
    return hits


def extract_method_signals(text: str) -> list[str]:
    low = text.lower()
    return [name for name, kws in METHOD_SIGNALS.items() if any(k in low for k in kws)]


def extract_datasets(text: str) -> list[str]:
    found: list[str] = []
    for ds in KNOWN_DATASETS:
        if re.search(rf"\b{re.escape(ds)}\b", text, re.I):
            found.append(ds)
    for pattern in DATASET_PATTERNS:
        for m in re.finditer(pattern, text):
            cand = m.group(1).strip()
            if 3 <= len(cand) <= 60 and cand not in found:
                found.append(cand)
    return found[:5]


def extract_metrics(text: str) -> list[str]:
    low = text.lower()
    return [m for m in METRIC_PATTERNS if m in low][:8]


def analyse_abstract(title: str, abstract: str | None) -> dict[str, Any]:
    """Structured extraction. `basis` records exactly what the text supported."""
    sents = sentences(abstract)
    if not abstract:
        return {
            "problem": None,
            "methodology": None,
            "datasets": [],
            "findings": [],
            "limitations": [],
            "metrics": [],
            "method_signals": extract_method_signals(title),
            "basis": "abstract unavailable — only the title was available",
            "usable": False,
        }
    return {
        "problem": (first_match(sents, PROBLEM_MARKERS, 1) or [sents[0] if sents else None])[0],
        "methodology": (first_match(sents, ["we propose", "we present", "this paper", "we introduce", "we develop", "we design", "using", "based on", "framework", "method"], 1) or [None])[0],
        "datasets": extract_datasets(f"{title} {abstract}"),
        "findings": first_match(sents, FINDING_MARKERS, 2),
        "limitations": first_match(sents, LIMITATION_MARKERS, 3),
        "metrics": extract_metrics(abstract),
        "method_signals": extract_method_signals(f"{title} {abstract}"),
        "basis": "extracted verbatim from the retrieved abstract (no language model involved)",
        "usable": True,
    }


def keywords(text: str, k: int = 12) -> list[str]:
    from app.services.scholarly.ranking import tokenize

    counts: dict[str, int] = {}
    for tok in tokenize(text):
        counts[tok] = counts.get(tok, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:k]]
