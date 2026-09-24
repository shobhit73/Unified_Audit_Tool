"""Every balance the tool reports must equal ADP's own printed subtotal.

Run:  python scratch/verify_timeoff_rounding.py

ADP writes each transaction as `=ROUND(x, 2.0)` and prints, per employee and
policy, a "Totals For ... -- Balance Amount:" row holding round(sum of x). The
tool used to round each transaction first and add afterwards, which costs a
cent whenever the dropped fractions add up: 284 of 2503 employee/policy totals
across the client files on this machine.

One employee can hold TWO ADP employment records (same Associate ID, two file
numbers) and then ADP prints two subtotals; UZIO has one row for that person,
so the expected figure is the sum of both.
"""
import glob
import io
import os
import re
import sys
from collections import defaultdict

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import timeoff_audit as ta          # noqa: E402

D = r"C:\Users\rohit.kaushik\Downloads"
failures = 0


class U(io.BytesIO):
    def __init__(self, path):
        with open(path, "rb") as fh:
            super().__init__(fh.read())
        self.name = os.path.basename(path)
        self.size = len(self.getvalue())


def check(label, ok, detail=""):
    global failures
    print("   %-66s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:400]))
    failures += 0 if ok else 1


def balance_files():
    out = []
    for f in glob.glob(os.path.join(D, "**", "*.xlsx"), recursive=True):
        base = os.path.basename(f).lower()
        if base.startswith("~$") or "time" not in base or "balance" not in base:
            continue
        out.append(f)
    return sorted(out)


INNER = re.compile(r"^\s*=\s*ROUND\(\s*(-?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*,", re.I)


def read_file(path):
    """Per (employee, policy): ADP's printed subtotal, the raw sum, and how many
    subtotal blocks ADP printed for it.

    One employee can hold two ADP employment records; ADP then prints two
    subtotals, each rounded on its own, so their sum can sit a cent away from
    the single figure UZIO needs.
    """
    ws = openpyxl.load_workbook(path, data_only=False).worksheets[0]
    head = [str(ws.cell(row=1, column=c).value or "").strip().upper()
            for c in range(1, ws.max_column + 1)]
    if "ASSOCIATE ID" not in head or "BALANCE AMOUNT" not in head:
        return None
    col = {h: i + 1 for i, h in enumerate(head)}
    c_id, c_bal = col["ASSOCIATE ID"], col["BALANCE AMOUNT"]
    c_pol = col.get("POLICY NAME")

    subs, raws, blocks = defaultdict(float), defaultdict(float), defaultdict(int)
    seen, last = False, None
    for r in range(2, ws.max_row + 1):
        eid = ta.clean_id(ws.cell(row=r, column=c_id).value)
        cell = ws.cell(row=r, column=c_bal).value
        if eid:
            last = (eid, str(ws.cell(row=r, column=c_pol).value or "").strip()
                    if c_pol else "")
            m = INNER.match(str(cell) or "")
            raws[last] += float(m.group(1)) if m else float(ta._evaluate_cell(cell) or 0)
            continue
        if "Totals For" in str(ws.cell(row=r, column=1).value or "") and last:
            val = ta._evaluate_cell(cell)
            if val is not None:
                subs[last] += float(val)
                blocks[last] += 1
                seen = True
    if not seen:
        return None
    return ({k: round(v, 2) for k, v in subs.items()},
            {k: round(v, 2) for k, v in raws.items()}, dict(blocks))


def main():
    files = balance_files()
    print("ADP time-off balance files found: %d" % len(files))
    single = multi = bad_raw = bad_adp = 0
    worst, split_examples = [], []

    for path in files:
        parsed = read_file(path)
        if not parsed:
            continue
        subs, raws, blocks = parsed
        df, err = ta.read_adp_balances(U(path))
        if err:
            check("%s reads" % os.path.basename(path)[:40], False, err)
            continue
        ours = {(r["id"], r["policy"]): r["balance"] for _, r in df.iterrows()}
        bad = []
        for key, adp in subs.items():
            if key not in ours:
                continue                      # ADP-only rows are a different check
            got = ours[key]
            got = None if got is None else float(got)
            # 1. the tool must equal the raw sum, rounded once
            if got is None or abs(got - raws[key]) >= 0.005:
                bad_raw += 1
                bad.append((key, got, raws[key], adp, blocks.get(key, 0)))
            # 2. where ADP printed ONE block, its own figure must agree too
            if blocks.get(key, 0) == 1:
                single += 1
                if got is None or abs(got - adp) >= 0.005:
                    bad_adp += 1
                    bad.append((key, got, raws[key], adp, 1))
            else:
                multi += 1
                if abs(raws[key] - adp) >= 0.005 and len(split_examples) < 3:
                    split_examples.append((os.path.relpath(path, D), key, raws[key], adp))
        if bad:
            worst.append((len(bad), os.path.relpath(path, D), bad[:3]))

    print()
    print("employee/policy totals with ONE ADP block  : %d" % single)
    print("   ... with two employment records         : %d" % multi)
    print("tool disagreeing with the raw sum          : %d" % bad_raw)
    print("tool disagreeing with ADP's printed total  : %d" % bad_adp)
    for n, rel, sample in sorted(worst, reverse=True)[:6]:
        print("   %-56s %d off" % (rel[:56], n))
        for key, got, raw, adp, blk in sample:
            print("        %-10s %-14s ours=%s raw=%s ADP=%s blocks=%s"
                  % (key[0], key[1][:14], got, raw, adp, blk))
    if split_examples:
        print()
        print("   employees ADP split across two records (ADP rounds each block, we round once):")
        for rel, key, raw, adp in split_examples:
            print("      %-44s %-10s ours=%.2f  ADP's two blocks add to %.2f"
                  % (rel[:44], key[0], raw, adp))

    print()
    check("every total equals the raw sum rounded once", bad_raw == 0, bad_raw)
    check("every single-record total matches ADP's printed figure", bad_adp == 0, bad_adp)
    check("something was actually compared", single > 2000, single)

    print()
    print("FAIL - %d check(s)" % failures if failures else "PASS - every check held")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
