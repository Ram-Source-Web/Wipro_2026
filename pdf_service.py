import os
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable

def generate_ats_report_pdf(scan_data, breakdown_data):
    """
    Generates a professional, print-ready ATS Audit & Optimized Resume Report PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#0F172A'),
        fontName='Helvetica-Bold'
    )
    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Heading2'],
        fontSize=12,
        leading=16,
        textColor=colors.HexColor('#1E293B'),
        fontName='Helvetica-Bold',
        spaceBefore=10,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )
    callout_style = ParagraphStyle(
        'Callout',
        parent=styles['Normal'],
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#065F46')
    )

    elements = []

    # Header
    elements.append(Paragraph(f"SkillBoost ATS — Comprehensive Audit Report", title_style))
    elements.append(Paragraph(f"Candidate: <b>{scan_data.get('candidate_name', 'Candidate')}</b> | Date: {scan_data.get('created_at', '')[:10]}", body_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#0284C7'), spaceBefore=2, spaceAfter=10))

    # Score Cards Table
    score = scan_data.get('score', 0)
    quality = breakdown_data.get('resume_quality_score', score)
    formatting = breakdown_data.get('formatting_score', score)

    score_data = [
        [
            Paragraph(f"<b>Overall ATS Score</b><br/><font size='16' color='#0284C7'><b>{score}%</b></font>", body_style),
            Paragraph(f"<b>Content Quality</b><br/><font size='16' color='#059669'><b>{quality}%</b></font>", body_style),
            Paragraph(f"<b>Format & Structure</b><br/><font size='16' color='#7C3AED'><b>{formatting}%</b></font>", body_style)
        ]
    ]
    score_table = Table(score_data, colWidths=[180, 180, 180])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8FAFC')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('ALIGN', (0,0), (-1,-1), 'CENTER')
    ]))
    elements.append(score_table)
    elements.append(Spacer(1, 14))

    # Executive Summary Section
    elements.append(Paragraph("1. AI-Generated Professional Summary", h2_style))
    ai_summary = breakdown_data.get('ai_summary') or breakdown_data.get('summary_ai') or "Experienced software professional."
    elements.append(Paragraph(f"<i>{ai_summary}</i>", body_style))
    elements.append(Spacer(1, 10))

    # Skills Breakdown
    elements.append(Paragraph("2. Skills Alignment & Technical Taxonomy", h2_style))
    detected = scan_data.get('skills_found', '')
    missing = scan_data.get('missing_skills', '')
    
    skills_table_data = [
        [Paragraph("<b>Detected Core Competencies:</b>", body_style), Paragraph(detected or "None flagged", body_style)],
        [Paragraph("<b>High-Value Keyword Recommendations:</b>", body_style), Paragraph(missing or "Complete alignment", callout_style)]
    ]
    skills_table = Table(skills_table_data, colWidths=[180, 360])
    skills_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F1F5F9')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(skills_table)
    elements.append(Spacer(1, 12))

    # Bullet Point Transformation
    elements.append(Paragraph("3. High-Impact Resume Rewrite (Before vs After)", h2_style))
    before_b = breakdown_data.get('before_bullet', 'Worked on software tasks.')
    after_b = breakdown_data.get('after_bullet', 'Engineered robust software solutions reducing defects by 45%.')
    
    bullet_data = [
        [Paragraph("<font color='#DC2626'><b>❌ Original / Weak Phrasing:</b></font><br/>" + before_b, body_style)],
        [Paragraph("<font color='#059669'><b>✅ ATS-Optimized High Impact Bullet:</b></font><br/>" + after_b, body_style)]
    ]
    bullet_table = Table(bullet_data, colWidths=[540])
    bullet_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,0), colors.HexColor('#FEF2F2')),
        ('BACKGROUND', (0,1), (0,1), colors.HexColor('#ECFDF5')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#CBD5E1')),
        ('INNERGRID', (0,0), (-1,-1), 1, colors.HexColor('#E2E8F0')),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(bullet_table)
    elements.append(Spacer(1, 12))

    # Top Interview Questions
    questions = breakdown_data.get('interview_questions', [])
    if questions:
        elements.append(Paragraph("4. Targeted Technical Interview Prep", h2_style))
        for idx, q in enumerate(questions[:4], 1):
            elements.append(Paragraph(f"<b>Q{idx}.</b> {q}", body_style))
            elements.append(Spacer(1, 3))

    elements.append(Spacer(1, 16))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#94A3B8'), spaceBefore=4, spaceAfter=8))
    elements.append(Paragraph("Generated by SkillBoost ATS Platform | Ram Bandaru Engineering | skillboost-ats.onrender.com", ParagraphStyle('Foot', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#94A3B8'), alignment=1)))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()
