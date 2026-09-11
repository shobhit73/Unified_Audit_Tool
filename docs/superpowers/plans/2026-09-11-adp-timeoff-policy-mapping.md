# ADP Time Off Policy Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill each UZIO Time Off template row from the ADP policies the user maps to that row's UZIO policy, instead of writing one all-policies total into every row an employee has.

**Architecture:** `read_adp_balances` keeps ADP policies apart (one row per employee per policy). A new `read_template_rows` reads the template once; `auto_map` suggests PTO → Paid PTO; `plan_fill` decides every template row (`write` / `blank` / `no_mapping` / `no_balance` / `salaried`); `fill_import_template` only writes the `write` rows; `build_audit_sheets` reports from the same plan. The Streamlit UI inserts a mapping step (one dropdown per ADP policy + a Salaried checkbox) between upload and Generate.

**Tech Stack:** Python 3, Streamlit, pandas, openpyxl. Verification is a standalone script (`scratch/verify_*.py`) — the repo has no pytest.

**Spec:** `docs/superpowers/specs/2026-09-11-adp-timeoff-policy-mapping-design.md`

## Global Constraints

- Only `apps/adp/timeoff_audit.py` changes in app code. ADP only — Paycom and `audit_fast_api` are out of scope.
- Blank Opening Balance = policy not assigned = never filled (unchanged rule).
- Negative balances are written as they are.
- The census stays mandatory; Exception Summary keeps exactly six columns: `Employee ID, Employee Name, Employment Status, Termination Date, Issue Category, ADP Balance`.
- Only PTO is auto-mapped: ADP names matching `\bPTO\b` or `paid time off` (case-insensitive) → template policy `Paid PTO` (case-insensitive, trimmed), else the single PTO-named template policy, else nothing.
- "Salaried" = the template row's `Pay Type` contains `salar` (case-insensitive). Checkbox label: **Fill balances for Salaried employees too**, default unchecked.
- New issue categories, verbatim: `Salaried — not filled (<UZIO policy>)`, `ADP policy not imported (<ADP policy>)` (non-zero balances only).
- New sheet `Policy Mapping` with columns `ADP Policy, Mapped To, Employees, Total ADP Balance, Set By`; `Set By` ∈ `Auto`, `You`, `Not filled`.
- Dropdown choice meaning "leave out": `Do not import`.
- Commits happen only when Rohit says so; never push without his consent.

---

### Task 1: Policy-aware backend

**Files:**
- Modify: `apps/adp/timeoff_audit.py` (constants, `read_adp_balances`, `_sum_money`, `read_census`, `fill_import_template`, `build_audit_sheets`, `run_tool`; add `_is_blank`, `_template_sheet`, `policy_summary`, `read_template_rows`, `auto_map`, `plan_fill`, `_policy_mapping_sheet`)
- Test: `scratch/verify_timeoff_policy_mapping.py` (create)

**Interfaces:**
- Produces:
  - `DO_NOT_IMPORT: str = "Do not import"`
  - `read_adp_balances(file_adp) -> (DataFrame[id, policy, balance, name] | None, error | None)`
  - `policy_summary(adp_df) -> list[tuple[str, int, float]]` — `(policy, employees, total)`, sorted by policy
  - `read_template_rows(file_uzio) -> (dict | None, error | None)`; dict keys `sheet: str`, `rows: list[dict]`, `policies: list[str]`, `has_pay_type: bool`; each row `{"row", "raw_id", "id", "name", "policy", "opening", "salaried"}`
  - `auto_map(adp_policies, uzio_policies) -> dict[str, str]`
  - `plan_fill(tpl, adp_df, mapping, include_salaried) -> dict` with `decisions: list[(row, action, amount)]`, `mapped: dict[(id, uzio_policy), float]`, `emp_total: dict[id, float]`, `targets: set[str]`
  - `fill_import_template(file_uzio, decisions) -> (workbook, filled_count, error)`
  - `build_audit_sheets(file_uzio, tpl, adp_df, census_df, plan, mapping, auto) -> (sheets, counts)`; `counts` keys `missing, unassigned, salaried, not_imported, unmapped_uzio`
  - `run_tool(file_adp, file_uzio, file_census, mapping=None, include_salaried=False) -> (filled_bytes, audit_bytes, stats)`; `stats` adds `salaried, not_imported, unmapped_uzio, has_pay_type` to the existing `employees, filled, missing, unassigned, terminated`

- [ ] **Step 1: Write the failing verification (groups `readers`, `filling`, `audit`)**

Create `scratch/verify_timeoff_policy_mapping.py`:

