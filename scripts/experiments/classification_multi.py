"""Multi-model architecture comparison — A (sequential), B (ensemble),
C (3-stage hierarchical) — vs the C2 single-model winner.

Pass/pillar decisions are composed from cached per-chunk scores in
``baseline.json`` (ClimateBERT) and ``shootout.json`` (finbert-esg,
esgbert, finbert-sentiment) — no model is re-run to make a decision.
Latency and RAM, however, ARE measured with fresh, warmed pipelines on
a small sample so production-cost numbers are honest.

Three architectures tested:
  A — Sequential : ClimateBERT (esg gate, score>0.3)
                   → finbert-esg-9-categories (pillar on survivors)
  B — Ensemble   : ClimateBERT  +  finbert-esg  +  nbroad/ESG-BERT
                   2-of-3 majority on "is ESG?";
                   pillar = majority of passing voters
                   (ties → highest-confidence vote;
                    ClimateBERT can only vote E because it is E-only)
  C — Hierarchy  : FinBERT-sentiment (max-class > 0.5 → business content)
                   → ClimateBERT (esg gate, score > 0.3)
                   → finbert-esg-9-categories (pillar)

Spec note: the user listed "ClimateBERT + best-from-C2 + finbert-esg" for
arch B. The C2 winner IS finbert-esg, so the third voter is the C2
runner-up (nbroad/ESG-BERT) to keep three INDEPENDENT votes.

Touches no pipeline file.  Writes ``results/multi_arch.json`` and (if
the MLflow server is up) one run per arch under
``m2-classification-experiments``.
"""

from __future__ import annotations

import gc
import io
import json
import os
import re
import sys
import time
import contextlib
from pathlib import Path
from typing import Any, Iterable

# ── Paths ───────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
EXP_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EXP_DIR / "results"
BASELINE_PATH = RESULTS_DIR / "baseline.json"
SHOOTOUT_PATH = RESULTS_DIR / "shootout.json"
GT_PATH = EXP_DIR / "ground_truth_60.json"
OUT_PATH = RESULTS_DIR / "multi_arch.json"

THRESHOLD = 0.3
FINBERT_BUSINESS_GATE = 0.5     # arch C, stage 1
DOC_LABEL = "beltone"
MLFLOW_EXPERIMENT = "m2-classification-experiments"

LATENCY_SAMPLE = 50             # chunks used for warm latency timing
LATENCY_WARMUP = 5              # warmup batches discarded

# ── Same per-model pillar maps as C2 (kept inline so this script stands
# alone; verified against actual model outputs in C2) ───────────────────
_PILLAR_MAP: dict[str, dict[str, str]] = {
    "finbert-esg": {
        "climate change": "E", "natural capital": "E",
        "pollution & waste": "E", "pollution and waste": "E",
        "human capital": "S", "product liability": "S",
        "community relations": "S",
        "corporate governance": "G",
        "business ethics & values": "G",
        "business ethics and values": "G",
    },
    "esgbert": {
        # E
        "climate_change": "E", "ghg_emissions": "E", "air_quality": "E",
        "energy_management": "E", "fuel_management": "E",
        "water_and_wastewater_management": "E",
        "waste_and_hazardous_materials_management": "E",
        "ecological_impacts": "E", "natural_capital": "E",
        "physical_impacts_of_climate_change": "E",
        # S
        "human_rights_and_community_relations": "S",
        "labor_practices": "S", "employee_health_and_safety": "S",
        "employee_engagement_inclusion_and_diversity": "S",
        "customer_welfare": "S", "customer_privacy": "S",
        "data_security": "S", "access_and_affordability": "S",
        "product_quality_and_safety": "S",
        "selling_practices_and_product_labeling": "S",
        # G
        "business_ethics": "G", "competitive_behavior": "G",
        "management_of_legal_and_regulatory_framework": "G",
        "critical_incident_risk_management": "G",
        "systemic_risk_management": "G", "supply_chain_management": "G",
        "business_model_resilience": "G",
        "materials_sourcing_and_efficiency": "G",
        "product_design_and_lifecycle_management": "G",
        "director_removal": "G",
    },
}


