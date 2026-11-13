"""Country-level snapshot extractor for Victoria 2 saves (tested on a German Empire 1873.8.1 save).

usage: python extract_countries.py SAVE.v2_or_FOLDER [OUT.csv] [--campaign NAME]

Given a folder, every .v2 file in it is processed and the rows are stacked into one table.
If several files share the same in-game date, only the most recently modified one is used.
Every row gets a 'campaign' label (default: the folder name) so separate campaigns can be
stacked later; the panel key is then (campaign, snapshot_date, tag).
"""
import sys, csv, re, argparse
from pathlib import Path
from collections import defaultdict
from vic2parse import parse, Block

COUNTRY_FIELDS = ["money", "prestige", "tax_base", "leadership", "war_exhaustion",
                  "plurality", "badboy", "revanchism", "diplomatic_points", "suppression",
                  "government", "primary_culture", "religion", "civilized", "capital"]

def iso_date(s):
    y, m, d = (int(x) for x in str(s).split("."))
    return f"{y:04d}-{m:02d}-{d:02d}"

def is_pop(k, v):
    return isinstance(v, Block) and v.get("size") is not None and v.get("literacy") is not None

def extract_snapshot(path):
    text = open(path, encoding="cp1252").read()          # saves are Windows-1252, CRLF
    root = parse(text)
    snap = iso_date(root.get("date"))

    # country blocks = top-level 3-char tags that carry a capital or money field
    countries = {k: v for k, v in root.items
                 if len(k) == 3 and isinstance(v, Block) and v.get("money") is not None}

    agg = defaultdict(lambda: defaultdict(float))
    for k, prov in root.items:
        if not (k.isdigit() and isinstance(prov, Block)):
            continue
        owner = prov.get("owner")
        if owner is None:                                  # unowned provinces
            continue
        a = agg[owner]
        a["n_provinces"] += 1
        for pk, pv in prov.items:
            if is_pop(pk, pv):
                s = pv.get("size")
                a["pop_total"] += s
                a["pop_" + pk] += s
                a["_lit"] += s * pv.get("literacy")
                a["_con"] += s * (pv.get("con") or 0)
                a["_mil"] += s * (pv.get("mil") or 0)
                a["pop_money"] += pv.get("money") or 0

    rows = []
    for tag, c in countries.items():
        a = agg.get(tag)
        if not a:                                          # dead / no provinces
            continue
        row = {"snapshot_date": snap, "tag": tag}
        for f in COUNTRY_FIELDS:
            row[f] = c.get(f)
        pt = a["pop_total"]
        row["n_provinces"] = int(a["n_provinces"])
        row["pop_total"] = pt
        row["literacy_wtd"] = a["_lit"] / pt if pt else None
        row["consciousness_wtd"] = a["_con"] / pt if pt else None
        row["militancy_wtd"] = a["_mil"] / pt if pt else None
        row["pop_money_sum"] = a["pop_money"]
        for k2, v2 in a.items():
            if k2.startswith("pop_") and k2 not in ("pop_total", "pop_money"):
                row[k2] = v2
        rows.append(row)
    return rows

def write_csv(rows, out):
    cols = []
    for r in rows:
        for k in r:
            if k not in cols:
                cols.append(k)
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

def peek_date(path):
    """In-game date from the first bytes of a save, without parsing the whole file."""
    with open(path, "rb") as f:
        head = f.read(400).decode("cp1252", errors="replace")
    m = re.search(r'date="(\d+\.\d+\.\d+)"', head)
    return iso_date(m.group(1)) if m else None

def collect_rows(src, campaign=None):
    src = Path(src)
    campaign = campaign or (src.name if src.is_dir() else src.parent.name)
    if src.is_file():
        files = [src]
    elif src.is_dir():
        files = sorted(src.glob("*.v2"))
        if not files:
            raise SystemExit(f"No .v2 files found in {src}")
    else:
        raise SystemExit(f"Path not found: {src}")
    by_date = {}
    for f in files:
        d = peek_date(f) or f.name
        if d in by_date:
            keep = max(by_date[d], f, key=lambda x: x.stat().st_mtime)
            print(f"  note: {by_date[d].name} and {f.name} share date {d}; using {keep.name}")
            by_date[d] = keep
        else:
            by_date[d] = f
    rows = []
    for d in sorted(by_date):
        print(f"parsing {by_date[d].name} ({d}) ...")
        for r in extract_snapshot(by_date[d]):
            rows.append({"campaign": campaign, **r})
    return rows

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="a .v2 save or a folder of saves from ONE campaign")
    ap.add_argument("out", nargs="?", default="countries.csv")
    ap.add_argument("--campaign", help="label for this campaign (default: folder name)")
    a = ap.parse_args()
    rows = collect_rows(a.src, a.campaign)
    write_csv(rows, a.out)
    print(len(rows), "rows,", len({r["snapshot_date"] for r in rows}), "snapshot(s), campaign",
          repr(rows[0]["campaign"]), "->", a.out)