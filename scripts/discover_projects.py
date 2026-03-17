#!/usr/bin/env python3
"""
FPGA Proje Keşif Aracı
========================
data/code/ altındaki FPGA projelerini tarar ve projects.yaml için
hazır girişler üretir.

Kullanım:
    python scripts/discover_projects.py --audit         # disk vs yaml karşılaştır (kör noktalar)
    python scripts/discover_projects.py --scan          # yeni proje raporu göster
    python scripts/discover_projects.py --scan --write  # projects.yaml'a ekle
    python scripts/discover_projects.py --pdfs          # PDF keşfi
    python scripts/discover_projects.py --pdfs --write  # DocStore config üret

Filtre kriterleri (geçmesi gereken):
    - En az 1 .tcl + 1 .xdc dosyası
    - TCL içinde 'create_bd_cell' veya 'create_project' var (gerçek Vivado projesi)
    - Toplam dosya sayısı: 5 - 3000 (boş veya dev Petalinux build değil)
    - Zaten indexli değil (projects.yaml'da yok)
"""

from __future__ import annotations

import re
import sys
import argparse
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).parent.parent
_CODE_DIR = _ROOT / "data" / "code"
_PDF_DIR  = _ROOT / "data" / "pdfs"

# ─────────────────────────────────────────────────────────────────────────────
# Proje keşif filtreleri
# ─────────────────────────────────────────────────────────────────────────────

_MIN_FILES  = 5
_MAX_FILES  = 3000

# Gerçek Vivado projesi işareti
_TCL_MARKERS = [
    "create_bd_cell",
    "create_project",
    "create_bd_design",
    "set_property -dict",
    "create_clock",
]

# Bu pattern'leri içeren dizinler atlanır (gürültü)
_SKIP_DIRS = [
    # IP / Board kütüphaneleri (proje değil)
    "vivado-library",      # IP core kütüphanesi
    "vivado-boards",       # Board definition files
    "XilinxTclStore",      # Xilinx TCL utility library
    "Custom_Part_Data",    # Board definition data files
    "vivado-hierarchies",  # Pmod/Zmod IP hierarchy repo
    # ML / HPC / Farklı domain
    "brevitas",            # ML quantization framework
    "finn",                # ML accelerator framework
    "PYNQ",                # Python framework
    "Vitis-AI",            # ML tools
    "Vitis_Accel",         # HLS examples
    "Vitis_Libraries",     # HLS libraries
    "Vitis_Model",         # Vitis Model Composer (MATLAB)
    "open-nic-shell",      # Network NIC
    "mlir-aie",            # AMD AI Engine compiler
    "device-tree-xlnx",    # Linux device tree generator
    "vivado-risc-v",       # RISC-V (farklı domain)
    "rc-fpga",             # RISC-V Rocket Chip
    "RecoNIC",             # Network specific
    "parallella",          # Parallella (Epiphany ecosystem)
    # Tutorial / Eğitim materyalleri (gerçek proje değil)
    "Vivado-Design-Tutorials",
    "FPGA-Design-Flow",
    "SDSoC-platforms",
    "xup_fpga_vivado",
    "xup_high_level",
    "Vitis-AI-Tutorials",
    "Vitis-Tutorials",
    "Zynq-Design-using-Vivado",
    "Zynq-Tutorial",
    # Umbrella repolar (alt projeler ayrı indexlenmeli)
    "vivado-git",          # Git workflow scripts
    # Bu sistemin kendisi
    "fpga_asist_dev",
]

# Umbrella repo tespiti: içinde "Projects/" dizini varsa alt projeler ayrı indexlenmeli
_UMBRELLA_SUBDIR = "Projects"

# FPGA part regex
_PART_RE = re.compile(r'(xc[0-9][a-z][0-9a-z]+[a-z]+-[0-9][a-z]+)', re.IGNORECASE)
# Board regex
_BOARD_RE = re.compile(
    r'(Nexys|Arty|Basys|Zybo|Cora|Genesys|Cmod|ZedBoard|Eclypse|Kria|Pynq|Anvyl)'
    r'[\s\-_]?[A-Z0-9\-]*',
    re.IGNORECASE
)
# Tool regex
_TOOL_RE = re.compile(r'Vivado\s+([\d.]+)', re.IGNORECASE)


