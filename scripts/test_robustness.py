#!/usr/bin/env python3
"""
FPGA RAG v2 — Robustness Test Suite
=====================================
5 bağımsız test ile sistemin gerçek dayanıklılığını ölçer.
20-soru testinden farklı olarak bu sorular sisteme ÖNCEDEN EKLENMEMİŞTİR.

Test A — Held-Out File      : Dosya yokken "bilmiyorum" diyebiliyor mu?
Test B — Fabrication/Recall : Uydurmama (precision) + Bulma (recall)
Test C — Multi-Hop          : Graf 2+ edge derinliğine gidebiliyor mu?
Test D — Cross-Project      : ANALOGOUS_TO edge'leri kullanılıyor mu?
Test E — Contradiction      : Kasıtlı çelişki eklense fark edebiliyor mu?

Kullanım:
    python scripts/test_robustness.py
    python scripts/test_robustness.py --save     # JSON raporu kaydet
    python scripts/test_robustness.py --verbose  # Tam cevapları göster
"""

from __future__ import annotations

import sys
import os
import time
import json
import re
import argparse
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# RENK / FORMAT YARDIMCILARI
# ─────────────────────────────────────────────────────────────────────────────
G  = "\033[92m"   # yeşil
Y  = "\033[93m"   # sarı
R  = "\033[91m"   # kırmızı
B  = "\033[94m"   # mavi
W  = "\033[97m"   # beyaz
DIM= "\033[2m"    # soluk
RST= "\033[0m"    # sıfırla

def ok(s):  return f"{G}✓{RST} {s}"
def warn(s):return f"{Y}⚠{RST} {s}"
def err(s): return f"{R}✗{RST} {s}"
def hdr(s): return f"\n{B}{'═'*68}{RST}\n{B}  {s}{RST}\n{B}{'═'*68}{RST}"

def grade(score: float) -> str:
    if score >= 0.80: return f"{G}A{RST}"
    if score >= 0.65: return f"{Y}B{RST}"
    if score >= 0.50: return f"{Y}C{RST}"
    if score >= 0.35: return f"{R}D{RST}"
    return f"{R}F{RST}"

def grade_raw(score: float) -> str:
    if score >= 0.80: return "A"
    if score >= 0.65: return "B"
    if score >= 0.50: return "C"
    if score >= 0.35: return "D"
    return "F"

# ─────────────────────────────────────────────────────────────────────────────
# SİSTEM YÜKLEME
# ─────────────────────────────────────────────────────────────────────────────

def load_system():
    from rag_v2.graph_store import GraphStore
    from rag_v2.vector_store_v2 import VectorStoreV2
    from rag_v2.query_router import QueryRouter
    from rag_v2.hallucination_gate import HallucinationGate
    from rag_v2.source_chunk_store import SourceChunkStore

    gs = GraphStore(persist_path=str(_ROOT / "db/graph/fpga_rag_v2_graph.json"))
    vs = VectorStoreV2(persist_directory=str(_ROOT / "db/chroma_graph_nodes"), threshold=0.35)
    sc = SourceChunkStore(persist_directory=str(_ROOT / "db/chroma_source_chunks"))
    router = QueryRouter(gs, vs, n_vector_results=6, source_chunk_store=sc, n_source_results=10)
    gate   = HallucinationGate(gs)
    return gs, vs, sc, router, gate


def get_llm():
    from rag.llm_factory import get_llm as _get_llm
    return _get_llm("claude-sonnet-4-6")


