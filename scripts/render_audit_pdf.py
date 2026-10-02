import re
from html import escape
from pathlib import Path

import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    Preformatted,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

root = Path(__file__).resolve().parents[1]
for name, file in [
    ("Body", "DejaVuSans.ttf"),
    ("BodyBold", "DejaVuSans-Bold.ttf"),
    ("Mono", "DejaVuSansMono.ttf"),
]:
    pdfmetrics.registerFont(TTFont(name, "/usr/share/fonts/truetype/dejavu/" + file))
pdfmetrics.registerFontFamily(
    "Body", normal="Body", bold="BodyBold", italic="Body", boldItalic="BodyBold"
)
styles = getSampleStyleSheet()
styles.add(
    ParagraphStyle(
        name="Text",
        fontName="Body",
        fontSize=9,
        leading=13,
        spaceAfter=8,
        textColor=colors.HexColor("#172b3a"),
    )
)
styles.add(
    ParagraphStyle(
        name="Section",
        parent=styles["Text"],
        fontName="BodyBold",
        fontSize=20,
        leading=25,
        spaceAfter=17,
        keepWithNext=True,
        textColor=colors.HexColor("#113d50"),
    )
)
styles.add(
    ParagraphStyle(
        name="Subsection",
        parent=styles["Text"],
        fontName="BodyBold",
        fontSize=13,
        leading=17,
        spaceBefore=15,
        spaceAfter=8,
        keepWithNext=True,
        textColor=colors.HexColor("#113d50"),
    )
)
styles.add(
    ParagraphStyle(
        name="Cell",
        parent=styles["Text"],
        fontSize=7.2,
        leading=10,
        spaceAfter=0,
        splitLongWords=True,
    )
)
styles.add(
    ParagraphStyle(
        name="CodeBlock",
        fontName="Mono",
        fontSize=7.5,
        leading=11,
        spaceBefore=7,
        spaceAfter=12,
        backColor=colors.HexColor("#f1f5f7"),
        borderPadding=8,
    )
)
styles.add(
    ParagraphStyle(
        name="Cover", parent=styles["Section"], fontSize=28, leading=35, spaceAfter=18
    )
)
styles.add(
    ParagraphStyle(
        name="TOC1",
        parent=styles["Text"],
        fontSize=10,
        leading=15,
        spaceBefore=10,
        fontName="BodyBold",
    )
)
styles.add(
    ParagraphStyle(
        name="TOC2",
        parent=styles["Text"],
        fontSize=8.5,
        leading=12,
        leftIndent=14,
        spaceBefore=3,
    )
)


def inline(s):
    # Protect links and code before formatting the surrounding text.
    tokens = []

    def save(value):
        tokens.append(value)
        return f"ZZTOKEN{len(tokens) - 1}ZZ"

    def link(m):
        label = m[1].replace("`", "")
        target = m[2]
        if not target.startswith(("https://", "http://", "#")):
            target = (
                "https://github.com/danialmazan/population_change_espext_madrid/blob/codex/integrate-official-source-audit/"
                + str((root / "docs" / target).resolve().relative_to(root))
            )
        return save(
            f'<link href="{escape(target, quote=True)}" color="#00677d">{escape(label)}</link>'
        )

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, s)
    s = re.sub(
        r"`([^`]+)`",
        lambda m: save('<font name="Mono" size="8">' + escape(m[1]) + "</font>"),
        s,
    )
    s = escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
    for i, value in enumerate(tokens):
        s = s.replace(f"ZZTOKEN{i}ZZ", value)
    return s


class Doc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in (
            "Section",
            "Subsection",
        ):
            key = "heading" + str(self.seq.nextf("heading"))
            level = 0 if flowable.style.name == "Section" else 1
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.getPlainText(), key, level=level)
            self.notify("TOCEntry", (level, flowable.getPlainText(), self.page, key))


def footer(c, doc):
    c.saveState()
    c.setFont("Body", 7)
    c.setFillColor(colors.HexColor("#5b7180"))
    c.drawString(45, 28, "Madrid demographic residual · Current audit · 2 October 2026")
    c.drawRightString(A4[0] - 45, 28, str(doc.page))
    c.restoreState()