def _should_skip(dir_path: Path) -> bool:
    """Dizin adı skip listesindeyse atla."""
    name = dir_path.name
    for skip in _SKIP_DIRS:
        if skip.lower() in name.lower():
            return True
    return False


def _count_files_fast(dir_path: Path) -> int:
    """Hızlı dosya sayımı (rglob yerine os.walk)."""
    import os
    total = 0
    for _, _, files in os.walk(dir_path):
        total += len(files)
        if total > _MAX_FILES + 100:
            return total  # erken çık
    return total


def _find_tcl_files(dir_path: Path) -> list[Path]:
    """TCL dosyalarını bul (en fazla 20)."""
    found = []
    for p in dir_path.rglob("*.tcl"):
        if p.is_file() and ".git" not in str(p):
            found.append(p)
            if len(found) >= 20:
                break
    return found


def _find_xdc_files(dir_path: Path) -> list[Path]:
    """XDC dosyalarını bul (en fazla 10)."""
    found = []
    for p in dir_path.rglob("*.xdc"):
        if p.is_file() and ".git" not in str(p):
            found.append(p)
            if len(found) >= 10:
                break
    return found


def _has_tcl_marker(tcl_files: list[Path]) -> bool:
    """TCL dosyalarından birinde Vivado marker var mı?"""
    for tcl in tcl_files[:5]:  # en fazla 5 dosya kontrol et
        try:
            content = tcl.read_text(encoding="utf-8", errors="replace")
            for marker in _TCL_MARKERS:
                if marker in content:
                    return True
        except Exception:
            pass
    return False


def _extract_fpga_part(tcl_files: list[Path], xdc_files: list[Path]) -> Optional[str]:
    """FPGA part numarasını TCL/XDC'den çıkar."""
    for f in tcl_files[:3] + xdc_files[:3]:
        try:
            content = f.read_text(encoding="utf-8", errors="replace")[:5000]
            m = _PART_RE.search(content)
            if m:
                return m.group(1).lower()
        except Exception:
            pass
    return None


def _extract_board(dir_path: Path, tcl_files: list[Path]) -> str:
    """Board adını dizin adı veya TCL'den tahmin et."""
    # Dizin adından
    name = dir_path.name
    m = _BOARD_RE.search(name)
    if m:
        return m.group(0).strip()
    # TCL'den
    for tcl in tcl_files[:2]:
        try:
            content = tcl.read_text(encoding="utf-8", errors="replace")[:3000]
            m = _BOARD_RE.search(content)
            if m:
                return m.group(0).strip()
        except Exception:
            pass
    return name  # fallback: dizin adı


def _make_project_id(dir_name: str) -> str:
    """Dizin adından geçerli project_id üret."""
    pid = dir_name.lower()
    pid = re.sub(r'[^a-z0-9_]', '_', pid)
    pid = re.sub(r'_+', '_', pid)
    return pid.strip('_')


def _detect_extra_exts(dir_path: Path) -> list[str]:
    """Projeye özgü ekstra uzantıları tespit et."""
    extra = []
    if list(dir_path.rglob("*.vhd"))[:1]:
        extra.append('".vhd"')
    if list(dir_path.rglob("*.sv"))[:1]:
        extra.append('".sv"')
    if list(dir_path.rglob("*.cc"))[:1]:
        extra.append('".cc"')
    if list(dir_path.rglob("*.cpp"))[:1]:
        extra.append('".cpp"')
    return extra


# ─────────────────────────────────────────────────────────────────────────────
# Ana tarama
# ─────────────────────────────────────────────────────────────────────────────