```python
"""Verify ADP Time Off policy mapping (spec 2026-09-11) on real client files.

Run:  python scratch/verify_timeoff_policy_mapping.py [readers|filling|audit|ui ...]

BASELINE is origin/main before this work. With every ADP policy mapped to a
one-policy template and Salaried included, the new code must reproduce the
baseline exactly — that is the regression guarantee for one-policy clients.
"""
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
from collections import defaultdict

import openpyxl
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from apps.adp import timeoff_audit as ta          # noqa: E402

BASELINE = "038c330"
D = r"C:\Users\rohit.kaushik\Downloads"
MOSES = (D + r"\Moses_Solutions_LLC_Time_Off_Balance_Summary.xlsx",
         D + r"\Moses_Time Off Import (2).xlsx", None)
EXPRESS = (D + r"\Express_Package_System_Inc_Time_Off_Balance_Summary.xlsx",
           D + r"\Time Off Import (1).xlsx",
           D + r"\Multi_Client_EXPRESS PACKAGE SYSTEM_Employee_Census.xlsm")
HD = (D + r"\High Distinction\New folder\Time Off Balance Summary.xlsx",
      D + r"\High Distinction\New folder\Time Off Import.xlsx",
      D + r"\High Distinction\Multi_Client_High Distinction Logistics LLC_Employee_Census.xlsm")
OLD_EXC_COLS = ["Employee ID", "Employee Name", "Issue Category", "ADP Balance"]


class U(io.BytesIO):
    def __init__(self, data, name):
        super().__init__(data)
        self.name = name
        self.size = len(data)


def up(path):
    return U(open(path, "rb").read(), os.path.basename(path))


failures = 0


def check(label, ok, detail=""):
    global failures
    print("   %-70s %s%s" % (label, "OK" if ok else "FAIL",
                             "" if ok else "  <- " + str(detail)[:300]))
    failures += 0 if ok else 1


def baseline():
    src = subprocess.run(["git", "-C", ROOT, "show", BASELINE + ":apps/adp/timeoff_audit.py"],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    path = os.path.join(tempfile.gettempdir(), "timeoff_audit_baseline.py")
    open(path, "w", encoding="utf-8").write(src)
    spec = importlib.util.spec_from_file_location("timeoff_audit_baseline", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def independent_balances(path):
    """(id, policy) -> balance, summed here rather than by the module under test."""
    ws = openpyxl.load_workbook(path).worksheets[0]
    head = [str(ws.cell(row=1, column=c).value or "").strip().upper()
            for c in range(1, ws.max_column + 1)]
    ci, cp, cb = (head.index(h) + 1 for h in ("ASSOCIATE ID", "POLICY NAME", "BALANCE AMOUNT"))
    out = defaultdict(float)
    for r in range(2, ws.max_row + 1):
        eid = ta.clean_id(ws.cell(row=r, column=ci).value)
        if eid:
            out[(eid, str(ws.cell(row=r, column=cp).value).strip())] += float(
                ta._evaluate_cell(ws.cell(row=r, column=cb).value))
    return {k: round(v, 2) for k, v in out.items()}


def new_run(files, mapping=None, include_salaried=False):
    """The new backend without Streamlit. Returns a dict of every intermediate."""
    a, t, _ = files
    adp_df, err = ta.read_adp_balances(up(a))
    assert not err, err
    tpl, err = ta.read_template_rows(up(t))
    assert not err, err
    auto = ta.auto_map([p for p, _, _ in ta.policy_summary(adp_df)], tpl["policies"])
    mapping = auto if mapping is None else mapping
    plan = ta.plan_fill(tpl, adp_df, mapping, include_salaried)
    wb, filled, err = ta.fill_import_template(up(t), plan["decisions"])
    assert not err, err
    return {"adp": adp_df, "tpl": tpl, "auto": auto, "mapping": mapping,
            "plan": plan, "wb": wb, "filled": filled}


def legacy_mapping(files):
    """Every ADP policy -> the template's one policy: what the old code did."""
    a, t, _ = files
    adp_df, _ = ta.read_adp_balances(up(a))
    tpl, _ = ta.read_template_rows(up(t))
    assert len(tpl["policies"]) == 1, tpl["policies"]
    return {p: tpl["policies"][0] for p, _, _ in ta.policy_summary(adp_df)}


def openings(wb_or_bytes):
    wb = (openpyxl.load_workbook(io.BytesIO(wb_or_bytes))
          if isinstance(wb_or_bytes, (bytes, bytearray)) else wb_or_bytes)
    ws = ta._template_sheet(wb)
    return {r: ws.cell(row=r, column=8).value for r in range(ta.UZIO_HEADER_ROW + 1, ws.max_row + 1)}


def sheet(xbytes, name):
    return pd.read_excel(io.BytesIO(xbytes), sheet_name=name, dtype=str).fillna("")


# ---------------------------------------------------------------- readers
def group_readers():
    print("\n== readers")
    r = new_run(MOSES)
    check("Moses ADP policies kept apart",
          set(r["adp"]["policy"]) == {"PTO", "Salary  PTO"}, set(r["adp"]["policy"]))
    summ = {p: (n, tot) for p, n, tot in ta.policy_summary(r["adp"])}
    check("Moses PTO summary is 204 EEs / 5056.63",
          summ.get("PTO") == (204, 5056.63), summ)
    check("Moses template policies in template order",
          r["tpl"]["policies"] == ["NY State Prenatal Leave", "Paid PTO"], r["tpl"]["policies"])
    check("Moses template has Pay Type; 12 Salaried rows",
          r["tpl"]["has_pay_type"] and sum(t["salaried"] for t in r["tpl"]["rows"]) == 12)
    check("auto_map Moses: both PTO policies -> Paid PTO",
          r["auto"] == {"PTO": "Paid PTO", "Salary  PTO": "Paid PTO"}, r["auto"])
    h = new_run(HD)
    check("auto_map HD: Amazon PTO -> Paid PTO, Salaried policies -> Do not import",
          h["auto"] == {"Amazon PTO": "Paid PTO",
                        "Salaried Sick Time Policy": ta.DO_NOT_IMPORT,
                        "Salaried Time Off Policy": ta.DO_NOT_IMPORT}, h["auto"])
    hansen = ta.auto_map(["New York City Prenatal Leave", "New York City Unpaid Leave", "PTO"],
                         ["NY State Prenatal Leave", "Paid PTO"])
    check("auto_map guesses PTO only, never a leave policy",
          hansen == {"New York City Prenatal Leave": ta.DO_NOT_IMPORT,
                     "New York City Unpaid Leave": ta.DO_NOT_IMPORT, "PTO": "Paid PTO"}, hansen)
    check("auto_map falls back to the single PTO-named template policy",
          ta.auto_map(["Amazon PTO"], ["PTO"]) == {"Amazon PTO": "PTO"})
    check("auto_map maps nothing when the PTO target is ambiguous",
          ta.auto_map(["PTO"], ["PTO A", "PTO B"]) == {"PTO": ta.DO_NOT_IMPORT})
    check("_sum_money never returns -0.0",
          str(ta._sum_money(pd.Series([-1e-15]))) == "0.0")


# ---------------------------------------------------------------- filling
def group_filling():
    print("\n== filling")
    base = baseline()
    r = new_run(MOSES)
    out, tpl_open = openings(r["wb"]), {t["row"]: t["opening"] for t in r["tpl"]["rows"]}
    pren = [t for t in r["tpl"]["rows"] if t["policy"] == "NY State Prenatal Leave"]
    check("Moses: all 96 prenatal rows stay 20.0",
          len(pren) == 96 and all(out[t["row"]] == 20.0 for t in pren))
    truth = independent_balances(MOSES[0])
    written = [t for t in r["tpl"]["rows"] if t["policy"] == "Paid PTO"
               and out[t["row"]] != tpl_open[t["row"]]]
    wrong = [(t["raw_id"], out[t["row"]], truth.get((t["id"], "PTO")))
             for t in r["tpl"]["rows"] if t["policy"] == "Paid PTO" and not t["salaried"]
             and not ta._is_blank(t["opening"]) and (t["id"], "PTO") in truth
             and out[t["row"]] != truth[(t["id"], "PTO")]]
    check("Moses: every assigned Hourly Paid PTO row equals ADP PTO", not wrong, wrong[:3])
    check("Moses: 86 rows written", r["filled"] == 86 and len(written) <= 86, r["filled"])
    check("Moses: Salaried rows untouched",
          all(out[t["row"]] == t["opening"] for t in r["tpl"]["rows"] if t["salaried"]))

    b_fill, _, _ = base.run_tool(up(EXPRESS[0]), up(EXPRESS[1]), up(EXPRESS[2]))
    on = new_run(EXPRESS, include_salaried=True)
    check("Express, Salaried on: filled template identical to baseline",
          openings(on["wb"]) == openings(b_fill))
    off = new_run(EXPRESS)
    base_open, off_open = openings(b_fill), openings(off["wb"])
    sal_rows = {t["row"] for t in off["tpl"]["rows"] if t["salaried"]}
    diff = {row for row in base_open if base_open[row] != off_open[row]}
    check("Express, Salaried off: every changed row is a Salaried row",
          diff <= sal_rows, sorted(diff - sal_rows)[:5])
    check("Express: 9 rows skipped as Salaried",
          sum(a == "salaried" for _, a, _ in off["plan"]["decisions"]) == 9)

    b_hd, _, _ = base.run_tool(up(HD[0]), up(HD[1]), up(HD[2]))
    leg = new_run(HD, mapping=legacy_mapping(HD), include_salaried=True)
    check("High Distinction, legacy mapping: identical to baseline",
          openings(leg["wb"]) == openings(b_hd))


# ---------------------------------------------------------------- audit
def group_audit():
    print("\n== audit")
    base = baseline()
    for name, files in (("Express", EXPRESS), ("High Distinction", HD)):
        a, t, c = files
        bf, ba, bs = base.run_tool(up(a), up(t), up(c))
        nf, na, ns = ta.run_tool(up(a), up(t), up(c), mapping=legacy_mapping(files),
                                 include_salaried=True)
        for s in ("Balance vs UZIO Status", "Unassigned Policies"):
            check("%s legacy: %s identical" % (name, s), sheet(ba, s).equals(sheet(na, s)))
        check("%s legacy: Exception Summary rows identical" % name,
              sheet(ba, "Exception Summary")[OLD_EXC_COLS].equals(
                  sheet(na, "Exception Summary")[OLD_EXC_COLS]))
        check("%s legacy: stats identical" % name,
              {k: ns[k] for k in bs} == bs, (bs, {k: ns.get(k) for k in bs}))

    _, audit, stats = ta.run_tool(up(HD[0]), up(HD[1]), up(HD[2]))
    exc = sheet(audit, "Exception Summary")
    ni = exc[exc["Issue Category"].str.startswith("ADP policy not imported")]
    got = {(r["Employee ID"], r["Issue Category"], float(r["ADP Balance"])) for _, r in ni.iterrows()}
    want = {("I40QAXG83", "ADP policy not imported (Salaried Sick Time Policy)", 4.0),
            ("I40QAXG83", "ADP policy not imported (Salaried Time Off Policy)", 1.0),
            ("2OFLJ8BJI", "ADP policy not imported (Salaried Time Off Policy)", 2.5)}
    check("HD: non-zero Do-not-import balances reported, zero ones not", got == want, got)
    bvs = sheet(audit, "Balance vs UZIO Status")
    check("HD: ADP Balance counts mapped policies only",
          not {"I40QAXG83", "2OFLJ8BJI"} & set(bvs["Employee ID"]))
    pm = sheet(audit, "Policy Mapping")
    check("HD: Policy Mapping lists all three ADP policies as Auto",
          set(pm["ADP Policy"]) == {"Amazon PTO", "Salaried Sick Time Policy",
                                    "Salaried Time Off Policy"}
          and set(pm["Set By"]) == {"Auto"}, pm.values.tolist())

    base_fill, _, _ = base.run_tool(up(EXPRESS[0]), up(EXPRESS[1]), up(EXPRESS[2]))
    _, audit, stats = ta.run_tool(up(EXPRESS[0]), up(EXPRESS[1]), up(EXPRESS[2]))
    exc = sheet(audit, "Exception Summary")
    sal = exc[exc["Issue Category"] == "Salaried — not filled (Paid PTO)"]
    check("Express: 9 'Salaried — not filled (Paid PTO)' rows",
          len(sal) == 9 and stats["salaried"] == 9, (len(sal), stats.get("salaried")))

    r = new_run(MOSES)
    sheets, counts = ta.build_audit_sheets(up(MOSES[1]), r["tpl"], r["adp"], None,
                                           r["plan"], r["mapping"], r["auto"])
    pm = sheets["Policy Mapping"].astype(str).values.tolist()
    check("Moses: Policy Mapping rows",
          pm == [["PTO", "Paid PTO", "204", "5056.63", "Auto"],
                 ["Salary  PTO", "Paid PTO", "1", "0.0", "Auto"],
                 ["(none)", "NY State Prenatal Leave", "—", "—", "Not filled"]], pm)
    check("Moses: 112 missing, no Salaried exceptions",
          counts["missing"] == 112 and counts["salaried"] == 0, counts)
    you = dict(r["mapping"], **{"Salary  PTO": ta.DO_NOT_IMPORT})
    plan = ta.plan_fill(r["tpl"], r["adp"], you, False)
    sheets, counts = ta.build_audit_sheets(up(MOSES[1]), r["tpl"], r["adp"], None,
                                           plan, you, r["auto"])
    row = sheets["Policy Mapping"].set_index("ADP Policy").loc["Salary  PTO"]
    check("Moses: a changed mapping is 'You'; a zero balance is not reported",
          row["Set By"] == "You" and not counts["not_imported"], (row.to_dict(), counts))


GROUPS = {"readers": group_readers, "filling": group_filling, "audit": group_audit}


def main(argv):
    for name in (argv or list(GROUPS)):
        try:
            GROUPS[name]()
        except Exception as e:                       # a missing function is a FAIL
            check("group %s ran" % name, False, repr(e))
    print()
    print("FAIL - %d check(s)" % failures if failures else "PASS - every check held")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `py -3 scratch/verify_timeoff_policy_mapping.py readers filling audit`
Expected: `FAIL` — `group readers ran ... AttributeError: ... 'auto_map'` (and the same for the other groups).

- [ ] **Step 3: Implement the backend**

In `apps/adp/timeoff_audit.py`:

(a) After `EXCEPTION_COLUMNS`, add:

```python
# The mapping dropdown's "leave this ADP policy out" choice.
DO_NOT_IMPORT = "Do not import"

