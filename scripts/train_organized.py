#!/usr/bin/env python3
"""
Organized Training Script - Kategorilere göre organize eğitim

Dosyaları anlamlı kategorilere böler ve her kategoriyi ayrı ayrı eğitir.
Bu sayede VS Code çökmesi durumunda bile kaldığı kategoriden devam edebilir.

Kategoriler:
    1. PDFs - Xilinx Dokümantasyonu (cihaz ailelerine göre bölünmüş)
    2. Code - Digilent projeleri (kart ailelerine göre bölünmüş)

Kullanım:
    python scripts/train_organized.py                    # Kaldığı yerden devam et
    python scripts/train_organized.py --list             # Kategorileri listele
    python scripts/train_organized.py --category IP      # Sadece belirli kategoriyi eğit
    python scripts/train_organized.py --reset            # Sıfırdan başla
    python scripts/train_organized.py --stats            # İstatistikleri göster
"""

import sys
import os
import json
import argparse
import gc
from pathlib import Path
from datetime import datetime
import time
from collections import defaultdict
from typing import Dict, List, Tuple, Optional

# Proje kök dizinini path'e ekle
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# ============================================================================
# KONFIGÜRASYON
# ============================================================================

CHECKPOINT_FILE = project_root / "training_organized_checkpoint.json"
DATA_DIR = project_root / "data"
PDF_DIR = DATA_DIR / "pdfs"
CODE_DIR = DATA_DIR / "code"

# Hafif ayarlar - sistem donmasin
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
EMBEDDING_BATCH_SIZE = 5  # Cok kucuk batch
FILES_PER_SAVE = 3  # Her 3 dosyada kaydet

# Global verbose flag
VERBOSE = False

def log(msg, level="info"):
    """Verbose logging."""
    if level == "info":
        print(msg)
    elif level == "debug" and VERBOSE:
        print(f"  [DEBUG] {msg}")
    elif level == "detail" and VERBOSE:
        print(f"    -> {msg}")

# ============================================================================
# KATEGORİ TANIMLARI
# ============================================================================

# PDF Kategorileri - Xilinx dokümantasyonu için
PDF_CATEGORIES = {
    # FPGA Aileleri
    "7_Series": {
        "name": "7 Series FPGAs",
        "description": "Artix-7, Kintex-7, Virtex-7 dokümantasyonu",
        "priority": 1,
        "path_pattern": "XilinxDocs/7_Series"
    },
    "UltraScale": {
        "name": "UltraScale/UltraScale+ FPGAs",
        "description": "UltraScale ve UltraScale+ FPGA ailesi",
        "priority": 2,
        "path_pattern": "XilinxDocs/UltraScale"
    },
    "Zynq_7000": {
        "name": "Zynq-7000 SoC",
        "description": "Zynq-7000 All Programmable SoC",
        "priority": 3,
        "path_pattern": "XilinxDocs/Zynq_7000"
    },
    "Zynq_MPSoC": {
        "name": "Zynq UltraScale+ MPSoC",
        "description": "Zynq UltraScale+ MPSoC ailesi",
        "priority": 4,
        "path_pattern": "XilinxDocs/Zynq_UltraScale+_MPSoC"
    },
    "Versal": {
        "name": "Versal Adaptive SoCs",
        "description": "Versal ACAP ailesi",
        "priority": 5,
        "path_pattern": "XilinxDocs/Versal_Device"
    },
    "Virtex_5": {
        "name": "Virtex-5 FPGAs",
        "description": "Virtex-5 ailesi (legacy)",
        "priority": 10,
        "path_pattern": "XilinxDocs/Virtex_5"
    },
    "Virtex_6": {
        "name": "Virtex-6 FPGAs",
        "description": "Virtex-6 ailesi (legacy)",
        "priority": 11,
        "path_pattern": "XilinxDocs/Virtex_6"
    },
    "Spartan_6": {
        "name": "Spartan-6 FPGAs",
        "description": "Spartan-6 ailesi (legacy)",
        "priority": 12,
        "path_pattern": "XilinxDocs/Spartan_6"
    },
    "CoolRunner": {
        "name": "CoolRunner CPLDs",
        "description": "CoolRunner CPLD ailesi",
        "priority": 13,
        "path_pattern": "XilinxDocs/CoolRunner"
    },
    
    # Araçlar
    "Vivado": {
        "name": "Vivado Design Suite",
        "description": "Vivado IDE ve araçları",
        "priority": 6,
        "path_pattern": "XilinxDocs/Vivado"
    },
    "Vitis": {
        "name": "Vitis Products",
        "description": "Vitis IDE, HLS, AI Engine",
        "priority": 7,
        "path_pattern": "XilinxDocs/Vitis_Products"
    },
    "IP": {
        "name": "IP Cores",
        "description": "Xilinx IP core dokümantasyonu",
        "priority": 8,
        "path_pattern": "XilinxDocs/IP"
    },
    "Alveo": {
        "name": "Alveo Accelerator Cards",
        "description": "Veri merkezi hızlandırıcı kartları",
        "priority": 9,
        "path_pattern": "XilinxDocs/Alveo"
    },
    
    # Diğer
    "PetaLinux": {
        "name": "PetaLinux Tools",
        "description": "PetaLinux embedded Linux",
        "priority": 14,
        "path_pattern": "XilinxDocs/PetaLinux"
    },
    "Other_PDFs": {
        "name": "Diğer PDF'ler",
        "description": "Kategorize edilmemiş PDF'ler",
        "priority": 99,
        "path_pattern": None  # Kalan tüm PDF'ler
    }
}

