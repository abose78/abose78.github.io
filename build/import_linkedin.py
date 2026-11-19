"""Update Arindam_Bose_Resume.docx from a LinkedIn export.

Put one of these in the linkedin/ folder:
  - Profile.pdf  (LinkedIn profile > More > Save to PDF)
  - the LinkedIn data export .zip, or its Positions.csv / Education.csv

Taken from LinkedIn: Experience and Education.
Kept from the current Word file: name, title line, contact line, summary,
technical skills, and any education entry that LinkedIn does not list
(for example a certificate program).
Settings live in build/linkedin_import.json.
"""
import csv, html, io, json, re, sys, zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import resume_docx

ROOT = Path(__file__).resolve().parent.parent
DOCX = ROOT / "Arindam_Bose_Resume.docx"
IN_DIR = ROOT / "linkedin"
CFG_FILE = Path(__file__).with_name("linkedin_import.json")

MONTHS = {m: m[:3] for m in ["January", "February", "March", "April", "May", "June", "July",
                             "August", "September", "October", "November", "December"]}
DATE_RE = re.compile(
    r"^((?:[A-Z][a-z]+ )?\d{4})\s*-\s*((?:[A-Z][a-z]+ )?\d{4}|Present)(?:\s*\(.*\))?$")
DURATION_RE = re.compile(r"^\d+ (years?|months?)( \d+ months?)?$")


def short_date(d):
    d = d.strip()
    for full, ab in MONTHS.items():
        d = d.replace(full, ab)
    return d


def clean(t):
    return html.unescape(re.sub(r"\s+", " ", t)).strip()


def join_lines(lines):
    out = ""
    for ln in lines:
        ln = ln.strip()
        if not out:
            out = ln
        elif out.endswith(("-", "/")) and not out.endswith(" -"):
            out += ln
        else:
            out += " " + ln
    return clean(out)


# ---------------------------------------------------------------- PDF
def lines_from_pdf(path):
    import pymupdf
    doc = pymupdf.open(path)
    out = []
    for page in doc:
        width = page.rect.width
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                text = "".join(s["text"] for s in l["spans"]).replace("\xa0", " ").strip()
                if not text or l["bbox"][0] < width * 0.3:   # skip left sidebar
                    continue
                s = l["spans"][0]
                size = round(s["size"], 1)
                if size < 9.5 and text.startswith("Page "):
                    continue
                grey = s["color"] not in (0, 1644825) and size < 12.5
                out.append({"t": text, "size": size, "grey": grey})
    return out