# ── Cached score loaders ────────────────────────────────────────────────
def load_cached() -> tuple[list[dict], dict[str, dict[str, dict]], list[dict]]:
    """Return (chunks, by_model_by_chunk, ground_truth)."""
    base = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    shoot = json.loads(SHOOTOUT_PATH.read_text(encoding="utf-8"))
    gt = json.loads(GT_PATH.read_text(encoding="utf-8"))

    chunks = base["per_chunk"]
    by_model: dict[str, dict[str, dict]] = {}
    by_model["climatebert"] = {c["chunk_id"]: c for c in chunks}
    for m in shoot["models"]:
        if "per_chunk" not in m:
            continue
        by_model[m["model_key"]] = {r["chunk_id"]: r for r in m["per_chunk"]}
    return chunks, by_model, gt


# ── Architecture decision functions ─────────────────────────────────────
def _arch_A_decide(cid: str, cache: dict[str, dict[str, dict]]) -> dict:
    """Stage 1: ClimateBERT gate. Stage 2: finbert-esg pillar."""
    cb = cache["climatebert"][cid]
    if cb["climatebert_score"] <= THRESHOLD:
        return {"passes": False, "pillar": None,
                "stage1_score": cb["climatebert_score"], "stage2_pillar": None}
    fe = cache["finbert-esg"][cid]
    pillar = fe["pillar"] if fe["pillar"] in ("E", "S", "G") else "Unknown"
    return {"passes": True, "pillar": pillar,
            "stage1_score": cb["climatebert_score"],
            "stage2_pillar": pillar,
            "stage2_pillar_mass": fe.get("pillar_mass")}


def _arch_B_decide(cid: str, cache: dict[str, dict[str, dict]]) -> dict:
    """ClimateBERT + finbert-esg + esgbert, 2-of-3 vote on ESG-relevance.
    Pillar = majority among passing voters (ties → highest-confidence)."""
    cb = cache["climatebert"][cid]
    fe = cache["finbert-esg"][cid]
    eb = cache["esgbert"][cid]

    # ESG-relevance signal per voter
    cb_esg = cb["climatebert_score"] > THRESHOLD
    fe_esg = fe["esg_mass"] > THRESHOLD
    eb_esg = eb["raw_score"] > THRESHOLD   # esgbert: top-1 confidence

    votes_for = int(cb_esg) + int(fe_esg) + int(eb_esg)
    passes = votes_for >= 2

    if not passes:
        return {"passes": False, "pillar": None,
                "votes_for": votes_for, "cb_esg": cb_esg,
                "fe_esg": fe_esg, "eb_esg": eb_esg}

    # Pillar voting — each passing voter votes its argmax pillar with its
    # confidence; ClimateBERT can only vote E (its single signal).
    pillar_votes: list[tuple[str, float]] = []
    if cb_esg:
        pillar_votes.append(("E", cb["climatebert_score"]))
    if fe_esg and fe["pillar"] in ("E", "S", "G"):
        # Use the model's strongest pillar mass as the vote confidence
        pm = fe.get("pillar_mass", {})
        pillar_votes.append((fe["pillar"], pm.get(fe["pillar"], fe["esg_mass"])))
    if eb_esg and eb["pillar"] in ("E", "S", "G"):
        pm = eb.get("pillar_mass", {})
        pillar_votes.append((eb["pillar"], pm.get(eb["pillar"], eb["raw_score"])))

    # Count votes per pillar, tie-break by total confidence
    if not pillar_votes:
        pillar = "Unknown"
    else:
        tally: dict[str, list[float]] = {}
        for p, conf in pillar_votes:
            tally.setdefault(p, []).append(conf)
        # majority by count, tie-break by sum of confidences
        max_count = max(len(v) for v in tally.values())
        candidates = [p for p, v in tally.items() if len(v) == max_count]
        pillar = max(candidates, key=lambda p: sum(tally[p]))

    return {"passes": True, "pillar": pillar, "votes_for": votes_for,
            "cb_esg": cb_esg, "fe_esg": fe_esg, "eb_esg": eb_esg,
            "pillar_votes": pillar_votes}


