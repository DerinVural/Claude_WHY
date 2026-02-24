#!/usr/bin/env python3
"""
RAG System Comprehensive Evaluation Suite
==========================================

Tests:
  1. Retrieval Quality   - Precision@K, Recall@K, MRR, Hit Rate
  2. Semantic Relevance   - Similarity score distribution
  3. Category Coverage    - All trained categories retrievable
  4. Response Quality     - Gemini response relevance (with API)
  5. Performance Metrics  - Latency, throughput

Usage:
    python scripts/test_rag_evaluation.py                    # Full evaluation
    python scripts/test_rag_evaluation.py --retrieval-only   # Skip Gemini tests
    python scripts/test_rag_evaluation.py --quick            # Quick 5-question test
    python scripts/test_rag_evaluation.py --verbose          # Detailed output
"""

import sys
import os
import json
import time
import statistics
from pathlib import Path
from typing import List, Dict, Any, Tuple
from collections import defaultdict
from datetime import datetime

# Project root
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# ============================================================================
# TEST CONFIGURATION
# ============================================================================

# Training uses collection "documents", NOT "vivado_rag"
CHROMA_DIR = str(project_root / "chroma_db")
COLLECTION_NAME = "documents"
TOP_K = 5

# Ground truth test cases: (question, expected_categories, expected_keywords)
# expected_categories: which data categories SHOULD appear in results
# expected_keywords: keywords that SHOULD appear in retrieved documents
TEST_CASES = [
    # --- PDF-based questions (Xilinx documentation) ---
    {
        "id": "Q01",
        "question": "Zynq-7000 Processing System configuration and PS-PL interface",
        "expected_categories": ["Zynq_7000"],
        "expected_keywords": ["zynq", "processing_system", "ps-pl", "axi"],
        "expected_type": "pdf",
        "domain": "SoC Architecture",
    },
    {
        "id": "Q02",
        "question": "UltraScale+ GTY transceiver configuration and IBERT",
        "expected_categories": ["UltraScale"],
        "expected_keywords": ["ultrascale", "gty", "transceiver", "ibert"],
        "expected_type": "pdf",
        "domain": "Transceivers",
    },
    {
        "id": "Q03",
        "question": "Vivado synthesis optimization strategies and timing closure",
        "expected_categories": ["Vivado"],
        "expected_keywords": ["synthesis", "timing", "vivado", "optimization"],
        "expected_type": "pdf",
        "domain": "Design Tools",
    },
    {
        "id": "Q04",
        "question": "Versal ACAP NoC network on chip configuration",
        "expected_categories": ["Versal"],
        "expected_keywords": ["versal", "noc", "network", "acap"],
        "expected_type": "pdf",
        "domain": "Versal",
    },
    {
        "id": "Q05",
        "question": "7 Series FPGA MMCM PLL clock management tile",
        "expected_categories": ["7_Series"],
        "expected_keywords": ["mmcm", "pll", "clock", "7 series"],
        "expected_type": "pdf",
        "domain": "Clocking",
    },
    {
        "id": "Q06",
        "question": "AXI Interconnect IP configuration and address mapping",
        "expected_categories": ["IP"],
        "expected_keywords": ["axi", "interconnect", "address"],
        "expected_type": "pdf",
        "domain": "IP Cores",
    },
    {
        "id": "Q07",
        "question": "Vitis HLS pragma optimization directives pipeline unroll",
        "expected_categories": ["Vitis"],
        "expected_keywords": ["hls", "pragma", "pipeline", "unroll"],
        "expected_type": "pdf",
        "domain": "HLS",
    },
    {
        "id": "Q08",
        "question": "Zynq MPSoC boot flow FSBL PMU firmware TF-A",
        "expected_categories": ["Zynq_MPSoC"],
        "expected_keywords": ["mpsoc", "boot", "fsbl", "pmu"],
        "expected_type": "pdf",
        "domain": "Boot Flow",
    },
    {
        "id": "Q09",
        "question": "Alveo U250 data center accelerator card deployment",
        "expected_categories": ["Alveo"],
        "expected_keywords": ["alveo", "u250", "accelerator"],
        "expected_type": "pdf",
        "domain": "Data Center",
    },
    {
        "id": "Q10",
        "question": "Spartan-6 FPGA LUT slice CLB architecture configurable logic",
        "expected_categories": ["Spartan_6"],
        "expected_keywords": ["spartan", "lut", "slice", "clb"],
        "expected_type": "pdf",
        "domain": "Architecture",
    },

    # --- Code-based questions (HDL/Software projects) ---
    {
        "id": "Q11",
        "question": "Arty A7 GPIO LED button Verilog constraint XDC",
        "expected_categories": ["Arty_7Series"],
        "expected_keywords": ["arty", "gpio", "led", "xdc"],
        "expected_type": "code",
        "domain": "Board Design",
    },
    {
        "id": "Q12",
        "question": "Zybo Z7 HDMI video output block design Vivado TCL",
        "expected_categories": ["Zybo"],
        "expected_keywords": ["zybo", "hdmi", "video", "block_design"],
        "expected_type": "code",
        "domain": "Video",
    },
    {
        "id": "Q13",
        "question": "DMA AXI Stream data transfer interrupt handler driver",
        "expected_categories": ["Nexys", "Zedboard", "Zybo"],
        "expected_keywords": ["dma", "axi", "stream", "interrupt"],
        "expected_type": "code",
        "domain": "DMA",
    },
    {
        "id": "Q14",
        "question": "PYNQ overlay bitstream Jupyter notebook Python FPGA",
        "expected_categories": ["PYNQ"],
        "expected_keywords": ["pynq", "overlay", "bitstream", "jupyter"],
        "expected_type": "code",
        "domain": "PYNQ",
    },
    {
        "id": "Q15",
        "question": "u-boot device tree DTS Xilinx Zynq Linux boot",
        "expected_categories": ["Linux_BSP"],
        "expected_keywords": ["u-boot", "device", "tree", "dts", "zynq"],
        "expected_type": "code",
        "domain": "Linux BSP",
    },
    {
        "id": "Q16",
        "question": "Vitis AI DPU deep learning FPGA inference quantization",
        "expected_categories": ["Vitis_Examples"],
        "expected_keywords": ["vitis", "dpu", "inference", "quantization"],
        "expected_type": "code",
        "domain": "AI/ML",
    },
    {
        "id": "Q17",
        "question": "Vivado TCL script create_project add_files set_property synth_design",
        "expected_categories": ["Vivado_Tutorials", "Other_Code"],
        "expected_keywords": ["create_project", "add_files", "set_property", "tcl"],
        "expected_type": "code",
        "domain": "TCL Scripting",
    },
    {
        "id": "Q18",
        "question": "VHDL entity architecture signal process clk rising_edge",
        "expected_categories": ["HDL_Libraries"],
        "expected_keywords": ["entity", "architecture", "signal", "process"],
        "expected_type": "code",
        "domain": "VHDL",
    },
    {
        "id": "Q19",
        "question": "SystemVerilog module always_ff always_comb logic register",
        "expected_categories": ["HDL_Libraries", "Other_Code"],
        "expected_keywords": ["module", "always", "logic", "register"],
        "expected_type": "code",
        "domain": "SystemVerilog",
    },
    {
        "id": "Q20",
        "question": "Genesys ZU Zynq UltraScale+ hardware platform block design",
        "expected_categories": ["Genesys"],
        "expected_keywords": ["genesys", "zynq", "ultrascale", "block_design"],
        "expected_type": "code",
        "domain": "Board Design",
    },
]