def parse_pdf(path):
    L = lines_from_pdf(path)
    big = sorted({l["size"] for l in L}, reverse=True)
    section_size = next(s for s in big if s < 20)          # "Summary", "Experience"...
    sec, rows = None, {"experience": [], "education": []}
    for l in L:
        if l["size"] == section_size:
            sec = {"experience": "experience", "education": "education"}.get(l["t"].lower())
            continue
        if sec:
            rows[sec].append(l)

    # Experience: company (largest), title (next), date, location (grey), body.
    exp = rows["experience"]
    if not exp:
        sys.exit("No Experience section found in the LinkedIn PDF.")
    company_size = max(l["size"] for l in exp)
    title_size = max(l["size"] for l in exp if l["size"] < company_size)
    roles, company = [], ""
    for l in exp:
        t = l["t"]
        if l["size"] == company_size:
            company = t
        elif l["size"] == title_size:
            roles.append({"company": company, "title": t, "date": "", "location": "",
                          "groups": []})
        elif not roles:
            continue
        elif DURATION_RE.match(t):
            continue
        elif not roles[-1]["date"] and DATE_RE.match(t):
            a, b = DATE_RE.match(t).groups()
            roles[-1]["date"] = f"{short_date(a)} – {short_date(b)}"
        elif l["grey"] and not roles[-1]["location"]:
            roles[-1]["location"] = t
        elif t.lower().startswith("client:"):
            roles[-1]["groups"].append({"client": t.split(":", 1)[1].strip(), "bullets": []})
        else:
            if not roles[-1]["groups"]:
                roles[-1]["groups"].append({"client": "", "bullets": []})
            g = roles[-1]["groups"][-1]
            if t.startswith(("•", "-", "–", "*")) or not g["bullets"]:
                g["bullets"].append([t.lstrip("•-–* ").strip()])
            else:
                g["bullets"][-1].append(t)
    flat = []
    for r in roles:
        clients = []
        for g in r["groups"]:
            if g["client"] and g["client"] not in clients:
                clients.append(g["client"])
        bullets = [join_lines(b) for g in r["groups"] for b in g["bullets"] if join_lines(b)]
        flat.append({"company": r["company"], "title": r["title"], "date": r["date"],
                     "location": r["location"], "client": "; ".join(clients), "bullets": bullets})

    # Education: school (larger, may wrap), then "Degree · (1998 - 2002)".
    edu_rows, schools = rows["education"], []
    if edu_rows:
        school_size = max(l["size"] for l in edu_rows)
        for l in edu_rows:
            if l["size"] == school_size:
                if schools and not schools[-1]["degree"]:
                    schools[-1]["school"] += " " + l["t"]
                else:
                    schools.append({"school": l["t"], "degree": "", "date": ""})
            elif schools:
                m = re.match(r"^(.*?)\s*·\s*\((.*)\)\s*$", l["t"])
                deg, dt = (m.group(1), m.group(2)) if m else (l["t"], "")
                schools[-1]["degree"] = (schools[-1]["degree"] + " " + deg).strip()
                # Resumes usually show the graduation year only.
                schools[-1]["date"] = short_date(dt.split("-")[-1].strip()) if dt else ""
    return flat, schools


# ---------------------------------------------------------------- CSV / ZIP
def _csv_rows(text):
    # LinkedIn CSVs sometimes start with "Notes:" lines before the header.
    lines = text.splitlines()
    for i, ln in enumerate(lines):
        if "," in ln and not ln.lower().startswith("notes"):
            return list(csv.DictReader(io.StringIO("\n".join(lines[i:]))))
    return []


def _get(row, *names):
    low = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for n in names:
        if low.get(n.lower()):
            return low[n.lower()]
    return ""


def _csv_date(d):
    d = d.strip()
    if not d:
        return "Present"
    m = re.match(r"^([A-Z][a-z]{2})\w* (\d{4})$", d)
    return f"{m.group(1)} {m.group(2)}" if m else d


def parse_csv_files(files):
    flat, schools = [], []
    pos = next((t for n, t in files.items() if n.lower().endswith("positions.csv")), None)
    if pos is None:
        sys.exit("Positions.csv not found in the LinkedIn export.")
    for row in _csv_rows(pos):
        desc = _get(row, "Description")
        parts = [p for p in re.split(r"\n+|\s*•\s*", desc) if p.strip()]
        client, bullets = "", []
        for p in parts:
            if p.lower().startswith("client:"):
                client = p.split(":", 1)[1].strip()
            else:
                bullets.append(clean(p.lstrip("-–* ")))
        flat.append({"company": _get(row, "Company Name"), "title": _get(row, "Title"),
                     "date": f"{_csv_date(_get(row, 'Started On'))} – {_csv_date(_get(row, 'Finished On'))}",
                     "location": _get(row, "Location"), "client": client, "bullets": bullets})
    edu = next((t for n, t in files.items() if n.lower().endswith("education.csv")), None)
    for row in _csv_rows(edu or ""):
        s, e_ = _get(row, "Start Date"), _get(row, "End Date")
        schools.append({"school": _get(row, "School Name"),
                        "degree": ", ".join(x for x in [_get(row, "Degree Name"), _get(row, "Notes")] if x),
                        "date": e_ or s})
    return flat, schools


# ---------------------------------------------------------------- merge
def _year_span(dates):
    starts, ends = [], []
    for d in dates:
        if "–" in d:
            a, b = [x.strip() for x in d.split("–", 1)]
            starts.append(a)
            ends.append(b)
    key = lambda x: (9999, 12) if x == "Present" else (
        int(x[-4:]), list(MONTHS.values()).index(x[:3]) + 1 if x[:3] in MONTHS.values() else 1)
    if not starts:
        return dates[0] if dates else ""
    return f"{min(starts, key=key)} – {max(ends, key=key)}"