def _arch_C_decide(cid: str, cache: dict[str, dict[str, dict]]) -> dict:
    """3-stage hierarchy: FinBERT-sentiment gate → ClimateBERT gate →
    finbert-esg pillar."""
    fb = cache["finbert"][cid]
    if fb["raw_score"] < FINBERT_BUSINESS_GATE:
        return {"passes": False, "pillar": None, "stopped_at": "stage1_business",
                "stage1_score": fb["raw_score"]}
    cb = cache["climatebert"][cid]
    if cb["climatebert_score"] <= THRESHOLD:
        return {"passes": False, "pillar": None, "stopped_at": "stage2_esg",
                "stage1_score": fb["raw_score"],
                "stage2_score": cb["climatebert_score"]}
    fe = cache["finbert-esg"][cid]
    pillar = fe["pillar"] if fe["pillar"] in ("E", "S", "G") else "Unknown"
    return {"passes": True, "pillar": pillar,
            "stage1_score": fb["raw_score"],
            "stage2_score": cb["climatebert_score"],
            "stage3_pillar": pillar,
            "stage3_pillar_mass": fe.get("pillar_mass")}


# ── Latency + RAM benchmarking ──────────────────────────────────────────
def _now_ms() -> float:
    return time.perf_counter() * 1000.0


def _rss_mb() -> float:
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)


def _bench_model(hf_name: str, texts: list[str], n_warm: int, n_meas: int) -> dict:
    """Load a model, warm it, time inference on a fixed sample, free it.

    Returns dict with: load_rss_mb (peak RSS after load), per_chunk_ms,
    total_ms.
    """
    from transformers import pipeline as hf_pipeline

    gc.collect()
    rss_before = _rss_mb()
    print(f"  loading {hf_name} (RSS {rss_before:.0f}MB)...")
    clf = hf_pipeline(
        "text-classification",
        model=hf_name,
        top_k=None,
        truncation=True,
        max_length=512,
    )
    rss_after_load = _rss_mb()
    delta = rss_after_load - rss_before
    print(f"    loaded (RSS {rss_after_load:.0f}MB, +{delta:.0f}MB)")

    warm_texts = texts[:n_warm]
    meas_texts = texts[:n_meas]
    truncated_warm = [t[:2000] for t in warm_texts]
    truncated_meas = [t[:2000] for t in meas_texts]

    clf(truncated_warm, batch_size=16)  # warmup, ignore timing
    t0 = _now_ms()
    clf(truncated_meas, batch_size=16)
    total_ms = _now_ms() - t0
    per_chunk_ms = total_ms / max(1, len(meas_texts))
    print(f"    timed {len(meas_texts)} chunks: {total_ms:.0f}ms total → {per_chunk_ms:.1f}ms/chunk")

    # free
    del clf
    gc.collect()
    return {"hf_name": hf_name, "load_delta_mb": round(delta, 1),
            "model_rss_mb": round(rss_after_load, 1),
            "total_ms": round(total_ms, 1),
            "per_chunk_ms": round(per_chunk_ms, 2)}


