import json

with open('training_checkpoint.json', encoding='utf-8') as f:
    d = json.load(f)

print("=" * 50)
print("📊 ÖNCEKI EĞITIM ÖZETI")
print("=" * 50)
print(f"📄 İşlenen PDF sayısı: {len(d.get('processed_pdfs', []))}")
print(f"💻 İşlenen Kod dosyası: {len(d.get('processed_codes', []))}")
print(f"📦 Son chunk index: {d.get('last_chunk_index', 0)}")
print(f"📈 Toplam chunk: {d.get('total_chunks', 0)}")
print(f"📅 Son güncelleme: {d.get('last_update', '-')}")
print(f"🔄 Durum: {d.get('status', '-')}")
print("=" * 50)

# İlk 10 PDF
print("\n📄 İşlenen PDF'lerden örnekler:")
for i, pdf in enumerate(d.get('processed_pdfs', [])[:10]):
    print(f"   {i+1}. {pdf}")
if len(d.get('processed_pdfs', [])) > 10:
    print(f"   ... ve {len(d.get('processed_pdfs', [])) - 10} daha")
