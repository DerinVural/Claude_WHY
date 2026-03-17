"""
FPGA RAG v2 — Mimari Dokümantasyon PDF Üreticisi
Kullanım: python scripts/generate_architecture_pdf.py
Çıktı: /home/test123/Desktop/FPGA_RAG_v2_Mimari.pdf
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.pdfgen import canvas
from reportlab.platypus.flowables import Flowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

# ─── Unicode font kayıt (Türkçe karakter desteği) ─────────────────────────────
_DEJAVU      = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_DEJAVU_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
_DEJAVU_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
pdfmetrics.registerFont(TTFont("DejaVuSans",     _DEJAVU))
pdfmetrics.registerFont(TTFont("DejaVuSans-Bold",_DEJAVU_BOLD))
pdfmetrics.registerFont(TTFont("DejaVuSansMono", _DEJAVU_MONO))

# ─── Renkler ──────────────────────────────────────────────────────────────────
C_DARK    = colors.HexColor("#1a1a2e")
C_BLUE    = colors.HexColor("#16213e")
C_ACCENT  = colors.HexColor("#0f3460")
C_TEAL    = colors.HexColor("#00b4d8")
C_LIGHT   = colors.HexColor("#caf0f8")
C_GREEN   = colors.HexColor("#06d6a0")
C_ORANGE  = colors.HexColor("#f77f00")
C_RED     = colors.HexColor("#d62828")
C_GRAY    = colors.HexColor("#adb5bd")
C_LGRAY   = colors.HexColor("#e9ecef")
C_WHITE   = colors.white
C_YELLOW  = colors.HexColor("#ffd166")
C_PURPLE  = colors.HexColor("#7b2d8b")

PAGE_W, PAGE_H = A4

# ─── Stiller ──────────────────────────────────────────────────────────────────
styles = getSampleStyleSheet()

def make_style(name, parent="Normal", **kwargs):
    s = ParagraphStyle(name, parent=styles[parent], **kwargs)
    return s

S_TITLE    = make_style("Title2",    fontSize=26, textColor=C_WHITE,    alignment=TA_CENTER, spaceAfter=6,  fontName="DejaVuSans-Bold")
S_SUBTITLE = make_style("Sub2",      fontSize=13, textColor=C_TEAL,     alignment=TA_CENTER, spaceAfter=4,  fontName="DejaVuSans")
S_H1       = make_style("H1",        fontSize=16, textColor=C_TEAL,     spaceBefore=14, spaceAfter=6,  fontName="DejaVuSans-Bold")
S_H2       = make_style("H2",        fontSize=13, textColor=C_ORANGE,   spaceBefore=10, spaceAfter=4,  fontName="DejaVuSans-Bold")
S_H3       = make_style("H3",        fontSize=11, textColor=C_YELLOW,   spaceBefore=8,  spaceAfter=3,  fontName="DejaVuSans-Bold")
S_BODY     = make_style("Body2",     fontSize=9.5,textColor=C_DARK,     spaceAfter=4,  leading=15,    fontName="DejaVuSans")
S_BODY_W   = make_style("BodyW",     fontSize=9.5,textColor=C_WHITE,    spaceAfter=4,  leading=15,    fontName="DejaVuSans")
S_CODE     = make_style("Code2",     fontSize=8,  textColor=C_GREEN,    spaceAfter=3,  leading=12,    fontName="DejaVuSansMono", backColor=C_BLUE, leftIndent=6)
S_CAPTION  = make_style("Cap",       fontSize=8,  textColor=C_GRAY,     alignment=TA_CENTER, spaceAfter=6, fontName="DejaVuSans")
S_BULLET   = make_style("Bull",      fontSize=9.5,textColor=C_DARK,     spaceAfter=3,  leading=14,    leftIndent=12, fontName="DejaVuSans", bulletIndent=4)
S_SMALL    = make_style("Small",     fontSize=8,  textColor=C_GRAY,     spaceAfter=2,  fontName="DejaVuSans")
S_TAG_G    = make_style("TagG",      fontSize=8,  textColor=C_WHITE,    fontName="DejaVuSans-Bold", backColor=C_GREEN,   alignment=TA_CENTER)
S_TAG_O    = make_style("TagO",      fontSize=8,  textColor=C_WHITE,    fontName="DejaVuSans-Bold", backColor=C_ORANGE,  alignment=TA_CENTER)
S_TAG_R    = make_style("TagR",      fontSize=8,  textColor=C_WHITE,    fontName="DejaVuSans-Bold", backColor=C_RED,     alignment=TA_CENTER)
S_TAG_T    = make_style("TagT",      fontSize=8,  textColor=C_WHITE,    fontName="DejaVuSans-Bold", backColor=C_TEAL,    alignment=TA_CENTER)
S_TAG_P    = make_style("TagP",      fontSize=8,  textColor=C_WHITE,    fontName="DejaVuSans-Bold", backColor=C_PURPLE,  alignment=TA_CENTER)

# ─── Yardımcı Flowable'lar ────────────────────────────────────────────────────
class ColorBox(Flowable):
    """Renkli arka planlı metin kutusu."""
    def __init__(self, text, bg=C_ACCENT, fg=C_WHITE, width=None, height=None,
                 fontsize=9, bold=False, padding=8):
        super().__init__()
        self.text    = text
        self.bg      = bg
        self.fg      = fg
        self._width  = width or (PAGE_W - 4*cm)
        self._height = height or (fontsize + 2*padding)
        self.fontsize= fontsize
        self.bold    = bold
        self.padding = padding

    def wrap(self, avail_w, avail_h):
        self.width = self._width
        self.height = self._height
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setFillColor(self.bg)
        c.roundRect(0, 0, self.width, self.height, 6, fill=1, stroke=0)
        c.setFillColor(self.fg)
        fn = "DejaVuSans-Bold" if self.bold else "DejaVuSans"
        c.setFont(fn, self.fontsize)
        c.drawCentredString(self.width/2, self.padding*0.8, self.text)


class StoreBlock(Flowable):
    """5-store diyagramındaki tek bir store bloğu."""
    def __init__(self, number, name, subtitle, color, items, width=None):
        super().__init__()
        self.number   = number
        self.name     = name
        self.subtitle = subtitle
        self.color    = color
        self.items    = items
        self._width   = width or 3.2*cm
        self.row_h    = 0.52*cm
        self._height  = 1.8*cm + len(items)*self.row_h

    def wrap(self, aw, ah):
        self.width = self._width
        self.height = self._height
        return self.width, self.height

    def draw(self):
        c = self.canv
        w, h = self.width, self.height
        # Gövde
        c.setFillColor(self.color)
        c.roundRect(0, 0, w, h, 8, fill=1, stroke=0)
        # Başlık
        c.setFillColor(C_WHITE)
        c.setFont("DejaVuSans-Bold", 8.5)
        c.drawCentredString(w/2, h - 0.7*cm, f"Store {self.number}")
        c.setFont("DejaVuSans-Bold", 9)
        c.drawCentredString(w/2, h - 1.2*cm, self.name)
        c.setFont("DejaVuSans", 7)
        c.setFillColor(C_LIGHT)
        c.drawCentredString(w/2, h - 1.6*cm, self.subtitle)
        # Çizgi
        c.setStrokeColor(C_WHITE)
        c.setLineWidth(0.5)
        c.line(0.3*cm, h - 1.8*cm, w - 0.3*cm, h - 1.8*cm)
        # Items
        c.setFont("DejaVuSans", 7)
        c.setFillColor(C_WHITE)
        y = h - 1.8*cm - self.row_h
        for item in self.items:
            c.drawString(0.3*cm, y + 0.1*cm, "• " + item)
            y -= self.row_h


class ArrowFlow(Flowable):
    """Yatay ok çizen flowable."""
    def __init__(self, label="", width=None, color=C_TEAL):
        super().__init__()
        self._width  = width or 1.2*cm
        self._height = 0.8*cm
        self.label   = label
        self.color   = color

    def wrap(self, aw, ah):
        self.width = self._width
        self.height = self._height
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setStrokeColor(self.color)
        c.setFillColor(self.color)
        c.setLineWidth(2)
        mid = self.height / 2
        c.line(0, mid, self.width - 0.3*cm, mid)
        # Ok ucu
        c.setLineWidth(0)
        p = c.beginPath()
        p.moveTo(self.width, mid)
        p.lineTo(self.width - 0.35*cm, mid + 0.2*cm)
        p.lineTo(self.width - 0.35*cm, mid - 0.2*cm)
        p.close()
        c.drawPath(p, fill=1, stroke=0)
        if self.label:
            c.setFont("DejaVuSans", 6)
            c.drawCentredString(self.width/2, mid + 0.15*cm, self.label)


class FlowDiagram(Flowable):
    """Sorgu akışı diyagramı."""
    def __init__(self):
        super().__init__()
        self.width  = PAGE_W - 4*cm
        self.height = 4.5*cm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        W, H = self.width, self.height

        boxes = [
            ("Kullanıcı\nSorusu", C_ORANGE),
            ("Classifier\n(query type)", C_PURPLE),
            ("Router\n(5 route)", C_ACCENT),
            ("5 Store\nParalel", C_TEAL),
            ("Response\nBuilder", C_GREEN),
            ("LLM\n(Claude)", C_RED),
            ("Cevap", C_ORANGE),
        ]
        n = len(boxes)
        bw = 1.9*cm
        bh = 1.3*cm
        gap = (W - n*bw) / (n - 1)
        y = (H - bh) / 2

        for i, (label, col) in enumerate(boxes):
            x = i * (bw + gap)
            c.setFillColor(col)
            c.roundRect(x, y, bw, bh, 5, fill=1, stroke=0)
            c.setFillColor(C_WHITE)
            c.setFont("DejaVuSans-Bold", 7.5)
            lines = label.split("\n")
            if len(lines) == 2:
                c.drawCentredString(x + bw/2, y + bh/2 + 0.1*cm, lines[0])
                c.setFont("DejaVuSans", 6.5)
                c.drawCentredString(x + bw/2, y + bh/2 - 0.3*cm, lines[1])
            else:
                c.drawCentredString(x + bw/2, y + bh/2, label)

            # Ok
            if i < n - 1:
                ax = x + bw + 0.1*cm
                ay = y + bh/2
                c.setStrokeColor(C_GRAY)
                c.setFillColor(C_GRAY)
                c.setLineWidth(1.5)
                c.line(ax, ay, ax + gap - 0.25*cm, ay)
                p = c.beginPath()
                p.moveTo(ax + gap - 0.05*cm, ay)
                p.lineTo(ax + gap - 0.3*cm, ay + 0.12*cm)
                p.lineTo(ax + gap - 0.3*cm, ay - 0.12*cm)
                p.close()
                c.drawPath(p, fill=1, stroke=0)


class ComparisonDiagram(Flowable):
    """Önceki vs Mevcut mimari karşılaştırması."""
    def __init__(self):
        super().__init__()
        self.width  = PAGE_W - 4*cm
        self.height = 7.5*cm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        W, H = self.width, self.height
        half = W / 2 - 0.3*cm

        # Sol panel — Önceki
        c.setFillColor(C_RED)
        c.roundRect(0, 0, half, H, 8, fill=1, stroke=0)
        c.setFillColor(C_WHITE)
        c.setFont("DejaVuSans-Bold", 11)
        c.drawCentredString(half/2, H - 0.7*cm, "ÖNCEKİ (2026-03-13)")
        c.setFont("DejaVuSans", 7.5)
        c.drawCentredString(half/2, H - 1.1*cm, "Robustness: 0.937/A")

        old_items = [
            ("GRAPH", "297 node", "(PROJECT+COMP+PATTERN+SDOC+CONST+REQ+DEC+EV+ISSUE)", C_DARK),
            ("VECTOR", "297 node embed", "chroma_v2", C_BLUE),
            ("SOURCE", "36,039 chunk", "93 meta chunk, FTS5+semantic", C_ACCENT),
            ("DOC", "176K chunk", "74 PDF, FTS5+semantic, RRF", C_PURPLE),
            ("FILTER", "Sadece PROJECT", "filtreli, COMP geçiyor", C_RED),
            ("REQ_TREE", "Filter'dan ÖNCE", "hesaplanıyor (hata!)", C_RED),
        ]
        y = H - 1.7*cm
        rh = 0.75*cm
        for name, val, note, col in old_items:
            c.setFillColor(col)
            c.roundRect(0.3*cm, y - rh + 0.05*cm, half - 0.6*cm, rh - 0.1*cm, 4, fill=1, stroke=0)
            c.setFillColor(C_WHITE)
            c.setFont("DejaVuSans-Bold", 7.5)
            c.drawString(0.55*cm, y - 0.3*cm, name + ":")
            c.setFont("DejaVuSans", 7.5)
            c.drawString(0.55*cm + 1.4*cm, y - 0.3*cm, val)
            c.setFont("DejaVuSans", 6.5)
            c.setFillColor(C_LIGHT)
            c.drawString(0.55*cm, y - rh + 0.15*cm, note)
            y -= rh + 0.05*cm

        # Sağ panel — Mevcut
        rx = half + 0.6*cm
        c.setFillColor(C_GREEN)
        c.roundRect(rx, 0, half, H, 8, fill=1, stroke=0)
        c.setFillColor(C_WHITE)
        c.setFont("DejaVuSans-Bold", 11)
        c.drawCentredString(rx + half/2, H - 0.7*cm, "MEVCUT (2026-03-16)")
        c.setFont("DejaVuSans", 7.5)
        c.drawCentredString(rx + half/2, H - 1.1*cm, "Robustness: 0.903/A")

        new_items = [
            ("GRAPH", "252 node", "(PATTERN/SDOC/CONST silindi, COMP korundu)", colors.HexColor("#1a5c3a")),
            ("VECTOR", "252 node embed", "chroma_v2 temizden rebuild", colors.HexColor("#1a5c3a")),
            ("SOURCE", "36,039 chunk", "93 meta chunk + $variable fix", colors.HexColor("#1a5c3a")),
            ("DOC", "176K chunk", "74 PDF, FTS5+semantic, RRF", C_ACCENT),
            ("FILTER", "COMP+DEC+EV+REQ+ISSUE", "hepsi filtreli (proje-bazlı)", colors.HexColor("#1a5c3a")),
            ("REQ_TREE", "Filter'dan SONRA", "hesaplanıyor (düzeltildi!)", colors.HexColor("#1a5c3a")),
        ]
        y = H - 1.7*cm
        for name, val, note, col in new_items:
            c.setFillColor(col)
            c.roundRect(rx + 0.3*cm, y - rh + 0.05*cm, half - 0.6*cm, rh - 0.1*cm, 4, fill=1, stroke=0)
            c.setFillColor(C_WHITE)
            c.setFont("DejaVuSans-Bold", 7.5)
            c.drawString(rx + 0.55*cm, y - 0.3*cm, name + ":")
            c.setFont("DejaVuSans", 7.5)
            c.drawString(rx + 0.55*cm + 1.4*cm, y - 0.3*cm, val)
            c.setFont("DejaVuSans", 6.5)
            c.setFillColor(C_LIGHT)
            c.drawString(rx + 0.55*cm, y - rh + 0.15*cm, note)
            y -= rh + 0.05*cm

        # Orta ok
        cx = half + 0.3*cm
        cy = H/2
        c.setStrokeColor(C_YELLOW)
        c.setFillColor(C_YELLOW)
        c.setLineWidth(2)
        c.line(cx, cy - 0.2*cm, cx, cy + 0.2*cm)
        c.setFont("DejaVuSans-Bold", 9)
        c.drawCentredString(cx, H/2 - 0.5*cm, "→")


class FiveStoreDiagram(Flowable):
    """5-store mimarisi diyagramı."""
    def __init__(self):
        super().__init__()
        self.width  = PAGE_W - 4*cm
        self.height = 5.5*cm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        W, H = self.width, self.height

        stores = [
            ("1", "Graph\nStore", "Yapısal\nbilgi",   C_TEAL,   ["84 PROJECT", "90 COMPONENT", "31 REQ", "21 EVIDENCE", "14 ISSUE", "12 DECISION"]),
            ("2", "Vector\nStore", "Semantic\narama",  C_PURPLE, ["252 node", "768-dim embed", "HNSW index", "cosine sim", "threshold≥0.45"]),
            ("3", "Source\nChunk", "Kaynak\nkod",      C_ORANGE, ["36,039 chunk", "FTS5 + semantic", "93 meta chunk", "RRF merge"]),
            ("4", "Doc\nStore",   "Xilinx\nPDF",       C_ACCENT, ["176K chunk", "74 PDF (UG/PG)", "FTS5 + semantic", "paraphrase-mpnet"]),
            ("5", "Req\nTree",    "Gereksinim\nahacı", C_GREEN,  ["31 REQ node", "DECOMPOSES_TO", "BFS genişleme", "filter sonrası"]),
        ]

        n = len(stores)
        bw = (W - (n-1)*0.4*cm) / n
        bh = H - 1.2*cm
        by = 1.0*cm

        for i, (num, name, sub, col, items) in enumerate(stores):
            x = i * (bw + 0.4*cm)
            # Blok
            c.setFillColor(col)
            c.roundRect(x, by, bw, bh, 8, fill=1, stroke=0)
            # Başlık bg
            c.setFillColor(colors.HexColor("#00000030"))
            c.roundRect(x, by + bh - 1.6*cm, bw, 1.6*cm, 8, fill=1, stroke=0)
            c.setFillColor(C_WHITE)
            c.setFont("DejaVuSans-Bold", 8)
            c.drawCentredString(x + bw/2, by + bh - 0.7*cm, f"Store {num}: {name.replace(chr(10),' ')}")
            c.setFont("DejaVuSans", 7)
            c.setFillColor(C_LIGHT)
            c.drawCentredString(x + bw/2, by + bh - 1.1*cm, sub.replace("\n"," "))
            # Çizgi
            c.setStrokeColor(C_WHITE)
            c.setLineWidth(0.5)
            c.line(x+0.2*cm, by + bh - 1.65*cm, x + bw - 0.2*cm, by + bh - 1.65*cm)
            # Items
            c.setFont("DejaVuSans", 6.8)
            c.setFillColor(C_WHITE)
            iy = by + bh - 2.1*cm
            for item in items:
                c.drawString(x + 0.25*cm, iy, "· " + item)
                iy -= 0.42*cm

        # Alt etiket
        c.setFillColor(C_DARK)
        c.setFont("DejaVuSans-Bold", 9)
        c.drawCentredString(W/2, 0.3*cm, "Tüm store'lar her sorguda paralel çalışır — sonuçlar Response Builder'da birleştirilir")


class ScenarioDiagram(Flowable):
    """Tek senaryo akış şeması."""
    def __init__(self, title, steps, color=C_TEAL):
        super().__init__()
        self.title  = title
        self.steps  = steps
        self.color  = color
        self.width  = PAGE_W - 4*cm
        self.height = 1.4*cm + len(steps)*1.1*cm

    def wrap(self, aw, ah):
        return self.width, self.height

    def draw(self):
        c = self.canv
        W = self.width
        # Başlık
        c.setFillColor(self.color)
        c.roundRect(0, self.height - 1.0*cm, W, 0.95*cm, 6, fill=1, stroke=0)
        c.setFillColor(C_WHITE)
        c.setFont("DejaVuSans-Bold", 10)
        c.drawCentredString(W/2, self.height - 0.65*cm, self.title)

        for i, (step_num, label, detail, col) in enumerate(self.steps):
            y = self.height - 1.2*cm - i*1.1*cm - 0.9*cm
            # Sol sayı balonu
            c.setFillColor(col)
            c.circle(0.5*cm, y + 0.4*cm, 0.35*cm, fill=1, stroke=0)
            c.setFillColor(C_WHITE)
            c.setFont("DejaVuSans-Bold", 9)
            c.drawCentredString(0.5*cm, y + 0.28*cm, str(step_num))
            # Satır arka planı
            c.setFillColor(C_LGRAY)
            c.roundRect(1.0*cm, y + 0.0*cm, W - 1.1*cm, 0.85*cm, 4, fill=1, stroke=0)
            c.setFillColor(C_DARK)
            c.setFont("DejaVuSans-Bold", 8.5)
            c.drawString(1.2*cm, y + 0.52*cm, label)
            c.setFont("DejaVuSans", 7.5)
            c.setFillColor(colors.HexColor("#444444"))
            c.drawString(1.2*cm, y + 0.15*cm, detail)
            # Ok (son adım hariç)
            if i < len(self.steps) - 1:
                c.setFillColor(C_GRAY)
                cx2 = 0.5*cm
                c.setFont("DejaVuSans", 9)
                c.drawCentredString(cx2, y - 0.1*cm, "↓")


# ─── Header/Footer ─────────────────────────────────────────────────────────────
def header_footer(canvas_obj, doc):
    canvas_obj.saveState()
    W, H = PAGE_W, PAGE_H
    # Header şeridi
    canvas_obj.setFillColor(C_DARK)
    canvas_obj.rect(0, H - 1.5*cm, W, 1.5*cm, fill=1, stroke=0)
    canvas_obj.setFillColor(C_TEAL)
    canvas_obj.setFont("DejaVuSans-Bold", 9)
    canvas_obj.drawString(1*cm, H - 0.9*cm, "FPGA RAG v2 — Sistem Mimarisi Dokümantasyonu")
    canvas_obj.setFillColor(C_GRAY)
    canvas_obj.setFont("DejaVuSans", 8)
    canvas_obj.drawRightString(W - 1*cm, H - 0.9*cm, "2026-03-17")
    # Footer
    canvas_obj.setFillColor(C_DARK)
    canvas_obj.rect(0, 0, W, 0.9*cm, fill=1, stroke=0)
    canvas_obj.setFillColor(C_GRAY)
    canvas_obj.setFont("DejaVuSans", 7.5)
    canvas_obj.drawCentredString(W/2, 0.35*cm, f"Sayfa {doc.page}")
    canvas_obj.restoreState()


# ─── İçerik Blokları ──────────────────────────────────────────────────────────

def cover_page():
    elems = []
    elems.append(Spacer(1, 5*cm))
    # Başlık kutusu
    data = [[Paragraph("FPGA RAG v2", S_TITLE)]]
    t = Table(data, colWidths=[PAGE_W - 4*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(-1,-1), C_DARK),
        ("ROUNDEDCORNERS", [12]),
        ("TOPPADDING", (0,0),(-1,-1), 18),
        ("BOTTOMPADDING", (0,0),(-1,-1), 18),
    ]))
    elems.append(t)
    elems.append(Spacer(1, 0.5*cm))
    elems.append(Paragraph("Sistem Mimarisi — Kapsamlı Dokümantasyon", S_SUBTITLE))
    elems.append(Spacer(1, 0.3*cm))
    elems.append(Paragraph("Kısaltmalar · Store'lar · Akışlar · Scriptler · Senaryolar", S_CAPTION))
    elems.append(Spacer(1, 2*cm))
    info = [
        ["Versiyon", "Phase 8 (2026-03-16)"],
        ["Robustness", "0.903/A"],
        ["Blind v5", "0.905/A"],
        ["Toplam Proje", "85+"],
        ["Kaynak Chunk", "36,039"],
        ["Dok. Chunk", "176,003 (74 PDF)"],
    ]
    t2 = Table(info, colWidths=[5*cm, 9*cm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0,0),(0,-1), C_ACCENT),
        ("BACKGROUND", (1,0),(1,-1), C_BLUE),
        ("TEXTCOLOR",  (0,0),(-1,-1), C_WHITE),
        ("FONTNAME",   (0,0),(0,-1), "DejaVuSans-Bold"),
        ("FONTNAME",   (1,0),(1,-1), "DejaVuSans"),
        ("FONTSIZE",   (0,0),(-1,-1), 10),
        ("GRID",       (0,0),(-1,-1), 0.5, C_TEAL),
        ("ROWBACKGROUNDS", (0,0),(-1,-1), [C_ACCENT, colors.HexColor("#1e3a5f")]),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("LEFTPADDING",   (0,0),(-1,-1), 10),
    ]))
    elems.append(t2)
    elems.append(PageBreak())
    return elems


def section_abbreviations():
    elems = []
    elems.append(Paragraph("1. Kısaltmalar Sözlüğü", S_H1))
    elems.append(HRFlowable(width="100%", thickness=1, color=C_TEAL, spaceAfter=8))

    abbrevs = [
        # (Kısaltma, Açıklım, Açıklama)
        ("RAG", "Retrieval-Augmented Generation",
         "LLM'in bilgi tabanına erişme yöntemi. Soru sorulduğunda önce ilgili belgeler/node'lar alınır (retrieval), sonra LLM bu bağlamla cevap üretir (generation). Büyük dil modelinin 'bilmediği' proje-özel bilgiye ulaşmasını sağlar."),
        ("LLM", "Large Language Model",
         "Büyük dil modeli. Bu sistemde Claude Sonnet 4.6 kullanılır. Sorular, RAG'ın getirdiği bağlamla birlikte LLM'e gönderilir; LLM Türkçe/İngilizce cevap üretir."),
        ("FTS5", "Full-Text Search version 5",
         "SQLite'ın yerleşik tam metin arama motoru. BM25 algoritmasıyla keyword eşleşmesi yapar. 'opt_design' gibi teknik terimleri tam olarak bulur. Sıfır dış bağımlılık, anında başlangıç (0ms cold-start)."),
        ("BM25", "Best Match 25",
         "Bilgi erişiminde kullanılan klasik keyword puanlama algoritması. Terim frekansı (TF) + ters döküman frekansını (IDF) dengeler. Nadir, spesifik terimler daha yüksek puan alır."),
        ("HNSW", "Hierarchical Navigable Small World",
         "Vektör benzerlik araması için grafik tabanlı indeks. ChromaDB'nin kullandığı algoritma. Milyonlarca vektörde logaritmik arama süresi sağlar."),
        ("RRF", "Reciprocal Rank Fusion",
         "FTS5 ve semantic arama sonuçlarını birleştirme algoritması. Her sonucun sırasını 1/(k+rank) formülüyle puanlar ve iki listeyi skor bazında birleştirir. k=60 varsayılan."),
        ("TCL", "Tool Command Language",
         "Vivado'nun komut dili. .tcl uzantılı dosyalar. İki tür: BD-TCL (IP Integrator blok diyagramı tanımı: create_bd_cell, connect_bd_net) ve Build-TCL (sentez/implementasyon akışı: synth_design, opt_design)."),
        ("XDC", "Xilinx Design Constraint",
         "FPGA pin atama ve zamanlama kısıtlama dosyası. set_property PACKAGE_PIN ile pin atanır, create_clock ile saat sinyali tanımlanır. Vivado'nun kısıtlama okuma formatı."),
        ("BD", "Block Design",
         "Vivado IP Integrator'deki grafiksel tasarım ortamı. IP'lerin bağlandığı, portların tanımlandığı blok şeması. BD-TCL ile script olarak ifade edilir."),
        ("VLNV", "Vendor:Library:Name:Version",
         "Xilinx IP tanımlayıcı formatı. Örnek: xilinx.com:ip:axi_dma:7.1 — Vendor=xilinx.com, Library=ip, Name=axi_dma, Version=7.1. create_bd_cell komutunda -vlnv parametresiyle kullanılır."),
        ("UG", "User Guide",
         "Xilinx/AMD kullanıcı kılavuzu. Örnek: UG898=Vivado TCL Scripting, UG901=Vivado Synthesis, UG904=Vivado Implementation, UG984=MicroBlaze. DocStore'da 74 adet UG/PG/XAPP PDF'i indexli."),
        ("PG", "Product Guide",
         "Xilinx/AMD IP ürün kılavuzu. Örnek: PG021=AXI DMA, PG144=AXI GPIO, PG065=Clocking Wizard, PG020=AXI VDMA. Her IP için detaylı parametre ve kullanım bilgisi içerir."),
        ("AXI", "Advanced eXtensible Interface",
         "ARM AMBA standardı; FPGA'da IP'lerin birbiriyle haberleşme protokolü. AXI4-Full (hafıza arayüzü), AXI4-Lite (register arayüzü), AXI4-Stream (veri akışı) çeşitleri vardır."),
        ("MIG", "Memory Interface Generator",
         "Xilinx DDR2/DDR3 hafıza kontrolcüsü IP'si. Karmaşık zamanlama gereksinimlerini otomatik yönetir. nexys_a7_dma_audio'da DDR2, GPIO/GTX projelerinde DDR3 için kullanılır."),
        ("DMA", "Direct Memory Access",
         "CPU'yu bypass ederek doğrudan bellek-çevre birimi veri transferi. AXI DMA IP'si scatter-gather ve simple modda çalışır. MicroBlaze CPU müdahalesi olmadan büyük blok veri taşır."),
        ("EMBED", "Embedding / Vektör Temsili",
         "Metni yüksek boyutlu sayı vektörüne dönüştürme. Benzer anlamlı metinler benzer vektörlere sahip olur. Bu sistemde paraphrase-multilingual-mpnet-base-v2 (768 boyut) kullanılır."),
        ("META CHUNK", "Dosya Düzeyi Özet Chunk",
         "TCL dosyalarından index-time'da statik parse ile üretilen özel chunk. Dosyanın HOW (nasıl çalıştırılır), RELATION (hangi dosyaları kaynak alır), WHAT (hangi BD/part) bilgilerini içerir. is_meta=1 ile işaretlenir."),
        ("PROJECT NODE", "Graph Proje Düğümü",
         "GraphStore'daki kök düğüm. Her fiziksel proje için bir adet. board, fpga_part, description, tool bilgilerini içerir. Tüm COMPONENT, REQUIREMENT, DECISION düğümleri bu düğüme bağlıdır."),
    ]

    for abbr, full, desc in abbrevs:
        row = [
            [Paragraph(f"<b>{abbr}</b>", make_style("ab", fontSize=9, textColor=C_WHITE, fontName="DejaVuSans-Bold")),
             Paragraph(full, make_style("af", fontSize=8.5, textColor=C_LIGHT, fontName="DejaVuSans")),
             Paragraph(desc, make_style("ad", fontSize=8, textColor=C_WHITE, leading=12, fontName="DejaVuSans"))],
        ]
        t = Table(row, colWidths=[2*cm, 4.5*cm, 10.5*cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(0,0), C_ACCENT),
            ("BACKGROUND", (1,0),(1,0), C_BLUE),
            ("BACKGROUND", (2,0),(2,0), C_DARK),
            ("VALIGN",     (0,0),(-1,-1), "TOP"),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("BOX",        (0,0),(-1,-1), 0.3, C_TEAL),
        ]))
        elems.append(t)
        elems.append(Spacer(1, 2))

    return elems


def section_architecture():
    elems = []
    elems.append(PageBreak())
    elems.append(Paragraph("2. Genel Mimari — 5-Store Sistemi", S_H1))
    elems.append(HRFlowable(width="100%", thickness=1, color=C_TEAL, spaceAfter=8))

    elems.append(Paragraph(
        "FPGA RAG v2, beş farklı veri deposunu (store) paralel kullanarak her sorguya en kapsamlı bağlamı sağlar. "
        "Her store farklı bir bilgi türünü saklar ve farklı bir arama yöntemi kullanır.",
        S_BODY))
    elems.append(Spacer(1, 0.3*cm))
    elems.append(FiveStoreDiagram())
    elems.append(Spacer(1, 0.2*cm))
    elems.append(Paragraph("Şekil 1: 5-Store Paralel Mimari — her store farklı veri türü ve arama stratejisi", S_CAPTION))
    elems.append(Spacer(1, 0.4*cm))

    stores_detail = [
        ("Store 1: GraphStore", C_TEAL, [
            "Ne saklar: Node'lar (PROJECT, COMPONENT, REQUIREMENT, DECISION, EVIDENCE, ISSUE) ve aralarındaki edge'ler (CONNECTS_TO, IMPLEMENTS, MOTIVATED_BY vb.)",
            "Nasıl çalışır: NetworkX directed graph → JSON dosyasına serialize edilir (fpga_rag_v2_graph.json). Node özellikleri ve edge tipleri korunur.",
            "Ne için: 'Bu proje hangi IP'leri kullanıyor?', 'Bu gereksinim hangi bileşen tarafından karşılanıyor?', 'Neden bu karar alındı?' gibi yapısal sorgular.",
            "Mevcut durum: 252 node — 84 PROJECT + 90 COMPONENT + 31 REQ + 21 EVIDENCE + 14 ISSUE + 12 DECISION",
        ]),
        ("Store 2: VectorStoreV2", C_PURPLE, [
            "Ne saklar: GraphStore'daki her node'un metin temsili → 768 boyutlu sayısal vektör. ChromaDB'de HNSW indeksi ile saklanır.",
            "Nasıl çalışır: Soru da aynı model (paraphrase-multilingual-mpnet-base-v2) ile vektöre dönüştürülür → kosinüs benzerliği hesaplanır → en benzer node'lar döner.",
            "Ne için: 'AXI DMA nedir?' sorusu semantik olarak AXI DMA COMPONENT node'una yönlendirilir — exact kelime eşleşmesi gerekmez.",
            "Eşik: similarity ≥ 0.45 (düşük eşik = daha fazla sonuç, daha az kaçırma)",
        ]),
        ("Store 3: SourceChunkStore", C_ORANGE, [
            "Ne saklar: 85+ projenin kaynak dosyaları (TCL, XDC, V/VHDL, C/C++, Python, MD) → parçalanmış chunk'lar. Her chunk ~200-500 token.",
            "Nasıl çalışır: FTS5 keyword araması + semantic embedding araması → RRF ile birleştirilir. FTS5 rank-1 garantisi: en iyi keyword eşleşmesi her zaman context'e girer.",
            "Özel: 93 meta chunk (is_meta=1) — TCL dosyalarından HOW/RELATION/WHAT boyutlu özet chunk'lar. HOW sorgularında önce bunlar eklenir.",
            "Mevcut: 36,039 chunk, db/chroma_source_chunks/ + db/fts5_source.db",
        ]),
        ("Store 4: DocStore", C_ACCENT, [
            "Ne saklar: 74 adet Xilinx/AMD PDF dökümantasyonu (UG/PG/XAPP/DS) → 176,003 chunk. Vivado ve IP kılavuzları.",
            "Nasıl çalışır: FTS5 keyword araması + semantic embedding → RRF merge. DocStore'dan n_doc sonuç döner (sorgu tipine göre 3-12 arası).",
            "Ne için: UG898 (TCL scripting), UG901 (synthesis), UG904 (implementation), PG021 (AXI DMA), PG144 (AXI GPIO) vb. referans içerikleri.",
            "Önemli: Türkçe sorular → multilingual model sayesinde İngilizce PDF içeriklerini bulabilir.",
        ]),
        ("Store 5: RequirementTree", C_GREEN, [
            "Ne saklar: GraphStore'daki REQUIREMENT node'larının DECOMPOSES_TO edge'leri ile oluşturduğu ağaç yapısı.",
            "Nasıl çalışır: BFS (genişlik öncelikli arama) ile bir REQ node'undan tüm alt gereksinimlere ulaşılır.",
            "Ne için: 'DMA_AUDIO_REQ üst gereksiniminin alt detayları neler?' gibi traceability sorguları.",
            "Phase 8 fix: req_tree artık _filter_cross_project_nodes() SONRASI hesaplanır — yanlış proje REQ'ları req_tree'ye sızmaz.",
        ]),
    ]

    for title, color, points in stores_detail:
        elems.append(Spacer(1, 0.2*cm))
        header_data = [[Paragraph(title, make_style("sh", fontSize=10, textColor=C_WHITE, fontName="DejaVuSans-Bold"))]]
        ht = Table(header_data, colWidths=[PAGE_W - 4*cm])
        ht.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), color),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("ROUNDEDCORNERS", [4]),
        ]))
        elems.append(ht)
        for p in points:
            elems.append(Paragraph("  • " + p, S_BULLET))

    return elems


def section_query_flow():
    elems = []
    elems.append(PageBreak())
    elems.append(Paragraph("3. Sorgu Akışı — Bir Soru Sistemde Nasıl İşlenir?", S_H1))
    elems.append(HRFlowable(width="100%", thickness=1, color=C_TEAL, spaceAfter=8))

    elems.append(FlowDiagram())
    elems.append(Spacer(1, 0.2*cm))
    elems.append(Paragraph("Şekil 2: Uçtan uca sorgu işleme akışı", S_CAPTION))
    elems.append(Spacer(1, 0.4*cm))

    flow_steps = [
        ("1. Classifier", C_PURPLE, [
            "Sorguyu 6 tipe sınıflandırır: WHAT · HOW · WHY · TRACE · CROSSREF · ENUMERATE",
            "WHAT: 'AXI DMA nedir?' — Genel bilgi sorusu",
            "HOW: 'MicroBlaze nasıl başlatılır?' — Uygulama/workflow sorusu",
            "WHY: 'Neden Scatter-Gather seçildi?' — Gerekçe sorusu",
            "TRACE: 'mig_7series_0 → fifo2audpwm zincirini izle' — Bağlantı takip sorusu",
            "CROSSREF: 'iki proje arasındaki fark nedir?' — Karşılaştırma sorusu",
            "ENUMERATE: 'Bu projede hangi IP'ler var?' — Listeleme sorusu",
        ]),
        ("2. Project Resolver (_resolve_project)", C_ORANGE, [
            "Tier 0 — Exact match: 'axi_gpio_example' → doğrudan proje ID eşleşmesi",
            "Tier 1 — Text signals: 'nexys video', 'dma audio' → proje sinyal tablosu",
            "Tier 2a — Graph vote: vector hits'teki node'ların 'project' alanı çoğunluk oyu",
            "Tier 2b — Semantic: %45 eşik üstü hit sayısı → tek proje baskınsa seç",
            "Sonuç: project=None (genel sorgu) veya project='nexys_a7_dma_audio' gibi belirli proje",
        ]),
        ("3. Router (5 farklı yol)", C_ACCENT, [
            "_route_what(): Tüm store'lardan paralel; genel sorgularda DocStore boost (3x)",
            "_route_how(): COMPONENT node'ları + meta chunk'lar + IP→Doc retrieval",
            "_route_why(): DECISION node'ları + MOTIVATED_BY edge traversal",
            "_route_trace(): IMPLEMENTS/VERIFIED_BY/DEPENDS_ON zincir takibi",
            "_route_crossref(): ANALOGOUS_TO/CONTRADICTS edge'leri; filter UYGULANMAZ",
        ]),
        ("4. _filter_cross_project_nodes()", C_RED, [
            "Proje tespit edildi → yalnızca o projenin COMPONENT/DEC/EV/REQ/ISSUE node'ları geçer",
            "Proje tespit edilmedi → bu tiplerin hiçbiri geçmez (genel sorguları kirletmez)",
            "PROJECT node'ları: proje tespitindeyse sadece o proje, yoksa hepsi geçer",
            "CROSSREF route'da çağrılmaz (çapraz proje karşılaştırması için gerekli)",
        ]),
        ("5. Response Builder", C_GREEN, [
            "5 store'dan gelen chunks + graph nodes birleştirilir",
            "System prompt + proje listesi + bağlam + soru → LLM'e gönderilir",
            "GroundingChecker: cevaptaki sayısal değerlerin context'te olup olmadığını kontrol eder",
            "PARSE_UNCERTAIN uyarısı: belirsiz parsing durumunda LLM'e bildirilir",
        ]),
    ]

    for title, color, points in flow_steps:
        header = [[Paragraph(title, make_style("fh", fontSize=10, textColor=C_WHITE, fontName="DejaVuSans-Bold"))]]
        ht = Table(header, colWidths=[PAGE_W - 4*cm])
        ht.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), color),
            ("TOPPADDING",    (0,0),(-1,-1), 6),
            ("BOTTOMPADDING", (0,0),(-1,-1), 6),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
        ]))
        elems.append(ht)
        for p in points:
            elems.append(Paragraph("  • " + p, S_BULLET))
        elems.append(Spacer(1, 0.2*cm))

    return elems


def section_comparison():
    elems = []
    elems.append(PageBreak())
    elems.append(Paragraph("4. Önceki vs Mevcut Mimari — Phase 8 Değişiklikleri", S_H1))
    elems.append(HRFlowable(width="100%", thickness=1, color=C_TEAL, spaceAfter=8))
    elems.append(ComparisonDiagram())
    elems.append(Spacer(1, 0.3*cm))
    elems.append(Paragraph("Şekil 3: Önceki (sol) ve mevcut (sağ) mimari karşılaştırması", S_CAPTION))
    elems.append(Spacer(1, 0.4*cm))

    changes = [
        ("DEĞİŞİKLİK 1: Graph Node Temizliği", C_TEAL,
         "Önceki", "297 node: PROJECT(85)+COMP(90)+PATTERN(12)+SOURCE_DOC(20)+CONSTRAINT(13)+REQ(31)+DEC(12)+EV(21)+ISSUE(14)",
         "Mevcut", "252 node: PROJECT(84)+COMP(90)+REQ(31)+DEC(12)+EV(21)+ISSUE(14) — PATTERN, SOURCE_DOC, CONSTRAINT silindi",
         "Neden: PATTERN/SOURCE_DOC/CONSTRAINT node'ları retrieval kalitesini artırmıyordu, gereksiz vektör karmaşası yaratıyordu."),
        ("DEĞİŞİKLİK 2: _filter_cross_project_nodes Güçlendirmesi", C_ORANGE,
         "Önceki", "_PROJECT_SPECIFIC = {DECISION, EVIDENCE, REQUIREMENT, ISSUE} — COMPONENT filtreli değildi",
         "Mevcut", "_PROJECT_SPECIFIC += COMPONENT — artık proje tespiti olmadan COMPONENT da geçmez",
         "Neden: Genel sorgularda (örn. 'MIG DDR3 nedir?') nexys_a7 COMPONENT node'ları context'e sızıyordu, cevabı kirletiyordu."),
        ("DEĞİŞİKLİK 3: req_tree Ordering Fix", C_PURPLE,
         "Önceki", "req_tree = _get_req_trees_for_nodes(graph_nodes) — filter'dan ÖNCE hesaplanıyordu (WHAT + TRACE route)",
         "Mevcut", "graph_nodes = filter(...) ardından req_tree = _get_req_trees_for_nodes(graph_nodes) — filter'dan SONRA",
         "Neden: Genel sorgularda filter COMPONENT/REQ node'larını kaldırıyordu ama req_tree zaten dolu kalıyordu. Sızma önlendi."),
        ("DEĞİŞİKLİK 4: query-time _get_ip_doc_chunks()", C_GREEN,
         "Önceki", "Graph COMPONENT node'larındaki vlnv alanından IP ismi çıkarılıp _IP_TO_DOCS tablosuna bakılıyordu",
         "Mevcut", "SourceChunkStore'daki TCL chunk'ları okunup create_bd_cell -vlnv regex ile IP isimleri çıkarılıyor",
         "Neden: Graph'a bağımlılık azaltıldı. Yeni proje eklendiğinde TCL indexlenince otomatik çalışır — graph update gerekmez."),
        ("DEĞİŞİKLİK 5: _tcl_meta_chunk() $variable Fix", C_RED,
         "Önceki", "create_bd_design $design_name → '$design_name' string'i olarak işleniyordu, meta chunk üretilmiyordu",
         "Mevcut", "set design_name system → değişken çözümleniyor → create_bd_design system → meta chunk üretiliyor",
         "Neden: Zybo projesinde system.tcl dosyası HOW sorularında hiç context vermiyordu."),
        ("DEĞİŞİKLİK 6: search_within_file/search_by_filename Pagination", C_GRAY,
         "Önceki", "col.get(include=['metadatas']) — tüm 36K chunk tek sorguda → SQLite 'too many SQL variables' hatası",
         "Mevcut", "col.get(limit=5000, offset=N) döngüsü — 5000'lik sayfalar halinde → hata yok",
         "Neden: 36,039 chunk'taki ChromaDB get() SQLite variable limitini (32766) aşıyordu."),
    ]

    for title, col, before_l, before_v, after_l, after_v, reason in changes:
        elems.append(Spacer(1, 0.1*cm))
        hdr = [[Paragraph(title, make_style("ch", fontSize=9.5, textColor=C_WHITE, fontName="DejaVuSans-Bold"))]]
        ht = Table(hdr, colWidths=[PAGE_W - 4*cm])
        ht.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(-1,-1), col),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ]))
        elems.append(ht)
        row_data = [
            [Paragraph(f"<b>Önceki:</b> {before_v}",
                       make_style("bv", fontSize=8, textColor=C_WHITE, fontName="DejaVuSans", leading=11)),
             Paragraph(f"<b>Mevcut:</b> {after_v}",
                       make_style("av", fontSize=8, textColor=C_WHITE, fontName="DejaVuSans", leading=11))],
        ]
        rt = Table(row_data, colWidths=[(PAGE_W-4*cm)/2]*2)
        rt.setStyle(TableStyle([
            ("BACKGROUND", (0,0),(0,0), C_RED),
            ("BACKGROUND", (1,0),(1,0), colors.HexColor("#1a5c3a")),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 6),
            ("VALIGN",        (0,0),(-1,-1), "TOP"),
        ]))
        elems.append(rt)
        elems.append(Paragraph(f"  ⓘ {reason}", make_style("rs", fontSize=8, textColor=colors.HexColor("#555555"), fontName="DejaVuSans", leftIndent=6, spaceAfter=3)))

    return elems


def section_scripts():
    elems = []
    elems.append(PageBreak())
    elems.append(Paragraph("5. Script Rehberi", S_H1))
    elems.append(HRFlowable(width="100%", thickness=1, color=C_TEAL, spaceAfter=8))

    scripts = [
        ("app_v2.py", "Ana Uygulama (Streamlit UI)", C_TEAL, [
            "Amaç: Kullanıcı arayüzü. Tarayıcıda çalışır. Soru yazılır → pipeline çalışır → cevap gösterilir.",
            "Çalıştırma: streamlit run app_v2.py",
            "İçerik: QueryRouter + 5 store yüklenir. Soru girilince route() çağrılır. Debug moduyla graph node'ları, source chunk'ları görünür.",
            "Port: varsayılan 8501. http://localhost:8501",
        ]),
        ("scripts/index_source_files.py", "Kaynak Kod İndeksleme", C_ORANGE, [
            "Amaç: data/code/ altındaki proje kaynak dosyalarını SourceChunkStore'a ekler.",
            "Çalıştırma: python scripts/index_source_files.py  (veya --reset ile sıfırdan)",
            "Yaptığı: PROJECT_SOURCE_CATALOG'daki her proje için dosyaları okur → chunk'lara böler → FTS5 + ChromaDB'ye yazar.",
            "Ne zaman: Yeni proje eklendiğinde veya dosyalar değiştiğinde çalıştırılır.",
            "--reset flag'i: ChromaDB dizinini tamamen siler + FTS5'i sıfırlar. Tam yeniden indeksleme.",
        ]),
        ("scripts/index_docs.py", "PDF Döküman İndeksleme", C_PURPLE, [
            "Amaç: Xilinx/AMD UG/PG/XAPP PDF'lerini DocStore'a ekler.",
            "Çalıştırma: python scripts/index_docs.py --doc ug904  (veya --all ile hepsini)",
            "Yaptığı: PDF'i sayfalar halinde okur → başlık regex ile bölümlere ayırır → her bölüm bir chunk → embed eder → ChromaDB + FTS5'e yazar.",
            "Ne zaman: Yeni bir Xilinx PDF indirildiğinde çalıştırılır.",
        ]),
        ("scripts/test_robustness.py", "Dayanıklılık Test Paketi", C_RED, [
            "Amaç: 5 kategoride sistem kalitesini ölçer. A=Held-Out Dosya, B=Fabrication/Recall, C=Multi-Hop Traversal, D=Cross-Project, E=Contradiction.",
            "Çalıştırma: python scripts/test_robustness.py  (veya --only C ile tek kategori)",
            "Nasıl ölçer: Her soru pipeline'a gönderilir → cevap beklenen terimlere göre puanlanır → ağırlıklı ortalama alınır.",
            "--save flag'i: robustness_report.json dosyasına kaydeder.",
            "Güncel skor: 0.903/A (A=0.900, B=0.904, C=0.956, D=0.772, E=1.000)",
        ]),
        ("scripts/test_blind_benchmark_v5.py", "Kör Benchmark (Workflow)", C_GREEN, [
            "Amaç: HOW workflow sorularını test eder. Sorular sisteme önceden eklenmemiş (kör).",
            "Kategoriler: HOW New Project, HOW Synthesis, HOW Constraints, HOW IP Config, WHAT Concepts, TRACE, Trap.",
            "Çalıştırma: python scripts/test_blind_benchmark_v5.py",
            "Güncel skor: 0.905/A",
        ]),
        ("scripts/build_full_index.py", "Tam İndeks Build", C_ACCENT, [
            "Amaç: Tüm indeksleme adımlarını sırayla çalıştırır. Yeni ortamda kurulum veya tam reset sonrası kullanılır.",
            "Sıra: GraphStore yükle → VectorStore build → SourceChunk index → DocStore index.",
        ]),
        ("scripts/discover_projects.py", "Proje Keşfi", C_GRAY, [
            "Amaç: data/code/ altındaki yeni projeleri otomatik keşfeder.",
            "Yaptığı: README.md, *.tcl, *.xdc dosyalarını tarar → FPGA part, board, tool bilgilerini çıkarır.",
            "Kullanım: Yeni proje eklenmeden önce 'bu proje ne içeriyor?' kontrolü için.",
        ]),
        ("src/rag_v2/query_router.py", "Sorgu Yönlendirici (Çekirdek)", C_TEAL, [
            "Amaç: Sorguyu sınıflandırır, projeyi saptar, 5 route'dan birini çalıştırır, 5 store'u paralel sorgular.",
            "Temel metodlar: classify(), route(), _resolve_project(), _filter_cross_project_nodes()",
            "Boyut: ~1600 satır. Sistemin kalbi. Tüm retrieval mantığı burada.",
            "_TEXT_PROJECT_SIGNALS: keyword → proje eşleme tablosu (529 sinyal, FTS5 otomatik + statik)",
        ]),
        ("src/rag_v2/response_builder.py", "Cevap Üretici", C_ORANGE, [
            "Amaç: Router'dan gelen QueryResult'u LLM'e uygun formata dönüştürür. System prompt, proje listesi, context, soru birleştirilir.",
            "build_system_prefix(): GraphStore'dan güncel proje listesini dinamik üretir.",
            "GroundingChecker entegrasyonu: sayısal değer halüsinasyonu tespiti.",
        ]),
    ]

    for script, title, col, points in scripts:
        elems.append(Spacer(1, 0.15*cm))
        hdr = [[Paragraph(f"<b>{script}</b>  —  {title}", make_style("sc", fontSize=9.5, textColor=C_WHITE, fontName="DejaVuSans-Bold"))]]
        ht = Table(hdr, colWidths=[PAGE_W - 4*cm])
        ht.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), col),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ]))
        elems.append(ht)
        for p in points:
            elems.append(Paragraph("  · " + p, S_BULLET))

    return elems


def section_scenarios():
    elems = []
    elems.append(PageBreak())
    elems.append(Paragraph("6. Basit Senaryolar — Bir Soru Nasıl İşlenir?", S_H1))
    elems.append(HRFlowable(width="100%", thickness=1, color=C_TEAL, spaceAfter=8))

    scenarios = [
        {
            "title": "Senaryo A: Genel Kavram Sorusu",
            "question": "\"AXI DMA nedir, ne işe yarar?\"",
            "type": "WHAT · Proje: None (genel)",
            "steps": [
                (1, "Classify → WHAT", "AXI DMA, ne, nedir kelimeleri → WHAT tipi", C_TEAL),
                (2, "Project: None", "Hiçbir proje adı/sinyali yok → project=None", C_GRAY),
                (3, "Vector search", "252 graph node → 'AXI DMA' yakın node'lar: COMP-A-axi_dma_0 (0.82), proje nodes", C_PURPLE),
                (4, "Filter uygula", "project=None → COMPONENT, DEC, EV, REQ, ISSUE hepsi çıkarılır → sadece PROJECT node'ları kalır", C_RED),
                (5, "Source chunks", "has_project_signal=False → source_chunks[:4] — genel proje kaynak kodu sınırlı", C_ORANGE),
                (6, "DocStore boost", "_is_general_query=True → n_doc*3=12 chunk — PG021 (AXI DMA), UG898 vb. getirilir", C_GREEN),
                (7, "LLM → Cevap", "Context: PG021'den AXI DMA açıklaması, scatter-gather modu, register map vb.", C_ACCENT),
            ],
            "result": "Cevap: Xilinx PG021 + UG898'den AXI DMA tanımı, özellikleri, kullanım alanları. Proje-spesifik konfigürasyon değil, genel döküman bilgisi.",
        },
        {
            "title": "Senaryo B: Proje-Özel HOW Sorusu",
            "question": "\"axi_gpio_example projesini nasıl çalıştırırım?\"",
            "type": "HOW · Proje: axi_gpio_example",
            "steps": [
                (1, "Classify → HOW", "nasıl, çalıştır kelimeleri → HOW tipi", C_ORANGE),
                (2, "Project: axi_gpio_example", "Tier 0 exact match: 'axi_gpio_example' query'de var → project tespit edildi", C_TEAL),
                (3, "Meta chunks önce", "get_meta_chunks('axi_gpio_example') → design_1_meta chunk: 'source design_1.tcl', board_part, BD design", C_GREEN),
                (4, "Source chunks", "FTS5: 'çalıştır'→tcl bulunmaz, 'axi_gpio_example'→project match. Semantic: design_1.tcl, run.tcl vb.", C_ORANGE),
                (5, "IP→Doc (TCL parse)", "design_1.tcl'den create_bd_cell -vlnv regex → {microblaze, clk_wiz, axi_gpio} → PG144, PG065, UG984", C_PURPLE),
                (6, "DocStore", "n_doc=3 chunk, project-specific → genel Vivado workflow dökümanları", C_ACCENT),
                (7, "LLM → Cevap", "Context: design_1.tcl meta chunk + IP PG'leri + kaynak dosyalar", C_TEAL),
            ],
            "result": "Cevap: 'source design_1.tcl komutunu Vivado TCL konsolunda çalıştırın. Proje axi_gpio_example için clk_wiz (PG065), AXI GPIO (PG144)...'",
        },
        {
            "title": "Senaryo C: Cross-Project Karşılaştırma",
            "question": "\"DMA Audio ve AXI GPIO projelerindeki MicroBlaze konfigürasyonları arasındaki fark nedir?\"",
            "type": "CROSSREF · Proje: nexys_a7_dma_audio + axi_gpio_example",
            "steps": [
                (1, "Classify → CROSSREF", "iki farklı proje sinyali + 'fark' → CROSSREF tipi", C_PURPLE),
                (2, "Proje: iki proje", "exact_matches: {nexys_a7_dma_audio, axi_gpio_example} — CrossRef onaylandı", C_TEAL),
                (3, "ANALOGOUS_TO edge'leri", "COMP-A-microblaze_0 ↔ COMP-B-microblaze_0 arası ANALOGOUS_TO kenarı traversal edilir", C_ACCENT),
                (4, "Filter UYGULANMAZ", "_route_crossref() _filter_cross_project_nodes() çağırmaz — iki projenin node'ları gerekli", C_ORANGE),
                (5, "Her iki proje source", "design_1.tcl (A) + design_1.tcl (B) içinden microblaze_0 chunk'ları alınır", C_GREEN),
                (6, "DocStore", "UG984 (MicroBlaze) + n_doc chunk getirilir", C_ACCENT),
                (7, "LLM → Cevap", "Context: A projesinin MB config + B projesinin MB config + ANALOGOUS_TO edge bilgisi", C_TEAL),
            ],
            "result": "Cevap: 'Proje A'da cache aktif (C_USE_ICACHE=1), debug modülü MDM ekli. Proje B'de daha minimal konfigürasyon...'",
        },
        {
            "title": "Senaryo D: Yanlış Proje Kirliliği — Filter Öncesi vs Sonrası",
            "question": "\"MIG DDR3 timing constraint'leri nelerdir?\"",
            "type": "WHAT · Proje: None (genel teknik soru)",
            "steps": [
                (1, "Classify → WHAT", "Genel DDR3 timing sorusu", C_TEAL),
                (2, "Project: None", "MIG, DDR3 genel terimler — belirli proje tespiti yok", C_GRAY),
                (3, "Vector search", "252 node → MIG ile ilgili node'lar: nexys_a7 COMPONENT ve REQUIREMENT node'ları yüksek benzerlik", C_PURPLE),
                (4, "Filter (MEVCUT)", "project=None → COMPONENT+REQ+DEC+EV+ISSUE hepsi çıkarılır → sadece PROJECT node'ları kalır ✓", C_GREEN),
                (4, "req_tree (MEVCUT)", "Filter SONRASI hesaplanır → graph_nodes boş → req_tree da boş. nexys_a7 REQ'ları sızmaz ✓", C_GREEN),
                (5, "DocStore", "UG586 (MIG 7-Series), UG586 timing constraints → genel referans", C_ACCENT),
                (6, "LLM → Cevap", "Context: UG586'dan DDR3 timing bilgisi — spesifik proje konfigürasyonu değil", C_TEAL),
            ],
            "result": "Cevap: UG586 kaynaklı genel DDR3 timing bilgisi. nexys_a7'nin özel DMA-REQ-L2-007 gibi gereksinim node'ları context'e girmez.",
        },
    ]

    for s in scenarios:
        elems.append(Spacer(1, 0.3*cm))
        # Soru kutusu
        q_data = [[Paragraph(f"<b>{s['title']}</b><br/><i>Soru:</i> {s['question']}<br/><font size='8' color='#00b4d8'>{s['type']}</font>",
                              make_style("qb", fontSize=9.5, textColor=C_WHITE, fontName="DejaVuSans", leading=14))]]
        qt = Table(q_data, colWidths=[PAGE_W - 4*cm])
        qt.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), C_BLUE),
            ("TOPPADDING",    (0,0),(-1,-1), 8),
            ("BOTTOMPADDING", (0,0),(-1,-1), 8),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("BOX",           (0,0),(-1,-1), 1, C_TEAL),
            ("ROUNDEDCORNERS", [4]),
        ]))
        elems.append(qt)

        # Adımlar
        for step_num, label, detail, col in s["steps"]:
            step_data = [[
                Paragraph(str(step_num), make_style("sn", fontSize=10, textColor=C_WHITE, fontName="DejaVuSans-Bold", alignment=TA_CENTER)),
                Paragraph(f"<b>{label}</b>", make_style("sl", fontSize=8.5, textColor=C_WHITE, fontName="DejaVuSans-Bold")),
                Paragraph(detail, make_style("sd", fontSize=7.5, textColor=C_LIGHT, fontName="DejaVuSans", leading=11)),
            ]]
            st = Table(step_data, colWidths=[0.7*cm, 4.5*cm, PAGE_W - 4*cm - 0.7*cm - 4.5*cm - 0.3*cm])
            st.setStyle(TableStyle([
                ("BACKGROUND", (0,0),(0,0), col),
                ("BACKGROUND", (1,0),(1,0), C_DARK),
                ("BACKGROUND", (2,0),(2,0), C_BLUE),
                ("VALIGN",     (0,0),(-1,-1), "MIDDLE"),
                ("TOPPADDING",    (0,0),(-1,-1), 4),
                ("BOTTOMPADDING", (0,0),(-1,-1), 4),
                ("LEFTPADDING",   (1,0),(-1,-1), 6),
            ]))
            elems.append(st)

        # Sonuç
        r_data = [[Paragraph(f"✓ <b>Sonuç:</b> {s['result']}",
                             make_style("res", fontSize=8.5, textColor=C_DARK, fontName="DejaVuSans", leading=12))]]
        rt2 = Table(r_data, colWidths=[PAGE_W - 4*cm])
        rt2.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), C_LIGHT),
            ("TOPPADDING",    (0,0),(-1,-1), 7),
            ("BOTTOMPADDING", (0,0),(-1,-1), 7),
            ("LEFTPADDING",   (0,0),(-1,-1), 10),
            ("BOX",           (0,0),(-1,-1), 1, C_GREEN),
        ]))
        elems.append(rt2)

    return elems


def section_benchmark():
    elems = []
    elems.append(PageBreak())
    elems.append(Paragraph("7. Benchmark Sonuçları & Açık Sorunlar", S_H1))
    elems.append(HRFlowable(width="100%", thickness=1, color=C_TEAL, spaceAfter=8))

    # Robustness tablosu
    elems.append(Paragraph("Robustness Test Paketi (2026-03-16, Phase 8)", S_H2))
    rob_data = [
        ["Test", "Açıklama", "Skor", "Not"],
        ["A — Held-Out", "Dosya kaldırıldığında 'bilmiyorum' diyebilme", "0.900/A", "Stabil"],
        ["B — Fabrication", "Sahte bilgi üretmeme + doğru bilgiyi bulma", "0.904/A", "Prev: 1.000/A"],
        ["C — Multi-Hop", "Graf 2+ edge derinliğinde zincir takibi", "0.956/A", "COMP restore ile kurtarıldı"],
        ["D — Cross-Project", "ANALOGOUS_TO edge'leri kullanımı", "0.772/B", "Prev: 0.806/A"],
        ["E — Contradiction", "Kasıtlı çelişki tespiti", "1.000/A", "Mükemmel"],
        ["TOPLAM", "", "0.903/A", "Prev best: 0.937/A"],
    ]
    rob_t = Table(rob_data, colWidths=[3.5*cm, 7*cm, 2.5*cm, 4*cm])
    rob_t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,0), C_DARK),
        ("TEXTCOLOR",   (0,0),(-1,0), C_TEAL),
        ("FONTNAME",    (0,0),(-1,0), "DejaVuSans-Bold"),
        ("FONTSIZE",    (0,0),(-1,-1), 8.5),
        ("ROWBACKGROUNDS", (0,1),(-1,-2), [C_LGRAY, C_WHITE]),
        ("BACKGROUND",  (0,-1),(-1,-1), C_DARK),
        ("TEXTCOLOR",   (0,-1),(-1,-1), C_YELLOW),
        ("FONTNAME",    (0,-1),(-1,-1), "DejaVuSans-Bold"),
        ("GRID",        (0,0),(-1,-1), 0.5, C_GRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
    ]))
    elems.append(rob_t)
    elems.append(Spacer(1, 0.4*cm))

    # Blind v5 tablosu
    elems.append(Paragraph("Blind Benchmark v5 (2026-03-16, 24 soru)", S_H2))
    blind_data = [
        ["Kategori", "Skor", "Notlar"],
        ["HOW New Project — IP Integrator sıfırdan", "0.948/A", "Uygun"],
        ["HOW Synthesis — sentez/impl/bitstream", "0.805/A", "HS-03=0.39 ⚠ (opt/place/route/write eksik)"],
        ["HOW Constraints — XDC, timing, pin", "1.000/A", "+0.14 iyileşme"],
        ["HOW IP Config — IP parametre ayarı", "0.910/A", "Uygun"],
        ["WHAT Concepts — kavramsal UG soruları", "0.838/A", "Stabil"],
        ["Regression TRACE — mevcut trace testleri", "0.871/A", "+0.107 iyileşme (req_tree fix)"],
        ["Trap v5 — workflow tuzakları", "1.000/A", "Mükemmel"],
        ["TOPLAM", "0.905/A", "Prev: 0.914/A"],
    ]
    blind_t = Table(blind_data, colWidths=[7.5*cm, 2.5*cm, 7*cm])
    blind_t.setStyle(TableStyle([
        ("BACKGROUND",  (0,0),(-1,0), C_DARK),
        ("TEXTCOLOR",   (0,0),(-1,0), C_TEAL),
        ("FONTNAME",    (0,0),(-1,0), "DejaVuSans-Bold"),
        ("FONTSIZE",    (0,0),(-1,-1), 8.5),
        ("ROWBACKGROUNDS", (0,1),(-1,-2), [C_LGRAY, C_WHITE]),
        ("BACKGROUND",  (0,-1),(-1,-1), C_DARK),
        ("TEXTCOLOR",   (0,-1),(-1,-1), C_YELLOW),
        ("FONTNAME",    (0,-1),(-1,-1), "DejaVuSans-Bold"),
        ("GRID",        (0,0),(-1,-1), 0.5, C_GRAY),
        ("TOPPADDING",    (0,0),(-1,-1), 5),
        ("BOTTOMPADDING", (0,0),(-1,-1), 5),
        ("LEFTPADDING",   (0,0),(-1,-1), 6),
    ]))
    elems.append(blind_t)
    elems.append(Spacer(1, 0.4*cm))

    # Açık sorunlar
    elems.append(Paragraph("Açık Sorunlar", S_H2))
    issues = [
        ("HS-03 (Kritik)", C_RED,
         "HOW Synthesis skoru 0.39 — 'opt_design, place_design, route_design, write_bitstream' komutları context'e girmiyor.",
         "Kök neden: HOW+proje_sinyali → DocStore FTS5 Türkçe query ile bu İngilizce komutları bulamıyor. UG904 (Vivado Implementation) indexli ama ulaşılamıyor.",
         "Önerilen fix: DocStore search() metoduna FTS5 rank-1 garantisi ekle (source_chunk_store'daki gibi). RRF merge'de FTS5 rank-1 her zaman eklenir."),
        ("D CrossRef (Düşük)", C_ORANGE,
         "D test skoru 0.806/A → 0.772/B — CROSSREF sorgu kalitesi hafif düştü.",
         "Kök neden: Büyük olasılıkla LLM variability (0.034 fark, tek run). COMPONENT node'ları geri yüklendi, CrossRef route filter'dan muaf.",
         "Önerilen aksiyon: Bir kez daha D testi çalıştır. Tutarlı düşüşse CrossRef route'u incele."),
        ("PARSE_UNCERTAIN", C_GRAY,
         "Tüm sorgularda PARSE_UNCERTAIN uyarısı görünüyor — cevap kalitesini etkilemiyor.",
         "Kök neden: response_builder.py'de parsing belirsizliği tespiti agresif ayarlanmış.",
         "Önerilen aksiyon: PARSE_UNCERTAIN eşiğini artır veya uyarı koşulunu gevşet."),
    ]

    for title, col, what, why, fix in issues:
        hdr = [[Paragraph(f"⚠ {title}", make_style("ih", fontSize=9.5, textColor=C_WHITE, fontName="DejaVuSans-Bold"))]]
        ht = Table(hdr, colWidths=[PAGE_W - 4*cm])
        ht.setStyle(TableStyle([
            ("BACKGROUND",    (0,0),(-1,-1), col),
            ("TOPPADDING",    (0,0),(-1,-1), 5),
            ("BOTTOMPADDING", (0,0),(-1,-1), 5),
            ("LEFTPADDING",   (0,0),(-1,-1), 8),
        ]))
        elems.append(ht)
        elems.append(Paragraph(f"  <b>Ne:</b> {what}", S_BULLET))
        elems.append(Paragraph(f"  <b>Neden:</b> {why}", S_BULLET))
        elems.append(Paragraph(f"  <b>Fix:</b> {fix}", S_BULLET))
        elems.append(Spacer(1, 0.1*cm))

    return elems


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    out_path = "/home/test123/Desktop/FPGA_RAG_v2_Mimari.pdf"

    doc = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm,  bottomMargin=1.5*cm,
        title="FPGA RAG v2 — Sistem Mimarisi",
        author="GC-RAG-VIVADO-2",
    )

    story = []
    story += cover_page()
    story += section_abbreviations()
    story += section_architecture()
    story += section_query_flow()
    story += section_comparison()
    story += section_scripts()
    story += section_scenarios()
    story += section_benchmark()

    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    print(f"PDF oluşturuldu: {out_path}")
    import os
    size = os.path.getsize(out_path) / 1024
    print(f"Boyut: {size:.1f} KB")


if __name__ == "__main__":
    main()