# Auto-mapping guesses PTO and nothing else: a wrong guess on a leave policy
# would move hours into the wrong bucket, and look plausible enough to be
# accepted unread.
_PTO = re.compile(r"\bPTO\b|paid\s+time\s+off", re.I)
PREFERRED_PTO_POLICY = "paid pto"
```

(b) After `_find`, add:

```python
def _is_blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def _template_sheet(wb):
    """The template sheet: the first one whose row 4 carries an Employee ID header."""
    return next((s for s in wb.worksheets
                 if _find([s.cell(row=UZIO_HEADER_ROW, column=c).value
                           for c in range(1, s.max_column + 1)], "employee id")), None)
```

(c) `read_adp_balances`: seek first, read `POLICY NAME`, group by `(id, policy)`. Docstring first line becomes "One row per employee per ADP time-off policy, with that policy's balance." and gains the paragraph:

```
    Policies are kept apart because the UZIO template has one row per employee
    per UZIO policy. Adding every ADP policy into one number and writing it into
    each of those rows overwrote Moses's NY State Prenatal Leave with PTO hours.

    Returns (DataFrame[id, policy, balance, name], error).
```

Body changes:

```python
    if hasattr(file_adp, "seek"):
        file_adp.seek(0)
    ...
    h_pol = _find(head, "policy name")
    c_pol = idx[h_pol] if h_pol else None
    ...
        rows.append({
            "id": eid,
            "name": ws.cell(row=r, column=c_name).value if c_name else "N/A",
            "policy": (str(ws.cell(row=r, column=c_pol).value or "").strip()
                       if c_pol else "") or "(no policy name)",
            "balance": _evaluate_cell(ws.cell(row=r, column=c_bal).value),
        })
    ...
    out = (df.groupby(["id", "policy"])
             .agg(balance=("balance", _sum_money), name=("name", "first"))
             .reset_index())
    return out, None