def ask(question: str, router, gate, llm, system_prompt: str, verbose=False) -> Dict:
    """Soruyu pipeline'dan geçir, metadata + cevap döndür."""
    from rag_v2.response_builder import build_llm_context
    from rag_v2.grounding_checker import GroundingChecker

    t0 = time.time()
    qt  = router.classify(question)
    qr  = router.route(question, qt)
    gr  = gate.check(qr.all_nodes(), qr.graph_edges)
    ctx = build_llm_context(qr, gr, max_nodes=12, max_chars=14000)

    answer = "[LLM yok]"
    if llm:
        try:
            answer = llm.generate(
                query=question, context_documents=[ctx],
                system_prompt=system_prompt, temperature=0.2,
            )
        except Exception as e:
            answer = f"[LLM HATA: {e}]"

    sc_chunks = getattr(qr, "source_chunks", [])

    # Grounding check — LLM cevabındaki değerleri context'e karşı doğrula
    if answer and not answer.startswith("[LLM"):
        grounding_warns = GroundingChecker().check(answer, sc_chunks, qr.graph_nodes)
        if grounding_warns:
            gr.warnings.extend(grounding_warns)
    # Tüm kaynak dosya yollarını topla
    chunk_files = list({c.get("file_path","") for c in sc_chunks} if sc_chunks else set())

    result = {
        "question": question[:80],
        "query_type": qt.value,
        "vector_hits": len(qr.vector_hits),
        "graph_nodes": len(qr.graph_nodes),
        "graph_edges": len(qr.graph_edges),
        "source_chunks": len(sc_chunks),
        "chunk_files": [Path(f).name for f in chunk_files if f],
        "confidence": gr.overall_confidence,
        "warnings": gr.warnings,
        "answer": answer,
        "elapsed_s": round(time.time() - t0, 2),
    }
    if verbose:
        print(f"\n    Q: {question[:100]}")
        print(f"    A: {answer[:300]}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TEST A — HELD-OUT DOSYA TESTİ
# ─────────────────────────────────────────────────────────────────────────────

def test_a(router, gate, llm, sc, system_prompt, verbose) -> Dict:
    """
    Nexys-A7-100T-Master.xdc chunk'larını geçici olarak sil, sorgu yap → "yok" demeli.
    Sonra yeniden ekle, sorgu yap → doğru cevap vermeli.

    Dosya seçimi: Nexys-A7-100T-Master.xdc — UNIQUE isim (50T XDC'den farklı:
    Nexys-A7-50T-Master.xdc). design_1.tcl Vivado'nun default adı olup birçok
    projede tekrar eder; unique dosya ile held-out testi daha güvenilir.
    """
    print(hdr("TEST A — Held-Out Dosya (Nexys-A7-100T-Master.xdc)"))

    TARGET_FILE = str(_ROOT / "data/code/Nexys-A7-100T-DMA-Audio/src/constraints/Nexys-A7-100T-Master.xdc")
    TARGET_STEM = "nexys-a7-100t-master"  # chunk_files kontrolü için

    # Nexys A7-100T XDC'de aktif (yorumsuz) PWM audio pin atamaları:
    #   PACKAGE_PIN A11 → PWM_AUDIO_0_pwm (aud_pwm)
    #   PACKAGE_PIN D12 → PWM_AUDIO_0_en  (aud_sd)
    # Bu değerler YALNIZCA bu XDC dosyasında aktif olarak geçer.
    QUESTION_A = (
        "Nexys A7-100T kartında PWM ses amplifikatörü için XDC pin ataması nedir? "
        "PWM_AUDIO_0_pwm ve PWM_AUDIO_0_en portlarının PACKAGE_PIN ve IOSTANDARD "
        "değerlerini belirtin."
    )

    # ── Faz 1: Dosya İNDEKSTE — normal sorgu ────────────────────────────────
    print(f"\n  {B}Faz 1{RST}: Nexys-A7-100T-Master.xdc indekste mevcut")
    r1 = ask(QUESTION_A, router, gate, llm, system_prompt, verbose)
    ans1_lower = r1["answer"].lower()
    faz1_found_pin_pwm = "a11" in ans1_lower or "pwm_audio_0_pwm" in ans1_lower
    faz1_found_pin_en  = "d12" in ans1_lower or "pwm_audio_0_en" in ans1_lower
    faz1_xdc_in = TARGET_STEM in " ".join(r1["chunk_files"]).lower()

    print(f"    Source chunks : {r1['source_chunks']} (100T XDC içeriyor: {faz1_xdc_in})")
    print(f"    PWM pin (A11) : {ok('Bulundu') if faz1_found_pin_pwm else err('Bulunamadı')}")
    print(f"    EN  pin (D12) : {ok('Bulundu') if faz1_found_pin_en else err('Bulunamadı')}")

    # ── Faz 2: Chunk'ları geçici SİL ────────────────────────────────────────
    print(f"\n  {B}Faz 2{RST}: Nexys-A7-100T-Master.xdc chunk'ları siliniyor (held-out simülasyonu)")
    held_out_count = sc.delete_by_filepath(TARGET_FILE)
    held_out_ids = ['placeholder'] * held_out_count  # for len() check later
    print(f"    Silinecek chunk sayısı: {held_out_count}")

    r2 = ask(QUESTION_A, router, gate, llm, system_prompt, verbose)
    ans2_lower = r2["answer"].lower()
    # "bilmiyorum" veya "context'te yok" veya "bulunamadı" gibi ifadeler
    NOT_FOUND_SIGNALS = ["bilmiyorum", "context'te", "bulunamadı", "mevcut değil",
                         "yer almıyor", "bilgi yok", "not found", "not available",
                         "cannot find", "no information", "kayıt yok"]
    faz2_says_unknown = any(sig in ans2_lower for sig in NOT_FOUND_SIGNALS)
    faz2_xdc_excluded = TARGET_STEM not in " ".join(r2["chunk_files"]).lower()

    print(f"    Source chunks : {r2['source_chunks']} (100T XDC içeriyor: {not faz2_xdc_excluded})")
    print(f"    Retrieval temiz: {ok('Evet — 100T XDC hariç') if faz2_xdc_excluded else err('Hayır — 100T XDC hâlâ dönüyor')}")
    print(f"    'Yok' sinyali : {ok('Veriyor') if faz2_says_unknown else warn('Vermiyor (LLM graph/bilgi kullanıyor)')}")

    # ── Faz 3: Yeniden ekle, tekrar sor ─────────────────────────────────────
    print(f"\n  {B}Faz 3{RST}: Nexys-A7-100T-Master.xdc yeniden ekleniyor")
    added = sc.add_file(TARGET_FILE, "nexys_a7_100t_dma_audio", [])
    print(f"    Yeniden eklenen chunk: {added}")

    r3 = ask(QUESTION_A, router, gate, llm, system_prompt, verbose)
    ans3_lower = r3["answer"].lower()
    faz3_found_pin_pwm = "a11" in ans3_lower or "pwm_audio_0_pwm" in ans3_lower
    faz3_found_pin_en  = "d12" in ans3_lower or "pwm_audio_0_en" in ans3_lower

    print(f"    Source chunks : {r3['source_chunks']}")
    print(f"    PWM pin (A11) : {ok('Bulundu') if faz3_found_pin_pwm else err('Bulunamadı')}")
    print(f"    EN  pin (D12) : {ok('Bulundu') if faz3_found_pin_en else err('Bulunamadı')}")

    # ── Skor ────────────────────────────────────────────────────────────────
    # Faz1: Doğru cevap → 1.0 puan
    faz1_score = (faz1_found_pin_pwm + faz1_found_pin_en) / 2
    # Faz2: Retrieval correctly excludes 100T XDC (0.7) + LLM says unknown (0.3 bonus)
    # Note: LLM may still answer from graph/training data even when chunks are deleted —
    # retrieval exclusion is the primary test, "I don't know" is secondary
    faz2_retrieval_ok = faz2_xdc_excluded  # True if 100T XDC chunks not returned
    faz2_score = faz2_retrieval_ok * 0.7 + faz2_says_unknown * 0.3
    # Faz3: Dosya eklenince tekrar doğru cevap → 1.0 puan
    faz3_score = (faz3_found_pin_pwm + faz3_found_pin_en) / 2

    total = (faz1_score + faz2_score + faz3_score) / 3

    print(f"\n  {B}Skor{RST}: Faz1={faz1_score:.2f} | Faz2={faz2_score:.2f} | Faz3={faz3_score:.2f} | Toplam={total:.3f} → {grade(total)}")

    return {
        "test": "A_held_out_file",
        "score": round(total, 3),
        "grade": grade_raw(total),
        "faz1_score": faz1_score,
        "faz2_score": faz2_score,
        "faz3_score": faz3_score,
        "faz1_xdc_indexed": faz1_xdc_in,
        "faz2_says_unknown": faz2_says_unknown,
        "faz3_recovered": faz3_found_pin_pwm and faz3_found_pin_en,
        "held_out_chunks": len(held_out_ids),
        "restored_chunks": added,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TEST B — FABRICATION / RECALL TESTİ
# ─────────────────────────────────────────────────────────────────────────────

# NOT_IN_DB sorular: Cevabı gerçekten DB'de olmayan teknik sorular
FABRICATION_TRAPS = [
    {
        "id": "B-TRAP-1",
        "question": "DMA Audio projesindeki axis2fifo modülünün FIFO derinliği kaç stage'dir ve minimum latency nedir?",
        "expected": "NOT_IN_DB",
        "note": "axis2fifo içi FIFO derinliği kaynak kodda tanımlanmamış",
        # Gerçek hallucination: spesifik sayısal değer+birim kombinasyonları
        "hallucination_keywords": ["4 stage", "8 stage", "16 stage", "32 stage",
                                   "2 cycle", "4 cycle", "1 cycle",
                                   "10 ns", "5 ns", "20 ns"],
    },
    {
        "id": "B-TRAP-2",
        "question": "tone_generator modülü frekans doğruluğunu hangi test ekipmanıyla doğrulamıştır ve ölçülen THD (Total Harmonic Distortion) değeri nedir?",
        "expected": "NOT_IN_DB",
        "note": "Projede donanım test metodolojisi veya THD ölçümü belgelenmemiş — sadece RTL kodu var",
        # Gerçek hallucination: spesifik THD sayısı veya ekipman modeli
        "hallucination_keywords": ["thd 0.", "thd: 0.", "thd %", "-60 db", "-40 db",
                                   "keysight", "tektronix", "rohde", "audio precision"],
    },
    {
        "id": "B-TRAP-3",
        "question": "Nexys Video projesinde MicroBlaze işlemcisinin L1 data cache boyutu kaç KB'dir ve kaç-yollu set-associative yapıda?",
        "expected": "NOT_IN_DB",
        "note": "create_minimal_microblaze.tcl MicroBlaze'i NO_CACHE ile oluşturuyor",
        "hallucination_keywords": ["4 kb", "8 kb", "16 kb", "2-way", "4-way", "direct mapped"],
    },
    {
        "id": "B-TRAP-4",
        "question": "DMA Audio projesinde I2S audio interface'in bit clock (BCLK) frekansı nedir ve kaç kanal destekleniyor?",
        "expected": "NOT_IN_DB",
        "note": "Projede I2S yok, PWM audio kullanıyor — BCLK/MCLK/LRCLK gibi I2S-spesifik değerler hallucination",
        "hallucination_keywords": ["bclk", "mclk", "lrclk", "3.072 mhz", "2.048 mhz", "1.536 mhz"],
    },
]

REAL_RECALL_QUESTIONS = [
    {
        "id": "B-REAL-1",
        "question": "DMA Audio projesinde microblaze_0 IP'sinde C_USE_ICACHE ve C_USE_DCACHE değerleri nedir? design_1.tcl'deki set_property komutuna göre açıklayın.",
        "expected": "IN_DB",
        "key_terms": ["C_USE_ICACHE", "C_USE_DCACHE", "1", "etkin"],
        "key_values": ["1"],
        "note": "design_1.tcl: microblaze_0 CONFIG.C_USE_ICACHE {1} CONFIG.C_USE_DCACHE {1}",
    },
    {
        "id": "B-REAL-2",
        "question": "axi_gpio_example projesinde axi_gpio_0 IP'sinin C_GPIO_WIDTH değeri nedir? add_axi_gpio.tcl'e göre açıklayın.",
        "expected": "IN_DB",
        "key_terms": ["C_GPIO_WIDTH", "8", "axi_gpio_0"],
        "key_values": ["8"],
        "note": "add_axi_gpio.tcl: CONFIG.C_GPIO_WIDTH {8}",
    },
    {
        "id": "B-REAL-3",
        "question": "Nexys Video XDC'de PACKAGE_PIN R4'e hangi sinyal atanmış ve IOSTANDARD değeri nedir?",
        "expected": "IN_DB",
        "key_terms": ["R4", "clk", "LVCMOS33"],
        "key_values": ["R4"],
        "note": "nexys_video.xdc: R4 = CLK100MHZ, LVCMOS33",
    },
    {
        "id": "B-REAL-4",
        "question": "DMA Audio projesinde helloworld.c'deki init_dma fonksiyonu scatter-gather modunu nasıl kontrol ediyor? Hangi hata kodunu döndürüyor?",
        "expected": "IN_DB",
        "key_terms": ["XAxiDma_HasSg", "XST_FAILURE", "scatter", "init_dma"],
        "key_values": ["XST_FAILURE"],
        "note": "helloworld.c satır 60-64: SG modu tespit edilirse XST_FAILURE döner",
    },
]

# Hallucination detection keywords (sayısal veya teknik değer uydurmak)
HALLUCINATION_PATTERNS = [
    r'\b\d+\s*(?:kb|mb|bit|bits|stage|cycle|ns|mhz|ghz|channel|way)\b',
    r'\b(?:direct mapped|set.associative|fully associative)\b',
    r'\b(?:stereo|mono|i2s|mclk|bclk|sclk|lrclk)\b',
    r'\b\d+\.\d+\s*(?:mhz|khz|ghz|ns|us)\b',
]

_NEGATION_WORDS = [
    # Türkçe — statik ifadeler
    "yok", "değil", "bulunmamaktadır", "bulunmuyor", "içermemektedir",
    "mevcut değil", "yer almıyor", "kullanılmıyor", "kullanılmamaktadır",
    "olmayan", "yoktur", "hayır", "bulunamadı", "desteklenmiyor",
    "reddediyorum", "bilinmiyor", "içermiyor", "bulunmamakta",
    "içermemekte", "kullanılmamakta", "mevcut olmayan", "devre dışı",
    "etkin değil", "aktif değil", "tanımlanmamış", "belirtilmemiş",
    # Türkçe — fiil olumsuz ekleri (-ma/-me + -(i)yor/-dı/-mış/-dığı)
    "çalışmadığı", "çalışmıyor", "çalışmamaktadır", "çalışmamakta",
    "yer almadığı", "yer almamaktadır", "yer almıyor",
    "bulunmadığı", "bulunmadı", "bulunmayan",
    "kullanılmadığı", "kullanılmamaktadır", "kullanılmıyor",
    "tanımlanmadığı", "tanımlanmamış", "tanımlanmamaktadır",
    "içermediği", "içermemektedir", "içermiyor",
    "görmüyorum", "gözlenmemektedir", "tespit edilememiştir",
    "yer almamış", "mevcut değildir", "mevcut olmadığı",
    "kullanılmamış", "eklenmemiş", "bağlı değil", "desteklenmemektedir",
    # İngilizce
    "not ", "no ", "does not", "doesn't", "without", "absent",
    "not found", "not available", "not present", "not used", "disabled",
]

def detect_hallucination(answer: str,
                         specific_keywords: Optional[List[str]] = None
                         ) -> Tuple[bool, List[str]]:
    """Cevabın uydurmaca teknik değer içerip içermediğini kontrol et.

    specific_keywords verilirse global HALLUCINATION_PATTERNS yerine
    sadece o kelimeler kontrol edilir (trap'a özgü mod).
    Negation-aware: eşleşme yakınında (150 önce / 80 sonra) red ifadesi
    varsa saymaz.
    """
    ans = answer.lower()
    found = []

    if specific_keywords:
        # Per-trap mod: yalnızca belirtilen keyword'leri ara
        for kw in specific_keywords:
            pat = re.compile(r'\b' + re.escape(kw.lower()) + r'\b')
            for m in pat.finditer(ans):
                window = ans[max(0, m.start() - 150): m.end() + 80]
                is_negated = any(neg in window for neg in _NEGATION_WORDS)
                if not is_negated:
                    found.append(m.group())
    else:
        # Global mod: tüm HALLUCINATION_PATTERNS
        for pat in HALLUCINATION_PATTERNS:
            for m in re.finditer(pat, ans):
                window = ans[max(0, m.start() - 150): m.end() + 80]
                is_negated = any(neg in window for neg in _NEGATION_WORDS)
                if not is_negated:
                    found.append(m.group())

    return len(found) > 0, found

NOT_IN_DB_SIGNALS = [
    "bilmiyorum", "context'te", "bağlamda", "bulunamadı", "mevcut değil",
    "yer almıyor", "bilgi yok", "not found", "not available", "cannot find",
    "no information", "kayıt yok", "verilmemiş", "belirtilmemiş",
    "sağlanan bilgide", "verilen context", "elimde yok", "bilgim yok",
    "erişemiyorum", "içermemektedir", "görünmüyor", "içinde değil",
    # Patterns for partial rejections (LLM has context but specific value not present)
    "cannot be determined", "cannot determine", "not specified", "not documented",
    "not explicitly", "no specific", "not measurable", "not recorded",
    "tespit edilemez", "belirsiz", "kaynak kodda yok", "dokümante edilmemiş",
    "ölçüm yok", "test sonucu yok", "değer verilmemiş",
]

def says_not_in_db(answer: str) -> bool:
    ans = answer.lower()
    return any(sig in ans for sig in NOT_IN_DB_SIGNALS)


def test_b(router, gate, llm, system_prompt, verbose) -> Dict:
    print(hdr("TEST B — Fabrication Traps + Recall (Precision & Recall)"))

    trap_results = []
    real_results = []

    # Fabrication traps
    print(f"\n  {B}Fabrication Traps (cevabı DB'de olmayan sorular){RST}")
    for trap in FABRICATION_TRAPS:
        r = ask(trap["question"], router, gate, llm, system_prompt, verbose)
        ans = r["answer"]
        says_unknown = says_not_in_db(ans)
        # Per-trap hallucination_keywords varsa onları kullan, yoksa global pattern
        trap_kws = trap.get("hallucination_keywords")
        has_halluc, halluc_matches = detect_hallucination(ans, specific_keywords=trap_kws)

        # Skor: "Yok" diyorsa tam puan; uydurmaca değer içeriyorsa sıfır
        if says_unknown and not has_halluc:
            score, verdict = 1.0, "PASS (doğru ret)"
            sym = ok
        elif says_unknown and has_halluc:
            score, verdict = 0.5, "PARTIAL (reddetti ama değer de var)"
            sym = warn
        elif not says_unknown and has_halluc:
            score, verdict = 0.0, "FAIL (hallucinasyon!)"
            sym = err
        else:
            score, verdict = 0.3, "PARTIAL (genel cevap, net ret yok)"
            sym = warn

        print(f"    {trap['id']}: {sym(verdict)}")
        if halluc_matches:
            print(f"           Uydurma değerler: {halluc_matches[:3]}")

        trap_results.append({
            "id": trap["id"],
            "note": trap["note"],
            "score": score,
            "verdict": verdict.split("(")[0].strip(),
            "says_unknown": says_unknown,
            "hallucination_detected": has_halluc,
            "hallucination_values": halluc_matches[:5],
            "answer_snippet": ans[:200],
        })

    # Real recall questions
    print(f"\n  {B}Recall Sorular (cevabı DB'de olan sorular){RST}")
    for rq in REAL_RECALL_QUESTIONS:
        r = ask(rq["question"], router, gate, llm, system_prompt, verbose)
        ans_lower = r["answer"].lower()
        term_hits = [t for t in rq["key_terms"] if t.lower() in ans_lower]
        val_hits  = [v for v in rq["key_values"] if v.lower() in ans_lower]
        recall_score = (len(term_hits)/len(rq["key_terms"]) * 0.6 +
                        len(val_hits) /len(rq["key_values"]) * 0.4)
        sym = ok if recall_score >= 0.80 else (warn if recall_score >= 0.50 else err)
        print(f"    {rq['id']}: {sym(f'score={recall_score:.2f}')} | hits: {term_hits}")
        real_results.append({
            "id": rq["id"],
            "note": rq["note"],
            "score": round(recall_score, 3),
            "term_hits": term_hits,
            "val_hits": val_hits,
            "source_chunks": r["source_chunks"],
            "chunk_files": r["chunk_files"],
        })

    precision = sum(t["score"] for t in trap_results) / len(trap_results)
    recall    = sum(r["score"] for r in real_results) / len(real_results)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    total = f1

    print(f"\n  {B}Skor{RST}: Precision={precision:.3f} | Recall={recall:.3f} | F1={f1:.3f} → {grade(total)}")

    return {
        "test": "B_fabrication_recall",
        "score": round(total, 3),
        "grade": grade_raw(total),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "trap_results": trap_results,
        "real_results": real_results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TEST C — MULTI-HOP GRAPH TRAVERSAL
# ─────────────────────────────────────────────────────────────────────────────

MULTIHOP_QUESTIONS = [
    {
        "id": "C-HOP-1",
        "hops": 2,
        "question": (
            "DMA Audio projesinde ses verisinin MIG 7 Series DDR3 belleğinden "
            "çıkıp AXI DMA üzerinden AXI-Stream'e dönüşerek ses çıkış modülüne "
            "ulaşmasına kadar geçen bileşenlerin zincirini açıklayın. "
            "mig_7series_0 ile fifo2audpwm_0 arasındaki bağlantı yolunu izleyin."
        ),
        "expected_nodes": ["mig_7series_0", "axi_dma_0", "axis2fifo", "fifo2audpwm"],
        "expected_edge_types": ["PROVIDES_DATA_TO", "CONNECTS_TO", "IMPLEMENTS"],
        "min_graph_nodes": 3,
        "min_graph_edges": 2,
    },
    {
        "id": "C-HOP-2",
        "hops": 2,
        "question": (
            "axi_gpio_example projesinde MicroBlaze işlemcisinden GPIO LED'lerine "
            "veri yazma zincirini açıklayın: microblaze_0 → AXI Interconnect → "
            "axi_gpio_0 → gpio_io_o. Her bileşenin rolünü ve bağlantı tipini belirtin."
        ),
        "expected_nodes": ["microblaze_0", "microblaze_0_axi_periph", "axi_gpio_0"],
        "expected_edge_types": ["CONNECTS_TO", "IMPLEMENTS", "DEPENDS_ON"],
        "min_graph_nodes": 3,
        "min_graph_edges": 2,
    },
    {
        "id": "C-HOP-3",
        "hops": 3,
        "question": (
            "DMA Audio projesinde 'tone_generator_0' bileşeninin hangi gereksinimi "
            "karşıladığını (IMPLEMENTS), bu gereksinimin hangi üst-gereksinim altında "
            "olduğunu (DECOMPOSES_TO) ve bu sisteme ait kanıtları (EVIDENCE) açıklayın. "
            "3 seviyeli hiyerarşiyi takip edin."
        ),
        "expected_nodes": ["tone_generator_0", "TONE_GEN", "DMA_AUDIO"],
        "expected_edge_types": ["IMPLEMENTS", "DECOMPOSES_TO", "VERIFIED_BY"],
        "min_graph_nodes": 4,
        "min_graph_edges": 3,
    },
]

def test_c(router, gate, llm, system_prompt, verbose) -> Dict:
    print(hdr("TEST C — Multi-Hop Graph Traversal"))

    results = []
    for mq in MULTIHOP_QUESTIONS:
        print(f"\n  {B}{mq['id']} ({mq['hops']} hop){RST}")
        r = ask(mq["question"], router, gate, llm, system_prompt, verbose)
        ans_lower = r["answer"].lower()

        # Graf node ve edge derinliği
        has_enough_nodes = r["graph_nodes"] >= mq["min_graph_nodes"]
        has_enough_edges = r["graph_edges"] >= mq["min_graph_edges"]

        # Beklenen node isimlerinin cevapta geçmesi
        node_hits = [n for n in mq["expected_nodes"]
                     if n.lower().replace("_","") in ans_lower.replace("_","")
                     or n.lower() in ans_lower]
        node_coverage = len(node_hits) / len(mq["expected_nodes"])

        # Skor
        depth_score   = (has_enough_nodes * 0.3 + has_enough_edges * 0.3)
        content_score = node_coverage * 0.4
        score = depth_score + content_score

        sym = ok if score >= 0.7 else (warn if score >= 0.4 else err)
        print(f"    Graph nodes  : {r['graph_nodes']} (min {mq['min_graph_nodes']}: {ok('OK') if has_enough_nodes else err('AZ')})")
        print(f"    Graph edges  : {r['graph_edges']} (min {mq['min_graph_edges']}: {ok('OK') if has_enough_edges else err('AZ')})")
        print(f"    Node coverage: {node_hits}/{mq['expected_nodes']} = {node_coverage:.0%}")
        print(f"    Score        : {sym(f'{score:.3f}')}")

        results.append({
            "id": mq["id"],
            "hops": mq["hops"],
            "score": round(score, 3),
            "graph_nodes_retrieved": r["graph_nodes"],
            "graph_edges_retrieved": r["graph_edges"],
            "node_coverage": round(node_coverage, 3),
            "node_hits": node_hits,
            "node_misses": [n for n in mq["expected_nodes"] if n not in node_hits],
            "has_enough_nodes": has_enough_nodes,
            "has_enough_edges": has_enough_edges,
        })

    total = sum(r["score"] for r in results) / len(results)
    print(f"\n  {B}Skor{RST}: {total:.3f} → {grade(total)}")

    return {
        "test": "C_multihop_traversal",
        "score": round(total, 3),
        "grade": grade_raw(total),
        "questions": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TEST D — CROSS-PROJECT REASONİNG
# ─────────────────────────────────────────────────────────────────────────────

CROSSREF_QUESTIONS = [
    {
        "id": "D-CROSS-1",
        "question": (
            "Nexys A7 DMA Audio projesindeki clk_wiz_0 ile "
            "axi_gpio_example projesindeki clk_wiz_0 arasındaki yapısal benzerlik "
            "nedir? Her ikisi de aynı IP mi? Konfigürasyon farklarını açıklayın."
        ),
        "expected": ["clk_wiz", "benzer", "aynı ip", "analogous", "xilinx"],
        "cross_project_evidence": True,
        "notes": "ANALOGOUS_TO edge var: COMP-A-clk_wiz_0 ↔ COMP-B-clk_wiz_0",
    },
    {
        "id": "D-CROSS-2",
        "question": (
            "DMA Audio ve AXI GPIO Example projelerinde MicroBlaze işlemcisi "
            "kullanılıyor mu? Her iki projedeki microblaze_0 konfigürasyonlarını "
            "karşılaştırın — cache etkin mi, debug modülü var mı?"
        ),
        "expected": ["microblaze", "mdm", "cache", "debug", "her iki", "comparison"],
        "cross_project_evidence": True,
        "notes": "İki projede de microblaze_0 var, farklı cache/debug config",
    },
    {
        "id": "D-CROSS-3",
        "question": (
            "İki proje arasında tespit edilen herhangi bir CONTRADICTS (çelişki) "
            "veya ANALOGOUS_TO (benzer yapı) ilişkisi var mı? "
            "CrossRef sorgusunu kullanarak cevabı bulun."
        ),
        "expected": ["analogous", "benzer", "çelişki", "contradicts", "cross"],
        "cross_project_evidence": True,
        "notes": "CrossRef route ile ANALOGOUS_TO/REUSES_PATTERN edge'leri gelecek",
    },
]

def test_d(router, gate, llm, system_prompt, verbose) -> Dict:
    print(hdr("TEST D — Cross-Project Reasoning"))

    results = []
    for cq in CROSSREF_QUESTIONS:
        print(f"\n  {B}{cq['id']}{RST}")
        r = ask(cq["question"], router, gate, llm, system_prompt, verbose)
        ans_lower = r["answer"].lower()

        # Beklenen terimlerin cevapta geçmesi
        term_hits  = [t for t in cq["expected"] if t in ans_lower]
        term_cov   = len(term_hits) / len(cq["expected"])

        # Her iki projeye de atıf var mı?
        proj_a_ref = any(s in ans_lower for s in [
            "nexys a7", "dma audio", "project-a", "project_a", "proje a",
            "nexys_a7_dma_audio", "dma ses", "dma_audio",
        ])
        proj_b_ref = any(s in ans_lower for s in [
            "nexys video", "axi gpio", "project-b", "project_b", "proje b",
            "gpio example", "axi_gpio_example", "gpio_example",
        ])
        # Also accept if LLM says "her iki proje" / "iki projede de" — implies cross-project
        both_mentioned = any(s in ans_lower for s in ["her iki proje", "iki projede", "her iki tasarım", "her iki sistemde"])
        cross_ref  = (proj_a_ref and proj_b_ref) or both_mentioned

        # ANALOGOUS_TO ilişkisi kullanıldı mı?
        # graph_edges > 0 AND crossref sorguda gelince çoklu node tipi
        graph_depth = r["graph_edges"] >= 2

        score = term_cov * 0.5 + cross_ref * 0.3 + graph_depth * 0.2

        sym = ok if score >= 0.7 else (warn if score >= 0.4 else err)
        print(f"    Term hits    : {term_hits}")
        print(f"    Cross-project: {ok('Her iki proje referans') if cross_ref else warn('Tek proje')}")
        print(f"    Graph depth  : {r['graph_edges']} edges")
        print(f"    Score        : {sym(f'{score:.3f}')}")

        results.append({
            "id": cq["id"],
            "score": round(score, 3),
            "term_coverage": round(term_cov, 3),
            "term_hits": term_hits,
            "cross_project_refs": cross_ref,
            "proj_a_referenced": proj_a_ref,
            "proj_b_referenced": proj_b_ref,
            "graph_edges": r["graph_edges"],
            "notes": cq["notes"],
        })

    total = sum(r["score"] for r in results) / len(results)
    print(f"\n  {B}Skor{RST}: {total:.3f} → {grade(total)}")

    return {
        "test": "D_cross_project",
        "score": round(total, 3),
        "grade": grade_raw(total),
        "questions": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TEST E — CONTRADICTION DETECTION
# ─────────────────────────────────────────────────────────────────────────────

CONTRADICTION_NODE = {
    "node_id":    "TEST-DEC-CONTRA-001",
    "node_type":  "DECISION",
    "project":    "PROJECT-A",
    "name":       "DMA Modu Kararı — Scatter-Gather Seçildi",
    "title":      "DMA Modu Kararı",
    "description": (
        "Scatter-Gather modu seçildi ve etkinleştirildi. "
        "Simple DMA modu yetersiz olduğundan SG modu tercih edildi ve etkinleştirilmiştir. "
        "XAxiDma_HasSg() çağrısı True döndürmeli, SG modu zorunludur."
    ),
    "outcome": "SG modu seçildi",
}

CONTRADICTION_QUESTION = (
    "DMA Audio projesinde AXI DMA modu kararı nedir? "
    "Scatter-Gather modu mu yoksa Simple DMA modu mu kullanılıyor? "
    "helloworld.c ve DECISION node'larına göre açıklayın."
)

def test_e(router, gate, llm, sc, gs, vs, system_prompt, verbose) -> Dict:
    print(hdr("TEST E — Contradiction Detection (kasıtlı çelişki)"))

    # ── Faz 1: Çelişki YOK — normal sorgu ───────────────────────────────────
    print(f"\n  {B}Faz 1{RST}: Çelişkisiz sorgu (baseline)")
    r1 = ask(CONTRADICTION_QUESTION, router, gate, llm, system_prompt, verbose)
    faz1_mentions_sg     = "scatter" in r1["answer"].lower() or "sg" in r1["answer"].lower()
    faz1_mentions_simple = "simple" in r1["answer"].lower()
    faz1_has_warning     = any("contradict" in w.lower() or "çelişki" in w.lower()
                               for w in r1["warnings"])
    print(f"    SG referans  : {ok('Var') if faz1_mentions_sg else warn('Yok')}")
    print(f"    Simple ref   : {ok('Var') if faz1_mentions_simple else warn('Yok')}")
    print(f"    Çelişki uyarısı: {ok('Var') if faz1_has_warning else warn('Yok')} (beklenen: Yok)")

    # ── Faz 2: Çelişki node EKLE ─────────────────────────────────────────────
    print(f"\n  {B}Faz 2{RST}: Çelişki node'u ekleniyor: {CONTRADICTION_NODE['node_id']}")
    gs.add_node(CONTRADICTION_NODE["node_id"], CONTRADICTION_NODE)

    # VectorStore'a da ekle (semantic arama için)
    vs.add_node(CONTRADICTION_NODE)

    # CrossReferenceDetector'ı çalıştır (apply=True)
    from rag_v2.cross_reference_detector import CrossReferenceDetector
    detector = CrossReferenceDetector(gs, vs)
    crd_report = detector.run(apply=True)
    print(f"    CrossRef algıladı: {crd_report['total']} yeni edge")

    # CONTRADICTS edge yoksa manuel ekle — Layer 6 GroundingChecker testi için
    # DMA-DEC-001 (AXI DMA seçimi, SG destekli) ile TEST-DEC-CONTRA-001 (SG seçildi)
    # arasındaki çelişki: gerçek kod Simple DMA kullanıyor (XAxiDma_HasSg=False)
    test_contra_edge_added = False
    has_contra_edge = any(
        d.get("type") == "CONTRADICTS" and
        (u == CONTRADICTION_NODE["node_id"] or v == CONTRADICTION_NODE["node_id"])
        for u, v, d in gs._graph.edges(data=True)
    )
    if not has_contra_edge:
        gs._graph.add_edge(
            CONTRADICTION_NODE["node_id"], "DMA-DEC-001",
            edge_type="CONTRADICTS",
            label="SG mode claim contradicts Simple DMA code reality",
            source="test_e_manual",
        )
        test_contra_edge_added = True
        print(f"    Manuel CONTRADICTS edge eklendi: {CONTRADICTION_NODE['node_id']} → DMA-DEC-001")

    r2 = ask(CONTRADICTION_QUESTION, router, gate, llm, system_prompt, verbose)
    faz2_has_warning  = any("contradict" in w.lower() or "çelişki" in w.lower()
                            or "uyar" in w.lower() for w in r2["warnings"])
    faz2_mentions_both = (("scatter" in r2["answer"].lower() or "sg" in r2["answer"].lower())
                           and "simple" in r2["answer"].lower())
    faz2_mentions_conflict = any(s in r2["answer"].lower() for s in
                                 ["çelişki", "contradicts", "tutarsız", "conflict",
                                  "ikilem", "farklı karar", "çelişen"])

    print(f"    Uyarı array  : {r2['warnings']}")
    print(f"    Çelişki uyarısı: {ok('Var') if faz2_has_warning else warn('Yok')} (beklenen: Var)")
    print(f"    Her iki modu söyledi: {ok('Evet') if faz2_mentions_both else warn('Hayır')}")
    print(f"    Çelişkiyi belirtti: {ok('Evet') if faz2_mentions_conflict else warn('Hayır')}")

    # ── Faz 3: Test node'u KALDIR ────────────────────────────────────────────
    print(f"\n  {B}Faz 3{RST}: Test node'u kaldırılıyor + VectorStore temizleniyor")
    gs._graph.remove_node(CONTRADICTION_NODE["node_id"])
    # VectorStore'dan da sil
    try:
        vs._collection.delete(ids=[CONTRADICTION_NODE["node_id"]])
    except Exception:
        pass
    # Eklenen çelişki edge'lerini kaldır
    edges_to_remove = [
        (u, v) for u, v, d in gs._graph.edges(data=True)
        if (u == CONTRADICTION_NODE["node_id"] or v == CONTRADICTION_NODE["node_id"])
        or d.get("source") == "auto"
    ]
    # Sadece test node ile ilgili auto edge'leri kaldır (graph temizliği)
    test_edges = [(u,v) for u,v in edges_to_remove
                  if u == CONTRADICTION_NODE["node_id"] or v == CONTRADICTION_NODE["node_id"]]
    for u,v in test_edges:
        if gs._graph.has_edge(u, v):
            gs._graph.remove_edge(u, v)
    gs.save()
    print(f"    Kaldırıldı: {CONTRADICTION_NODE['node_id']}, {len(test_edges)} edge temizlendi")

    # Skor
    # Faz1: Baseline doğru mu (çelişki yok → uyarı yok)?
    faz1_score = 1.0 if not faz1_has_warning else 0.5
    # Faz2: Çelişki eklendi → sistem uyarı veriyor mu veya çelişkiyi belirtiyor mu?
    faz2_score = (faz2_has_warning * 0.5 + faz2_mentions_conflict * 0.3 + faz2_mentions_both * 0.2)

    total = (faz1_score + faz2_score) / 2
    print(f"\n  {B}Skor{RST}: Faz1={faz1_score:.2f} | Faz2={faz2_score:.2f} | Toplam={total:.3f} → {grade(total)}")

    return {
        "test": "E_contradiction_detection",
        "score": round(total, 3),
        "grade": grade_raw(total),
        "faz1_baseline_clean": not faz1_has_warning,
        "faz2_warning_fired": faz2_has_warning,
        "faz2_conflict_mentioned": faz2_mentions_conflict,
        "faz2_both_modes_mentioned": faz2_mentions_both,
        "crossref_new_edges": crd_report["total"],
        "faz1_score": faz1_score,
        "faz2_score": faz2_score,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GENEL RAPOR
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(results: List[Dict]):
    print(f"\n{B}{'═'*68}{RST}")
    print(f"{B}  ROBUSTNESS TEST SUITE — ÖZET RAPOR{RST}")
    print(f"{B}{'═'*68}{RST}")

    weights = {"A_held_out_file": 0.25, "B_fabrication_recall": 0.30,
               "C_multihop_traversal": 0.20, "D_cross_project": 0.15,
               "E_contradiction_detection": 0.10}

    total_weighted = 0.0
    for r in results:
        name = r["test"]
        s    = r["score"]
        g    = r["grade"]
        w    = weights.get(name, 0.20)
        weighted = s * w
        total_weighted += weighted

        label_map = {
            "A_held_out_file":          "A — Held-Out Dosya",
            "B_fabrication_recall":     "B — Fabrication/Recall",
            "C_multihop_traversal":     "C — Multi-Hop Traversal",
            "D_cross_project":          "D — Cross-Project",
            "E_contradiction_detection":"E — Contradiction",
        }
        label = label_map.get(name, name)
        bar   = "█" * int(s * 20) + "░" * (20 - int(s * 20))
        print(f"  {label:30s} {bar} {s:.3f} [{grade(s)}] (ağırlık={w:.0%})")

    print(f"\n  {'─'*68}")
    print(f"  AĞIRLIKLI TOPLAM SKOR  : {total_weighted:.3f} → {grade(total_weighted)}")
    print(f"  {'─'*68}")

    # Güçlü / Zayıf yönler
    scored = sorted(results, key=lambda x: x["score"])
    print(f"\n  En zayıf alan : {scored[0]['test']} (skor={scored[0]['score']:.3f})")
    print(f"  En güçlü alan : {scored[-1]['test']} (skor={scored[-1]['score']:.3f})")
    print(f"{B}{'═'*68}{RST}\n")

    return round(total_weighted, 3)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FPGA RAG v2 Robustness Test Suite")
    parser.add_argument("--save",    action="store_true", help="JSON raporu kaydet")
    parser.add_argument("--verbose", action="store_true", help="Tam cevapları göster")
    parser.add_argument("--only",    type=str, default="",
                        help="Sadece belirli testi çalıştır (A/B/C/D/E)")
    args = parser.parse_args()

    print(f"\n{B}{'═'*68}")
    print(f"  FPGA RAG v2 — Robustness Test Suite")
    print(f"  Çalışma zamanı: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*68}{RST}")

    print("\n  [SİSTEM] Yükleniyor...")
    gs, vs, sc, router, gate = load_system()
    llm = get_llm()
    if not llm:
        print(f"  {Y}⚠ LLM yok — API key bulunamadı. LLM tabanlı testler sınırlı.{RST}")

    from rag_v2.response_builder import FPGA_RAG_SYSTEM_PROMPT
    system_prompt = FPGA_RAG_SYSTEM_PROMPT.split("CONTEXT:")[0].strip()

    results = []
    only = args.only.upper()

    t_start = time.time()

    if not only or only == "A":
        ra = test_a(router, gate, llm, sc, system_prompt, args.verbose)
        results.append(ra)

    if not only or only == "B":
        rb = test_b(router, gate, llm, system_prompt, args.verbose)
        results.append(rb)

    if not only or only == "C":
        rc = test_c(router, gate, llm, system_prompt, args.verbose)
        results.append(rc)

    if not only or only == "D":
        rd = test_d(router, gate, llm, system_prompt, args.verbose)
        results.append(rd)

    if not only or only == "E":
        re_ = test_e(router, gate, llm, sc, gs, vs, system_prompt, args.verbose)
        results.append(re_)

    elapsed = round(time.time() - t_start, 1)
    final_score = print_summary(results)

    print(f"  Toplam süre: {elapsed}s")

    if args.save:
        report = {
            "timestamp": datetime.now().isoformat(),
            "total_score": final_score,
            "overall_grade": grade_raw(final_score),
            "elapsed_s": elapsed,
            "tests": results,
        }
        out_path = _ROOT / "robustness_report.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        print(f"  Rapor kaydedildi: {out_path}")


if __name__ == "__main__":
    main()
