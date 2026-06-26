"""
PDF report generator for top matched candidates.
Uses ReportLab to produce a clean, branded one-page summary.

Install:
    pip install reportlab --break-system-packages
"""

import os
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = "output/reports"


def generate_report(candidates: list[dict], query: str) -> str:
    """
    Generate a PDF report for the ranked candidate list.
    Returns the absolute path to the saved PDF.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        )
    except ImportError:
        raise RuntimeError("ReportLab not installed. Run: pip install reportlab --break-system-packages")

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename  = f"{OUTPUT_DIR}/candidates_{timestamp}.pdf"

    doc = SimpleDocTemplate(
        filename,
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm,  bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    BRAND = colors.HexColor("#1a6b5e")      # Teal accent
    GRAY  = colors.HexColor("#6b6b6b")
    LIGHT = colors.HexColor("#f4f4f0")

    title_style = ParagraphStyle("Title", parent=styles["Title"],
                                 fontSize=18, textColor=BRAND, spaceAfter=4)
    sub_style   = ParagraphStyle("Sub",   parent=styles["Normal"],
                                 fontSize=10, textColor=GRAY, spaceAfter=12)
    head_style  = ParagraphStyle("H2",    parent=styles["Heading2"],
                                 fontSize=13, textColor=BRAND, spaceBefore=12, spaceAfter=4)
    body_style  = ParagraphStyle("Body",  parent=styles["Normal"],
                                 fontSize=10, leading=14)
    label_style = ParagraphStyle("Label", parent=styles["Normal"],
                                 fontSize=9, textColor=GRAY, leading=12)

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("Resume Screening Report", title_style))
    story.append(Paragraph(
        f"Query: <b>{_safe(query[:120])}</b> &nbsp;·&nbsp; "
        f"Generated: {datetime.now().strftime('%d %b %Y %H:%M')} &nbsp;·&nbsp; "
        f"Top {len(candidates)} candidates",
        sub_style
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=BRAND, spaceAfter=8))

    # ── Score summary table ───────────────────────────────────────────────────
    table_data = [["Rank", "Name", "Role", "Skills matched", "Score"]]
    for i, c in enumerate(candidates, 1):
        skills_preview = ", ".join(c.get("skills", "").split(",")[:3])
        if len(c.get("skills", "").split(",")) > 3:
            skills_preview += "…"
        table_data.append([
            str(i),
            _safe(c.get("name") or "—"),
            _safe(c.get("job_role") or "—"),
            _safe(skills_preview),
            f"{c.get('score', 0):.1f}%",
        ])

    col_widths = [1.2*cm, 4*cm, 4*cm, 6*cm, 2*cm]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",  (0,0), (-1,0),  BRAND),
        ("TEXTCOLOR",   (0,0), (-1,0),  colors.white),
        ("FONTNAME",    (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LIGHT]),
        ("GRID",        (0,0), (-1,-1), 0.4, colors.HexColor("#d0d0d0")),
        ("ALIGN",       (0,0), (-1,-1), "LEFT"),
        ("ALIGN",       (-1,0), (-1,-1), "CENTER"),
        ("VALIGN",      (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING",  (0,0), (-1,-1), 5),
        ("BOTTOMPADDING",(0,0), (-1,-1), 5),
        ("LEFTPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 16))

    # ── Per-candidate detail ──────────────────────────────────────────────────
    for i, c in enumerate(candidates, 1):
        story.append(Paragraph(f"{i}. {_safe(c.get('name') or 'Unknown')}", head_style))

        # Contact row
        contact_parts = []
        if c.get("email"):  contact_parts.append(f"✉ {c['email']}")
        if c.get("phone"):  contact_parts.append(f"☎ {c['phone']}")
        if c.get("location"): contact_parts.append(f"📍 {c['location']}")
        if contact_parts:
            story.append(Paragraph(" &nbsp;|&nbsp; ".join(contact_parts), label_style))

        # Score bar (text representation)
        score = c.get("score", 0)
        bar   = "█" * int(score / 5) + "░" * (20 - int(score / 5))
        story.append(Paragraph(
            f"<font color='#{BRAND.hexval()[2:]}'>Match score: {score:.1f}%</font> "
            f"<font size='7'>{bar}</font>",
            body_style
        ))

        # Match reasons
        reasons = c.get("match_reasons", [])
        if reasons:
            story.append(Paragraph("Why matched: " + " · ".join(reasons), label_style))

        # Key fields
        for label, key in [
            ("Role",       "job_role"),
            ("Skills",     "skills"),
            ("Experience", "experience_summary"),
            ("Education",  "education"),
        ]:
            val = c.get(key, "")
            if val:
                story.append(Paragraph(f"<b>{label}:</b> {_safe(str(val)[:300])}", body_style))

        story.append(HRFlowable(width="100%", thickness=0.4,
                                color=colors.HexColor("#cccccc"), spaceAfter=4))

    doc.build(story)
    return os.path.abspath(filename)


def _safe(text: str) -> str:
    """Escape XML special chars for ReportLab Paragraph."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")