```

(d) `_sum_money` last line and docstring addition:

```python
    # `+ 0.0` turns the -0.0 that round() leaves on a tiny negative remainder
    # into 0.0, so a balance netting to zero is never written as "-0".
    total = series.sum(min_count=1)
    return total if pd.isna(total) else round(total, 2) + 0.0
```

(e) After `_sum_money`, add:

```python
def policy_summary(adp_df):
    """[(ADP policy, employees, total balance)] sorted by policy name."""
    return [(pol, int(g["id"].nunique()), _sum_money(g["balance"]))
            for pol, g in adp_df.groupby("policy")]
```

(f) `read_census`: first line of the body becomes `if hasattr(file_census, "seek"): file_census.seek(0)`.

(g) Add after `read_census`:

```python
def read_template_rows(file_uzio):
    """Every employee row of the UZIO Time Off Import template.

    Returns ({"sheet", "rows", "policies", "has_pay_type"}, error). Each row is
    {"row", "raw_id", "id", "name", "policy", "opening", "salaried"}; `row` is
    the Excel row number the filler writes back to, and `policies` lists the
    distinct Time Off Policy Names in template order.

    "Salaried" is the template's own Pay Type. At High Distinction the two
    holders of ADP's "Salaried ..." policies are Hourly in UZIO, so the ADP
    policy name cannot decide it.
    """
    file_uzio.seek(0)
    try:
        wb = openpyxl.load_workbook(file_uzio)
    except Exception as e:
        return None, f"Error reading Uzio Template: {e}"
    ws = _template_sheet(wb)
    if ws is None:
        return None, (f"Could not find an `Employee ID` header on row "
                      f"{UZIO_HEADER_ROW} of any sheet in the Uzio template.")

    head = [ws.cell(row=UZIO_HEADER_ROW, column=c).value for c in range(1, ws.max_column + 1)]
    pos = {h: i + 1 for i, h in enumerate(head)}
    h_id = _find(head, "employee id")
    h_bal = _find(head, "opening balance") or _find(head, "operating balance")
    if not h_bal:
        return None, ("Could not find `Employee ID` or `Opening Balance` headers "
                      f"in row {UZIO_HEADER_ROW} of the Uzio template.")
    h_pol = _find(head, "policy")
    h_pay = _find(head, "pay type")
    h_fn, h_ln = _find(head, "employee first name"), _find(head, "employee last name")
    h_nm = _find(head, "employee name")

    def cell(r, h):
        return ws.cell(row=r, column=pos[h]).value if h else None

    rows, policies = [], []
    for r in range(UZIO_HEADER_ROW + 1, ws.max_row + 1):
        raw = cell(r, h_id)
        eid = clean_id(raw)
        if not eid:
            continue
        policy = str(cell(r, h_pol) or "").strip() or "(no policy name)"
        if policy not in policies:
            policies.append(policy)
        name = " ".join(str(v).strip() for v in (cell(r, h_fn), cell(r, h_ln))
                        if not _is_blank(v))
        if not name:
            name = str(cell(r, h_nm)).strip() if not _is_blank(cell(r, h_nm)) else "N/A"
        rows.append({
            "row": r, "raw_id": raw, "id": eid, "name": name, "policy": policy,
            "opening": cell(r, h_bal),
            "salaried": bool(h_pay) and "salar" in str(cell(r, h_pay) or "").lower(),
        })
    return {"sheet": ws.title, "rows": rows, "policies": policies,
            "has_pay_type": bool(h_pay)}, None