def merge_roles(flat):
    """Combine consecutive roles at the same company for the same client."""
    merged = []
    for r in flat:
        prev = merged[-1] if merged else None
        same_client = prev and prev["company"] == r["company"] and (
            prev["client"] == r["client"] or (not r["bullets"] and not prev["_bullets_by_title"][-1][1]
                                              and prev["client"].split("/")[0].strip() == r["client"].split("/")[0].strip()))
        if same_client:
            if r["title"] not in prev["titles"]:
                prev["titles"].append(r["title"])
            prev["dates"].append(r["date"])
            prev["bullets"] += [b for b in r["bullets"] if b not in prev["bullets"]]
            prev["_bullets_by_title"].append((r["title"], r["bullets"]))
        else:
            merged.append({**r, "titles": [r["title"]], "dates": [r["date"]],
                           "_bullets_by_title": [(r["title"], r["bullets"])]})
    return merged


def to_entries(flat, cfg):
    out = []
    for r in merge_roles(flat):
        org = [r["company"]]
        if r["client"] and cfg.get("show_client", True):
            org.append("Client: " + r["client"])
        if r["location"]:
            org.append(r["location"])
        out.append({"title": " / ".join(r["titles"]), "org": " — ".join(org),
                    "date": _year_span(r["dates"]), "bullets": r["bullets"]})
    return out


def _school_key(s):
    return " ".join(re.findall(r"[a-z]+", s.lower())[:2])


def main():
    cfg = json.loads(CFG_FILE.read_text()) if CFG_FILE.exists() else {}
    src = sys.argv[1] if len(sys.argv) > 1 else None
    files = sorted(IN_DIR.glob("*")) if IN_DIR.exists() else []
    if src:
        files = [Path(src)]
    zips = [f for f in files if f.suffix.lower() == ".zip"]
    csvs = [f for f in files if f.suffix.lower() == ".csv"]
    pdfs = [f for f in files if f.suffix.lower() == ".pdf"]
    if zips:
        with zipfile.ZipFile(zips[-1]) as z:
            data = {n: z.read(n).decode("utf-8-sig", "replace") for n in z.namelist() if n.lower().endswith(".csv")}
        flat, schools = parse_csv_files(data)
        used = zips[-1].name
    elif csvs:
        flat, schools = parse_csv_files({f.name: f.read_text("utf-8-sig") for f in csvs})
        used = ", ".join(f.name for f in csvs)
    elif pdfs:
        flat, schools = parse_pdf(pdfs[-1])
        used = pdfs[-1].name
    else:
        sys.exit("No LinkedIn file found in linkedin/ (expected Profile.pdf, a .zip, or Positions.csv).")

    if not flat:
        sys.exit("No positions found in the LinkedIn file; Word file left unchanged.")

    current = resume_docx.read(DOCX)
    skip = [s.lower() for s in cfg.get("skip_education_containing", [])]
    li_edu = [{"title": s["degree"] or s["school"], "org": s["school"] if s["degree"] else "",
               "date": s["date"], "bullets": []}
              for s in schools if not any(k in (s["school"] + " " + s["degree"]).lower() for k in skip)]
    # Keep bullets for schools already on the resume; keep resume-only entries (e.g. certificates).
    li_keys = {_school_key(e["org"] or e["title"]) for e in li_edu}
    for e in li_edu:
        for old in current["education"]:
            if _school_key(old["org"]) == _school_key(e["org"]):
                e["bullets"] = old["bullets"]
    kept = [old for old in current["education"] if _school_key(old["org"]) not in li_keys]

    new = dict(current)
    new["experience"] = to_entries(flat, cfg)
    new["education"] = kept + li_edu
    resume_docx.write(new, DOCX)
    print(f"Updated {DOCX.name} from {used}: {len(new['experience'])} experience entries, "
          f"{len(new['education'])} education entries.")


if __name__ == "__main__":
    main()
