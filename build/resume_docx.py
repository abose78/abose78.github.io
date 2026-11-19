"""Read and write the resume Word file.

Resume data shape:
  {"name", "title", "contact": [..], "summary",
   "skills": [(label, text)],
   "experience": [{"title", "org", "date", "bullets": [..]}],
   "education":  [{"title", "org", "date", "bullets": [..]}]}
"""
import re
import sys

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

SECTIONS = {
    "summary": ("professional summary", "summary", "profile", "about"),
    "skills": ("technical skills", "skills", "core skills", "top skills"),
    "experience": ("experience", "professional experience", "work experience"),
    "education": ("education", "education & certifications", "certifications"),
}
HEADINGS = {"summary": "Professional Summary", "skills": "Technical Skills",
            "experience": "Experience", "education": "Education"}


def _section_of(text):
    t = text.strip().lower().rstrip(":")
    for key, names in SECTIONS.items():
        if t in names:
            return key
    return None


def _is_bullet(p):
    if p.style is not None and "list" in p.style.name.lower():
        return True
    pPr = p._p.pPr
    return pPr is not None and pPr.numPr is not None


def _all_bold(p):
    runs = [r for r in p.runs if r.text.strip()]
    return bool(runs) and all(r.bold for r in runs)


def _split_title(text):
    if "\t" in text:
        a, b = text.rsplit("\t", 1)
        return a.strip(), b.strip()
    m = re.search(r"\s{2,}(\S.*)$", text)
    return (text[: m.start()].strip(), m.group(1).strip()) if m else (text.strip(), "")


def _entries(items):
    entries = []
    for p in items:
        t = p.text.strip()
        if _is_bullet(p):
            if entries:
                entries[-1]["bullets"].append(t)
        elif _all_bold(p) or "\t" in p.text:
            ti, dt = _split_title(p.text)
            entries.append({"title": ti, "date": dt, "org": "", "bullets": []})
        elif entries and not entries[-1]["org"]:
            entries[-1]["org"] = t
        elif entries:
            entries[-1]["bullets"].append(t)
    return entries


def read(path):
    paras = [p for p in Document(path).paragraphs if p.text.strip()]
    header, cur, data = [], None, {k: [] for k in SECTIONS}
    for p in paras:
        sec = _section_of(p.text)
        if sec:
            cur = sec
            continue
        (data[cur] if cur else header).append(p)
    if len(header) < 2 or not data["experience"]:
        sys.exit("Could not find the name/title or the Experience section in the Word file.")
    skills = []
    for p in data["skills"]:
        t = p.text.strip()
        k, v = t.split(":", 1) if ":" in t else ("", t)
        skills.append((k.strip(), v.strip()))
    return {
        "name": header[0].text.strip(),
        "title": header[1].text.strip() if len(header) > 2 else "",
        "contact": [c.strip() for c in re.split(r"\s*[|•·]\s*", header[-1].text) if c.strip()],
        "summary": " ".join(p.text.strip() for p in data["summary"]),
        "skills": skills,
        "experience": _entries(data["experience"]),
        "education": _entries(data["education"]),
    }


def write(r, path):
    d = Document()
    s = d.sections[0]
    s.left_margin = s.right_margin = Inches(0.7)
    s.top_margin = s.bottom_margin = Inches(0.6)
    st = d.styles["Normal"]
    st.font.name = "Calibri"
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Calibri")

    def para(text="", bold=False, size=None, align=None, after=2, color=None):
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(after)
        p.paragraph_format.space_before = Pt(0)
        if align is not None:
            p.alignment = align
        if text:
            run = p.add_run(text)
            run.bold = bold
            if size:
                run.font.size = Pt(size)
            if color:
                run.font.color.rgb = RGBColor.from_string(color)
        return p

    def heading(t):
        p = para(t.upper(), bold=True, size=11.5, after=3, color="1F3A5F")
        p.paragraph_format.space_before = Pt(8)
        pPr = p._p.get_or_add_pPr()
        b = OxmlElement("w:pBdr")
        bt = OxmlElement("w:bottom")
        for k, v in [("val", "single"), ("sz", "6"), ("space", "1"), ("color", "1F3A5F")]:
            bt.set(qn("w:" + k), v)
        b.append(bt)
        pPr.append(b)

    def entry(en):
        p = para(after=0)
        p.paragraph_format.tab_stops.add_tab_stop(Inches(7.1), WD_TAB_ALIGNMENT.RIGHT)
        p.paragraph_format.space_before = Pt(4)
        p.add_run(en["title"]).bold = True
        p.add_run("\t" + en["date"]).bold = True
        if en["org"]:
            para(en["org"], after=1, color="444444")
        for b in en["bullets"]:
            bp = d.add_paragraph(b, style="List Bullet")
            bp.paragraph_format.space_after = Pt(1)

    para(r["name"], bold=True, size=20, align=WD_ALIGN_PARAGRAPH.CENTER, after=0)
    if r["title"]:
        para(r["title"], size=12, align=WD_ALIGN_PARAGRAPH.CENTER, after=1, color="1F3A5F")
    para(" | ".join(r["contact"]), size=10, align=WD_ALIGN_PARAGRAPH.CENTER, after=4)
    if r["summary"]:
        heading(HEADINGS["summary"])
        para(r["summary"], after=2)
    if r["skills"]:
        heading(HEADINGS["skills"])
        for k, v in r["skills"]:
            p = para(after=1)
            if k:
                p.add_run(k + ": ").bold = True
            p.add_run(v)
    heading(HEADINGS["experience"])
    for en in r["experience"]:
        entry(en)
    if r["education"]:
        heading(HEADINGS["education"])
        for en in r["education"]:
            entry(en)
    d.save(path)
