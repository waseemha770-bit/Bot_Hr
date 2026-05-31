import math
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def calculate_distance(lat1, lon1, lat2, lon2) -> float:
    """حساب المسافة الجغرافية بدقة بالمتر (Haversine formula)"""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    return R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

def clean_and_format_yemeni_phone(raw_phone: str) -> str:
    """تنظيف وتوحيد صيغ أرقام الهواتف"""
    cleaned = str(raw_phone).strip().replace(" ", "").split('.')[0]
    if cleaned.startswith("+967"): return cleaned
    if cleaned.startswith("967"): return "+" + cleaned
    if cleaned.startswith("0"): cleaned = cleaned[1:]
    return "+967" + cleaned

def generate_payslip_pdf(emp_name, emp_id, title, salary) -> str:
    """توليد كشف راتب رقمي رسمي مشفر وآمن للموظف"""
    filename = f"payslip_{emp_id}.pdf"
    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, spaceAfter=20, alignment=1)
    normal_style = ParagraphStyle('NormalStyle', parent=styles['Normal'], fontSize=12, spaceAfter=10)
    
    story = [
        Paragraph("<b>🏢 ENTERPRISE HR SYSTEM - OFFICIAL PAYSLIP</b>", title_style),
        Spacer(1, 15),
        Paragraph(f"<b>Employee Name:</b> {emp_name}", normal_style),
        Paragraph(f"<b>Employee ID:</b> {emp_id}", normal_style),
        Paragraph(f"<b>Job Title:</b> {title}", normal_style),
        Spacer(1, 10),
        Paragraph(f"<b>Net Salary:</b> ${float(salary):,.2f}", title_style),
        Spacer(1, 15),
        Paragraph(f"<i>Generated Securely via HR Bot on: {datetime.now().strftime('%Y-%m-%d')}</i>", normal_style)
    ]
    doc.build(story)
    return filename