def auto_map(adp_policies, uzio_policies):
    """Suggested ADP -> UZIO policy mapping; the user can change every entry.

    Only PTO is guessed. An ADP policy named with the word PTO (or "Paid Time
    Off") goes to the template's `Paid PTO`, or failing that to its one
    PTO-named policy if there is exactly one. Everything else starts on
    Do not import.
    """
    target = next((p for p in uzio_policies
                   if p.strip().casefold() == PREFERRED_PTO_POLICY), None)
    if target is None:
        named = [p for p in uzio_policies if _PTO.search(p)]
        target = named[0] if len(named) == 1 else None
    return {a: target if target and _PTO.search(a) else DO_NOT_IMPORT
            for a in adp_policies}


def plan_fill(tpl, adp_df, mapping, include_salaried):
    """Decide what happens to every template row.

    Row (employee E, UZIO policy P) is written with the sum of E's balances
    across every ADP policy mapped to P. It is left exactly as it is when the
    template leaves it blank (policy not assigned), when nothing is mapped to
    P, when E has no balance in any policy mapped to P, or when E is Salaried
    and `include_salaried` is off.

    Returns {"decisions": [(row, action, amount)], "mapped": {(E, P): amount},
             "emp_total": {E: amount}, "targets": {mapped UZIO policies}}.
    action is one of "write", "blank", "no_mapping", "no_balance", "salaried".
    """
    targets = {p for p in mapping.values() if p != DO_NOT_IMPORT}
    df = adp_df.assign(uzio=adp_df["policy"].map(lambda p: mapping.get(p, DO_NOT_IMPORT)))
    df = df[df["uzio"] != DO_NOT_IMPORT]
    mapped = df.groupby(["id", "uzio"])["balance"].agg(_sum_money).to_dict()
    emp_total = df.groupby("id")["balance"].agg(_sum_money).to_dict()

    decisions = []
    for t in tpl["rows"]:
        amount = mapped.get((t["id"], t["policy"]))
        if _is_blank(t["opening"]):
            action = "blank"
        elif t["policy"] not in targets:
            action = "no_mapping"
        elif amount is None or pd.isna(amount):
            action = "no_balance"
        elif t["salaried"] and not include_salaried:
            action = "salaried"
        else:
            action = "write"
        decisions.append((t, action, amount))
    return {"decisions": decisions, "mapped": mapped, "emp_total": emp_total,
            "targets": targets}
