"""M2 NLP full chain test — chunker + embedder + ClimateBERT classifier"""
import sys, time, os
from pathlib import Path

# Run from project root: python backend/test_nlp.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

PDF = str(PROJECT_ROOT / "data" / "ADCB - ESG-report-english.pdf")

# ── Step 1: Ingest ─────────────────────────────────────────────────────
from app.core.ingestion.parser import ingest_document
print("Ingesting...")
doc = ingest_document(PDF)
print(f"  -> {doc.page_count} pages, {len(doc.full_text):,} chars\n")

# ── Step 2: Chunk ──────────────────────────────────────────────────────
from app.core.nlp.chunker import chunk_document
print("Chunking...")
t0 = time.time()
chunks = chunk_document(doc)
print(f"  -> {len(chunks)} chunks in {time.time()-t0:.2f}s\n")

# ── Step 3: Embeddings (sample 20 chunks to verify dimensions) ─────────
from app.core.nlp.embedder import compute_embeddings
print("Computing embeddings for 20 sample chunks...")
t0 = time.time()
embedded = compute_embeddings(chunks[:20])
print(f"  -> {len(embedded)} embeddings in {time.time()-t0:.2f}s")
print(f"  -> vector dimension: {embedded[0].dimension}\n")

# ── Step 4: Classify all chunks (ClimateBERT + keywords) ───────────────
from app.core.nlp.classifier import classify_chunks
print("Classifying all 1479 chunks (ClimateBERT E + keywords S/G)...")
t0 = time.time()
classified = classify_chunks(chunks, use_climate_model=True)
elapsed = time.time() - t0

relevant  = [c for c in classified if c.is_relevant]
by_pillar = {}
for c in relevant:
    by_pillar[c.pillar] = by_pillar.get(c.pillar, 0) + 1
score_dist = {"high(>0.8)": 0, "mid(0.5-0.8)": 0, "low(<0.5)": 0}
for c in classified:
    if c.esg_score > 0.8:   score_dist["high(>0.8)"] += 1
    elif c.esg_score >= 0.5: score_dist["mid(0.5-0.8)"] += 1
    else:                    score_dist["low(<0.5)"] += 1

print(f"  -> {len(classified)} chunks classified in {elapsed:.1f}s")
print(f"  -> relevant : {len(relevant)} ({100*len(relevant)//len(classified)}%)")
print(f"  -> filtered : {len(classified)-len(relevant)}")
print(f"  -> by pillar: E={by_pillar.get('E',0)}, S={by_pillar.get('S',0)}, G={by_pillar.get('G',0)}")
print(f"  -> score dist: {score_dist}\n")

# ── Sample chunks ──────────────────────────────────────────────────────
print("=== TOP 3 — Environmental (E) — ClimateBERT ===")
e_top = sorted([c for c in classified if c.pillar == "E"], key=lambda x: -x.climate_score)[:3]
for cc in e_top:
    print(f"  Page {cc.chunk.page_number} | climate={cc.climate_score:.2f} | {cc.chunk.section_header}")
    print(f"  {cc.chunk.text[:200].replace(chr(10), ' ')}")
    print()

print("=== TOP 3 — Social (S) ===")
s_top = sorted([c for c in classified if c.pillar == "S"], key=lambda x: -x.social_score)[:3]
for cc in s_top:
    print(f"  Page {cc.chunk.page_number} | s={cc.social_score:.2f} | {cc.chunk.section_header}")
    print(f"  {cc.chunk.text[:200].replace(chr(10), ' ')}")
    print()

print("=== TOP 3 — Governance (G) ===")
g_top = sorted([c for c in classified if c.pillar == "G"], key=lambda x: -x.governance_score)[:3]
for cc in g_top:
    print(f"  Page {cc.chunk.page_number} | g={cc.governance_score:.2f} | {cc.chunk.section_header}")
    print(f"  {cc.chunk.text[:200].replace(chr(10), ' ')}")
    print()

print("=== SAMPLE — 1 filtered-out chunk ===")
irrelevant = [c for c in classified if not c.is_relevant]
if irrelevant:
    cc = irrelevant[0]
    print(f"  Page {cc.chunk.page_number} | esg_score={cc.esg_score:.2f}")
    print(f"  {cc.chunk.text[:200].replace(chr(10), ' ')}")
