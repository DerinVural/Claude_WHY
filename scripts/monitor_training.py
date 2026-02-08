#!/usr/bin/env python3
"""Real-time Training Monitor - Her 5 saniyede metrikleri gösterir."""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

CHECKPOINT = project_root / "training_organized_checkpoint.json"

def clear_screen():
    """Ekranı temizle."""
    import os
    os.system('cls' if os.name == 'nt' else 'clear')

def load_checkpoint():
    """Checkpoint yükle."""
    if CHECKPOINT.exists():
        with open(CHECKPOINT, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def format_time(iso_str):
    """ISO zaman formatını okunabilir yap."""
    try:
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%H:%M:%S")
    except:
        return iso_str

def print_metrics():
    """Metrikleri yazdır."""
    clear_screen()
    
    checkpoint = load_checkpoint()
    
    print("=" * 70)
    print("🔥 GERÇEK ZAMANLI EĞİTİM MONİTÖRÜ")
    print("=" * 70)
    print(f"⏰ Zaman: {datetime.now().strftime('%H:%M:%S')}")
    print()
    
    # Durum
    status = checkpoint.get('status', 'unknown')
    status_emoji = {
        'not_started': '⚪ HENÜZ BAŞLAMADI',
        'running': '🟢 ÇALIŞIYOR',
        'in_progress': '🟢 ÇALIŞIYOR',
        'paused': '⏸️ DURAKLADI',
        'completed': '✅ TAMAMLANDI',
        'error': '❌ HATA'
    }
    print(f"📊 Durum: {status_emoji.get(status, status)}")
    print()
    
    # Progress
    current_cat = checkpoint.get('current_category')
    file_idx = checkpoint.get('current_file_index', 0)
    total_files = checkpoint.get('total_files_processed', 0)
    total_chunks = checkpoint.get('total_chunks_embedded', 0)
    
    print(f"📂 Mevcut Kategori: {current_cat or 'Yok'}")
    print(f"📄 İşlenen Dosya: {total_files}")
    print(f"📦 Toplam Chunk: {total_chunks:,}")
    print()
    
    # Tamamlanan kategoriler
    completed = checkpoint.get('completed_categories', [])
    print(f"✅ Tamamlanan Kategoriler ({len(completed)}):")
    for cat in completed[-5:]:  # Son 5 kategori
        print(f"   • {cat}")
    print()
    
    # Stats per category
    cat_stats = checkpoint.get('category_stats', {})
    if cat_stats:
        print("📈 Kategori İstatistikleri:")
        for cat_name, stats in list(cat_stats.items())[-3:]:
            files = stats.get('files', 0)
            chunks = stats.get('chunks', 0)
            print(f"   • {cat_name}: {files} dosya, {chunks:,} chunk")
        print()
    
    # Son güncelleme
    last_update = checkpoint.get('last_update')
    if last_update:
        print(f"🕐 Son Güncelleme: {format_time(last_update)}")
    
    # Hatalar
    errors = checkpoint.get('errors', [])
    if errors:
        print(f"\n⚠️ Hatalar ({len(errors)}):")
        for error in errors[-3:]:
            print(f"   • {error}")
    
    print()
    print("=" * 70)
    print("💡 Çıkmak için Ctrl+C")
    print("=" * 70)

if __name__ == "__main__":
    print("🚀 Training Monitor başlatılıyor...")
    print("   Her 5 saniyede güncellenir.\n")
    time.sleep(2)
    
    try:
        while True:
            print_metrics()
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n\n👋 Monitor durduruldu.")