```

(h) Replace `fill_import_template` with:

```python
def fill_import_template(file_uzio, decisions):
    """Write the planned balances into a copy of the UZIO Time Off Import template.

    The workbook is returned untouched apart from the Opening Balance cells of
    the rows `plan_fill` marked "write" — same sheets, same formatting — so it
    can be uploaded to UZIO as-is.

    Returns (workbook, filled_count, error).
    """
    file_uzio.seek(0)
    try:
        wb = openpyxl.load_workbook(file_uzio)
    except Exception as e:
        return None, 0, f"Error reading Uzio Template: {e}"
    ws = _template_sheet(wb)
    if ws is None:
        return None, 0, (f"Could not find an `Employee ID` header on row "
                         f"{UZIO_HEADER_ROW} of any sheet in the Uzio template.")
    head = [ws.cell(row=UZIO_HEADER_ROW, column=c).value for c in range(1, ws.max_column + 1)]
    pos = {h: i + 1 for i, h in enumerate(head)}
    h_bal = _find(head, "opening balance") or _find(head, "operating balance")
    if not h_bal:
        return None, 0, ("Could not find `Employee ID` or `Opening Balance` headers "
                         f"in row {UZIO_HEADER_ROW} of the Uzio template.")
    filled = 0
    for t, action, amount in decisions:
        if action == "write":
            ws.cell(row=t["row"], column=pos[h_bal]).value = amount
            filled += 1
    return wb, filled, None
```

(i) `build_audit_sheets(file_uzio, tpl, adp_df, census_df, plan, mapping, auto)`:
- read `df_u` with `sheet_name=tpl["sheet"]` instead of the literal `"Time Off Details"`;
- `balance_map = plan["emp_total"]`; `name_map = adp_df.groupby("id")["name"].first().to_dict()`;
- replace the "missing" loop with one over `plan["mapped"]`, skipping pairs present in `{(t["id"], t["policy"]) for t in tpl["rows"]}` and NaN amounts, using `name_map.get(eid, "N/A")`;
- start `sheets` as `{"Policy Mapping": _policy_mapping_sheet(adp_df, tpl, mapping, auto, plan["targets"])}`;
- build `df_status` with named columns — `pd.DataFrame(rows, columns=["Employee ID", "Employee Name", "ADP Balance", "UZIO Employment Status", "Termination Date", "In Import Template"])`. With nothing mapped `rows` is empty, and a bare `DataFrame([])` has no columns, so the ranking line raises `KeyError: 'UZIO Employment Status'` (found by the `ui` group's "nothing mapped" check during execution);
- after the Terminated rows, append:

```python
    for t, action, amount in plan["decisions"]:
        if action == "salaried":
            exceptions.append({
                "Employee ID": str(t["raw_id"]), "Employee Name": t["name"],
                "Issue Category": f"Salaried — not filled ({t['policy']})",
                "ADP Balance": amount,
            })
    left_out = adp_df[(adp_df["policy"].map(lambda p: mapping.get(p, DO_NOT_IMPORT))
                       == DO_NOT_IMPORT)
                      & adp_df["balance"].notna() & (adp_df["balance"] != 0)]
    for _, r in left_out.iterrows():
        exceptions.append({
            "Employee ID": r["id"], "Employee Name": r["name"],
            "Issue Category": f"ADP policy not imported ({r['policy']})",
            "ADP Balance": r["balance"],
        })
```

- return counts:

```python
    counts = {
        "missing": len(missing),
        "unassigned": len(unassigned_rows),
        "salaried": sum(1 for _, a, _ in plan["decisions"] if a == "salaried"),
        "not_imported": [(pol, int(g["id"].nunique()), _sum_money(g["balance"]))
                         for pol, g in left_out.groupby("policy")],
        "unmapped_uzio": [p for p in tpl["policies"] if p not in plan["targets"]],
    }
```

and add before `audit_workbook_bytes`:

```python
def _policy_mapping_sheet(adp_df, tpl, mapping, auto, targets):
    """Where each ADP policy went, plus every UZIO policy nothing went into."""
    rows = []
    for pol, n, total in policy_summary(adp_df):
        target = mapping.get(pol, DO_NOT_IMPORT)
        rows.append({"ADP Policy": pol, "Mapped To": target, "Employees": n,
                     "Total ADP Balance": total,
                     "Set By": "Auto" if target == auto.get(pol, DO_NOT_IMPORT) else "You"})
    for p in tpl["policies"]:
        if p not in targets:
            rows.append({"ADP Policy": "(none)", "Mapped To": p, "Employees": "—",
                         "Total ADP Balance": "—", "Set By": "Not filled"})
    return pd.DataFrame(rows, columns=["ADP Policy", "Mapped To", "Employees",
                                       "Total ADP Balance", "Set By"])
