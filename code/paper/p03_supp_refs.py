"""Reference list for the supplement: every entry of the full list cited in the supplement's text or tables."""
import re


def add_refs(doc, full_path, heading):
    full = [r.strip() for r in open(full_path, encoding="utf-8").read().split("\n\n") if r.strip()]
    txt = "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join(c.text for t in doc.tables for row in t.rows for c in row.cells)
    orgs = ("MfE", "EECA", "MBIE", "IPCC", "EMS")

    def cited(r):
        m = re.search(r"\((\d{4}[a-z]?)", r)
        yr = m.group(1); au = r[:m.start()]
        first = au.split(",")[0].split(".")[0].strip()
        if au.startswith("Ministry for the Environment"): first = "MfE"
        if au.startswith("EECA"): first = "EECA"
        sur = first if first in orgs else first.split()[-1]
        labs = re.findall(re.escape(sur) + r"[^;()\n]{0,45}?\(?" + re.escape(yr) + r"[a-z]?\)?", txt)
        if not labs:
            return False
        if first in orgs:
            return True
        names = re.findall(r"([A-Z][\w'’\-]+), [A-Z]\.", au)
        if len(names) <= 1:
            return any(("et al" not in l and "&" not in l) for l in labs)
        if len(names) == 2:
            return any(names[1] in l for l in labs)
        return any(("et al" in l) or (names[1] in l) for l in labs)

    heading("References")
    n = 0
    for r in full:
        if cited(r):
            doc.add_paragraph(r); n += 1
    return n