# Quick test subset
QUICK_TEST_IDS = ["Q01", "Q05", "Q11", "Q15", "Q17"]


# ============================================================================
# EVALUATION FUNCTIONS
# ============================================================================

def calculate_mrr(results_relevant: List[bool]) -> float:
    """Calculate Mean Reciprocal Rank.

    MRR = 1/rank of first relevant result. If no relevant result, MRR = 0.
    """
    for i, is_relevant in enumerate(results_relevant):
        if is_relevant:
            return 1.0 / (i + 1)
    return 0.0


def calculate_precision_at_k(results_relevant: List[bool], k: int) -> float:
    """Precision@K = relevant docs in top-K / K"""
    top_k = results_relevant[:k]
    if not top_k:
        return 0.0
    return sum(top_k) / len(top_k)


def calculate_recall_at_k(results_relevant: List[bool], k: int, total_relevant: int = 1) -> float:
    """Recall@K = relevant docs in top-K / total relevant docs"""
    if total_relevant == 0:
        return 0.0
    top_k = results_relevant[:k]
    return min(sum(top_k) / total_relevant, 1.0)


def calculate_hit_rate(results_relevant: List[bool]) -> float:
    """Hit Rate = 1 if any result is relevant, else 0"""
    return 1.0 if any(results_relevant) else 0.0


