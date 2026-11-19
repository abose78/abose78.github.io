"""Build index.html from Arindam_Bose_Resume.docx.

Runs in GitHub Actions on every push. Reads the Word file, finds the
sections by their headings, and fills build/template.html.
"""
import html, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import resume_docx

ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "Arindam_Bose_Resume.docx"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "_site"

e = html.escape


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
    r = resume_docx.read(DOCX)
    name, title, contact, summary = r["name"], r["title"], r["contact"], r["summary"]
    skills_html = "".join(
        f'<div class="skill"><dt>{e(k)}</dt><dd>{e(v)}</dd></div>' for k, v in r["skills"]
    )
    jobs, edu, skills = r["experience"], r["education"], r["skills"]
    for en in jobs + edu:
        en["org"] = en["org"].replace(" — ", " · ")

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
