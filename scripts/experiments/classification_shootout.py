"""Shootout: 4 alternative classifiers vs ClimateBERT baseline (read-only).

Reuses the exact chunks from ``baseline.json`` (no re-ingestion), runs
each candidate model, maps its native labels to E / S / G, applies the
same threshold = 0.3, and measures pct_E / pct_S / pct_G / n_passed.

A 60-chunk ground truth (20 E, 20 S, 20 G) is auto-seeded from the
strongest single-pillar chunks in the baseline; precision per pillar
and overall is computed for each model on that GT.

Touches no pipeline file.  All outputs land in
``scripts/experiments/results/shootout.json`` and (if reachable) the
MLflow experiment ``m2-classification-experiments``.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable

# ── Paths ───────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
EXP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EXP_DIR / "results"
BASELINE_PATH = RESULTS_DIR / "baseline.json"
GT_PATH = EXP_DIR / "ground_truth_60.json"
SHOOTOUT_PATH = RESULTS_DIR / "shootout.json"

THRESHOLD = 0.3
DOC_LABEL = "beltone"
MLFLOW_EXPERIMENT = "m2-classification-experiments"


# ── Same heuristic regexes as C1 — used ONLY for ground-truth seeding ───
E_KW = [r"energy", r"emission", r"carbon", r"climate", r"water", r"waste", r"GHG"]
S_KW = [r"employee", r"diversity", r"injury", r"community", r"training", r"gender"]
G_KW = [r"board", r"governance", r"audit", r"compliance", r"risk", r"director"]


def _compile(words: Iterable[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(words) + r")\b", re.IGNORECASE)


_E_RE, _S_RE, _G_RE = _compile(E_KW), _compile(S_KW), _compile(G_KW)


def _kw_counts(text: str) -> tuple[int, int, int]:
    return (
        len(_E_RE.findall(text)),
        len(_S_RE.findall(text)),
        len(_G_RE.findall(text)),
    )


# ── Ground truth: 20 pure-E + 20 pure-S + 20 pure-G chunks ──────────────
def build_ground_truth(chunks: list[dict]) -> list[dict]:
    """Pick 20 chunks per pillar with the strongest *single-pillar* keyword
    density (other pillars must score 0 — keeps the GT clean)."""
    if GT_PATH.exists():
        return json.loads(GT_PATH.read_text(encoding="utf-8"))

    scored = []
    for c in chunks:
        e, s, g = _kw_counts(c["text"])
        scored.append((c, e, s, g))

    pure_E = sorted([(c, e) for c, e, s, g in scored if e > 0 and s == 0 and g == 0],
                    key=lambda x: x[1], reverse=True)[:20]
    pure_S = sorted([(c, s) for c, e, s, g in scored if s > 0 and e == 0 and g == 0],
                    key=lambda x: x[1], reverse=True)[:20]
    pure_G = sorted([(c, g) for c, e, s, g in scored if g > 0 and e == 0 and s == 0],
                    key=lambda x: x[1], reverse=True)[:20]

    gt = []
    for c, _ in pure_E:
        gt.append({"chunk_id": c["chunk_id"], "page_number": c["page_number"],
                   "label": "E", "text_preview": c["text"][:300]})
    for c, _ in pure_S:
        gt.append({"chunk_id": c["chunk_id"], "page_number": c["page_number"],
                   "label": "S", "text_preview": c["text"][:300]})
    for c, _ in pure_G:
        gt.append({"chunk_id": c["chunk_id"], "page_number": c["page_number"],
                   "label": "G", "text_preview": c["text"][:300]})

    GT_PATH.write_text(json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8")
    return gt


# ── Native-label → E/S/G mapping ────────────────────────────────────────
# Maps lowercased model output label -> pillar letter. Anything not in the
# map yields "Unknown" (so the chunk is counted but not assigned a pillar).
_PILLAR_MAP: dict[str, dict[str, str]] = {
    # FinBERT-ESG 9 categories (yiyanghkust/finbert-esg-9-categories)
    "finbert-esg": {
        "climate change": "E",
        "natural capital": "E",
        "pollution & waste": "E",
        "pollution and waste": "E",
        "human capital": "S",
        "product liability": "S",
        "community relations": "S",
        "corporate governance": "G",
        "business ethics & values": "G",
        "business ethics and values": "G",
        # everything else (incl. "non-esg") -> Unknown
    },
    # EnvironmentalBERT — binary: env vs none
    "envbert": {
        "environmental": "E",
        "yes": "E",
        "label_1": "E",
        # "none"/"label_0" -> Unknown
    },
    # Plain FinBERT (ProsusAI/finbert) — sentiment, no ESG signal.
    # We log its predictions but every label maps to Unknown so pct_E/S/G
    # stays honest about its (lack of) pillar capability.
    "finbert": {},
    # nbroad/ESG-BERT — 26 SASB topics in snake_case. Mapping verified
    # against actual model output on the Beltone run.
    "esgbert": {
        # E
        "climate_change": "E",
        "ghg_emissions": "E",
        "air_quality": "E",
        "energy_management": "E",
        "fuel_management": "E",
        "water_and_wastewater_management": "E",
        "waste_and_hazardous_materials_management": "E",
        "ecological_impacts": "E",
        "natural_capital": "E",
        "physical_impacts_of_climate_change": "E",
        # S
        "human_rights_and_community_relations": "S",
        "labor_practices": "S",
        "employee_health_and_safety": "S",
        "employee_engagement_inclusion_and_diversity": "S",
        "customer_welfare": "S",
        "customer_privacy": "S",
        "data_security": "S",
        "access_and_affordability": "S",
        "product_quality_and_safety": "S",
        "selling_practices_and_product_labeling": "S",
        # G
        "business_ethics": "G",
        "competitive_behavior": "G",
        "management_of_legal_and_regulatory_framework": "G",
        "critical_incident_risk_management": "G",
        "systemic_risk_management": "G",
        "supply_chain_management": "G",
        "business_model_resilience": "G",
        "materials_sourcing_and_efficiency": "G",
        "product_design_and_lifecycle_management": "G",
        "director_removal": "G",
    },
}


def _to_pillar(model_key: str, raw_label: str) -> str:
    return _PILLAR_MAP[model_key].get(raw_label.lower().strip(), "Unknown")


# ── Models to test ──────────────────────────────────────────────────────
MODELS = [
    {"key": "finbert-esg", "hf": "yiyanghkust/finbert-esg-9-categories",
     "run_name": "finbert-esg",
     "note": "9 ESG categories; native pillar prediction."},
    {"key": "envbert", "hf": "ESGBERT/EnvironmentalBERT-environmental",
     "run_name": "envbert",
     "note": "Binary E specialist; S/G always Unknown by design."},
    {"key": "finbert", "hf": "ProsusAI/finbert",
     "run_name": "finbert",
     "note": "Financial sentiment — NOT an ESG classifier. Control run."},
    {"key": "esgbert", "hf": "nbroad/ESG-BERT",
     "run_name": "esgbert",
     "note": "26 SASB/GRI sustainability topics."},
]


# ── HF inference helper ─────────────────────────────────────────────────
def _score_model(hf_name: str, texts: list[str]) -> list[dict]:
    """Return [{'label': str, 'score': float, 'all_scores': {lbl: score, ...}}, ...]."""
    from transformers import pipeline as hf_pipeline

    clf = hf_pipeline(
        "text-classification",
        model=hf_name,
        top_k=None,         # return all labels w/ scores
        truncation=True,
        max_length=512,
    )
    truncated = [t[:2000] for t in texts]
    raw = clf(truncated, batch_size=16)
    out = []
    for row in raw:
        # row is a list of {label, score} dicts
        all_scores = {d["label"]: float(d["score"]) for d in row}
        best = max(all_scores.items(), key=lambda kv: kv[1])
        out.append({"label": best[0], "score": best[1], "all_scores": all_scores})
    return out


# ── Per-model evaluation ────────────────────────────────────────────────
def evaluate_model(spec: dict, chunks: list[dict], gt: list[dict]) -> dict:
    print(f"\n[model] {spec['hf']}  ({spec['note']})")
    t0 = time.time()
    preds = _score_model(spec["hf"], [c["text"] for c in chunks])
    print(f"        scored {len(preds)} chunks in {time.time()-t0:.1f}s")

    # "Passes" rule: total probability mass on ESG-mapped labels > threshold.
    # Pillar: argmax among labels that map to E / S / G (ignore Non-ESG/none).
    # This matches the C1 convention where score = P(positive-class), not
    # argmax confidence (which would let "Non-ESG" predictions slip through
    # whenever the model is confident they are non-ESG).
    by_chunk_id: dict[str, dict] = {}
    passed = []
    pillar_counts = {"E": 0, "S": 0, "G": 0, "Unknown": 0}
    for c, p in zip(chunks, preds):
        # Aggregate per-pillar probability mass
        pillar_mass = {"E": 0.0, "S": 0.0, "G": 0.0}
        for lbl, sc in p["all_scores"].items():
            pl = _to_pillar(spec["key"], lbl)
            if pl in pillar_mass:
                pillar_mass[pl] += sc
        esg_mass = sum(pillar_mass.values())
        # Pillar = argmax over E/S/G mass; "Unknown" if no ESG mass at all
        if esg_mass > 0:
            pillar = max(pillar_mass, key=pillar_mass.get)
        else:
            pillar = "Unknown"
        passes = esg_mass > THRESHOLD
        rec = {
            "chunk_id": c["chunk_id"],
            "page_number": c["page_number"],
            "raw_label": p["label"],            # argmax across ALL labels (for debug)
            "raw_score": round(p["score"], 4),  # its score
            "esg_mass": round(esg_mass, 4),
            "pillar_mass": {k: round(v, 4) for k, v in pillar_mass.items()},
            "pillar": pillar,
            "passes_threshold": passes,
        }
        by_chunk_id[c["chunk_id"]] = rec
        if passes:
            passed.append(rec)
            pillar_counts[pillar] += 1

    n_passed = len(passed)
    pct_E = round(100.0 * pillar_counts["E"] / n_passed, 2) if n_passed else 0.0
    pct_S = round(100.0 * pillar_counts["S"] / n_passed, 2) if n_passed else 0.0
    pct_G = round(100.0 * pillar_counts["G"] / n_passed, 2) if n_passed else 0.0
    pct_unknown = round(100.0 * pillar_counts["Unknown"] / n_passed, 2) if n_passed else 0.0

    # ── Precision on the 60-chunk ground truth ──────────────────────────
    # Precision_X = (# GT-X chunks where model predicted X) / (# GT-X chunks).
    # On a fixed GT this is precision = recall = accuracy per class; we
    # report it as "precision" per the spec's column name.
    gt_by_label = {"E": [], "S": [], "G": []}
    for g in gt:
        gt_by_label[g["label"]].append(g["chunk_id"])

    def _prec(label: str) -> float:
        ids = gt_by_label[label]
        if not ids:
            return 0.0
        correct = sum(1 for cid in ids if by_chunk_id.get(cid, {}).get("pillar") == label)
        return round(correct / len(ids), 4)

    p_E, p_S, p_G = _prec("E"), _prec("S"), _prec("G")
    p_overall = round((p_E + p_S + p_G) / 3, 4)

    print(f"        n_passed={n_passed}  pct E/S/G/U = {pct_E}/{pct_S}/{pct_G}/{pct_unknown}")
    print(f"        precision E/S/G/overall = {p_E}/{p_S}/{p_G}/{p_overall}")

    return {
        "model_key": spec["key"],
        "model_hf": spec["hf"],
        "run_name": spec["run_name"],
        "n_chunks_total": len(chunks),
        "n_passed": n_passed,
        "pillar_counts_passed": pillar_counts,
        "pct_E": pct_E, "pct_S": pct_S, "pct_G": pct_G, "pct_unknown": pct_unknown,
        "precision_E": p_E, "precision_S": p_S, "precision_G": p_G,
        "precision_overall": p_overall,
        "per_chunk": list(by_chunk_id.values()),
    }


# ── MLflow (best-effort) ────────────────────────────────────────────────
def _mlflow_log_run(model_result: dict) -> str | None:
    try:
        # Silence MLflow's emoji-laden status prints on the Windows cp1252
        # console; the run still completes, just no banner.
        os.environ.setdefault("MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING", "false")
        import io
        import contextlib
        import mlflow

        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001"))
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), mlflow.start_run(run_name=model_result["run_name"]) as run:
            mlflow.log_params({
                "model_name": model_result["model_hf"],
                "threshold": THRESHOLD,
                "doc": DOC_LABEL,
            })
            mlflow.log_metrics({
                "pct_E": model_result["pct_E"],
                "pct_S": model_result["pct_S"],
                "pct_G": model_result["pct_G"],
                "n_passed": model_result["n_passed"],
                "precision_E": model_result["precision_E"],
                "precision_S": model_result["precision_S"],
                "precision_G": model_result["precision_G"],
                "precision_overall": model_result["precision_overall"],
            })
            return run.info.run_id
    except Exception as exc:
        print(f"[mlflow] skipped for {model_result['run_name']}: {exc}")
        return None


# ── Main ────────────────────────────────────────────────────────────────
def main() -> int:
    if not BASELINE_PATH.exists():
        print(f"Missing {BASELINE_PATH} — run classification_baseline.py first.", file=sys.stderr)
        return 1

    print(f"Loading baseline chunks from {BASELINE_PATH.name} ...")
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    chunks = baseline["per_chunk"]
    print(f"  {len(chunks)} chunks loaded.")

    print("Building / loading ground truth (60 chunks: 20 E + 20 S + 20 G) ...")
    gt = build_ground_truth(chunks)
    by_lbl: dict[str, int] = {"E": 0, "S": 0, "G": 0}
    for g in gt:
        by_lbl[g["label"]] = by_lbl.get(g["label"], 0) + 1
    print(f"  GT saved at {GT_PATH}  counts: {by_lbl}")

    # Run all 4 models
    results: list[dict] = []
    for spec in MODELS:
        try:
            results.append(evaluate_model(spec, chunks, gt))
            _mlflow_log_run(results[-1])
        except Exception as exc:
            print(f"  !! model {spec['key']} FAILED: {exc}")
            results.append({
                "model_key": spec["key"], "model_hf": spec["hf"],
                "run_name": spec["run_name"], "error": str(exc),
            })

    # ── Comparison table ────────────────────────────────────────────────
    print()
    print("=" * 90)
    print(f"{'Model':<14} {'n_passed':>10} {'pct_E':>8} {'pct_S':>8} {'pct_G':>8} {'prec_E':>8} {'prec_S':>8} {'prec_G':>8} {'prec':>8}")
    print("-" * 90)
    for r in results:
        if "error" in r:
            print(f"{r['run_name']:<14} ERROR: {r['error'][:80]}")
            continue
        print(f"{r['run_name']:<14} {r['n_passed']:>10} "
              f"{r['pct_E']:>8} {r['pct_S']:>8} {r['pct_G']:>8} "
              f"{r['precision_E']:>8} {r['precision_S']:>8} {r['precision_G']:>8} "
              f"{r['precision_overall']:>8}")
    print("=" * 90)

    # ── Best single model by balanced score ────────────────────────────
    # A simple "balance" measure: min(pct_E,pct_S,pct_G) — high only if all
    # three pillars are well represented. Then multiply by precision_overall.
    scored = []
    for r in results:
        if "error" in r or r["n_passed"] == 0:
            continue
        balance = min(r["pct_E"], r["pct_S"], r["pct_G"])
        composite = balance * r["precision_overall"]
        scored.append((r["run_name"], balance, r["precision_overall"], composite))
    scored.sort(key=lambda x: x[3], reverse=True)
    if scored:
        print("\nBalanced-pillar × precision ranking (composite = min(pct)*precision):")
        for name, bal, prec, comp in scored:
            print(f"  {name:<14}  min-pillar%={bal:5.2f}  precision={prec:.3f}  composite={comp:.3f}")
        print(f"\nBest single model on this metric: {scored[0][0]}")

    # ── Write shootout.json ────────────────────────────────────────────
    payload = {
        "doc": DOC_LABEL,
        "threshold": THRESHOLD,
        "n_chunks_total": len(chunks),
        "n_ground_truth": len(gt),
        "models": results,
    }
    SHOOTOUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {SHOOTOUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())