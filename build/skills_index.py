"""Build search-index.json: per-skill metrics computed from the resume.

For every skill in skills_taxonomy.json it finds the resume lines that mention
it and computes years of hands-on use (overlaps merged), last used, roles,
companies, related techs present, and an expertise score/level.
"""
import datetime as dt
import json
import re
from pathlib import Path

MON = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
TODAY = dt.date.today()


def _point(s, end=False):
    s = s.strip()
    if s.lower() in ("present", "current", "now"):
        return TODAY.year * 12 + TODAY.month
    m = re.match(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{4})", s)
    if m and m.group(1).title() in MON:
        return int(m.group(2)) * 12 + MON[m.group(1).title()]
    m = re.search(r"(\d{4})", s)
    if m:
        return int(m.group(1)) * 12 + (12 if end else 1)
    return None


def parse_range(date):
    parts = re.split(r"\s*[–—-]\s*", date.strip(), maxsplit=1)
    if len(parts) == 2:
        a, b = _point(parts[0]), _point(parts[1], end=True)
    else:
        a = b = _point(parts[0], end=True)
    return (a, b) if a and b else None


def merged_months(ranges):
    ranges = sorted(r for r in ranges if r)
    total, cur = 0, None
    for a, b in ranges:
        if cur and a <= cur[1] + 1:
            cur = (cur[0], max(cur[1], b))
        else:
            if cur:
                total += cur[1] - cur[0] + 1
            cur = (a, b)
    if cur:
        total += cur[1] - cur[0] + 1
    return total


def _alias_re(alias):
    a = re.escape(alias.lower())
    return re.compile(rf"(?<![a-z0-9]){a}(?![a-z0-9])")


def company_of(org):
    return re.split(r"\s+[—·|]\s+", org)[0].strip()


def build(resume, taxonomy_path):
    tax = json.loads(Path(taxonomy_path).read_text())["skills"]
    pats = {s["name"]: [_alias_re(a) for a in [s["name"]] + s["aliases"]] for s in tax}

    docs = []  # each searchable line
    for kind in ("experience", "education"):
        for i, en in enumerate(resume[kind]):
            rng = parse_range(en["date"]) if en["date"] else None
            texts = en["bullets"] or [en["title"]]
            for t in texts:
                docs.append({"kind": kind, "role": en["title"], "org": en["org"],
                             "company": company_of(en["org"]) if en["org"] else en["title"],
                             "date": en["date"], "range": rng,
                             "text": t, "match_text": (t + " " + en["title"]).lower()})
    skills_text = " ".join(f"{k} {v}" for k, v in resume["skills"]).lower()
    summary = resume.get("summary", "").lower()

    out = []
    for s in tax:
        hits = [d for d in docs if any(p.search(d["match_text"]) for p in pats[s["name"]])]
        listed = any(p.search(skills_text) for p in pats[s["name"]])
        in_summary = any(p.search(summary) for p in pats[s["name"]])
        work = [d for d in hits if d["kind"] == "experience"]
        study = [d for d in hits if d["kind"] == "education"]
        if not (hits or listed):
            continue
        role_keys = {(d["role"], d["org"], d["date"]) for d in work}
        months = merged_months([r for r in {(d["role"], d["org"], d["date"]): d["range"]
                                             for d in work}.values() if r])
        last = max([d["range"][1] for d in hits if d["range"]], default=None)
        first = min([d["range"][0] for d in work if d["range"]], default=None)
        out.append({"name": s["name"], "category": s["category"], "aliases": s["aliases"],
                    "related": s["related"], "listed": listed, "in_summary": in_summary,
                    "months": months, "first": first, "last": last,
                    "roles": len(role_keys),
                    "companies": sorted({d["company"] for d in work}),
                    "study": len(study),
                    "evidence": [{"text": d["text"], "role": d["role"], "company": d["company"],
                                  "date": d["date"], "kind": d["kind"]} for d in hits]})

    present = {o["name"] for o in out}
    now = TODAY.year * 12 + TODAY.month
    for o in out:
        rel = [r for r in o["related"] if r in present]
        years = o["months"] / 12
        s_years = min(years / 8, 1) * 45
        since = (now - o["last"]) / 12 if o["last"] else 99
        s_recent = 20 if since <= 1 else 14 if since <= 3 else 8 if since <= 6 else 3 if since < 99 else 0
        if o["listed"]:
            s_recent = max(s_recent, 14)   # listed in current skills
        s_breadth = min(o["roles"] / 3, 1) * 15
        s_related = (len(rel) / len(o["related"]) if o["related"] else 0) * 20
        bonus = 0
        if not o["months"] and (o["study"] or o["listed"]):
            bonus = 10 if o["study"] else 5   # studied or listed, not yet used at work
        score = round(min(s_years + s_recent + s_breadth + s_related + bonus, 100))
        level = ("Expert" if score >= 75 else "Advanced" if score >= 55
                 else "Proficient" if score >= 35 else "Familiar")
        o.update({"years": round(years, 1), "related_present": rel,
                  "related_missing": [r for r in o["related"] if r not in present],
                  "score": score, "level": level,
                  "parts": {"Hands-on years": round(s_years), "Recency": s_recent,
                            "Breadth of roles": round(s_breadth),
                            "Related techs": round(s_related), "Study / listed": bonus},
                  "first_label": _label(o["first"]), "last_label": _label(o["last"], now)})
        del o["first"], o["last"]
    out.sort(key=lambda o: -o["score"])
    return {"generated": TODAY.isoformat(),
            "career_years": round(merged_months([d["range"] for d in docs if d["kind"] == "experience" and d["range"]]) / 12),
            "skills": out,
            "docs": [{"text": d["text"], "role": d["role"], "company": d["company"],
                      "date": d["date"], "kind": d["kind"]} for d in docs]}


def _label(p, now=None):
    if not p:
        return ""
    if now and p >= now:
        return "Present"
    y, m = divmod(p - 1, 12)
    return f"{list(MON)[m]} {y}"
