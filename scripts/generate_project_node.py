#!/usr/bin/env python3
"""
LLM-Assisted Graph Node Generator
===================================
Proje dizinindeki kaynak dosyaları okur, Claude ile analiz eder,
GraphStore'a kaliteli PROJECT node ekler ve VectorStoreV2'ye embed eder.

Kullanım:
    python scripts/generate_project_node.py --project nexys_a7_dma_audio
    python scripts/generate_project_node.py --all
    python scripts/generate_project_node.py --all --skip-existing
    python scripts/generate_project_node.py --project my_project --dry-run

Tasarım ilkeleri:
    - LLM yalnızca dosyalarda açıkça bulunan bilgileri çıkarır (halüsinasyon engeli)
    - LLM başarısız olursa YAML metadata'dan fallback node oluşturulur
    - İdempotent: aynı proje iki kez çalıştırılırsa güncelleme yapar
    - Pipeline'ı asla bloke etmez — hata loglanır, devam edilir
"""

from __future__ import annotations

import sys
import json
import re
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env")


# ─────────────────────────────────────────────────────────────────────────────
# YAML loader (projects.yaml)
# ─────────────────────────────────────────────────────────────────────────────

def load_project_catalog(yaml_path: Optional[Path] = None) -> Dict[str, Any]:
    """projects.yaml'ı yükle, path değişkenlerini expand et."""
    import yaml

    yaml_path = yaml_path or (_ROOT / "projects.yaml")
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    variables = raw.get("variables", {})
    vt = str(Path(variables.get("vt", "")).expanduser())

    defaults = raw.get("defaults", {})
    default_include_exts = defaults.get("include_exts", [".v", ".sv", ".c", ".h", ".xdc", ".tcl", ".prj"])
    default_exclude_patterns = defaults.get("exclude_patterns", [".git", "__pycache__", ".cache"])

    projects = {}
    for proj_id, cfg in raw.get("projects", {}).items():
        def expand(s: str) -> str:
            s = s.replace("{root}", str(_ROOT))
            s = s.replace("{vt}", vt)
            return str(Path(s).expanduser())

        projects[proj_id] = {
            "project_id": proj_id,
            "display_name": cfg.get("display_name", proj_id),
            "board": cfg.get("board", ""),
            "fpga_part": cfg.get("fpga_part", ""),
            "roots": [expand(r) for r in cfg.get("roots", [])],
            "include_exts": cfg.get("include_exts", default_include_exts),
            "exclude_patterns": cfg.get("exclude_patterns", default_exclude_patterns),
            "specific_files": [expand(s) for s in cfg.get("specific_files", [])],
            "file_node_map": cfg.get("file_node_map", {}),
        }

    return projects


# ─────────────────────────────────────────────────────────────────────────────
# Dosya okuma yardımcıları
# ─────────────────────────────────────────────────────────────────────────────

def _read_safe(path: Path, max_chars: int = 3000) -> str:
    """Dosyayı güvenli oku, max_chars ile sınırla."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        return text[:max_chars]
    except Exception:
        return ""


def _find_file(roots: List[str], glob_pattern: str) -> Optional[Path]:
    """Tüm root'larda pattern'e uyan ilk dosyayı bul."""
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for p in sorted(root_path.rglob(glob_pattern)):
            if p.is_file():
                return p
    return None


def _find_bd_tcl(roots: List[str]) -> Optional[Path]:
    """Block Design TCL dosyasını bul (create_bd_cell içeren)."""
    candidates = []
    for root in roots:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for p in root_path.rglob("*.tcl"):
            if p.is_file():
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    if "create_bd_cell" in content:
                        candidates.append((p, content.count("create_bd_cell")))
                except Exception:
                    pass
    if candidates:
        # En çok create_bd_cell içereni seç
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]
    return None


def collect_project_files(proj: Dict[str, Any]) -> Dict[str, str]:
    """
    Proje için LLM analizine gönderilecek dosyaları topla.
    Döndürür: {label: içerik} dict
    """
    roots = proj["roots"]
    files: Dict[str, str] = {}

    # 1. README
    readme = _find_file(roots, "README.md") or _find_file(roots, "readme.md")
    if readme:
        files["README.md"] = _read_safe(readme, 2500)

    # 2. Block Design TCL (IP listesi için)
    bd_tcl = _find_bd_tcl(roots)
    if bd_tcl:
        files[bd_tcl.name] = _read_safe(bd_tcl, 3000)

    # 3. XDC (pin atamaları ve saat kısıtlamaları)
    xdc = _find_file(roots, "*.xdc")
    if xdc:
        files[xdc.name] = _read_safe(xdc, 2000)

    # 4. Ana C/C++ dosyası (SDK bilgisi için)
    for pattern in ["helloworld.c", "main.c", "main.cc"]:
        c_file = _find_file(roots, pattern)
        if c_file:
            files[c_file.name] = _read_safe(c_file, 1500)
            break

    return files


# ─────────────────────────────────────────────────────────────────────────────
# LLM extraction prompt
# ─────────────────────────────────────────────────────────────────────────────

_EXTRACTION_SYSTEM = """\
Sen bir FPGA proje analisti olarak verilen proje dosyalarını incelersin.
GÖREV: Dosyalarda AÇIKÇA bulunan teknik bilgileri çıkar.
KURAL: Tahmin veya yorum ekleme. Dosyada yoksa null kullan.
KURAL: Yalnızca JSON döndür, başka hiçbir şey yazma."""

_EXTRACTION_TEMPLATE = """\
Aşağıdaki FPGA proje dosyalarını analiz et.
Proje ID: {project_id}
YAML'dan bilinen bilgiler: board={board}, fpga_part={fpga_part}

