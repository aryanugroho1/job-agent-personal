"""
run_initial.py
Setup module to parse master_cv.md into structured master_cv.json
"""
import sys
import re
import json
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def parse_master_cv(md_path: Path) -> dict:
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()

    data = {
        "candidate": {
            "name": "ARYA MAULANA NUGROHO, ITIL®",
            "title_placeholder": "{{TARGET_ROLE_TITLE}}",
            "location": "Ota-ku, Tokyo, Japan",
            "phone": "+817090934764",
            "email": "arya.nugroho.works@gmail.com",
            "linkedin": "https://linkedin.com/in/aryanugroho1/"
        },
        "summary": {
            "placeholder": "{{TAILORED_SUMMARY}}",
            "baseline": (
                "Over 10 years of cross-functional expertise bridging Radio Access Networks "
                "(4G/5G NR SA/NSA, Open RAN, Non-RT RIC) with Enterprise Data Engineering and Applied AI/ML workflows. "
                "Proven track record in orchestrating autonomous network features, delivering production-grade rApps, "
                "and designing scalable big data pipelines supporting over 10 million subscribers. "
                "Awarded Rakuten Group MVP for spearheading an AI-driven energy-saving solution that achieved a 15% reduction "
                "in network power consumption while maintaining strict SLA and KPI stability."
            )
        },
        "competencies": {},
        "experience": [],
        "education": [],
        "certifications_awards": []
    }

    # Extract Core Competencies
    comp_section = re.search(r"## CORE COMPETENCIES & TECHNICAL SKILLS\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if comp_section:
        comp_lines = comp_section.group(1).strip().split("\n")
        for line in comp_lines:
            line = line.strip()
            if line.startswith("- **"):
                match = re.match(r"- \*\*(.*?):\*\*\s*(.*)", line)
                if match:
                    cat = match.group(1).strip()
                    skills = [s.strip() for s in match.group(2).split(",") if s.strip()]
                    data["competencies"][cat] = skills

    # Extract Professional Experience
    exp_section = re.search(r"## PROFESSIONAL EXPERIENCE\s*\n(.*?)(?=\n## EDUCATION|\Z)", content, re.DOTALL)
    if exp_section:
        raw_exp = exp_section.group(1)
        job_blocks = re.split(r"\n(?=### \*\*)", raw_exp)
        for block in job_blocks:
            if not block.strip():
                continue
            header_match = re.search(r"### \*\*(.*?)\*\*\s*\|\s*(.*?)\n\*\*(.*?)\*\*\s*\n\*\((.*?)\)\*", block)
            if header_match:
                company = header_match.group(1).strip()
                loc = header_match.group(2).strip()
                role = header_match.group(3).strip()
                period = header_match.group(4).strip()
                bullets = [
                    re.sub(r"^-\s*", "", b.strip())
                    for b in block.split("\n")
                    if b.strip().startswith("- ")
                ]
                data["experience"].append({
                    "company": company,
                    "location": loc,
                    "role": role,
                    "period": period,
                    "highlights": bullets
                })

    # Extract Education
    edu_section = re.search(r"## EDUCATION\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if edu_section:
        edu_lines = edu_section.group(1).strip().split("\n")
        current_edu = None
        for line in edu_lines:
            line = line.strip()
            if line.startswith("- **"):
                current_edu = {"degree": line.replace("- **", "").replace("**", "").strip()}
            elif current_edu and line:
                current_edu["institution"] = line
                data["education"].append(current_edu)
                current_edu = None

    # Extract Certifications & Awards
    cert_section = re.search(r"## CERTIFICATIONS & AWARDS\s*\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
    if cert_section:
        for line in cert_section.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- "):
                data["certifications_awards"].append(line[2:].strip())

    return data

def main():
    md_file = Path("master_data/master_cv.md")
    json_file = Path("master_data/master_cv.json")
    
    if not md_file.exists():
        print(f"❌ File {md_file} tidak ditemukan!")
        return

    parsed = parse_master_cv(md_file)
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)

    print(f"✅ Master CV berhasil diparsing dan disimpan ke {json_file}")
    print(f"   - Total posisi kerja: {len(parsed['experience'])}")
    print(f"   - Kategori kompetensi: {len(parsed['competencies'])}")
    print(f"   - Sertifikasi & penghargaan: {len(parsed['certifications_awards'])}")

if __name__ == "__main__":
    main()