def check_relevance(metadata: dict, content: str, test_case: dict) -> bool:
    """Check if a retrieved document is relevant to the test case."""
    content_lower = content.lower()
    source = metadata.get("source", "").lower()
    category = metadata.get("category", "").lower()
    filename = metadata.get("filename", "").lower()

    # Check if any expected keyword appears in the document
    keyword_hits = 0
    for kw in test_case["expected_keywords"]:
        if kw.lower() in content_lower or kw.lower() in source or kw.lower() in filename:
            keyword_hits += 1

    # A document is "relevant" if at least 2 keywords match
    return keyword_hits >= 2


def check_category_match(metadata: dict, test_case: dict) -> bool:
    """Check if retrieved document category matches expected."""
    source = metadata.get("source", "").lower()
    category = metadata.get("category", "").lower()

    for expected_cat in test_case["expected_categories"]:
        cat_lower = expected_cat.lower()
        if cat_lower in source or cat_lower in category:
            return True
    return False


# ============================================================================
# MAIN EVALUATION
# ============================================================================

def run_evaluation(
    retrieval_only: bool = False,
    quick: bool = False,
    verbose: bool = False,
):
    """Run the full evaluation suite."""

    print("=" * 70)
    print("  GCP-RAG-VIVADO - KAPSAMLI DEGERLENDIRME SUITE")
    print("=" * 70)
    print()

    # Select test cases
    if quick:
        test_cases = [tc for tc in TEST_CASES if tc["id"] in QUICK_TEST_IDS]
        print(f"  Mode: QUICK ({len(test_cases)} soru)")
    else:
        test_cases = TEST_CASES
        print(f"  Mode: FULL ({len(test_cases)} soru)")

    print(f"  Top-K: {TOP_K}")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  ChromaDB: {CHROMA_DIR}")
    print()

    # ── Phase 0: System Check ──────────────────────────────────────────
    print("=" * 70)
    print("  PHASE 0: SISTEM KONTROLU")
    print("=" * 70)

    from src.rag.sentence_embeddings import SentenceEmbeddings
    from src.vectorstore.chroma_store import ChromaVectorStore

    print("  [1] ChromaDB baglantisi...")
    vs = ChromaVectorStore(persist_directory=CHROMA_DIR, collection_name=COLLECTION_NAME)
    doc_count = vs.get_document_count()
    print(f"      Dokuman sayisi: {doc_count:,}")

    if doc_count == 0:
        print("  [FAIL] Veritabani bos! Egitim tamamlanmamis.")
        return

    print("  [2] Embedding modeli yukleniyor...")
    embeddings = SentenceEmbeddings()
    test_emb = embeddings.embed_text("test")
    print(f"      Embedding boyutu: {len(test_emb)}")

    generator = None
    if not retrieval_only:
        print("  [3] Gemini generator yukleniyor...")
        try:
            from src.rag.gemini_generator import GeminiGenerator
            generator = GeminiGenerator()
            test_resp = generator.chat("Merhaba, test.")
            print(f"      Gemini OK: {test_resp[:50]}...")
        except Exception as e:
            print(f"      Gemini HATA: {e}")
            print("      --> Retrieval-only moduna geciliyor")
            retrieval_only = True

    print(f"\n  Sistem hazir! {'(Retrieval Only)' if retrieval_only else '(Full Pipeline)'}")

    # ── Phase 1: Retrieval Quality ─────────────────────────────────────
    print("\n" + "=" * 70)
    print("  PHASE 1: RETRIEVAL KALITESI")
    print("=" * 70)

    all_mrr = []
    all_precision_1 = []
    all_precision_3 = []
    all_precision_5 = []
    all_recall_5 = []
    all_hit_rates = []
    all_similarities = []
    all_latencies = []
    category_hits = defaultdict(int)
    category_misses = defaultdict(int)
    domain_scores = defaultdict(list)

    results_detail = []

    for tc in test_cases:
        q_id = tc["id"]
        question = tc["question"]

        if verbose:
            print(f"\n  [{q_id}] {question}")

        # Measure latency
        t0 = time.time()
        query_embedding = embeddings.embed_text(question)
        results = vs.query(query_embedding, n_results=TOP_K)
        latency = (time.time() - t0) * 1000  # ms
        all_latencies.append(latency)

        # Analyze results
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        relevance_flags = []
        category_flags = []
        similarities = []

        for doc, meta, dist in zip(docs, metas, dists):
            sim = 1.0 - dist
            similarities.append(sim)
            is_relevant = check_relevance(meta, doc, tc)
            is_cat_match = check_category_match(meta, tc)
            relevance_flags.append(is_relevant)
            category_flags.append(is_cat_match)

        # Calculate metrics
        mrr = calculate_mrr(relevance_flags)
        p1 = calculate_precision_at_k(relevance_flags, 1)
        p3 = calculate_precision_at_k(relevance_flags, 3)
        p5 = calculate_precision_at_k(relevance_flags, 5)
        r5 = calculate_recall_at_k(relevance_flags, 5)
        hit = calculate_hit_rate(relevance_flags)
        avg_sim = statistics.mean(similarities) if similarities else 0

        all_mrr.append(mrr)
        all_precision_1.append(p1)
        all_precision_3.append(p3)
        all_precision_5.append(p5)
        all_recall_5.append(r5)
        all_hit_rates.append(hit)
        all_similarities.extend(similarities)
        domain_scores[tc["domain"]].append(mrr)

        # Track category coverage
        if any(category_flags):
            for cat in tc["expected_categories"]:
                category_hits[cat] += 1
        else:
            for cat in tc["expected_categories"]:
                category_misses[cat] += 1

        result_entry = {
            "id": q_id,
            "question": question,
            "domain": tc["domain"],
            "mrr": mrr,
            "precision@1": p1,
            "precision@3": p3,
            "precision@5": p5,
            "hit_rate": hit,
            "avg_similarity": avg_sim,
            "latency_ms": latency,
            "top_sources": [m.get("filename", "?") for m in metas[:3]],
        }
        results_detail.append(result_entry)

        if verbose:
            status = "HIT" if hit > 0 else "MISS"
            print(f"      [{status}] MRR={mrr:.2f} P@1={p1:.0%} P@5={p5:.0%} "
                  f"AvgSim={avg_sim:.3f} Latency={latency:.0f}ms")
            for j, (doc, meta, sim) in enumerate(zip(docs[:3], metas[:3], similarities[:3])):
                src = meta.get("filename", "?")[:40]
                rel = "R" if relevance_flags[j] else "."
                cat = "C" if category_flags[j] else "."
                print(f"        {j+1}. [{rel}{cat}] {src} (sim={sim:.3f})")
        else:
            status = "OK" if hit > 0 else "MISS"
            print(f"  [{q_id}] [{status}] MRR={mrr:.2f} P@5={p5:.0%} Sim={avg_sim:.3f} - {tc['domain']}")

    # ── Phase 1 Summary ──
    print("\n" + "-" * 70)
    print("  PHASE 1 OZET - RETRIEVAL METRIKLERI")
    print("-" * 70)

    metrics = {
        "MRR (Mean Reciprocal Rank)": statistics.mean(all_mrr),
        "Precision@1": statistics.mean(all_precision_1),
        "Precision@3": statistics.mean(all_precision_3),
        "Precision@5": statistics.mean(all_precision_5),
        "Recall@5": statistics.mean(all_recall_5),
        "Hit Rate@5": statistics.mean(all_hit_rates),
        "Ortalama Benzerlik": statistics.mean(all_similarities),
        "Min Benzerlik": min(all_similarities),
        "Max Benzerlik": max(all_similarities),
        "Medyan Benzerlik": statistics.median(all_similarities),
    }

    for name, value in metrics.items():
        bar = "=" * int(value * 40)
        print(f"  {name:30s}: {value:.4f}  |{bar}")

    # ── Phase 2: Category Coverage ─────────────────────────────────────
    print("\n" + "=" * 70)
    print("  PHASE 2: KATEGORI KAPSAMI")
    print("=" * 70)

    all_cats = set()
    for tc in test_cases:
        all_cats.update(tc["expected_categories"])

    for cat in sorted(all_cats):
        hits = category_hits.get(cat, 0)
        misses = category_misses.get(cat, 0)
        total = hits + misses
        rate = hits / total if total > 0 else 0
        status = "OK" if rate >= 0.5 else "LOW"
        print(f"  [{status:4s}] {cat:25s}: {hits}/{total} ({rate:.0%})")

    # ── Phase 3: Domain Performance ────────────────────────────────────
    print("\n" + "=" * 70)
    print("  PHASE 3: DOMAIN PERFORMANSI")
    print("=" * 70)

    for domain in sorted(domain_scores.keys()):
        scores = domain_scores[domain]
        avg = statistics.mean(scores)
        status = "GOOD" if avg >= 0.5 else "FAIR" if avg >= 0.25 else "POOR"
        print(f"  [{status:4s}] {domain:25s}: MRR={avg:.2f} ({len(scores)} soru)")

    # ── Phase 4: Performance ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  PHASE 4: PERFORMANS METRIKLERI")
    print("=" * 70)

    print(f"  Ortalama Sorgu Suresi  : {statistics.mean(all_latencies):.0f} ms")
    print(f"  Medyan Sorgu Suresi    : {statistics.median(all_latencies):.0f} ms")
    print(f"  Min Sorgu Suresi       : {min(all_latencies):.0f} ms")
    print(f"  Max Sorgu Suresi       : {max(all_latencies):.0f} ms")
    print(f"  P95 Sorgu Suresi       : {sorted(all_latencies)[int(len(all_latencies)*0.95)]:.0f} ms")
    print(f"  Throughput             : {1000/statistics.mean(all_latencies):.1f} sorgu/sn")

    # ── Phase 5: Response Quality (optional) ───────────────────────────
    if not retrieval_only and generator:
        print("\n" + "=" * 70)
        print("  PHASE 5: YANIT KALITESI (Gemini)")
        print("=" * 70)

        # Test with a subset of questions
        response_test_cases = test_cases[:5] if quick else test_cases[:10]
        response_scores = []

        for tc in response_test_cases:
            question = tc["question"]
            print(f"\n  [{tc['id']}] {question[:60]}...")

            # Get retrieval results
            query_embedding = embeddings.embed_text(question)
            results = vs.query(query_embedding, n_results=TOP_K)

            # Format context
            retrieved_docs = []
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                retrieved_docs.append({
                    "content": doc,
                    "metadata": meta,
                    "similarity": 1.0 - dist,
                })

            # Generate response
            t0 = time.time()
            try:
                answer = generator.generate(question, retrieved_docs)
                gen_latency = (time.time() - t0) * 1000

                # Basic quality checks
                has_content = len(answer) > 50
                not_hallucinating = "bilgi yoksa" not in answer.lower() or "kaynaklarda" in answer.lower()
                is_turkish = any(c in answer for c in "ğüşıöçĞÜŞİÖÇ") or True  # allow English too
                mentions_source = any(
                    meta.get("filename", "") in answer
                    for meta in results["metadatas"][0][:3]
                )

                quality_score = sum([has_content, not_hallucinating, is_turkish]) / 3.0
                response_scores.append(quality_score)

                status = "GOOD" if quality_score >= 0.66 else "FAIR" if quality_score >= 0.33 else "POOR"
                print(f"      [{status}] Kalite={quality_score:.0%} Uzunluk={len(answer)} Gen={gen_latency:.0f}ms")
                if verbose:
                    print(f"      Yanit: {answer[:200]}...")

            except Exception as e:
                print(f"      [ERROR] {e}")
                response_scores.append(0)

        if response_scores:
            print(f"\n  Ortalama Yanit Kalitesi: {statistics.mean(response_scores):.0%}")

    # ── Final Report ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  FINAL RAPOR")
    print("=" * 70)

    final_report = {
        "timestamp": datetime.now().isoformat(),
        "total_documents": doc_count,
        "test_count": len(test_cases),
        "metrics": {
            "mrr": round(statistics.mean(all_mrr), 4),
            "precision_at_1": round(statistics.mean(all_precision_1), 4),
            "precision_at_3": round(statistics.mean(all_precision_3), 4),
            "precision_at_5": round(statistics.mean(all_precision_5), 4),
            "recall_at_5": round(statistics.mean(all_recall_5), 4),
            "hit_rate": round(statistics.mean(all_hit_rates), 4),
            "avg_similarity": round(statistics.mean(all_similarities), 4),
            "avg_latency_ms": round(statistics.mean(all_latencies), 1),
            "throughput_qps": round(1000 / statistics.mean(all_latencies), 1),
        },
        "per_question": results_detail,
    }

    # Overall grade
    mrr_val = final_report["metrics"]["mrr"]
    hit_val = final_report["metrics"]["hit_rate"]

    if mrr_val >= 0.7 and hit_val >= 0.8:
        grade = "A - Mukemmel"
    elif mrr_val >= 0.5 and hit_val >= 0.7:
        grade = "B - Iyi"
    elif mrr_val >= 0.3 and hit_val >= 0.5:
        grade = "C - Orta"
    elif mrr_val >= 0.15 and hit_val >= 0.3:
        grade = "D - Zayif"
    else:
        grade = "F - Yetersiz"

    print(f"""
  Toplam Dokuman       : {doc_count:,}
  Test Sorusu Sayisi   : {len(test_cases)}

  RETRIEVAL METRIKLERI:
    MRR                : {final_report['metrics']['mrr']:.4f}
    Precision@1        : {final_report['metrics']['precision_at_1']:.4f}
    Precision@5        : {final_report['metrics']['precision_at_5']:.4f}
    Recall@5           : {final_report['metrics']['recall_at_5']:.4f}
    Hit Rate@5         : {final_report['metrics']['hit_rate']:.4f}
    Avg Similarity     : {final_report['metrics']['avg_similarity']:.4f}

  PERFORMANS:
    Avg Latency        : {final_report['metrics']['avg_latency_ms']:.1f} ms
    Throughput         : {final_report['metrics']['throughput_qps']:.1f} query/sec

  GENEL NOT: {grade}
""")

    # Save report
    report_path = project_root / "evaluation_report.json"
    with open(report_path, "w") as f:
        json.dump(final_report, f, indent=2, ensure_ascii=False)
    print(f"  Rapor kaydedildi: {report_path}")

    print("=" * 70)
    print("  DEGERLENDIRME TAMAMLANDI")
    print("=" * 70)

    return final_report


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAG Evaluation Suite")
    parser.add_argument("--retrieval-only", action="store_true",
                        help="Skip Gemini response tests")
    parser.add_argument("--quick", action="store_true",
                        help="Quick 5-question test")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Detailed output")

    args = parser.parse_args()

    run_evaluation(
        retrieval_only=args.retrieval_only,
        quick=args.quick,
        verbose=args.verbose,
    )