# Kod Kategorileri - Digilent kartlarına göre
CODE_CATEGORIES = {
    "Arty_7Series": {
        "name": "Arty A7 & S7 Projeleri",
        "description": "Arty A7, Arty S7 FPGA kartları",
        "priority": 1,
        "patterns": ["Arty-A7", "Arty-S7", "Arty-GPIO", "Arty-Pmod", "Arty-XADC", "Arty-template"]
    },
    "Arty_Zynq": {
        "name": "Arty Z7 Projeleri",
        "description": "Arty Z7 Zynq kartları",
        "priority": 2,
        "patterns": ["Arty-Z7", "ArtyZ7"]
    },
    "Basys": {
        "name": "Basys Projeleri",
        "description": "Basys-3 FPGA eğitim kartları",
        "priority": 3,
        "patterns": ["Basys"]
    },
    "Nexys": {
        "name": "Nexys Projeleri",
        "description": "Nexys A7, Nexys Video, Nexys 4",
        "priority": 4,
        "patterns": ["Nexys"]
    },
    "Zybo": {
        "name": "Zybo Projeleri",
        "description": "Zybo Z7 Zynq kartları",
        "priority": 5,
        "patterns": ["Zybo", "ZYBO"]
    },
    "Cmod": {
        "name": "Cmod Projeleri",
        "description": "Cmod A7, Cmod S7",
        "priority": 6,
        "patterns": ["Cmod"]
    },
    "Cora": {
        "name": "Cora Projeleri",
        "description": "Cora Z7 Zynq kartları",
        "priority": 7,
        "patterns": ["Cora"]
    },
    "Genesys": {
        "name": "Genesys Projeleri",
        "description": "Genesys 2, Genesys ZU",
        "priority": 8,
        "patterns": ["Genesys"]
    },
    "Eclypse": {
        "name": "Eclypse Projeleri",
        "description": "Eclypse Z7",
        "priority": 9,
        "patterns": ["Eclypse"]
    },
    "Zedboard": {
        "name": "Zedboard Projeleri",
        "description": "Zedboard Zynq",
        "priority": 10,
        "patterns": ["Zedboard", "ZedBoard"]
    },
    "Vitis_Examples": {
        "name": "Vitis Örnekleri",
        "description": "Vitis, Vitis-AI, HLS örnekleri",
        "priority": 11,
        "patterns": ["Vitis", "finn", "brevitas"]
    },
    "Vivado_Tutorials": {
        "name": "Vivado Tutorials",
        "description": "Vivado tasarım eğitimleri",
        "priority": 12,
        "patterns": ["Vivado-Design", "vivado-library", "vivado-boards", "FPGA-Design-Flow"]
    },
    "HDL_Libraries": {
        "name": "HDL Kütüphaneleri",
        "description": "Genel HDL ve IP kütüphaneleri",
        "priority": 13,
        "patterns": ["hdl", "digilent-", "vivado-library"]
    },
    "PYNQ": {
        "name": "PYNQ Projeleri",
        "description": "Python productivity for Zynq",
        "priority": 14,
        "patterns": ["PYNQ", "pynq"]
    },
    "Linux_BSP": {
        "name": "Linux BSP",
        "description": "PetaLinux, u-boot, device-tree",
        "priority": 15,
        "patterns": ["Petalinux", "u-boot", "device-tree", "linux"]
    },
    "Other_Code": {
        "name": "Diğer Kod",
        "description": "Kategorize edilmemiş projeler",
        "priority": 99,
        "patterns": []  # Kalan tüm kod
    }
}