def scan_code_directory(existing_ids: set[str], verbose: bool = False, quiet: bool = False) -> list[dict]:
    """
    data/code/ altındaki dizinleri tara, filtreleri geçen projeleri döndür.
    quiet=True: özet satırlarını bastır (audit modu için).
    """
    if not _CODE_DIR.exists():
        print(f"HATA: {_CODE_DIR} bulunamadı")
        return []

    results = []
    skipped_framework = 0
    skipped_no_tcl = 0
    skipped_no_xdc = 0
    skipped_size = 0
    skipped_existing = 0

    dirs = sorted([d for d in _CODE_DIR.iterdir() if d.is_dir()])
    total = len(dirs)

    if not quiet:
        print(f"  Taranan dizin: {_CODE_DIR}")
        print(f"  Toplam alt dizin: {total}")
        print()

    for i, dir_path in enumerate(dirs, 1):
        if verbose:
            print(f"  [{i:3d}/{total}] {dir_path.name}", end="... ", flush=True)

        # Framework/tool skip
        if _should_skip(dir_path):
            skipped_framework += 1
            if verbose: print("SKIP (framework)")
            continue

        # Umbrella repo skip: "Projects/" alt dizini var → alt projeler ayrı indexlenmeli
        if (dir_path / _UMBRELLA_SUBDIR).is_dir():
            skipped_framework += 1
            if verbose: print("SKIP (umbrella repo — sub-projects should be indexed separately)")
            continue

        # Zaten indexli mi?
        pid = _make_project_id(dir_path.name)
        if pid in existing_ids:
            skipped_existing += 1
            if verbose: print("SKIP (already indexed)")
            continue

        # Dosya sayısı kontrolü
        file_count = _count_files_fast(dir_path)
        if file_count < _MIN_FILES or file_count > _MAX_FILES:
            skipped_size += 1
            if verbose: print(f"SKIP (size={file_count})")
            continue

        # TCL kontrolü
        tcl_files = _find_tcl_files(dir_path)
        if not tcl_files:
            skipped_no_tcl += 1
            if verbose: print("SKIP (no TCL)")
            continue

        # XDC kontrolü
        xdc_files = _find_xdc_files(dir_path)
        if not xdc_files:
            skipped_no_xdc += 1
            if verbose: print("SKIP (no XDC)")
            continue

        # Vivado marker kontrolü
        if not _has_tcl_marker(tcl_files):
            skipped_no_tcl += 1
            if verbose: print("SKIP (no Vivado TCL marker)")
            continue

        # Metadata çıkar
        fpga_part = _extract_fpga_part(tcl_files, xdc_files) or ""
        board = _extract_board(dir_path, tcl_files)
        extra_exts = _detect_extra_exts(dir_path)

        results.append({
            "project_id": pid,
            "dir_name": dir_path.name,
            "dir_path": str(dir_path),
            "board": board,
            "fpga_part": fpga_part,
            "file_count": file_count,
            "tcl_count": len(tcl_files),
            "xdc_count": len(xdc_files),
            "extra_exts": extra_exts,
        })
        if verbose: print(f"OK ({file_count} dosya, {fpga_part or '?'})")

    if not quiet:
        print(f"  Sonuç:")
        print(f"    Geçen proje       : {len(results)}")
        print(f"    Zaten indexli     : {skipped_existing}")
        print(f"    Framework/tool    : {skipped_framework}")
        print(f"    Dosya sayısı dışı : {skipped_size}")
        print(f"    TCL yok/geçersiz  : {skipped_no_tcl}")
        print(f"    XDC yok           : {skipped_no_xdc}")

    return results


# ─────────────────────────────────────────────────────────────────────────────
# YAML çıktısı
# ─────────────────────────────────────────────────────────────────────────────

def format_yaml_entry(proj: dict) -> str:
    """Tek proje için YAML girişi oluştur."""
    pid   = proj["project_id"]
    board = proj["board"]
    part  = proj["fpga_part"]
    path  = proj["dir_path"].replace(str(_ROOT), "{root}")
    exts  = proj["extra_exts"]

    lines = [
        f"  # ── {proj['dir_name']} ({proj['file_count']} dosya) ──",
        f"  {pid}:",
        f'    display_name: "{proj["dir_name"]}"',
        f'    board: "{board}"',
        f'    fpga_part: "{part}"',
        f"    roots:",
        f'      - "{path}"',
    ]
    if exts:
        lines.append(f"    include_exts:")
        lines.append(f'      - ".v"')
        lines.append(f'      - ".sv"')
        lines.append(f'      - ".c"')
        lines.append(f'      - ".h"')
        lines.append(f'      - ".xdc"')
        lines.append(f'      - ".tcl"')
        lines.append(f'      - ".prj"')
        for ext in exts:
            lines.append(f"      - {ext}")
    lines.append(f"    exclude_patterns:")
    lines.append(f'      - ".git"')
    lines.append(f'      - "__pycache__"')
    lines.append(f'      - ".cache"')
    lines.append(f'      - ".gen"')
    lines.append(f'      - ".runs"')
    lines.append(f'      - ".hw"')
    lines.append(f'      - ".ip_user_files"')
    lines.append(f'      - "ipshared"')
    lines.append(f"    file_node_map: {{}}")
    return "\n".join(lines)


