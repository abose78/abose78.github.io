"""Build index.html from Arindam_Bose_Resume.docx.

Runs in GitHub Actions on every push. Reads the Word file, finds the
sections by their headings, and fills build/template.html.
"""
import html, json, re, sys
from pathlib import Path
from docx import Document

ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "Arindam_Bose_Resume.docx"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site"

SECTIONS = {
    "summary": ("professional summary", "summary", "profile", "about"),
    "skills": ("technical skills", "skills", "core skills", "top skills"),
    "experience": ("experience", "professional experience", "work experience"),
    "education": ("education", "education & certifications", "certifications"),
}
e = html.escape


def section_of(text):
    t = text.strip().lower().rstrip(":")
    for key, names in SECTIONS.items():
        if t in names:
            return key
    return None


def is_bullet(p):
    if p.style is not None and "list" in p.style.name.lower():
        return True
    pPr = p._p.pPr
    return pPr is not None and pPr.numPr is not None


def all_bold(p):
    runs = [r for r in p.runs if r.text.strip()]
    return bool(runs) and all(r.bold for r in runs)


def split_title(text):
    """'Title<TAB>Date' -> (title, date)."""
    if "\t" in text:
        a, b = text.rsplit("\t", 1)
        return a.strip(), b.strip()
    m = re.search(r"\s{2,}(\S.*)$", text)
    return (text[: m.start()].strip(), m.group(1).strip()) if m else (text.strip(), "")


def contact_html(items):
    out = []
    for c in items:
        c = c.strip()
        if "@" in c:
            out.append(f'<li><a href="mailto:{e(c)}">{e(c)}</a></li>')
        elif re.fullmatch(r"[\d\s().+-]{7,}", c):
            digits = re.sub(r"\D", "", c)
            out.append(f'<li><a href="tel:+1{digits[-10:]}">{e(c)}</a></li>')
        elif "linkedin" in c.lower() or "github" in c.lower() or c.startswith("http"):
            url = c if c.startswith("http") else "https://www." + c.removeprefix("www.")
            label = "LinkedIn" if "linkedin" in c.lower() else ("GitHub" if "github" in c.lower() else c)
            out.append(f'<li><a href="{e(url)}" target="_blank" rel="noopener">{label}</a></li>')
        else:
            out.append(f"<li>{e(c)}</li>")
    return "".join(out)


def entries_html(entries):
    parts = []
    for en in entries:
        bl = "".join(f"<li>{e(b)}</li>" for b in en["bullets"])
        parts.append(
            f'<article class="job"><header><div><h3>{e(en["title"])}</h3>'
            f'<p class="org">{e(en["org"])}</p></div><time>{e(en["date"])}</time></header>'
            f'{"<ul>" + bl + "</ul>" if bl else ""}</article>'
        )
    return "".join(parts)


def main():
    paras = [p for p in Document(DOCX).paragraphs if p.text.strip()]
    header, cur, data = [], None, {k: [] for k in SECTIONS}
    for p in paras:
        sec = section_of(p.text)
        if sec:
            cur = sec
            continue
        (data[cur] if cur else header).append(p)

    if len(header) < 2 or not data["experience"]:
        sys.exit("Could not find name/title or the Experience section in the Word file.")
    name = header[0].text.strip()
    title = header[1].text.strip() if len(header) > 2 else ""
    contact_line = header[-1].text
    contact = [c for c in re.split(r"\s*[|•·]\s*", contact_line) if c.strip()]

    summary = " ".join(p.text.strip() for p in data["summary"])

    skills = []
    for p in data["skills"]:
        t = p.text.strip()
        if ":" in t:
            k, v = t.split(":", 1)
            skills.append((k.strip(), v.strip()))
        else:
            skills.append(("", t))
    skills_html = "".join(
        f'<div class="skill"><dt>{e(k)}</dt><dd>{e(v)}</dd></div>' for k, v in skills
    )

    def parse_entries(items):
        entries = []
        for p in items:
            t = p.text.strip()
            if is_bullet(p):
                if entries:
                    entries[-1]["bullets"].append(t)
            elif all_bold(p) or "\t" in p.text:
                ti, dt = split_title(p.text)
                entries.append({"title": ti, "date": dt, "org": "", "bullets": []})
            elif entries and not entries[-1]["org"]:
                entries[-1]["org"] = t.replace(" — ", " · ")
            elif entries:
                entries[-1]["bullets"].append(t)
        return entries

    jobs = parse_entries(data["experience"])
    edu = parse_entries(data["education"])

    stats_file = Path(__file__).with_name("stats.json")
    stats = json.loads(stats_file.read_text()) if stats_file.exists() else []
    stats_html = (
        '<div class="stats" aria-label="Highlights">'
        + "".join(f'<div class="stat"><b>{e(s["value"])}</b><span>{e(s["label"])}</span></div>' for s in stats)
        + "</div>"
        if stats else ""
    )

    page = Path(__file__).with_name("template.html").read_text()
    for k, v in {
        "{{NAME}}": e(name), "{{TITLE}}": e(title), "{{SUMMARY}}": e(summary),
        "{{CONTACT}}": contact_html(contact), "{{SKILLS}}": skills_html,
        "{{JOBS}}": entries_html(jobs), "{{EDU}}": entries_html(edu), "{{STATS}}": stats_html,
    }.items():
        page = page.replace(k, v)
    page = page.replace("© 2026", "© " + __import__("datetime").date.today().strftime("%Y"))

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "index.html").write_text(page)
    (OUT / DOCX.name).write_bytes(DOCX.read_bytes())
    (OUT / ".nojekyll").write_text("")
    print(f"Built {OUT/'index.html'}: {len(jobs)} jobs, {len(skills)} skill rows, {len(edu)} education entries")


if __name__ == "__main__":
    main()