# ============================================================================
# YARDIMCI FONKSİYONLAR
# ============================================================================

def print_banner():
    print("")
    print("=" * 60)
    print("   GCP-RAG-VIVADO ORGANIZED TRAINER")
    print("   Kategorilere Gore Organize Egitim Araci")
    print("=" * 60)
    print("")


def load_checkpoint() -> dict:
    """Checkpoint yükle."""
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "completed_categories": [],
        "current_category": None,
        "current_file_index": 0,
        "total_files_processed": 0,
        "total_chunks_embedded": 0,
        "category_stats": {},
        "last_update": None,
        "status": "not_started",
        "errors": []
    }


def save_checkpoint(checkpoint: dict):
    """Checkpoint kaydet."""
    checkpoint["last_update"] = datetime.now().isoformat()
    with open(CHECKPOINT_FILE, 'w', encoding='utf-8') as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)
    if VERBOSE:
        print(f"      [CHECKPOINT] {checkpoint['total_files_processed']} dosya, {checkpoint['total_chunks_embedded']} chunk kaydedildi", flush=True)
    gc.collect()  # Bellek temizle


def categorize_pdf(filepath: Path) -> str:
    """PDF dosyasını kategorize et."""
    # Windows ve Unix path'lerini normalize et
    rel_path = str(filepath.relative_to(PDF_DIR)).replace("\\", "/")
    
    for cat_id, cat_info in PDF_CATEGORIES.items():
        pattern = cat_info.get("path_pattern")
        if pattern:
            # Pattern'i de normalize et
            normalized_pattern = pattern.replace("\\", "/")
            if normalized_pattern in rel_path:
                return cat_id
    
    return "Other_PDFs"


def categorize_code(dirpath: Path) -> str:
    """Kod klasörünü kategorize et."""
    dirname = dirpath.name
    
    for cat_id, cat_info in CODE_CATEGORIES.items():
        patterns = cat_info.get("patterns", [])
        for pattern in patterns:
            if pattern in dirname:
                return cat_id
    
    return "Other_Code"


def get_all_pdfs_by_category() -> Dict[str, List[Path]]:
    """Tüm PDF'leri kategorilere göre grupla."""
    categories = defaultdict(list)
    
    if not PDF_DIR.exists():
        return categories
    
    for pdf in PDF_DIR.rglob("*.pdf"):
        cat = categorize_pdf(pdf)
        categories[cat].append(pdf)
    
    return dict(categories)


def get_all_code_by_category() -> Dict[str, List[Path]]:
    """Tüm kod klasörlerini kategorilere göre grupla."""
    categories = defaultdict(list)
    
    if not CODE_DIR.exists():
        return categories
    
    # Her proje klasörünü kategorize et
    for item in CODE_DIR.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            cat = categorize_code(item)
            categories[cat].append(item)
    
    return dict(categories)