def write_to_yaml(new_projects: list[dict]) -> None:
    """Yeni projeleri projects.yaml'a ekle."""
    import yaml

    yaml_path = _ROOT / "projects.yaml"
    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    existing_projects = raw.get("projects", {})
    added = 0
    for proj in new_projects:
        pid = proj["project_id"]
        if pid in existing_projects:
            continue
        # Add minimal entry
        existing_projects[pid] = {
            "display_name": proj["dir_name"],
            "board": proj["board"],
            "fpga_part": proj["fpga_part"],
            "roots": [proj["dir_path"].replace(str(_ROOT) + "/", "{root}/")],
            "exclude_patterns": [
                ".git", "__pycache__", ".cache", ".gen", ".runs",
                ".hw", ".ip_user_files", "ipshared",
            ],
            "file_node_map": {},
        }
        if proj["extra_exts"]:
            base = [".v", ".sv", ".c", ".h", ".xdc", ".tcl", ".prj"]
            extra = [e.strip('"') for e in proj["extra_exts"]]
            existing_projects[pid]["include_exts"] = base + extra

        added += 1

    raw["projects"] = existing_projects

    with open(yaml_path, "w", encoding="utf-8") as f:
        import yaml as _yaml
        _yaml.dump(raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    print(f"\n  ✅ {added} proje projects.yaml'a eklendi.")


# ─────────────────────────────────────────────────────────────────────────────
# Audit: disk vs yaml karşılaştırması
# ─────────────────────────────────────────────────────────────────────────────

def audit(verbose: bool = False) -> dict:
    """
    data/code/ ile projects.yaml'ı karşılaştır — kör noktaları bul.

    Üç kategori:
      ✓ yaml'da VE disk'te geçerli   → sağlıklı
      ⚠ disk'te VAR, yaml'da YOK    → kör nokta (eklenebilir)
      ✗ yaml'da VAR, disk'te yok    → kırık referans
    """
    import yaml

    yaml_path = _ROOT / "projects.yaml"
    if yaml_path.exists():
        with open(yaml_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        yaml_projects: dict = raw.get("projects", {})
    else:
        yaml_projects = {}

    yaml_ids = set(yaml_projects.keys())

    # yaml'daki variable tanımlarını çöz ({root}, {vt}, ...)
    vars_raw: dict = raw.get("variables", raw.get("vars", {}))
    def _expand(path_str: str) -> str:
        result = path_str.replace("{root}", str(_ROOT))
        for key, val in vars_raw.items():
            val_expanded = str(val).replace("~", str(Path.home()))
            result = result.replace("{" + key + "}", val_expanded)
        return result

    # Disk'teki TÜM geçerli projeleri tara (existing_ids=boş → hepsini döndür)
    print("  Disk taranıyor (filtre uygulanıyor, bu biraz sürebilir)...")
    disk_projects = scan_code_directory(existing_ids=set(), verbose=verbose, quiet=True)
    disk_ids = {p["project_id"] for p in disk_projects}
    disk_map = {p["project_id"]: p for p in disk_projects}

    # yaml_only: disk'te yok diye görünen ama dışarıda geçerli root'u olan projeler ayrıl
    # (örn. {vt}/... yollu projeler data/code/ dışında ama geçerli)
    truly_missing: set[str] = set()
    external_ok:   set[str] = set()
    for pid in yaml_ids - disk_ids:
        proj = yaml_projects[pid]
        roots = proj.get("roots", [])
        if any(Path(_expand(r)).exists() for r in roots):
            external_ok.add(pid)
        else:
            truly_missing.add(pid)

    in_both   = yaml_ids & disk_ids
    disk_only = disk_ids - yaml_ids          # kör nokta
    yaml_only = yaml_ids - disk_ids          # data/code/ dışında (external veya gerçekten yok)

    # yaml root yolları gerçekten mevcut mu?
    broken_roots: list[tuple[str, str]] = []
    for pid, proj in yaml_projects.items():
        for root in proj.get("roots", []):
            real = _expand(root)
            if not Path(real).exists():
                broken_roots.append((pid, real))

    # ── Rapor ──────────────────────────────────────────────────────────────
    print()
    print(f"  {'═'*72}")
    print(f"  AUDIT SONUCU — data/code/ vs projects.yaml")
    print(f"  {'═'*72}")
    print(f"  ✓ projects.yaml'da VE data/code/ altında: {len(in_both):4d} proje")
    print(f"  ✓ yaml'da VE dışarıda geçerli yolda     : {len(external_ok):4d} proje")
    print(f"  ⚠ Disk'te VAR, yaml'da YOK (kör nokta)  : {len(disk_only):4d} proje")
    print(f"  ✗ Gerçekten kayıp (hiçbir yerde yok)    : {len(truly_missing):4d} proje")
    if broken_roots:
        print(f"  ✗ Kırık root yolu                       : {len(broken_roots):4d} adet")

    if disk_only:
        print()
        print(f"  KÖR NOKTA — Eklenebilecek Projeler ({len(disk_only)}):")
        print(f"  {'─'*90}")
        print(f"  {'ID':40s} {'Kart':22s} {'Part':22s} {'Dosya':6s}")
        print(f"  {'─'*90}")
        for pid in sorted(disk_only):
            p = disk_map[pid]
            board = (p["board"] or "?")[:22]
            part  = (p["fpga_part"] or "?")[:22]
            print(f"  {pid:40s} {board:22s} {part:22s} {p['file_count']:6d}")
        print()
        print(f"  Eklemek için:")
        print(f"    python scripts/discover_projects.py --scan --write")

    if truly_missing:
        print()
        print(f"  GERÇEKTEN KAYIP PROJELER ({len(truly_missing)}) — yaml'da var ama hiçbir yolda yok:")
        for pid in sorted(truly_missing):
            print(f"    ✗ {pid}")

    if external_ok:
        print()
        print(f"  DIŞ YOLLU PROJELER ({len(external_ok)}) — data/code/ dışında, geçerli:")
        for pid in sorted(external_ok):
            roots = yaml_projects[pid].get("roots", [])
            print(f"    ✓ {pid}: {roots[0] if roots else '?'}")

    if broken_roots:
        print()
        print(f"  KIRIK ROOT YOLLARI ({len(broken_roots)}):")
        for pid, root in broken_roots:
            print(f"    ✗ {pid}: {root}")

    if not disk_only and not truly_missing and not broken_roots:
        print()
        print(f"  ✅ Sistem sağlıklı — disk ve yaml tamamen eşleşiyor.")

    return {
        "in_both":      in_both,
        "external_ok":  external_ok,
        "disk_only":    disk_only,
        "truly_missing": truly_missing,
        "broken_roots": broken_roots,
        "disk_map":     disk_map,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PDF keşfi
# ─────────────────────────────────────────────────────────────────────────────

_PDF_PREFIXES = ["ug", "pg", "xapp", "wp", "ds"]  # User/Product Guide, AppNote, White Paper, DataSheet

def scan_pdfs(verbose: bool = False) -> dict:
    """data/pdfs/ altındaki ilgili PDF'leri tara."""
    if not _PDF_DIR.exists():
        print(f"HATA: {_PDF_DIR} bulunamadı")
        return {}

    all_pdfs = list(_PDF_DIR.rglob("*.pdf"))
    total = len(all_pdfs)

    relevant = []
    for p in all_pdfs:
        name = p.name.lower()
        for prefix in _PDF_PREFIXES:
            if name.startswith(prefix):
                relevant.append(p)
                break

    by_prefix: dict[str, list] = {}
    for p in relevant:
        name = p.name.lower()
        prefix = next((px for px in _PDF_PREFIXES if name.startswith(px)), "other")
        by_prefix.setdefault(prefix, []).append(p)

    print(f"  Toplam PDF     : {total}")
    print(f"  İlgili PDF     : {len(relevant)}")
    print()
    for prefix, files in sorted(by_prefix.items()):
        print(f"    {prefix:8s}: {len(files):4d} dosya")

    if verbose:
        print()
        print("  Örnek dosyalar:")
        for prefix, files in sorted(by_prefix.items()):
            for p in files[:3]:
                print(f"    {p.name}")
            if len(files) > 3:
                print(f"    ... ({len(files)-3} daha)")

    return {"total": total, "relevant": len(relevant), "by_prefix": by_prefix, "files": relevant}


def write_pdf_config(pdf_result: dict) -> None:
    """İlgili PDF'ler için index konfigürasyonu yaz."""
    output_path = _ROOT / "scripts" / "index_pdfs.py"
    pdfs = pdf_result.get("files", [])

    lines = [
        "#!/usr/bin/env python3",
        '"""Auto-generated PDF index configuration."""',
        "from pathlib import Path",
        "",
        "_ROOT = Path(__file__).parent.parent",
        "",
        "PDF_CATALOG = [",
    ]

    for p in pdfs:
        rel = str(p).replace(str(_ROOT) + "/", "")
        lines.append(f'    str(_ROOT / "{rel}"),')

    lines += [
        "]",
        "",
        'if __name__ == "__main__":',
        '    print(f"Toplam PDF: {len(PDF_CATALOG)}")',
    ]

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n  ✅ PDF katalog: {output_path} ({len(pdfs)} dosya)")


# ─────────────────────────────────────────────────────────────────────────────
# Ana giriş
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="FPGA Proje Keşif Aracı")
    parser.add_argument("--scan",    action="store_true", help="data/code/ tara — yeni projeleri bul")
    parser.add_argument("--audit",   action="store_true", help="disk vs yaml karşılaştır — kör noktaları göster")
    parser.add_argument("--pdfs",    action="store_true", help="data/pdfs/ tara")
    parser.add_argument("--write",   action="store_true", help="Sonuçları dosyaya yaz")
    parser.add_argument("--verbose", "-v", action="store_true", help="Ayrıntılı çıktı")
    args = parser.parse_args()

    if not args.scan and not args.pdfs and not args.audit:
        parser.error("--scan, --audit veya --pdfs belirtilmeli")

    print("=" * 72)
    print("  FPGA RAG v2 — Proje & Döküman Keşif Aracı")
    print("=" * 72)

    if args.audit:
        print("\n  [AUDIT — disk vs yaml]")
        print(f"  {'─' * 60}")
        audit(verbose=args.verbose)

    if args.scan:
        print("\n  [PROJE TARAMASI]")
        print(f"  {'─' * 60}")

        # Mevcut indexli proje ID'leri
        import yaml
        yaml_path = _ROOT / "projects.yaml"
        existing_ids = set()
        if yaml_path.exists():
            with open(yaml_path) as f:
                raw = yaml.safe_load(f)
            existing_ids = set(raw.get("projects", {}).keys())
        print(f"  Zaten indexli proje: {len(existing_ids)}")
        print()

        new_projects = scan_code_directory(existing_ids, verbose=args.verbose)

        # Özet tablo
        print()
        print(f"  {'─' * 60}")
        print(f"  YENİ PROJE LİSTESİ ({len(new_projects)} adet):")
        print(f"  {'─' * 60}")
        print(f"  {'ID':40s} {'Kart':20s} {'Part':20s} {'Dosya':6s}")
        print(f"  {'─' * 90}")
        for p in sorted(new_projects, key=lambda x: x["project_id"]):
            part = p["fpga_part"] or "?"
            board = p["board"][:20] if p["board"] else "?"
            print(f"  {p['project_id']:40s} {board:20s} {part:20s} {p['file_count']:6d}")

        if args.write and new_projects:
            write_to_yaml(new_projects)
            print(f"\n  Sonraki adım:")
            print(f"    python scripts/generate_project_node.py --all --skip-existing")
            print(f"    python scripts/index_source_files.py")

    if args.pdfs:
        print("\n  [PDF TARAMASI]")
        print(f"  {'─' * 60}")
        pdf_result = scan_pdfs(verbose=args.verbose)

        if args.write:
            write_pdf_config(pdf_result)

    print()


if __name__ == "__main__":
    main()