# ── Per-arch evaluation ─────────────────────────────────────────────────
def _evaluate(arch_name: str, decide_fn, cache, chunks: list[dict], gt: list[dict],
              per_model_latency: dict[str, dict], models_loaded: list[str],
              latency_chain: list[str]) -> dict:
    """Apply a decision function to every chunk and tally results.

    per_model_latency: { model_key -> {"per_chunk_ms": float, ...} }
    models_loaded: which models the arch keeps resident → RAM cost
    latency_chain: ordered list of (model_key, applies_to_fraction);
        special form "model:always" runs on every chunk;
        "model:after-X" runs only on chunks passing X (we compute the
        fraction empirically from the decisions).
    """
    decisions = {c["chunk_id"]: decide_fn(c["chunk_id"], cache) for c in chunks}
    passed = [c for c in chunks if decisions[c["chunk_id"]]["passes"]]
    n_passed = len(passed)
    pillars = {"E": 0, "S": 0, "G": 0, "Unknown": 0}
    for c in passed:
        p = decisions[c["chunk_id"]].get("pillar") or "Unknown"
        pillars[p] = pillars.get(p, 0) + 1
    pct_E = round(100.0 * pillars["E"] / n_passed, 2) if n_passed else 0.0
    pct_S = round(100.0 * pillars["S"] / n_passed, 2) if n_passed else 0.0
    pct_G = round(100.0 * pillars["G"] / n_passed, 2) if n_passed else 0.0
    pct_U = round(100.0 * pillars["Unknown"] / n_passed, 2) if n_passed else 0.0

    # Precision on GT
    gt_by_label: dict[str, list[str]] = {"E": [], "S": [], "G": []}
    for g in gt:
        gt_by_label[g["label"]].append(g["chunk_id"])

    def _prec(label: str) -> float:
        ids = gt_by_label[label]
        if not ids:
            return 0.0
        correct = sum(1 for cid in ids
                      if decisions.get(cid, {}).get("pillar") == label)
        return round(correct / len(ids), 4)

    p_E, p_S, p_G = _prec("E"), _prec("S"), _prec("G")
    p_overall = round((p_E + p_S + p_G) / 3, 4)

    # ── Latency: sum per-chunk cost weighted by gating fractions ────────
    # latency_chain format examples:
    #   [("climatebert", "always"), ("finbert-esg", "after:climatebert")]
    #   [("climatebert", "always"), ("finbert-esg", "always"), ("esgbert", "always")]
    #   [("finbert", "always"), ("climatebert", "after:finbert"),
    #    ("finbert-esg", "after:climatebert")]
    n_total = len(chunks)
    # Build per-stage passing counts from decisions for "after:X" weighting
    # ClimateBERT passes (cached):
    cb_passing = sum(1 for c in chunks if cache["climatebert"][c["chunk_id"]]["climatebert_score"] > THRESHOLD)
    # FinBERT sentiment passes (arch C stage 1):
    fb_passing = sum(1 for c in chunks if cache["finbert"][c["chunk_id"]]["raw_score"] >= FINBERT_BUSINESS_GATE)
    # ClimateBERT passes among FinBERT survivors (arch C stage 2 input):
    fb_then_cb_passing = sum(
        1 for c in chunks
        if cache["finbert"][c["chunk_id"]]["raw_score"] >= FINBERT_BUSINESS_GATE
        and cache["climatebert"][c["chunk_id"]]["climatebert_score"] > THRESHOLD
    )

    inference_ms = 0.0
    for model_key, gate in latency_chain:
        per_ms = per_model_latency[model_key]["per_chunk_ms"]
        if gate == "always":
            inference_ms += per_ms * n_total
        elif gate == "after:climatebert":
            inference_ms += per_ms * cb_passing
        elif gate == "after:finbert":
            inference_ms += per_ms * fb_passing
        elif gate == "after:finbert+climatebert":
            inference_ms += per_ms * fb_then_cb_passing
        else:
            raise ValueError(f"Unknown gate: {gate}")
    latency_ms_per_chunk = round(inference_ms / n_total, 2)

    # ── RAM = sum of resident models ───────────────────────────────────
    ram_mb = round(sum(per_model_latency[m]["load_delta_mb"]
                       for m in models_loaded), 1)

    print(f"  [{arch_name}] n_passed={n_passed}  "
          f"E/S/G/U = {pct_E}/{pct_S}/{pct_G}/{pct_U}   "
          f"prec={p_overall:.3f}  latency={latency_ms_per_chunk}ms/chunk  ram={ram_mb}MB")

    return {
        "arch": arch_name,
        "n_chunks_total": n_total,
        "n_passed": n_passed,
        "pillar_counts": pillars,
        "pct_E": pct_E, "pct_S": pct_S, "pct_G": pct_G, "pct_unknown": pct_U,
        "precision_E": p_E, "precision_S": p_S, "precision_G": p_G,
        "precision_overall": p_overall,
        "latency_ms_per_chunk": latency_ms_per_chunk,
        "inference_total_ms": round(inference_ms, 1),
        "ram_mb": ram_mb,
        "models_loaded": models_loaded,
        "latency_chain": [{"model": m, "gate": g} for m, g in latency_chain],
        "decisions": [
            {"chunk_id": c["chunk_id"], **decisions[c["chunk_id"]]}
            for c in chunks
        ],
    }


