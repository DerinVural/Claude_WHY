#!/usr/bin/env python3
"""
FPGA RAG v2 — Blind Benchmark v3
====================================
v2'den tamamen farklı, hiç görülmemiş sorular.
PDF Reference Manual kategorisi yeni eklendi (nexys-a7_rm.pdf).

7 Kategori:
  PDF Reference   (5 soru, w=20%) — nexys-a7_rm.pdf bölümleri
  IP Config       (4 soru, w=15%) — design_1.tcl (v2'den farklı sorular)
  RTL Signal      (4 soru, w=15%) — tone_generator.v / axis2fifo.v
  C Code          (4 soru, w=15%) — helloworld.c farklı işlevler
  XDC Detail      (4 soru, w=15%) — PROJECT-B XDC detayları
  Cross-Project   (3 soru, w=10%) — yeni karşılaştırma soruları
  Trap v3         (3 soru, w=10%) — DB'de olmayan bilgiler

Çalıştırma:
    source .venv/bin/activate
    python scripts/test_blind_benchmark_v3.py --save
    python scripts/test_blind_benchmark_v3.py --verbose
    python scripts/test_blind_benchmark_v3.py --category pdf_ref
"""

from __future__ import annotations

import sys
import re
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Tuple

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")

# ─────────────────────────────────────────────────────────────────────────────
# RENK / FORMAT
# ─────────────────────────────────────────────────────────────────────────────
G   = "\033[92m"
Y   = "\033[93m"
R   = "\033[91m"
B   = "\033[94m"
RST = "\033[0m"

def ok(s):   return f"{G}✓{RST} {s}"
def warn(s): return f"{Y}⚠{RST} {s}"
def err(s):  return f"{R}✗{RST} {s}"
def hdr(s):  return f"\n{B}{'═'*68}{RST}\n{B}  {s}{RST}\n{B}{'═'*68}{RST}"

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
# SORU KATEGORİLERİ
# ─────────────────────────────────────────────────────────────────────────────