def list_all_categories():
    """Tum kategorileri listele."""
    print("\n[PDF KATEGORILERI]")
    print("=" * 60)
    
    pdf_cats = get_all_pdfs_by_category()
    sorted_pdf_cats = sorted(
        PDF_CATEGORIES.items(),
        key=lambda x: x[1].get("priority", 99)
    )
    
    for cat_id, cat_info in sorted_pdf_cats:
        count = len(pdf_cats.get(cat_id, []))
        if count > 0:
            print(f"  [{cat_id:20}] {cat_info['name']:30} ({count:4} PDF)")
    
    print("\n[KOD KATEGORILERI]")
    print("=" * 60)
    
    code_cats = get_all_code_by_category()
    sorted_code_cats = sorted(
        CODE_CATEGORIES.items(),
        key=lambda x: x[1].get("priority", 99)
    )
    
    for cat_id, cat_info in sorted_code_cats:
        count = len(code_cats.get(cat_id, []))
        if count > 0:
            print(f"  [{cat_id:20}] {cat_info['name']:30} ({count:4} proje)")
    
    # Toplam istatistikler
    total_pdfs = sum(len(v) for v in pdf_cats.values())
    total_code = sum(len(v) for v in code_cats.values())
    
    print("\n" + "=" * 60)
    print(f"  Toplam: {total_pdfs} PDF, {total_code} kod projesi")


def show_stats(checkpoint: dict):
    """Istatistikleri goster."""
    print("\n[EGITIM ISTATISTIKLERI]")
    print("=" * 60)
    
    print(f"  Durum: {checkpoint.get('status', 'Bilinmiyor')}")
    print(f"  Islenen Dosya: {checkpoint.get('total_files_processed', 0)}")
    print(f"  Olusturulan Chunk: {checkpoint.get('total_chunks_embedded', 0)}")
    print(f"  Son Guncelleme: {checkpoint.get('last_update', 'Yok')}")
    
    completed = checkpoint.get("completed_categories", [])
    print(f"\n  Tamamlanan Kategoriler ({len(completed)}):")
    for cat in completed:
        stats = checkpoint.get("category_stats", {}).get(cat, {})
        files = stats.get("files", 0)
        chunks = stats.get("chunks", 0)
        print(f"    [OK] {cat}: {files} dosya, {chunks} chunk")
    
    current = checkpoint.get("current_category")
    if current:
        idx = checkpoint.get("current_file_index", 0)
        print(f"\n  Devam Eden: {current} (dosya #{idx})")
    
    errors = checkpoint.get("errors", [])
    if errors:
        print(f"\n  Hatalar ({len(errors)}):")
        for err in errors[-5:]:  # Son 5 hata
            print(f"    [!] {err}")


# ============================================================================
# METİN İŞLEME FONKSİYONLARI
# ============================================================================

def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Metni akıllı parçalara böl."""
    if not text or len(text.strip()) == 0:
        return []
    
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    start = 0
    
    while start < len(text):
        end = min(start + chunk_size, len(text))
        
        # Doğal sınırda kes
        if end < len(text):
            # Paragraf sonu ara
            para_break = text.rfind("\n\n", start + chunk_size // 2, end)
            if para_break > start:
                end = para_break + 2
            else:
                # Cümle sonu ara
                for sep in [". ", ".\n", "?\n", "!\n"]:
                    sent_break = text.rfind(sep, start + chunk_size // 3, end)
                    if sent_break > start:
                        end = sent_break + len(sep)
                        break
                else:
                    # Satır sonu ara
                    line_break = text.rfind("\n", start + chunk_size // 2, end)
                    if line_break > start:
                        end = line_break + 1
        
        chunk = text[start:end].strip()
        if chunk and len(chunk) > 50:  # Çok kısa chunk'ları atla
            chunks.append(chunk)
        
        # Overlap ile sonraki chunk'a geç
        start = end - overlap if end < len(text) else end
    
    return chunks


def extract_text_from_pdf(pdf_path: Path) -> Tuple[str, dict]:
    """PDF'den metin çıkar."""
    try:
        import fitz  # PyMuPDF
        
        doc = fitz.open(str(pdf_path))
        text_parts = []
        
        for page_num, page in enumerate(doc):
            text = page.get_text()
            if text.strip():
                text_parts.append(text)
        
        doc.close()
        
        full_text = "\n\n".join(text_parts)
        metadata = {
            "source": str(pdf_path),
            "filename": pdf_path.name,
            "type": "pdf"
        }
        
        return full_text, metadata
        
    except Exception as e:
        return "", {"error": str(e)}