# ── MLflow (best-effort, emoji-safe) ────────────────────────────────────
def _mlflow_log(arch_result: dict) -> str | None:
    try:
        os.environ.setdefault("MLFLOW_ENABLE_SYSTEM_METRICS_LOGGING", "false")
        import mlflow
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5001"))
        mlflow.set_experiment(MLFLOW_EXPERIMENT)
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), mlflow.start_run(run_name=arch_result["arch"]) as run:
            mlflow.log_params({
                "arch": arch_result["arch"],
                "doc": DOC_LABEL,
                "threshold": THRESHOLD,
                "models_loaded": ",".join(arch_result["models_loaded"]),
            })
            mlflow.log_metrics({
                "pct_E": arch_result["pct_E"],
                "pct_S": arch_result["pct_S"],
                "pct_G": arch_result["pct_G"],
                "n_passed": arch_result["n_passed"],
                "precision_E": arch_result["precision_E"],
                "precision_S": arch_result["precision_S"],
                "precision_G": arch_result["precision_G"],
                "precision_overall": arch_result["precision_overall"],
                "latency_ms_per_chunk": arch_result["latency_ms_per_chunk"],
                "ram_mb": arch_result["ram_mb"],
            })
            return run.info.run_id
    except Exception as exc:
        print(f"[mlflow] skipped for {arch_result['arch']}: {exc}")
        return None