BLIND_QUESTIONS_V3: Dict[str, List[Dict]] = {

    # ─── PDF Reference Manual (nexys-a7_rm.pdf) ───────────────────────────
    "pdf_ref": [
        {
            "id": "PDF-01",
            "project": "PROJECT-A",
            "question": (
                "Nexys A7 kartındaki SMSC Ethernet PHY'nin part numarası nedir? "
                "Bu PHY hangi arayüzü kullanır ve maksimum hızı nedir?"
            ),
            "key_terms":  ["LAN8720A", "RMII", "10/100", "Ethernet", "PHY"],
            "key_values": ["LAN8720A", "RMII", "10/100"],
            "note": "nexys-a7_rm.pdf s.12: SMSC LAN8720A, RMII interface, 10/100 Mb/s",
        },
        {
            "id": "PDF-02",
            "project": "PROJECT-A",
            "question": (
                "Nexys A7 reference manual'a göre DDR2 belleğin maksimum "
                "clock period (tCK) sınırı nedir? "
                "Önerilen (recommended) tCK değeri kaç ps'dir?"
            ),
            "key_terms":  ["3000", "3077", "tCK", "DDR2", "ps"],
            "key_values": ["3000", "3077"],
            "note": "nexys-a7_rm.pdf s.11 Tablo 3.1.1: max 3000ps, recommended 3077ps",
        },
        {
            "id": "PDF-03",
            "project": "PROJECT-A",
            "question": (
                "Nexys A7 kartındaki ivmeölçer (accelerometer) hangi SPI modunu "
                "kullanır? İvmeölçerin kesme (interrupt) pini Artix-7'de hangi "
                "sinyal adıyla bağlanmıştır?"
            ),
            "key_terms":  ["ADXL362", "SPI", "interrupt", "INT1", "INT2"],
            "key_values": ["ADXL362", "SPI"],
            "note": "nexys-a7_rm.pdf s.27: ADXL362, SPI mode, INT1/INT2 interrupt pins",
        },
        {
            "id": "PDF-04",
            "project": "PROJECT-A",
            "question": (
                "Nexys A7 kartındaki sıcaklık sensörü hangi I2C adresine sahiptir? "
                "Sıcaklık verisi kaç bitlik MSB ve LSB registerlarında tutulur?"
            ),
            "key_terms":  ["ADT7420", "I2C", "0x48", "MSB", "LSB", "13"],
            "key_values": ["ADT7420", "0x48"],
            "note": "nexys-a7_rm.pdf s.26: ADT7420, I2C addr 0x48, 13-bit MSB+LSB registers",
        },
        {
            "id": "PDF-05",
            "project": "PROJECT-A",
            "question": (
                "Nexys A7 kartındaki mikrofon hangi modülasyon tekniğini kullanır? "
                "Mikrofondan veri okumak için gereken saat (clock) frekansı "
                "referans kılavuza göre hangi aralıktadır?"
            ),
            "key_terms":  ["PDM", "pulse density", "mikrofon", "clock", "MHz"],
            "key_values": ["PDM"],
            "note": "nexys-a7_rm.pdf s.28: PDM (Pulse Density Modulation), clock 1-3.2 MHz",
        },
    ],

    # ─── IP Config (design_1.tcl — v2'den farklı sorular) ─────────────────
    "ip_config": [
        {
            "id": "IC-01",
            "project": "PROJECT-A",
            "question": (
                "nexys_a7_dma_audio projesinde design_1.tcl'de "
                "microblaze_0 IP'sinin C_USE_ICACHE ve C_USE_DCACHE "
                "değerleri nedir? Cache etkin mi?"
            ),
            "key_terms":  ["C_USE_ICACHE", "C_USE_DCACHE", "1", "microblaze", "cache"],
            "key_values": ["1"],
            "note": "design_1.tcl: CONFIG.C_USE_ICACHE {1} CONFIG.C_USE_DCACHE {1}",
        },
        {
            "id": "IC-02",
            "project": "PROJECT-A",
            "question": (
                "design_1.tcl'de axi_interconnect_0 IP'sinin "
                "NUM_SI (slave arayüzü) ve NUM_MI (master arayüzü) "
                "değerleri nedir?"
            ),
            "key_terms":  ["NUM_SI", "NUM_MI", "axi_interconnect", "1", "5"],
            "key_values": ["1", "5"],
            "note": "design_1.tcl: axi_interconnect_0 NUM_SI=1 NUM_MI=5",
        },
        {
            "id": "IC-03",
            "project": "PROJECT-A",
            "question": (
                "design_1.tcl'de tone_generator_0 IP'sinin "
                "AUD_SAMPLE_FREQ parametresi nedir? "
                "Bu değer hangi bileşenle ilişkilidir?"
            ),
            "key_terms":  ["AUD_SAMPLE_FREQ", "96000", "tone_generator", "audio"],
            "key_values": ["96000"],
            "note": "tone_generator.v: AUD_SAMPLE_FREQ=96000 Hz",
        },
        {
            "id": "IC-04",
            "project": "PROJECT-A",
            "question": (
                "design_1.tcl'de xlconcat_1 IP'si kaç port içermektedir? "
                "NUM_PORTS değeri nedir? Bu blok neden kullanılmaktadır?"
            ),
            "key_terms":  ["xlconcat", "NUM_PORTS", "interrupt", "concat", "2"],
            "key_values": ["2"],
            "note": "design_1.tcl: xlconcat_1 NUM_PORTS=2, interrupt concatenation for MicroBlaze INTC",
        },
    ],

    # ─── RTL Signal (tone_generator.v / axis2fifo.v) ───────────────────────
    "rtl_signal": [
        {
            "id": "RTL-01",
            "project": "PROJECT-A",
            "question": (
                "tone_generator.v modülünde TONE_FREQ parametresinin "
                "varsayılan değeri nedir? Bu frekans hangi nota ile ilişkilidir?"
            ),
            "key_terms":  ["TONE_FREQ", "261", "Hz", "tone_generator"],
            "key_values": ["261"],
            "note": "tone_generator.v: TONE_FREQ=261 Hz (Middle C / Do notası)",
        },
        {
            "id": "RTL-02",
            "project": "PROJECT-A",
            "question": (
                "tone_generator.v modülünde PACKET_SIZE ve "
                "ACCUMULATOR_DEPTH parametrelerinin değerleri nedir? "
                "AXIS çıkışı kaç bayt paket gönderir?"
            ),
            "key_terms":  ["PACKET_SIZE", "256", "ACCUMULATOR_DEPTH", "32"],
            "key_values": ["256", "32"],
            "note": "tone_generator.v: PACKET_SIZE=256, ACCUMULATOR_DEPTH=32",
        },
        {
            "id": "RTL-03",
            "project": "PROJECT-A",
            "question": (
                "axis2fifo.v modülünde axis_tvalid ile axis_tready "
                "sinyallerinin AND koşulu ne zaman fifo_wr_en sinyalini aktif eder? "
                "FIFO yazma işleminin tam koşulunu belirtin."
            ),
            "key_terms":  ["axis_tvalid", "axis_tready", "fifo_wr_en", "fifo_full", "and"],
            "key_values": ["axis_tvalid", "axis_tready"],
            "note": "axis2fifo.v: fifo_wr_en = axis_tvalid & axis_tready & ~fifo_full",
        },
        {
            "id": "RTL-04",
            "project": "PROJECT-A",
            "question": (
                "tone_generator.v'de axis_tlast sinyali nasıl üretilmektedir? "
                "packet_count hangi değere ulaştığında axis_tlast aktif olur?"
            ),
            "key_terms":  ["axis_tlast", "packet_count", "PACKET_SIZE", "255"],
            "key_values": ["packet_count", "PACKET_SIZE"],
            "note": "tone_generator.v: axis_tlast = (packet_count == PACKET_SIZE-1) yani 255",
        },
    ],

    # ─── C Code (helloworld.c — v2'den farklı işlevler) ───────────────────
    "c_code": [
        {
            "id": "CC-01",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki Demo struct'ında ses verisi için "
                "kullanılan buffer (ddr_buf) nedir? "
                "Boyutu (DDR_AUDIO_LENGTH) kaçtır?"
            ),
            "key_terms":  ["ddr_buf", "DDR_AUDIO_LENGTH", "buffer", "u8"],
            "key_values": ["ddr_buf", "DDR_AUDIO_LENGTH"],
            "note": "helloworld.c: Demo struct has u8 *ddr_buf, DDR_AUDIO_LENGTH define",
        },
        {
            "id": "CC-02",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki init_dma fonksiyonunda XAxiDma_Initialize "
                "başarısız olursa ne döndürülür? "
                "DMA reset başarısız olursa hata mesajı nedir?"
            ),
            "key_terms":  ["XST_FAILURE", "XAxiDma_Initialize", "reset", "timeout", "ERROR"],
            "key_values": ["XST_FAILURE"],
            "note": "helloworld.c: returns XST_FAILURE on init error or DMA reset timeout",
        },
        {
            "id": "CC-03",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'deki sw_tone_gen fonksiyonu hangi frekansta "
                "sinüs dalgası üretir? Frekansı hesaplamak için kullanılan "
                "sabit değer nedir?"
            ),
            "key_terms":  ["TONE_FREQ", "sw_tone_gen", "sin", "261", "tone"],
            "key_values": ["TONE_FREQ", "261"],
            "note": "helloworld.c: sw_tone_gen uses TONE_FREQ=261 Hz, sinüs tablosu ile",
        },
        {
            "id": "CC-04",
            "project": "PROJECT-A",
            "question": (
                "helloworld.c'de UART üzerinden kullanıcı girişi okunurken "
                "hangi mod karakterleri tanınmaktadır? "
                "Tuş girişi ile mod değiştirme fonksiyonu nedir?"
            ),
            "key_terms":  ["button_pe", "mode", "buton", "SW_TONE_GEN", "HW_TONE_GEN", "RECV"],
            "key_values": ["SW_TONE_GEN", "HW_TONE_GEN"],
            "note": "helloworld.c: button_pe() fonksiyonu, SW_TONE_GEN/HW_TONE_GEN/RECV_WAV/PLAY_WAV modları",
        },
    ],

    # ─── XDC Detail (PROJECT-B) ────────────────────────────────────────────
    "xdc_detail": [
        {
            "id": "XD-01",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde leds[0] ve leds[7] hangi "
                "PACKAGE_PIN'lere atanmıştır?"
            ),
            "key_terms":  ["T14", "V16", "leds", "PACKAGE_PIN", "LED"],
            "key_values": ["T14", "V16"],
            "note": "nexys_video.xdc: leds[0]=T14, leds[7]=V16, IOSTANDARD=LVCMOS25",
        },
        {
            "id": "XD-02",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde sistem saati (sys_clk) için "
                "create_clock komutu hangi periyotta tanımlanmıştır? "
                "Hangi pin kullanılmaktadır?"
            ),
            "key_terms":  ["create_clock", "10.000", "100", "MHz", "sys_clk", "R4"],
            "key_values": ["10.000", "R4"],
            "note": "nexys_video.xdc: create_clock -period 10.000 -name sys_clk [get_ports sys_clk], pin R4",
        },
        {
            "id": "XD-03",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde switches[1] ve switches[2] "
                "hangi PACKAGE_PIN'lere atanmıştır? IOSTANDARD nedir?"
            ),
            "key_terms":  ["F22", "G21", "LVCMOS12", "switch", "PACKAGE_PIN"],
            "key_values": ["F22", "G21", "LVCMOS12"],
            "note": "nexys_video.xdc: switches[1]=F22, switches[2]=G21, IOSTANDARD=LVCMOS12",
        },
        {
            "id": "XD-04",
            "project": "PROJECT-B",
            "question": (
                "create_axi_with_xdc.tcl dosyasında axi_gpio_0 'ın "
                "GPIO_IO_O port genişliği (C_GPIO_WIDTH) kaçtır? "
                "GPIO2 (switch) kanal genişliği nedir?"
            ),
            "key_terms":  ["C_GPIO_WIDTH", "8", "GPIO", "GPIO2", "switch"],
            "key_values": ["8"],
            "note": "create_axi_with_xdc.tcl: C_GPIO_WIDTH=8 (8-bit LED output, 8-bit switch input)",
        },
    ],

    # ─── Cross-Project (A vs B) ────────────────────────────────────────────
    "cross_project": [
        {
            "id": "CR-01",
            "question": (
                "nexys_a7_dma_audio projesinde axi_uartlite baud rate nedir? "
                "axi_gpio_example projesinde axi_uartlite var mı? "
                "İki proje arasındaki UART konfigürasyonunu karşılaştırın."
            ),
            "project": "BOTH",
            "key_terms":  ["230400", "baud", "C_BAUDRATE", "uartlite", "fark"],
            "key_values": ["230400"],
            "note": "A: axi_uartlite_0 C_BAUDRATE=230400, B: axi_uartlite farklı veya yok",
        },
        {
            "id": "CR-02",
            "question": (
                "nexys_a7_dma_audio projesinde MIG 7-Series DDR2 IP bloğu var mı? "
                "axi_gpio_example projesinde DDR bellek kontrolcüsü var mı? "
                "İki proje bellek mimarisini karşılaştırın."
            ),
            "project": "BOTH",
            "key_terms":  ["mig_7series", "DDR2", "128MB", "GPIO", "bellek", "yok"],
            "key_values": ["mig_7series", "DDR2"],
            "note": "A: mig_7series_0 DDR2 128MB var, B: DDR yok (sadece BRAM/MicroBlaze local memory)",
        },
        {
            "id": "CR-03",
            "question": (
                "nexys_a7_dma_audio projesinde proc_sys_reset IP'si "
                "ext_reset_in portuna ne bağlıdır? "
                "axi_gpio_example projesinde reset mantığı nasıl farklıdır?"
            ),
            "project": "BOTH",
            "key_terms":  ["proc_sys_reset", "ext_reset_in", "reset", "dcm_locked", "clk_wiz"],
            "key_values": ["proc_sys_reset", "ext_reset_in"],
            "note": "A: proc_sys_reset ext_reset_in→reset_btn, dcm_locked→dcm_locked; B: farklı reset yapısı",
        },
    ],

    # ─── Trap v3 (DB'de olmayan bilgiler) ─────────────────────────────────
    "trap_v3": [
        {
            "id": "TR3-01",
            "project": "PROJECT-A",
            "question": (
                "nexys_a7_dma_audio projesinde HDMI çıkışı IP bloğu "
                "(DVI/HDMI transmitter) var mı? "
                "Video encoder parametreleri ve çözünürlük nedir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["hdmi", "dvi", "video", "encoder", "1080p", "720p",
                                       "pixel", "resolution", "axi_dynclk", "rgb2dvi"],
            "note": "Projede HDMI/DVI YOK — ses DMA projesi, video çıkışı yok",
        },
        {
            "id": "TR3-02",
            "project": "PROJECT-B",
            "question": (
                "axi_gpio_example projesinde SPI flash programlama için "
                "boot loader (u-boot veya FSBL) konfigürasyonu nedir? "
                "Quad-SPI controller parametreleri nelerdir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["u-boot", "fsbl", "boot loader", "quad-spi",
                                       "qspi", "flash", "axi_quad_spi", "xip"],
            "note": "Projede boot loader/FSBL konfigürasyonu YOK — saf GPIO örneği",
        },
        {
            "id": "TR3-03",
            "project": "PROJECT-A",
            "question": (
                "nexys_a7_dma_audio projesinde USB OTG veya USB 3.0 "
                "kontrolcüsü var mı? USB descriptor ve endpoint konfigürasyonu nedir?"
            ),
            "expected": "NOT_IN_DB",
            "hallucination_keywords": ["usb otg", "usb 3.0", "usb 2.0", "descriptor",
                                       "endpoint", "hid", "bulk", "isochronous",
                                       "xhci", "ehci", "axi_usb"],
            "note": "Projede USB kontrolcüsü YOK — sadece UART-USB köprü (FT2232) var, IP bloğu değil",
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORİ META
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_INFO_V3 = {
    "pdf_ref":       ("PDF Ref Manual (nexys-a7_rm.pdf)",           0.20),
    "ip_config":     ("IP Config      (design_1.tcl, PROJECT-A)",   0.15),
    "rtl_signal":    ("RTL Signal     (tone_gen/axis2fifo)",        0.15),
    "c_code":        ("C Code         (helloworld.c)",              0.15),
    "xdc_detail":    ("XDC Detail     (PROJECT-B)",                 0.15),
    "cross_project": ("Cross-Project  (A ↔ B)",                    0.10),
    "trap_v3":       ("Trap v3        (DB'de yok)",                 0.10),
}


# ─────────────────────────────────────────────────────────────────────────────
# SKOR
# ─────────────────────────────────────────────────────────────────────────────

NOT_IN_DB_SIGNALS = [
    "bilmiyorum", "context'te", "bağlamda", "bulunamadı", "mevcut değil",
    "yer almıyor", "bilgi yok", "not found", "not available", "cannot find",
    "no information", "kayıt yok", "verilmemiş", "belirtilmemiş",
    "sağlanan bilgide", "verilen context", "elimde yok", "bilgim yok",
    "erişemiyorum", "içermemektedir", "görünmüyor", "içinde değil",
    "bulunmamaktadır", "bulunmuyor", "tespit edilemedi",
]

_NEGATION_WORDS = [
    "yok", "değil", "bulunmamaktadır", "bulunmuyor", "içermemektedir",
    "mevcut değil", "yer almıyor", "kullanılmıyor", "kullanılmamaktadır",
    "olmayan", "yoktur", "hayır", "bulunamadı", "desteklenmiyor",
    "bilinmiyor", "içermiyor", "bulunmamakta", "içermemekte",
    "kullanılmamakta", "mevcut olmayan", "devre dışı", "etkin değil",
    "aktif değil", "tanımlanmamış", "belirtilmemiş",
    "çalışmadığı", "çalışmıyor", "yer almadığı", "bulunmadığı",
    "kullanılmadığı", "tanımlanmadığı", "içermediği",
    "not ", "no ", "does not", "doesn't", "without", "absent",
    "not found", "not available", "not present", "not used", "disabled",
]


def score_real(q: Dict, answer: str) -> Tuple[float, List[str], List[str]]:
    ans = answer.lower()
    term_hits = [t for t in q["key_terms"]  if t.lower() in ans]
    val_hits  = [v for v in q["key_values"] if v.lower() in ans]
    score = len(term_hits) / len(q["key_terms"]) * 0.60 + \
            len(val_hits)  / len(q["key_values"]) * 0.40
    return round(score, 3), term_hits, val_hits


def score_trap(q: Dict, answer: str) -> Tuple[float, str, List[str]]:
    ans = answer.lower()
    says_unknown = any(s in ans for s in NOT_IN_DB_SIGNALS)
    halluc = []
    for kw in q.get("hallucination_keywords", []):
        pat = re.compile(r'\b' + re.escape(kw.lower()) + r'\b')
        for m in pat.finditer(ans):
            window = ans[max(0, m.start()-150): m.end()+80]
            if not any(n in window for n in _NEGATION_WORDS):
                halluc.append(m.group())
    has_halluc = bool(halluc)

    if says_unknown and not has_halluc:
        return 1.0, "PASS", []
    elif says_unknown and has_halluc:
        return 0.5, "PARTIAL (reddetti ama uydurma var)", halluc
    elif not says_unknown and has_halluc:
        return 0.0, "FAIL (hallucinasyon)", halluc
    else:
        return 0.3, "PARTIAL (genel cevap, net ret yok)", []


# ─────────────────────────────────────────────────────────────────────────────
# SİSTEM YÜKLEME
# ─────────────────────────────────────────────────────────────────────────────

def load_system():
    from rag_v2.graph_store        import GraphStore
    from rag_v2.vector_store_v2    import VectorStoreV2
    from rag_v2.source_chunk_store import SourceChunkStore
    from rag_v2.query_router       import QueryRouter
    from rag_v2.hallucination_gate import HallucinationGate

    gs = GraphStore(persist_path=str(_ROOT / "db/graph/fpga_rag_v2_graph.json"))
    vs = VectorStoreV2(persist_directory=str(_ROOT / "db/chroma_v2"), threshold=0.35)
    sc = SourceChunkStore(persist_directory=str(_ROOT / "db/chroma_source_chunks"))
    router = QueryRouter(gs, vs, source_chunk_store=sc,
                         n_vector_results=6, n_source_results=10)
    gate = HallucinationGate(gs)
    return gs, vs, sc, router, gate


def get_llm():
    from rag.llm_factory import get_llm as _get
    return _get("claude-sonnet-4-6")


def ask(question: str, router, gate, llm, system_prompt: str, verbose=False) -> Dict:
    from rag_v2.response_builder   import build_llm_context, FPGA_RAG_SYSTEM_PROMPT
    from rag_v2.grounding_checker  import GroundingChecker

    t0 = time.time()
    qt = router.classify(question)
    qr = router.route(question, qt)
    gr = gate.check(qr.all_nodes(), qr.graph_edges)
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
    if answer and not answer.startswith("[LLM"):
        grounding_warns = GroundingChecker().check(answer, sc_chunks, qr.graph_nodes)
        if grounding_warns:
            gr.warnings.extend(grounding_warns)

    chunk_labels = [c.get("chunk_label", c.get("chunk_id", "?"))[:30]
                    for c in sc_chunks[:5]]
    chunk_files  = list({Path(c.get("file_path","")).name for c in sc_chunks if c.get("file_path")})

    result = {
        "question":      question[:80],
        "query_type":    qt.value,
        "vector_hits":   len(qr.vector_hits),
        "graph_nodes":   len(qr.graph_nodes),
        "source_chunks": len(sc_chunks),
        "chunk_labels":  chunk_labels,
        "chunk_files":   chunk_files,
        "confidence":    gr.overall_confidence,
        "warnings":      gr.warnings,
        "answer":        answer,
        "elapsed_s":     round(time.time() - t0, 2),
    }
    if verbose:
        print(f"\n    Q : {question[:100]}")
        print(f"    [Type={qt.value} | chunks={len(sc_chunks)}: {chunk_labels}]")
        print(f"    A : {answer[:500]}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# KATEGORİ ÇALIŞTIRICISI
# ─────────────────────────────────────────────────────────────────────────────

def run_category(cat_key, questions, router, gate, llm, system_prompt, verbose) -> Dict:
    label, _ = CATEGORY_INFO_V3[cat_key]
    print(hdr(f"KATEGORİ: {label}"))

    results = []
    for q in questions:
        is_trap = q.get("expected") == "NOT_IN_DB"
        print(f"\n  {B}{q['id']}{RST}  [{q['project']}]")
        r = ask(q["question"], router, gate, llm, system_prompt, verbose)

        if is_trap:
            score, verdict, halluc = score_trap(q, r["answer"])
            sym = ok if score >= 0.8 else (warn if score >= 0.4 else err)
            print(f"    {sym(f'Trap skor={score:.2f} — {verdict}')}")
            if halluc:
                print(f"    Uydurma: {halluc[:3]}")
            results.append({
                "id": q["id"], "category": cat_key,
                "project": q["project"], "type": "trap",
                "score": score, "verdict": verdict,
                "hallucination_matches": halluc,
                "source_chunks": r["source_chunks"],
                "chunk_labels": r["chunk_labels"],
                "query_type": r["query_type"],
                "answer_snippet": r["answer"][:300],
                "ground_truth": q.get("note", ""),
            })
        else:
            score, term_hits, val_hits = score_real(q, r["answer"])
            sym = ok if score >= 0.8 else (warn if score >= 0.5 else err)
            print(f"    {sym(f'Skor={score:.2f}')} | terms={term_hits} | vals={val_hits}")
            print(f"    Chunks [{r['source_chunks']}]: {r['chunk_labels']}")
            results.append({
                "id": q["id"], "category": cat_key,
                "project": q["project"], "type": "real",
                "score": score,
                "term_hits": term_hits,
                "term_misses": [t for t in q["key_terms"]  if t not in term_hits],
                "val_hits": val_hits,
                "val_misses": [v for v in q["key_values"] if v not in val_hits],
                "source_chunks": r["source_chunks"],
                "chunk_labels": r["chunk_labels"],
                "query_type": r["query_type"],
                "answer_snippet": r["answer"][:300],
                "ground_truth": q.get("note", ""),
            })

    avg = sum(x["score"] for x in results) / len(results) if results else 0.0
    print(f"\n  {B}Kategori skoru{RST}: {avg:.3f} → {grade(avg)}")
    return {
        "category": cat_key, "label": label,
        "score": round(avg, 3), "grade": grade_raw(avg),
        "n_questions": len(results), "questions": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ÖZET RAPOR
# ─────────────────────────────────────────────────────────────────────────────

def print_summary(cat_results: List[Dict]) -> float:
    print(f"\n{B}{'═'*68}{RST}")
    print(f"{B}  BLIND BENCHMARK v3 — ÖZET RAPOR{RST}")
    print(f"{B}{'═'*68}{RST}")

    total_weighted = 0.0
    for cr in cat_results:
        _, weight = CATEGORY_INFO_V3.get(cr["category"], ("?", 0.15))
        s   = cr["score"]
        bar = "█" * int(s * 20) + "░" * (20 - int(s * 20))
        total_weighted += s * weight
        print(f"  {cr['label']:42s} {bar} {s:.3f} [{grade(s)}] (w={weight:.0%})")

    print(f"\n  {'─'*68}")
    print(f"  AĞIRLIKLI TOPLAM SKOR : {total_weighted:.3f} → {grade(total_weighted)}")
    print(f"  {'─'*68}")

    all_q = [q for cr in cat_results for q in cr["questions"]]
    n_total     = len(all_q)
    n_pass      = sum(1 for q in all_q if q["score"] >= 0.80)
    n_fail      = sum(1 for q in all_q if q["score"] < 0.50)
    n_trap      = sum(1 for q in all_q if q["type"] == "trap")
    n_trap_pass = sum(1 for q in all_q if q["type"] == "trap" and q["score"] >= 0.80)

    print(f"\n  Toplam soru      : {n_total}")
    print(f"  Geçen  (≥0.80)   : {n_pass}/{n_total}")
    print(f"  Başarısız (<0.50): {n_fail}/{n_total}")
    print(f"  Trap geçen       : {n_trap_pass}/{n_trap}")

    worst = sorted(all_q, key=lambda x: x["score"])[:5]
    print(f"\n  En düşük 5 soru:")
    for q in worst:
        misses = q.get("term_misses", []) + q.get("val_misses", [])
        print(f"    {q['id']}: skor={q['score']:.2f} | eksik={misses}")

    print(f"{B}{'═'*68}{RST}\n")
    return round(total_weighted, 3)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FPGA RAG v2 Blind Benchmark v3")
    parser.add_argument("--save",     action="store_true", help="JSON raporu kaydet")
    parser.add_argument("--verbose",  action="store_true", help="Tam cevapları göster")
    parser.add_argument("--category", type=str, default="",
                        help="Belirli kategori: pdf_ref|ip_config|rtl_signal|"
                             "c_code|xdc_detail|cross_project|trap_v3")
    args = parser.parse_args()

    n_total = sum(len(v) for v in BLIND_QUESTIONS_V3.values())
    print(f"\n{B}{'═'*68}")
    print(f"  FPGA RAG v2 — Blind Benchmark v3")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*68}{RST}")
    print(f"\n  Kapsam  : {n_total} soru × 7 kategori")
    print(f"  YENİ    : PDF Reference Manual kategorisi (nexys-a7_rm.pdf)")
    print(f"  Tümü    : v2'den tamamen farklı, hiç görülmemiş sorular")

    print("\n  [SİSTEM] Yükleniyor...")
    gs, vs, sc, router, gate = load_system()
    print(f"  Source chunks: {sc.count()}")
    llm = get_llm()
    if not llm:
        print(f"  {Y}⚠ LLM yok{RST}")

    from rag_v2.response_builder import FPGA_RAG_SYSTEM_PROMPT
    system_prompt = FPGA_RAG_SYSTEM_PROMPT

    t_start = time.time()
    cat_results = []
    only_cat = args.category.lower()

    for cat_key, questions in BLIND_QUESTIONS_V3.items():
        if only_cat and cat_key != only_cat:
            continue
        cr = run_category(cat_key, questions, router, gate, llm, system_prompt, args.verbose)
        cat_results.append(cr)

    elapsed = round(time.time() - t_start, 1)
    final_score = print_summary(cat_results)
    print(f"  Toplam süre: {elapsed}s\n")

    if args.save:
        out_path = _ROOT / "blind_benchmark_v3_report.json"
        report = {
            "timestamp":     datetime.now().isoformat(),
            "version":       "v3",
            "total_score":   final_score,
            "overall_grade": grade_raw(final_score),
            "elapsed_s":     elapsed,
            "n_questions":   n_total,
            "categories":    cat_results,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  Rapor kaydedildi: {out_path}\n")


if __name__ == "__main__":
    main()