def load_code_files(project_dir: Path) -> List[Tuple[str, dict]]:
    """Proje klasöründen kod dosyalarını yükle."""
    results = []
    
    # Desteklenen uzantılar
    extensions = {
        ".v": "verilog",
        ".sv": "systemverilog",
        ".vhd": "vhdl",
        ".vhdl": "vhdl",
        ".tcl": "tcl",
        ".xdc": "constraints",
        ".xci": "ip_config",
        ".bd": "block_design",
        ".c": "c",
        ".h": "c_header",
        ".cpp": "cpp",
        ".py": "python",
        ".mk": "makefile",
        ".sh": "shell"
    }
    
    for ext, lang in extensions.items():
        for file in project_dir.rglob(f"*{ext}"):
            try:
                # Çok büyük dosyaları atla
                if file.stat().st_size > 500_000:  # 500KB
                    continue
                
                text = file.read_text(encoding='utf-8', errors='ignore')
                if text.strip():
                    metadata = {
                        "source": str(file),
                        "filename": file.name,
                        "project": project_dir.name,
                        "language": lang,
                        "type": "code"
                    }
                    results.append((text, metadata))
                    
            except Exception:
                continue
    
    return results


# ============================================================================
# EĞİTİM FONKSİYONLARI
# ============================================================================