```

(j) `run_tool(file_adp, file_uzio, file_census, mapping=None, include_salaried=False)`: after reading ADP and census, read the template with `read_template_rows`, compute `auto = auto_map([p for p, _, _ in policy_summary(adp_df)], tpl["policies"])`, default `mapping` to `auto`, build `plan = plan_fill(tpl, adp_df, mapping, include_salaried)`, call `fill_import_template(file_uzio, plan["decisions"])` and `build_audit_sheets(file_uzio, tpl, adp_df, census_df, plan, mapping, auto)`; `stats["employees"]` becomes `int(adp_df["id"].nunique())` and gains `"salaried"`, `"not_imported"`, `"unmapped_uzio"`, `"has_pay_type": tpl["has_pay_type"]`.

- [ ] **Step 4: Run and confirm it passes**

Run: `py -3 scratch/verify_timeoff_policy_mapping.py readers filling audit`
Expected: every line `OK`, last line `PASS - every check held`.

- [ ] **Step 5: Commit (only when Rohit says so)**

```bash
git add apps/adp/timeoff_audit.py scratch/verify_timeoff_policy_mapping.py
git commit -m "feat(adp-timeoff): fill each template row from the ADP policies mapped to it"
```

---

### Task 2: Mapping step in the Streamlit UI

**Files:**
- Modify: `apps/adp/timeoff_audit.py` (`render_ui`; add `_file_sig`, `_mapping_context`, `_render_mapping`, `_render_left_out`)
- Test: `scratch/verify_timeoff_policy_mapping.py` (add group `ui`)

**Interfaces:**
- Consumes: `read_adp_balances`, `read_template_rows`, `policy_summary`, `auto_map`, `run_tool(..., mapping, include_salaried)`, `DO_NOT_IMPORT` from Task 1.
- Produces: session keys `adp_timeoff_ctx` (parsed upload pair) and `adp_timeoff_result` (unchanged name; its `signature` now also covers the mapping and the checkbox).

- [ ] **Step 1: Add the failing `ui` group**

Append to `scratch/verify_timeoff_policy_mapping.py`, before `GROUPS`:

```python
def group_ui():
    print("\n== ui")
    import json
    from streamlit.testing.v1 import AppTest

    def script():
        import io as _io
        import json as _json
        import os as _os
        import sys as _sys
        _sys.path.insert(0, _os.environ["TO_REPO_ROOT"])
        import streamlit as _st
        from apps.adp import timeoff_audit
        files = _json.loads(_os.environ.get("TO_FILES", "{}"))

        class _U(_io.BytesIO):
            def __init__(self, p):
                with open(p, "rb") as fh:
                    super().__init__(fh.read())
                self.name = _os.path.basename(p)
                self.size = len(self.getvalue())

        _st.file_uploader = lambda *a, **k: (_U(files[k["key"]]) if k.get("key") in files
                                             else None)
        timeoff_audit.render_ui()

    a, t, c = EXPRESS
    os.environ["TO_REPO_ROOT"] = ROOT
    os.environ["TO_FILES"] = json.dumps({"at_a": a, "at_u": t})
    at = AppTest.from_function(script, default_timeout=180).run()
    check("mapping renders once ADP + template are in", not at.exception and len(at.selectbox) == 1,
          at.exception or len(at.selectbox))
    sb = at.selectbox[0]
    check("Amazon PTO pre-mapped to Paid PTO", "Amazon PTO" in sb.label and sb.value == "Paid PTO",
          (sb.label, sb.value))
    check("Salaried checkbox starts unchecked", len(at.checkbox) == 1 and at.checkbox[0].value is False)

    os.environ["TO_FILES"] = json.dumps({"at_a": a, "at_u": t, "at_c": c})
    at.run()
    at.button(key="run_timeoff_adp").click().run()
    metrics = {m.label: m.value for m in at.metric}
    expect = new_run(EXPRESS)["filled"]
    check("Generate writes the expected balances",
          len(at.get("download_button")) == 2 and str(metrics.get("Balances written")) == str(expect),
          (len(at.get("download_button")), metrics, expect))
    check("left-out warning mentions the Salaried rows",
          any("Salaried" in w.value for w in at.warning), [w.value for w in at.warning])

    at.selectbox[0].select(ta.DO_NOT_IMPORT).run()
    check("changing a mapping discards the previous downloads",
          len(at.get("download_button")) == 0)
    at.button(key="run_timeoff_adp").click().run()
    metrics = {m.label: m.value for m in at.metric}
    check("nothing mapped -> nothing written", str(metrics.get("Balances written")) == "0", metrics)
```

and register it: `GROUPS = {"readers": group_readers, "filling": group_filling, "audit": group_audit, "ui": group_ui}`.

- [ ] **Step 2: Run it and confirm it fails**

Run: `py -3 scratch/verify_timeoff_policy_mapping.py ui`
Expected: `FAIL` on "mapping renders once ADP + template are in" (0 selectboxes).

- [ ] **Step 3: Implement the UI**

Add above `render_ui`:

```python
def _file_sig(f):
    return (f.name, getattr(f, "size", None)) if f is not None else None


def _mapping_context(f_a, f_u):
    """Parse the ADP file and the template once per upload pair (cached)."""
    key = (_file_sig(f_a), _file_sig(f_u))
    ctx = st.session_state.get("adp_timeoff_ctx")
    if ctx and ctx["key"] == key:
        return ctx
    with st.spinner("Reading policies..."):
        adp_df, err = read_adp_balances(f_a)
        tpl = None
        if not err:
            tpl, err = read_template_rows(f_u)
    if err:
        ctx = {"key": key, "error": err}
    else:
        summary = policy_summary(adp_df)
        ctx = {"key": key, "error": None, "summary": summary,
               "uzio": tpl["policies"], "has_pay_type": tpl["has_pay_type"],
               "auto": auto_map([p for p, _, _ in summary], tpl["policies"])}
    st.session_state["adp_timeoff_ctx"] = ctx
    return ctx


