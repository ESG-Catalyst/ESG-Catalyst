"""One-shot verification: do candidate AR signatures appear in chunked AR doc?"""
from __future__ import annotations
import sys, os, io
sys.path.insert(0, "backend")
os.environ["PYTHONPATH"] = "backend"
from app.core.ingestion.parser import ingest_document
from app.core.nlp.chunker import chunk_document

doc = ingest_document("data/ingestion_test_files/ar-adib-esg-report-2022_ar.pdf")
chunks = chunk_document(doc)
texts = [c.text for c in chunks]
joined = "\n".join(texts)

def cov(sig):
    n_match = sum(1 for t in texts if all(s in t for s in sig))
    in_union = all(s in joined for s in sig)
    return n_match, in_union

# Substrings are picked to be distinctive but short enough to survive
# block-level newline insertion by the chunker.
candidates: dict[str, list[str]] = {
    "islamic_finance_113": ["113", "التمويل المتوافق"],
    "net_profit_55": ["55", "صافي"],
    "capital_adequacy_17": ["17.2", "كفاية رأس المال"],
    "sust_finance_6_6": ["6.6", "تمويل االستدامة"],
    "whistle_12_reports": ["12", "اإلبالغ عن المخالفات"],
    "complaint_resolution_976": ["97.6", "الشكاوي"],
    "volunteer_2869": ["2869", "موظفا"],
    "volunteer_2869_alt": ["2869"],
    "training_hours_53k": ["53,082"],
    "aml_100pct": ["100", "غسيل االموال"],
    "women_suppliers_19": ["19", "نساء"],
    "moodys_a2": ["A2", "موديز"],
    "fitch_a_plus": ["A+", "فتش"],
    "roe_21_4": ["21.4", "حقوق المساهمين"],
    "iso_45001": ["45001"],
    "digital_31pct": ["31", "اإلنترنت"],
    "itm_22": ["22", "ITMs"],
    "retail_1m": ["1,101,000"],
    "retail_new_126k": ["126000"],
    "solar_900mw": ["900", "ميغاوات"],
    "shuaa_430m": ["430", "شعاع"],
    "dividend_1779": ["1.779", "توزيعات"],
    "esg_training_22pct": ["22", "تغطي الممارسات البيئية"],
    "board_training_9h": ["9 ساعات", "اإلدارة"],
    "complaints_count_2022": ["4,412"],
    "ai_face_40pct": ["40", "الذكاء االصطناعي"],
}

with io.open("scripts/experiments/results/_ar_signature_check.txt", "w", encoding="utf-8") as f:
    f.write(f"n_chunks={len(texts)} avg_chars={sum(len(t) for t in texts)//max(1,len(texts))}\n\n")
    f.write(f"{'key':<26s} {'per_chunk':>10s} {'union_ok':>10s}  signature\n")
    f.write("-" * 110 + "\n")
    for k, sig in candidates.items():
        n, u = cov(sig)
        f.write(f"{k:<26s} {n:>10d} {str(u):>10s}  {sig}\n")
print("wrote scripts/experiments/results/_ar_signature_check.txt")