def train_category(
    category_id: str,
    category_type: str,  # "pdf" veya "code"
    files: List[Path],
    checkpoint: dict,
    embeddings,
    vectorstore
):
    """Bir kategoriyi eğit."""
    
    cat_info = (PDF_CATEGORIES if category_type == "pdf" else CODE_CATEGORIES).get(category_id, {})
    cat_name = cat_info.get("name", category_id)
    
    print(f"\n{'='*60}")
    print(f"[*] Kategori: {cat_name}")
    print(f"    Tip: {category_type.upper()}")
    print(f"    Dosya Sayisi: {len(files)}")
    print(f"{'='*60}")
    
    # Kaldığı yerden devam et
    start_index = 0
    if checkpoint.get("current_category") == f"{category_type}_{category_id}":
        start_index = checkpoint.get("current_file_index", 0)
        print(f"    --> Dosya #{start_index}'den devam ediliyor...")
    
    # Kategori istatistikleri
    cat_key = f"{category_type}_{category_id}"
    if cat_key not in checkpoint.get("category_stats", {}):
        checkpoint.setdefault("category_stats", {})[cat_key] = {"files": 0, "chunks": 0}
    
    total_chunks = 0
    files_processed = 0
    
    for i, file_path in enumerate(files[start_index:], start=start_index):
        try:
            print(f"\n   [{i+1}/{len(files)}] {file_path.name[:50]}...", end=" ", flush=True)
            
            # Icerigi yukle
            if category_type == "pdf":
                text, metadata = extract_text_from_pdf(file_path)
                if not text:
                    print("[EMPTY]")
                    continue
                documents = [(text, metadata)]
                if VERBOSE:
                    print(f"\n      -> PDF yuklendi: {len(text)} karakter")
            else:
                documents = load_code_files(file_path)
                if not documents:
                    print("[EMPTY]")
                    continue
                if VERBOSE:
                    print(f"\n      -> {len(documents)} kod dosyasi yuklendi")
            
            # Parçala ve embed et
            all_chunks = []
            all_metadata = []
            
            for text, meta in documents:
                chunks = chunk_text(text)
                for j, chunk in enumerate(chunks):
                    chunk_meta = meta.copy()
                    chunk_meta["chunk_index"] = j
                    chunk_meta["category"] = category_id
                    all_chunks.append(chunk)
                    all_metadata.append(chunk_meta)
            
            if not all_chunks:
                print("[NO CHUNKS]")
                continue
            
            if VERBOSE:
                print(f"      -> {len(all_chunks)} chunk olusturuldu")
            
            # Batch halinde embed et
            batch_count = 0
            for batch_start in range(0, len(all_chunks), EMBEDDING_BATCH_SIZE):
                batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(all_chunks))
                batch_chunks = all_chunks[batch_start:batch_end]
                batch_meta = all_metadata[batch_start:batch_end]
                
                try:
                    # Embedding olustur
                    batch_embeddings = embeddings.embed_texts(batch_chunks)
                    
                    # Unique ID'ler olustur
                    import uuid
                    batch_ids = [str(uuid.uuid4()) for _ in batch_chunks]
                    
                    # ChromaDB'ye ekle
                    vectorstore.add_documents(
                        documents=batch_chunks,
                        embeddings=batch_embeddings,
                        ids=batch_ids,
                        metadatas=batch_meta
                    )
                    batch_count += 1
                    if VERBOSE:
                        print(f"      -> Batch {batch_count}: {len(batch_chunks)} chunk embed edildi")
                except Exception as e:
                    print(f"[EMBED ERROR] {e}")
                    time.sleep(2)  # Rate limit icin bekle
                    continue
            
            total_chunks += len(all_chunks)
            files_processed += 1
            print(f"[OK] {len(all_chunks)} chunk")
            
            # Periyodik kaydet
            if files_processed % FILES_PER_SAVE == 0:
                checkpoint["current_category"] = cat_key
                checkpoint["current_file_index"] = i + 1
                checkpoint["total_files_processed"] += files_processed
                checkpoint["total_chunks_embedded"] += total_chunks
                checkpoint["category_stats"][cat_key]["files"] += files_processed
                checkpoint["category_stats"][cat_key]["chunks"] += total_chunks
                checkpoint["status"] = "in_progress"
                save_checkpoint(checkpoint)
                
                # İstatistikleri sıfırla
                files_processed = 0
                total_chunks = 0
                
                print(f"\n    [SAVED] Checkpoint kaydedildi (dosya #{i+1})")
                if VERBOSE:
                    print(f"      -> Toplam: {checkpoint['total_files_processed']} dosya, {checkpoint['total_chunks_embedded']} chunk")
                gc.collect()
                
        except KeyboardInterrupt:
            print("\n\n[STOPPED] Kullanici tarafindan durduruldu.")
            checkpoint["current_category"] = cat_key
            checkpoint["current_file_index"] = i
            checkpoint["status"] = "paused"
            save_checkpoint(checkpoint)
            raise
            
        except Exception as e:
            error_msg = f"{file_path.name}: {str(e)[:100]}"
            checkpoint.setdefault("errors", []).append(error_msg)
            print(f"[ERROR] {e}")
            if VERBOSE:
                import traceback
                traceback.print_exc()
            continue
    
    # Kategori tamamlandı
    checkpoint["completed_categories"].append(cat_key)
    checkpoint["current_category"] = None
    checkpoint["current_file_index"] = 0
    checkpoint["total_files_processed"] += files_processed
    checkpoint["total_chunks_embedded"] += total_chunks
    checkpoint["category_stats"][cat_key]["files"] += files_processed
    checkpoint["category_stats"][cat_key]["chunks"] += total_chunks
    save_checkpoint(checkpoint)
    
    cat_stats = checkpoint["category_stats"][cat_key]
    print(f"\n    [DONE] Kategori tamamlandi: {cat_stats['files']} dosya, {cat_stats['chunks']} chunk")


def get_training_queue(checkpoint: dict, specific_category: str = None) -> List[Tuple[str, str, List[Path]]]:
    """Eğitim kuyruğunu oluştur."""
    queue = []
    completed = set(checkpoint.get("completed_categories", []))
    
    # PDF kategorileri
    pdf_cats = get_all_pdfs_by_category()
    sorted_pdf_cats = sorted(
        PDF_CATEGORIES.items(),
        key=lambda x: x[1].get("priority", 99)
    )
    
    for cat_id, cat_info in sorted_pdf_cats:
        key = f"pdf_{cat_id}"
        if key in completed:
            continue
        if specific_category and cat_id != specific_category:
            continue
        
        files = pdf_cats.get(cat_id, [])
        if files:
            queue.append(("pdf", cat_id, files))
    
    # Kod kategorileri
    code_cats = get_all_code_by_category()
    sorted_code_cats = sorted(
        CODE_CATEGORIES.items(),
        key=lambda x: x[1].get("priority", 99)
    )
    
    for cat_id, cat_info in sorted_code_cats:
        key = f"code_{cat_id}"
        if key in completed:
            continue
        if specific_category and cat_id != specific_category:
            continue
        
        files = code_cats.get(cat_id, [])
        if files:
            queue.append(("code", cat_id, files))
    
    return queue