def _render_mapping(ctx):
    """One dropdown per ADP policy plus the Salaried checkbox."""
    st.subheader("Policy Mapping")
    st.caption(
        "Pick the UZIO policy each ADP policy's balance goes into. PTO is "
        "pre-selected; everything else starts on Do not import, because a wrong "
        "guess would move hours into the wrong policy. ADP policies mapped to the "
        "same UZIO policy are added together. A UZIO policy nothing is mapped to "
        "is left exactly as the template has it."
    )
    # Widget keys carry the upload pair, so a new client starts from its own
    # auto-mapping instead of inheriting the previous client's choices.
    tag = zlib.crc32(repr(ctx["key"]).encode())
    options = [DO_NOT_IMPORT] + ctx["uzio"]
    mapping = {}
    for i, (pol, n, total) in enumerate(ctx["summary"]):
        shown = "—" if pd.isna(total) else "%.2f" % total
        default = ctx["auto"].get(pol, DO_NOT_IMPORT)
        mapping[pol] = st.selectbox(
            f"**{pol}** · {n} employee(s) · {shown} total",
            options, index=options.index(default), key=f"to_pol_{tag}_{i}")
    include_salaried = st.checkbox(
        "Fill balances for Salaried employees too", value=False, key=f"to_sal_{tag}",
        help="Unticked, rows whose Pay Type is Salaried are left exactly as the "
             "template has them.")
    if not ctx["has_pay_type"]:
        st.caption("This template has no Pay Type column, so nobody is treated as Salaried.")
    return mapping, include_salaried


def _render_left_out(stats):
    """Everything deliberately not written — no silent omissions."""
    notes = []
    if stats["salaried"]:
        notes.append(f"{stats['salaried']} Salaried row(s) left as the template has them — "
                     "tick **Fill balances for Salaried employees too** to fill them.")
    for pol, n, total in stats["not_imported"]:
        notes.append(f"ADP policy **{pol}** not imported — {n} employee(s), "
                     f"{total:.2f} total.")
    if stats["unmapped_uzio"]:
        notes.append("No ADP policy mapped, so not filled: "
                     + ", ".join(f"**{p}**" for p in stats["unmapped_uzio"]) + ".")
    if notes:
        st.warning("**Left out on purpose — also listed in the audit report:**\n\n"
                   + "\n".join(f"- {n}" for n in notes))
```

Add `import zlib` to the imports.

In `render_ui`:
- in the intro markdown, after "All three files are required." add the sentence "Once the ADP file and the template are in, map each ADP policy to the UZIO policy its balance should go into.";
- after the three uploaders:

```python
    mapping, include_salaried = None, False
    if f_a is not None and f_u is not None:
        ctx = _mapping_context(f_a, f_u)
        if ctx["error"]:
            st.error(ctx["error"])
            return
        mapping, include_salaried = _render_mapping(ctx)
```

- the cached-result signature covers the settings:

```python
    settings = (tuple(sorted(mapping.items())) if mapping else None, include_salaried)
    sig = (_signature(f_a, f_u, f_c), settings)
```

- the Generate call becomes `run_tool(f_a, f_u, f_c, mapping, include_salaried)`;
- after the four metrics: `_render_left_out(stats)`.

- [ ] **Step 4: Run and confirm it passes**

Run: `py -3 scratch/verify_timeoff_policy_mapping.py`
Expected: every group `OK`, `PASS - every check held`.

- [ ] **Step 5: Commit (only when Rohit says so)**

```bash
git add apps/adp/timeoff_audit.py scratch/verify_timeoff_policy_mapping.py
git commit -m "feat(adp-timeoff): map ADP policies to UZIO policies before filling"
```

---

### Task 3: Keep the Exception Summary verification valid

`scratch/verify_timeoff_exception_status.py` compares the working tree against a baseline with `run_tool(a, t, c)`. The new defaults (auto-mapping, Salaried off) change that output on purpose, so it must run the new code in legacy mode to keep testing what it was written to test.

**Files:**
- Modify: `scratch/verify_timeoff_exception_status.py`

**Interfaces:**
- Consumes: `read_adp_balances`, `read_template_rows`, `policy_summary`, `run_tool(..., mapping, include_salaried)`.

- [ ] **Step 1: Run it and confirm it now fails**

Run: `py -3 scratch/verify_timeoff_exception_status.py`
Expected: `FAIL` on "filled template unchanged" for Express (the 9 Salaried rows).

- [ ] **Step 2: Run the new code in legacy mode**

Add after `sheet_df`:

```python
def legacy_mapping(adp_b, tpl_b):
    """Every ADP policy -> the template's one policy: what the baseline did."""
    adp_df, _ = new.read_adp_balances(U(adp_b, "a.xlsx"))
    tpl, _ = new.read_template_rows(U(tpl_b, "t.xlsx"))
    return {p: tpl["policies"][0] for p, _, _ in new.policy_summary(adp_df)}
```

In `run_case`, the new call becomes:

```python
    n_fill, n_audit, n_stats = new.run_tool(U(adp_b, "a.xlsx"), U(tpl_b, "t.xlsx"),
                                            U(cen_b, "c.xlsm"),
                                            mapping=legacy_mapping(adp_b, tpl_b),
                                            include_salaried=True)
```

and the stats check compares the baseline's keys only:

```python
    check("stats unchanged", {k: n_stats[k] for k in o_stats} == o_stats, (o_stats, n_stats))
```

- [ ] **Step 3: Run and confirm it passes**

Run: `py -3 scratch/verify_timeoff_exception_status.py`
Expected: `PASS - every check held`.

- [ ] **Step 4: Commit (only when Rohit says so)**

```bash
git add scratch/verify_timeoff_exception_status.py
git commit -m "test(adp-timeoff): keep the exception-status check on legacy mapping"
```