# ── Main ────────────────────────────────────────────────────────────────
def main() -> int:
    for p in (BASELINE_PATH, SHOOTOUT_PATH, GT_PATH):
        if not p.exists():
            print(f"Missing {p}", file=sys.stderr)
            return 1

    print("Loading cached scores ...")
    chunks, cache, gt = load_cached()
    print(f"  {len(chunks)} chunks, {len(gt)} ground-truth labels, "
          f"models cached: {sorted(cache.keys())}")

    # ── Latency / RAM benchmark on a small warmed sample ────────────────
    print("\nBenchmarking model latency & RAM (sample size "
          f"{LATENCY_SAMPLE}, warmup {LATENCY_WARMUP}) ...")
    sample_texts = [c["text"] for c in chunks[:LATENCY_SAMPLE + LATENCY_WARMUP]]
    per_model_latency: dict[str, dict] = {}
    for key, hf in [
        ("climatebert", "climatebert/distilroberta-base-climate-detector"),
        ("finbert-esg", "yiyanghkust/finbert-esg-9-categories"),
        ("esgbert",     "nbroad/ESG-BERT"),
        ("finbert",     "ProsusAI/finbert"),
    ]:
        try:
            per_model_latency[key] = _bench_model(hf, sample_texts, LATENCY_WARMUP, LATENCY_SAMPLE)
        except Exception as exc:
            print(f"  !! benchmark for {key} failed: {exc}")
            per_model_latency[key] = {"hf_name": hf, "per_chunk_ms": 0.0,
                                       "load_delta_mb": 0.0, "model_rss_mb": 0.0,
                                       "total_ms": 0.0, "error": str(exc)}

    # ── Run each architecture ───────────────────────────────────────────
    print("\nEvaluating architectures ...")
    arch_results: list[dict] = []

    arch_results.append(_evaluate(
        "arch-A", _arch_A_decide, cache, chunks, gt,
        per_model_latency,
        models_loaded=["climatebert", "finbert-esg"],
        latency_chain=[("climatebert", "always"),
                       ("finbert-esg", "after:climatebert")],
    ))
    _mlflow_log(arch_results[-1])

    arch_results.append(_evaluate(
        "arch-B", _arch_B_decide, cache, chunks, gt,
        per_model_latency,
        models_loaded=["climatebert", "finbert-esg", "esgbert"],
        latency_chain=[("climatebert", "always"),
                       ("finbert-esg", "always"),
                       ("esgbert", "always")],
    ))
    _mlflow_log(arch_results[-1])

    arch_results.append(_evaluate(
        "arch-C", _arch_C_decide, cache, chunks, gt,
        per_model_latency,
        models_loaded=["finbert", "climatebert", "finbert-esg"],
        latency_chain=[("finbert", "always"),
                       ("climatebert", "after:finbert"),
                       ("finbert-esg", "after:finbert+climatebert")],
    ))
    _mlflow_log(arch_results[-1])

    # ── Cross-experiment comparison table (C1 + C2 + C3) ───────────────
    print()
    print("=" * 110)
    print(f"{'Approach':<26} {'n_passed':>9} {'pct_E':>7} {'pct_S':>7} {'pct_G':>7} "
          f"{'prec_E':>7} {'prec_S':>7} {'prec_G':>7} {'precision':>10} "
          f"{'lat_ms':>8} {'ram_MB':>8}")
    print("-" * 110)

    # C1 baseline (no latency/ram measured here — climatebert alone numbers)
    cb_latency = per_model_latency.get("climatebert", {}).get("per_chunk_ms", 0.0)
    cb_ram = per_model_latency.get("climatebert", {}).get("load_delta_mb", 0.0)
    base = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["summary"]
    print(f"{'C1 climatebert (baseline)':<26} {base['n_passed']:>9} "
          f"{base['pillar_percent_passed']['E']:>7} "
          f"{base['pillar_percent_passed']['S']:>7} "
          f"{base['pillar_percent_passed']['G']:>7} "
          f"{'-':>7} {'-':>7} {'-':>7} {'-':>10} "
          f"{cb_latency:>8.1f} {cb_ram:>8.1f}")

    shoot = json.loads(SHOOTOUT_PATH.read_text(encoding="utf-8"))
    for m in shoot["models"]:
        if "error" in m:
            continue
        key = m["model_key"]
        lat = per_model_latency.get(key, {}).get("per_chunk_ms", 0.0)
        ram = per_model_latency.get(key, {}).get("load_delta_mb", 0.0)
        print(f"{'C2 ' + key:<26} {m['n_passed']:>9} "
              f"{m['pct_E']:>7} {m['pct_S']:>7} {m['pct_G']:>7} "
              f"{m['precision_E']:>7} {m['precision_S']:>7} {m['precision_G']:>7} "
              f"{m['precision_overall']:>10.4f} "
              f"{lat:>8.1f} {ram:>8.1f}")

    for r in arch_results:
        print(f"{'C3 ' + r['arch']:<26} {r['n_passed']:>9} "
              f"{r['pct_E']:>7} {r['pct_S']:>7} {r['pct_G']:>7} "
              f"{r['precision_E']:>7} {r['precision_S']:>7} {r['precision_G']:>7} "
              f"{r['precision_overall']:>10.4f} "
              f"{r['latency_ms_per_chunk']:>8.1f} {r['ram_mb']:>8.1f}")

    print("=" * 110)

    # ── Recommendation: highest precision_overall × min-pillar-coverage,
    #     penalised by latency.  composite = min(pct)*precision / log10(latency+10)
    import math
    candidates = []
    # Include C2 winner (finbert-esg) and all C3 archs in the running.
    fe2 = next((m for m in shoot["models"] if m["model_key"] == "finbert-esg"), None)
    if fe2:
        candidates.append({
            "name": "C2 finbert-esg",
            "min_pct": min(fe2["pct_E"], fe2["pct_S"], fe2["pct_G"]),
            "precision": fe2["precision_overall"],
            "latency": per_model_latency["finbert-esg"]["per_chunk_ms"],
            "ram": per_model_latency["finbert-esg"]["load_delta_mb"],
        })
    for r in arch_results:
        candidates.append({
            "name": "C3 " + r["arch"],
            "min_pct": min(r["pct_E"], r["pct_S"], r["pct_G"]),
            "precision": r["precision_overall"],
            "latency": r["latency_ms_per_chunk"],
            "ram": r["ram_mb"],
        })
    for c in candidates:
        c["composite"] = round(
            c["min_pct"] * c["precision"] / math.log10(c["latency"] + 10),
            3,
        )
    candidates.sort(key=lambda c: c["composite"], reverse=True)
    print("\nComposite ranking — min(pct_E,pct_S,pct_G) × precision_overall / log10(latency+10):")
    for c in candidates:
        print(f"  {c['name']:<22}  min_pct={c['min_pct']:5.2f}  prec={c['precision']:.3f}  "
              f"lat={c['latency']:6.1f}ms  ram={c['ram']:6.1f}MB  composite={c['composite']}")
    print(f"\nRecommendation: {candidates[0]['name']}")

    # ── Write JSON ──────────────────────────────────────────────────────
    payload = {
        "doc": DOC_LABEL,
        "threshold": THRESHOLD,
        "finbert_business_gate": FINBERT_BUSINESS_GATE,
        "latency_sample_size": LATENCY_SAMPLE,
        "n_chunks_total": len(chunks),
        "n_ground_truth": len(gt),
        "per_model_latency_ram": per_model_latency,
        "architectures": arch_results,
        "composite_ranking": candidates,
    }
    OUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())