def main():
    global VERBOSE
    parser = argparse.ArgumentParser(description="Organize edilmis RAG egitimi")
    parser.add_argument("--list", action="store_true", help="Kategorileri listele")
    parser.add_argument("--category", type=str, help="Belirli bir kategoriyi egit")
    parser.add_argument("--reset", action="store_true", help="Sifirdan basla")
    parser.add_argument("--stats", action="store_true", help="Istatistikleri goster")
    parser.add_argument("-v", "--verbose", action="store_true", help="Detayli cikti goster")
    args = parser.parse_args()
    
    VERBOSE = args.verbose
    if VERBOSE:
        print("[VERBOSE MODE ENABLED]")
    
    print_banner()
    
    # Kategorileri listele
    if args.list:
        list_all_categories()
        return
    
    # Checkpoint yükle
    if args.reset and CHECKPOINT_FILE.exists():
        print("[DELETE] Checkpoint siliniyor...")
        CHECKPOINT_FILE.unlink()
    
    checkpoint = load_checkpoint()
    
    # İstatistikler
    if args.stats:
        show_stats(checkpoint)
        return
    
    # Eğitim kuyruğu
    queue = get_training_queue(checkpoint, args.category)
    
    if not queue:
        print("\n[COMPLETE] Tum kategoriler egitilmis!")
        show_stats(checkpoint)
        return
    
    print(f"\n[QUEUE] Egitim Kuyrugu: {len(queue)} kategori")
    for cat_type, cat_id, files in queue:
        print(f"   • {cat_type}/{cat_id}: {len(files)} dosya")
    
    # Embedding ve vectorstore baslat
    print("\n[INIT] Sistem hazirlaniyor...", flush=True)
    
    try:
        print("    -> Importing modules...", flush=True)
        from src.rag.sentence_embeddings import SentenceEmbeddings
        from src.vectorstore.chroma_store import ChromaVectorStore
        
        print("    -> SentenceEmbeddings olusturuluyor (768 dim, local)...", flush=True)
        embeddings = SentenceEmbeddings()  # all-mpnet-base-v2, 768 boyut
        
        print("    -> ChromaVectorStore olusturuluyor...", flush=True)
        vectorstore = ChromaVectorStore(
            persist_directory=str(project_root / "chroma_db"),
            verbose=VERBOSE
        )
        
        print("    -> Dokuman sayisi kontrol ediliyor...", flush=True)
        doc_count = vectorstore.get_document_count()
        print(f"    [OK] Hazir! ChromaDB: {doc_count} dokuman mevcut", flush=True)
        
    except Exception as e:
        print(f"    [ERROR] Baslatma hatasi: {e}")
        return
    
    # Eğitimi başlat
    checkpoint["status"] = "running"
    save_checkpoint(checkpoint)
    
    try:
        for cat_type, cat_id, files in queue:
            train_category(
                category_id=cat_id,
                category_type=cat_type,
                files=files,
                checkpoint=checkpoint,
                embeddings=embeddings,
                vectorstore=vectorstore
            )
            
    except KeyboardInterrupt:
        print("\n\n[PAUSED] Egitim duraklatildi. Tekrar calistirarak devam edebilirsiniz.")
        
    finally:
        # PersistentClient otomatik kaydeder
        doc_count = vectorstore.get_document_count()
        print(f"\n[SAVED] VectorStore kaydedildi. Toplam {doc_count} dokuman.")
    
    # Final istatistikler
    checkpoint = load_checkpoint()
    checkpoint["status"] = "completed" if not get_training_queue(checkpoint) else "paused"
    save_checkpoint(checkpoint)
    show_stats(checkpoint)


if __name__ == "__main__":
    main()
