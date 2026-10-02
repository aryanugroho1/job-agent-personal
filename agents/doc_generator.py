import os
import subprocess
from pathlib import Path
from docxtpl import DocxTemplate

TEMPLATES_DIR = Path("templates")
GENERATED_DIR = Path("generated_cvs")

def ensure_directories():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

def generate_custom_cv(
    master_cv: dict,
    tailored_title: str,
    tailored_summary: str,
    company_name: str,
    job_id: str,
    template_name: str = "cv_template.docx"
) -> Path:
    """
    Renders docx template with tailored resume information,
    then converts to PDF using headless LibreOffice or Word CLI.
    Returns the absolute path to the generated PDF.
    """
    ensure_directories()
    
    template_path = TEMPLATES_DIR / template_name
    if not template_path.exists():
        # Create a clean fallback template if not existing
        from docx import Document
        doc = Document()
        doc.add_heading("ARYA MAULANA NUGROHO, ITIL®", level=1)
        doc.add_paragraph("{{ target_role_title }}")
        doc.add_paragraph("Tokyo, Japan | +817090934764 | arya.nugroho.works@gmail.com | linkedin.com/in/aryanugroho1/")
        doc.add_heading("Professional Summary", level=2)
        doc.add_paragraph("{{ tailored_summary }}")
        doc.add_heading("Experience", level=2)
        doc.add_paragraph("{% for exp in experience %}")
        doc.add_paragraph("{{ exp.company }} - {{ exp.role }} ({{ exp.period }})")
        doc.add_paragraph("{% for h in exp.highlights %}")
        doc.add_paragraph("• {{ h }}")
        doc.add_paragraph("{% endfor %}")
        doc.add_paragraph("{% endfor %}")
        doc.save(template_path)

    doc = DocxTemplate(template_path)

    # Sanitize file safe company name
    safe_company = "".join(c for c in company_name if c.isalnum() or c in (" ", "_", "-")).strip()
    safe_company = safe_company.replace(" ", "_")

    out_docx_path = GENERATED_DIR / f"{safe_company}_{job_id}.docx"
    out_pdf_path = GENERATED_DIR / f"{safe_company}_{job_id}.pdf"

    context = {
        "candidate_name": master_cv["candidate"]["name"],
        "target_role_title": tailored_title,
        "tailored_summary": tailored_summary,
        "candidate": master_cv["candidate"],
        "competencies": master_cv.get("competencies", {}),
        "experience": master_cv.get("experience", []),
        "education": master_cv.get("education", []),
        "certifications_awards": master_cv.get("certifications_awards", [])
    }

    doc.render(context)
    doc.save(out_docx_path)

    # Convert to PDF
    convert_docx_to_pdf(out_docx_path, GENERATED_DIR)

    return out_pdf_path

def convert_docx_to_pdf(docx_path: Path, output_dir: Path):
    """
    Converts docx to PDF via libreoffice headless or docx2pdf.
    """
    # 1. Try LibreOffice CLI (standard on Ubuntu Server & Windows if installed)
    try:
        cmd = [
            "libreoffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_dir),
            str(docx_path)
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode == 0:
            return
    except Exception:
        pass

    # 2. Try 'soffice' alias for LibreOffice
    try:
        cmd = [
            "soffice",
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(output_dir),
            str(docx_path)
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
        if result.returncode == 0:
            return
    except Exception:
        pass

    print(f"[Doc Generator Warning] LibreOffice CLI not available for direct PDF conversion of {docx_path}. Retaining DOCX.")