output = root / "reports/current-audit.pdf"
doc = Doc(
    str(output),
    pagesize=A4,
    leftMargin=45,
    rightMargin=45,
    topMargin=48,
    bottomMargin=48,
    title="Madrid demographic residual — Current audit",
    author="Madrid demographic residual project",
)
doc.addPageTemplates(
    PageTemplate(
        id="body",
        frames=Frame(
            45,
            48,
            A4[0] - 90,
            A4[1] - 96,
            id="body",
            leftPadding=0,
            rightPadding=0,
            topPadding=0,
            bottomPadding=0,
        ),
        onPage=footer,
    )
)
flow = [
    Spacer(1, 45),
    Paragraph("Madrid demographic residual", styles["Cover"]),
    Paragraph(
        "Current research results and audit reports",
        ParagraphStyle("CoverSubtitle", parent=styles["Subsection"]),
    ),
    Paragraph("2 October 2026", styles["Text"]),
    Spacer(1, 24),
    Paragraph("Contents", styles["Subsection"]),
]
toc = TableOfContents()
toc.levelStyles = [styles["TOC1"], styles["TOC2"]]
flow.append(toc)
# Contents title has no outline level, so replace its style to keep TOC hierarchy valid.
flow[-2] = Paragraph(
    "Contents", ParagraphStyle("ContentsHeading", parent=styles["Subsection"])
)


def table_rows(lines):
    rows = []
    for line in lines:
        parts = [x.strip() for x in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r":?-+:?", p) for p in parts):
            continue
        rows.append(parts)
    return rows


for source in (
    "RESEARCH_RESULTS.md",
    "OFFICIAL_INTEGRATION.md",
    "RECONCILIATION.md",
    "SOURCE_AUDIT.md",
    "BOUNDARY_REVIEW.md",
    "HISTORICAL_PARENT_SOURCES.md",
):
    lines = (root / "docs" / source).read_text().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith("# "):
            flow.append(PageBreak())
            flow.append(Paragraph(inline(line[2:]), styles["Section"]))
            i += 1
            continue
        if line.startswith("## "):
            flow.append(Paragraph(inline(line[3:]), styles["Subsection"]))
            i += 1
            continue
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            flow.append(Preformatted("\n".join(code), styles["CodeBlock"]))
            i += 1
            continue
        if line.startswith("|"):
            raw = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw.append(lines[i])
                i += 1
            rows = table_rows(raw)
            n = len(rows[0])
            width = (A4[0] - 90) / n
            cells = [
                [Paragraph(inline(c), styles["Cell"]) for c in row] for row in rows
            ]
            t = Table(cells, colWidths=[width] * n, repeatRows=1, hAlign="LEFT")
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e9f1f4")),
                        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cddae0")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            flow.extend([t, Spacer(1, 10)])
            continue
        if line.startswith("- ") or re.match(r"^\d+\. ", line):
            match = re.match(r"^(\d+\.) (.*)", line)
            bullet = match[1] if match else "•"
            text = match[2] if match else line[2:]
            style = ParagraphStyle(
                "ListItem",
                parent=styles["Text"],
                leftIndent=13,
                firstLineIndent=-13,
                spaceAfter=5,
            )
            flow.append(Paragraph(escape(bullet) + " " + inline(text), style))
            i += 1
            continue
        parts = [line]
        i += 1
        while (
            i < len(lines)
            and lines[i].strip()
            and not re.match(r"^(#|\||```|- |\d+\. )", lines[i].strip())
        ):
            parts.append(lines[i].strip())
            i += 1
        flow.append(Paragraph(inline(" ".join(parts)), styles["Text"]))
doc.multiBuild(flow)
pdf = fitz.open(output)
print("PDF:", output, "pages:", len(pdf), "bytes:", output.stat().st_size)
for index in (0, 1, 2):
    if index < len(pdf):
        pdf[index].get_pixmap(matrix=fitz.Matrix(1.3, 1.3)).save(
            f"/tmp/audit-page-{index + 1}.png"
        )
text = " ".join(" ".join(p.get_text() for p in pdf).split())
for phrase in (
    "3,540,364",
    "3,527,924",
    "3,506,730",
    "304,657",
    "Official analysis remains gated",
    "Official source acquisition and preliminary feasibility audit",
):
    assert phrase in text, phrase
assert "448,625.595" in text
assert "34,170" in text
assert "2,343" in text
assert "historical" in text
print("Research results and audit figures verified in extracted PDF text.")