{file_sections}

Yalnızca aşağıdaki JSON formatında döndür (başka metin yok):
{{
  "description": "Tek cümle: ana IP blokları ve sistem mimarisi (örn. 'MicroBlaze + AXI DMA + DDR2 + PWM Audio sistemi')",
  "key_logic": "2-3 cümle: kritik veri yolu, tasarım kararları veya önemli parametreler",
  "ip_instances": ["TCL create_bd_cell'den çıkarılan IP instance adları listesi"],
  "tool": "Vivado sürümü (dosyalarda varsa, yoksa null)",
  "confidence": "HIGH"
}}"""


def build_prompt(proj: Dict[str, Any], files: Dict[str, str]) -> str:
    """LLM prompt'unu oluştur."""
    sections = []
    for label, content in files.items():
        sections.append(f"=== {label} ===\n{content}")
    file_sections = "\n\n".join(sections) if sections else "(Dosya bulunamadı)"

    return _EXTRACTION_TEMPLATE.format(
        project_id=proj["project_id"],
        board=proj["board"],
        fpga_part=proj["fpga_part"],
        file_sections=file_sections,
    )


# ─────────────────────────────────────────────────────────────────────────────
# JSON parse (LLM cevabından)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """LLM cevabından JSON bloğunu çıkar."""
    # Önce düz parse
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # ```json ... ``` bloğu
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # İlk { ... } bloğu
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def _validate_extracted(data: Dict[str, Any]) -> bool:
    """Çıkarılan JSON'ın minimum alanları içerip içermediğini kontrol et."""
    return bool(data.get("description"))


# ─────────────────────────────────────────────────────────────────────────────
# Fallback node (LLM başarısız olursa)
# ─────────────────────────────────────────────────────────────────────────────

def _make_fallback_node(proj: Dict[str, Any]) -> Dict[str, Any]:
    """YAML metadata'dan minimal ama geçerli bir node oluştur."""
    return {
        "description": f"{proj['display_name']} — {proj['board']} ({proj['fpga_part']})",
        "key_logic": "",
        "ip_instances": [],
        "tool": None,
        "confidence": "MEDIUM",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Graph + VectorStore güncelleme
# ─────────────────────────────────────────────────────────────────────────────

def upsert_project_node(proj: Dict[str, Any], extracted: Dict[str, Any]) -> None:
    """GraphStore'a PROJECT node ekle/güncelle, VectorStoreV2'ye embed et."""
    from rag_v2.graph_store import GraphStore
    from rag_v2.vector_store_v2 import VectorStoreV2

    gs = GraphStore(persist_path=str(_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json"))
    vs = VectorStoreV2(persist_directory=str(_ROOT / "db" / "chroma_v2"))

    project_id = proj["project_id"]

    ip_list = extracted.get("ip_instances", [])
    ip_summary = ", ".join(ip_list[:10]) if ip_list else ""

    node_attrs = {
        "node_type": "PROJECT",
        "name": proj["display_name"],
        "board": proj["board"],
        "fpga_part": proj["fpga_part"],
        "description": extracted.get("description", ""),
        "key_logic": extracted.get("key_logic", ""),
        "rationale": ip_summary,
        "tool": extracted.get("tool") or "",
        "confidence": extracted.get("confidence", "MEDIUM"),
        "auto_generated": True,
    }

    gs.add_node(project_id, node_attrs)
    gs.save()

    # VectorStore'a embed et
    node_for_embed = {"node_id": project_id, **node_attrs}
    vs.add_nodes_batch([node_for_embed])


# ─────────────────────────────────────────────────────────────────────────────
# Tek proje işleme
# ─────────────────────────────────────────────────────────────────────────────

def process_project(
    proj: Dict[str, Any],
    skip_existing: bool = False,
    dry_run: bool = False,
    verbose: bool = False,
) -> str:
    """
    Tek proje için node üret.
    Döndürür: "skipped" | "dry_run" | "llm_ok" | "fallback" | "error"
    """
    from rag_v2.graph_store import GraphStore

    project_id = proj["project_id"]
    print(f"\n  [{project_id}] {proj['display_name']}")

    # Mevcut node kontrolü
    if skip_existing:
        gs = GraphStore(persist_path=str(_ROOT / "db" / "graph" / "fpga_rag_v2_graph.json"))
        existing = gs.get_node(project_id)
        if existing and existing.get("node_type") == "PROJECT":
            print(f"    → Zaten var, atlanıyor (--skip-existing)")
            return "skipped"

    # Dosya toplama
    files = collect_project_files(proj)
    if verbose:
        print(f"    Analiz edilecek dosyalar: {list(files.keys())}")

    if not files:
        print(f"    ⚠️  Hiç dosya bulunamadı, fallback node kullanılacak")
        extracted = _make_fallback_node(proj)
        status = "fallback"
    else:
        if dry_run:
            print(f"    [DRY-RUN] Dosyalar: {list(files.keys())}")
            print(f"    [DRY-RUN] LLM çağrısı yapılmayacak")
            return "dry_run"

        # LLM extraction
        try:
            from rag.claude_code_generator import _run_claude, _is_available
            if not _is_available():
                raise RuntimeError("claude CLI bulunamadı")

            full_prompt = (
                f"[SİSTEM TALİMATLARI]\n{_EXTRACTION_SYSTEM}\n\n"
                f"[GÖREV]\n{build_prompt(proj, files)}"
            )

            print(f"    → Claude ile analiz ediliyor...")
            raw = _run_claude(full_prompt, model="claude-sonnet-4-6", timeout=120)

            if verbose:
                print(f"    LLM cevabı (ilk 300 karakter): {raw[:300]}")

            extracted = _extract_json(raw)
            if not extracted or not _validate_extracted(extracted):
                print(f"    ⚠️  JSON parse başarısız, fallback kullanılacak")
                extracted = _make_fallback_node(proj)
                status = "fallback"
            else:
                status = "llm_ok"
                print(f"    ✓ LLM analizi başarılı")
                print(f"    description: {extracted.get('description', '')[:80]}...")

        except Exception as e:
            print(f"    ⚠️  LLM hatası: {e}")
            print(f"    → Fallback node ile devam ediliyor")
            extracted = _make_fallback_node(proj)
            status = "fallback"

    # Graph + VectorStore güncelle
    if not dry_run:
        upsert_project_node(proj, extracted)
        label = "LLM" if status == "llm_ok" else "FALLBACK"
        print(f"    ✓ NODE eklendi [{label}]: {proj['fpga_part']}")

    return status


# ─────────────────────────────────────────────────────────────────────────────
# Ana giriş
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="LLM-Assisted FPGA Project Node Generator"
    )
    parser.add_argument("--project", "-p",
                        help="Tek proje ID'si (projects.yaml'daki key)")
    parser.add_argument("--all", action="store_true",
                        help="projects.yaml'daki tüm projeleri işle")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Zaten graph node'u olan projeleri atla")
    parser.add_argument("--dry-run", action="store_true",
                        help="Dosyaları göster, LLM/DB işlemi yapma")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Ayrıntılı çıktı")
    args = parser.parse_args()

    if not args.project and not args.all:
        parser.error("--project veya --all belirtilmeli")

    print("=" * 72)
    print("  FPGA RAG v2 — LLM-Assisted Project Node Generator")
    print("=" * 72)

    catalog = load_project_catalog()

    if args.project:
        if args.project not in catalog:
            print(f"HATA: '{args.project}' projects.yaml'da bulunamadı")
            print(f"Mevcut projeler: {', '.join(catalog.keys())}")
            sys.exit(1)
        targets = {args.project: catalog[args.project]}
    else:
        targets = catalog

    stats = {"llm_ok": 0, "fallback": 0, "skipped": 0, "error": 0, "dry_run": 0}
    for proj_id, proj in targets.items():
        result = process_project(
            proj,
            skip_existing=args.skip_existing,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        stats[result] = stats.get(result, 0) + 1

    print(f"\n{'=' * 72}")
    print(f"  ÖZET")
    print(f"{'=' * 72}")
    print(f"  LLM başarılı  : {stats.get('llm_ok', 0)}")
    print(f"  Fallback      : {stats.get('fallback', 0)}")
    print(f"  Atlandı       : {stats.get('skipped', 0)}")
    print(f"  Hata          : {stats.get('error', 0)}")
    if args.dry_run:
        print(f"  [DRY-RUN] Hiçbir değişiklik yapılmadı.")
    else:
        print(f"\n  ✅ Tamamlandı!")


if __name__ == "__main__":
    main()
