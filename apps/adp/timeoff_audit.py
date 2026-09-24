import io
import re
import zlib

import openpyxl
import pandas as pd
import streamlit as st
from openpyxl.utils.dataframe import dataframe_to_rows

from apps.adp.prior_payroll_sanity import _evaluate_cell

APP_TITLE = "ADP vs Uzio – Time Off Tool"

# Both UZIO workbooks (Time Off Import, Employee Census) put their headers on
# row 4 with a title/notes block above.
UZIO_HEADER_ROW = 4

EXCEPTION_COLUMNS = ["Employee ID", "Employee Name", "Employment Status",
                     "Termination Date", "Issue Category", "ADP Balance"]

# The mapping dropdown's "leave this ADP policy out" choice.
DO_NOT_IMPORT = "Do not import"

# Auto-mapping guesses PTO and nothing else: a wrong guess on a leave policy
# would move hours into the wrong bucket, and look plausible enough to be
# accepted unread.
_PTO = re.compile(r"\bPTO\b|paid\s+time\s+off", re.I)
PREFERRED_PTO_POLICY = "paid pto"


def clean_id(x):
    """Normalize Employee ID (remove .0, strip, remove leading zeros)."""
    if pd.isna(x):
        return ""
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    # Remove leading zeros to match typically
    s = s.lstrip("0")
    return s


def _norm_header(c):
    """UZIO headers carry stray spaces, embedded newlines and required-field
    asterisks (' Employee ID*', 'Employment\\nStatus*'). Flatten them so a
    lookup by plain name works."""
    return re.sub(r"\s+", " ", str(c)).strip().rstrip("*").strip().lower()


def _find(cols, *needles):
    """First column whose normalized header contains every needle."""
    for c in cols:
        n = _norm_header(c)
        if all(x in n for x in needles):
            return c
    return None


def _is_blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def _template_sheet(wb):
    """The template sheet: the first one whose row 4 carries an Employee ID header."""
    return next((s for s in wb.worksheets
                 if _find([s.cell(row=UZIO_HEADER_ROW, column=c).value
                           for c in range(1, s.max_column + 1)], "employee id")), None)


# ─────────────────────────────────────────────────────────────────────────────
# ADP side
# ─────────────────────────────────────────────────────────────────────────────

def read_adp_balances(file_adp):
    """One row per employee per ADP time-off policy, with that policy's balance.

    ADP writes money cells as `=ROUND(x, 2.0)` formulas WITHOUT caching the
    computed value, so `pd.read_excel` (which reads the cache) sees the whole
    BALANCE AMOUNT column as null. Summing an all-null group then yields 0.0
    rather than NaN, which silently filled every Opening Balance with zero. Read
    through openpyxl and evaluate the formulas instead — the same treatment
    `prior_payroll_sanity` already gives ADP money columns.

    ADP's "Totals For <name> - <policy> -- Balance Amount:" subtotal rows carry
    no ASSOCIATE ID, so dropping blank IDs removes them and the per-transaction
    rows sum to exactly ADP's own subtotal.

    Policies are kept apart because the UZIO template has one row per employee
    per UZIO policy. Adding every ADP policy into one number and writing it into
    each of those rows overwrote Moses's NY State Prenatal Leave with PTO hours.

    Returns (DataFrame[id, policy, balance, name], error).
    """
    if hasattr(file_adp, "seek"):
        file_adp.seek(0)
    try:
        wb = openpyxl.load_workbook(file_adp, data_only=False)
    except Exception as e:
        return None, f"Error reading ADP file: {e}"

    ws = None
    for sheet in wb.worksheets:
        head = [sheet.cell(row=1, column=c).value for c in range(1, sheet.max_column + 1)]
        if _find(head, "associate id") and _find(head, "balance amount"):
            ws = sheet
            break
    if ws is None:
        return None, ("Could not find a sheet with both `ASSOCIATE ID` and "
                      "`BALANCE AMOUNT` columns in the ADP file.")

    head = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    idx = {h: i + 1 for i, h in enumerate(head)}
    c_id = idx[_find(head, "associate id")]
    c_bal = idx[_find(head, "balance amount")]
    name_hdr = next((h for h in head
                     if h and "name" in _norm_header(h) and "policy" not in _norm_header(h)), None)
    c_name = idx[name_hdr] if name_hdr else None
    h_pol = _find(head, "policy name")
    c_pol = idx[h_pol] if h_pol else None

    rows = []
    for r in range(2, ws.max_row + 1):
        eid = clean_id(ws.cell(row=r, column=c_id).value)
        if not eid:
            continue          # subtotal / blank rows
        rows.append({
            "id": eid,
            "name": ws.cell(row=r, column=c_name).value if c_name else "N/A",
            "policy": (str(ws.cell(row=r, column=c_pol).value or "").strip()
                       if c_pol else "") or "(no policy name)",
            "balance": _raw_amount(ws.cell(row=r, column=c_bal).value),
        })
    if not rows:
        return None, "No valid Employee IDs found in ADP file."

    df = pd.DataFrame(rows)
    df["balance"] = pd.to_numeric(df["balance"], errors="coerce")
    out = (df.groupby(["id", "policy"])
             .agg(balance=("balance", _sum_money), name=("name", "first"))
             .reset_index())
    return out, None


_ROUND_FORMULA = re.compile(r"^\s*=\s*ROUND\(\s*(-?\d*\.?\d+(?:[eE][+-]?\d+)?)\s*,", re.I)


def _raw_amount(cell):
    """The amount ADP stored, BEFORE its own per-row rounding.

    Each transaction is written as `=ROUND(x, 2.0)`, and ADP's own
    "Totals For ... -- Balance Amount:" row holds round(sum of x). Rounding
    every row first and adding afterwards loses the dropped fractions, which
    add up to a cent often enough to matter: 281 of 2504 employee/policy
    totals across the client files on this machine came out 0.01 away from
    what the client's own ADP report says. So the inner x is summed and
    `_sum_money` rounds once, the way ADP does.

    Anything that is not a plain `=ROUND(number, n)` falls back to the
    evaluator.
    """
    if isinstance(cell, str):
        m = _ROUND_FORMULA.match(cell)
        if m:
            return float(m.group(1))
    return _evaluate_cell(cell)


def _sum_money(series):
    """Total a set of 2-decimal money values back into a 2-decimal money value.

    `min_count=1` keeps an employee with no readable amounts at NaN rather than
    reporting a real 0.00 balance.

    The rounding matters: the transaction amounts are exact to the cent as
    decimals, but not in binary floating point, so adding them leaves dust.
    3.62 + 24.42 - 28.04 is 0.00 on paper and 3.55e-15 in a float. On this
    client 71 of 132 employees carried such dust; it stayed invisible wherever
    the total was large (18.709999999999994 renders as 18.71) and surfaced only
    where the total was exactly zero, which Excel then showed as `3.55271E-15`.
    """
    # `+ 0.0` turns the -0.0 that round() leaves on a tiny negative remainder
    # into 0.0, so a balance netting to zero is never written as "-0".
    total = series.sum(min_count=1)
    return total if pd.isna(total) else round(total, 2) + 0.0


def policy_summary(adp_df):
    """[(ADP policy, employees, total balance)] sorted by policy name."""
    return [(pol, int(g["id"].nunique()), _sum_money(g["balance"]))
            for pol, g in adp_df.groupby("policy")]


# ─────────────────────────────────────────────────────────────────────────────
# UZIO census
# ─────────────────────────────────────────────────────────────────────────────

def read_census(file_census):
    """Employee ID → employment status + termination date from a UZIO census.

    Returns (DataFrame[id, status, termination date, name], error).
    """
    if hasattr(file_census, "seek"):
        file_census.seek(0)
    try:
        book = pd.read_excel(file_census, sheet_name=None,
                             header=UZIO_HEADER_ROW - 1, dtype=str)
    except Exception as e:
        return None, f"Error reading census file: {e}"

    for df in book.values():
        c_id = _find(df.columns, "employee id")
        c_st = _find(df.columns, "employment", "status")
        if c_id and c_st:
            c_td = _find(df.columns, "termination date")
            c_fn = _find(df.columns, "employee first name")
            c_ln = _find(df.columns, "employee last name")
            out = pd.DataFrame({
                "id": df[c_id].apply(clean_id),
                "status": df[c_st].fillna("").astype(str).str.strip(),
                "termination date": (df[c_td].fillna("").astype(str).str.strip()
                                     if c_td else ""),
                "census name": ((df[c_fn].fillna("") + " " + df[c_ln].fillna("")).str.strip()
                                if c_fn and c_ln else ""),
            })
            return out[out["id"] != ""].reset_index(drop=True), None

    return None, ("Could not find `Employee ID` and `Employment Status` columns "
                  f"on row {UZIO_HEADER_ROW} of any sheet in the census file.")


# ─────────────────────────────────────────────────────────────────────────────
# UZIO template + the ADP -> UZIO policy mapping
# ─────────────────────────────────────────────────────────────────────────────

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


def plan_fill(tpl, adp_df, mapping, include_salaried, include_blank_hourly=True):
    """Decide what happens to every template row.

    Row (employee E, UZIO policy P) is written with the sum of E's balances
    across every ADP policy mapped to P. It is left exactly as it is when the
    template leaves it blank (policy not assigned), when nothing is mapped to
    P, when E has no balance in any policy mapped to P, or when E is Salaried
    and `include_salaried` is off.

    `include_blank_hourly` (on by default) fills a BLANK row when the employee
    is Hourly and has a balance — a balance of 0.00 included. That ASSIGNS the
    policy in UZIO, so the screen says how many rows it filled and the audit
    names them. A Salaried blank row is never filled, whatever
    `include_salaried` says: that switch is for Salaried rows which already
    carry a value.

    Returns {"decisions": [(row, action, amount)], "mapped": {(E, P): amount},
             "emp_total": {E: amount}, "targets": {mapped UZIO policies}}.
    action is one of "write", "write_blank", "blank", "no_mapping",
    "no_balance", "salaried".
    """
    targets = {p for p in mapping.values() if p != DO_NOT_IMPORT}
    df = adp_df.assign(uzio=adp_df["policy"].map(lambda p: mapping.get(p, DO_NOT_IMPORT)))
    df = df[df["uzio"] != DO_NOT_IMPORT]
    mapped = df.groupby(["id", "uzio"])["balance"].agg(_sum_money).to_dict()
    emp_total = df.groupby("id")["balance"].agg(_sum_money).to_dict()

    decisions = []
    for t in tpl["rows"]:
        amount = mapped.get((t["id"], t["policy"]))
        has_amount = amount is not None and not pd.isna(amount)
        if _is_blank(t["opening"]):
            action = ("write_blank"
                      if (include_blank_hourly and not t["salaried"]
                          and t["policy"] in targets and has_amount)
                      else "blank")
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


# ─────────────────────────────────────────────────────────────────────────────
# File 1 — the filled import template
# ─────────────────────────────────────────────────────────────────────────────

def fill_import_template(file_uzio, decisions):
    """Write the planned balances into a copy of the UZIO Time Off Import template.

    The workbook is returned untouched apart from the Opening Balance cells of
    the rows `plan_fill` marked "write" — same sheets, same formatting — so it
    can be uploaded to UZIO as-is. A BLANK Opening Balance (policy not
    assigned) is never among them.

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
        if action in ("write", "write_blank"):
            ws.cell(row=t["row"], column=pos[h_bal]).value = amount
            filled += 1
    return wb, filled, None


# ─────────────────────────────────────────────────────────────────────────────
# File 2 — the audit workbook
# ─────────────────────────────────────────────────────────────────────────────

def build_audit_sheets(file_uzio, tpl, adp_df, census_df, plan, mapping, auto):
    """Every audit view, as {sheet name: DataFrame}.

    An employee whose template row exists but has a BLANK balance is an
    unassigned policy, NOT missing from UZIO — both used to be reported, so the
    same person appeared twice. Template rows are matched regardless of whether
    the balance is filled, and only genuinely absent IDs count as missing.

    An employee's "ADP Balance" is the sum of their MAPPED policies only; a
    policy set to Do not import contributes nothing and is reported instead.
    """
    file_uzio.seek(0)
    df_u = pd.read_excel(file_uzio, sheet_name=tpl["sheet"],
                         header=UZIO_HEADER_ROW - 1)
    c_id = _find(df_u.columns, "employee id")
    c_bal = _find(df_u.columns, "opening balance") or _find(df_u.columns, "operating balance")
    # The template splits the name across two columns; reading only the first
    # one put "Ryan" and "Caleb" in the Exception Summary instead of full names.
    c_fn = _find(df_u.columns, "employee first name")
    c_ln = _find(df_u.columns, "employee last name")
    c_name = _find(df_u.columns, "employee name")       # single-column fallback

    def template_name(row):
        parts = [str(row[c]).strip() for c in (c_fn, c_ln)
                 if c and pd.notna(row[c]) and str(row[c]).strip()]
        if parts:
            return " ".join(parts)
        if c_name and pd.notna(row[c_name]) and str(row[c_name]).strip():
            return str(row[c_name]).strip()
        return "N/A"

    balance_map = plan["emp_total"]                      # mapped policies only
    name_map = adp_df.groupby("id")["name"].first().to_dict()

    # A blank row we filled is no longer unassigned — we just assigned it. It
    # leaves the Unassigned sheet and is named, with its amount, as a policy
    # the client is about to gain in UZIO.
    c_pol_u = _find(df_u.columns, "policy")
    filled_blanks = {(t["id"], t["policy"]): amount
                     for t, action, amount in plan["decisions"] if action == "write_blank"}

    template_ids, unassigned_rows, exceptions = set(), [], []
    for _, row in df_u.iterrows():
        eid = clean_id(row[c_id])
        if eid:
            template_ids.add(eid)                       # present, filled or not
        val = row[c_bal]
        if pd.isna(val) or str(val).strip() == "":
            policy = (str(row[c_pol_u]).strip() if c_pol_u and pd.notna(row[c_pol_u])
                      else "")
            if (eid, policy) in filled_blanks:
                exceptions.append({
                    "Employee ID": str(row[c_id]) if pd.notna(row[c_id]) else "",
                    "Employee Name": template_name(row),
                    "Issue Category": f"Blank filled — policy assigned ({policy})",
                    "ADP Balance": filled_blanks[(eid, policy)],
                })
                continue
            unassigned_rows.append(row.to_dict())
            exceptions.append({
                "Employee ID": str(row[c_id]) if pd.notna(row[c_id]) else "",
                "Employee Name": template_name(row),
                "Issue Category": "Unassigned Policy (Blank Balance)",
                "ADP Balance": "",
            })

    # Missing = a mapped balance with no (employee, UZIO policy) row to go into.
    # For a one-policy client that is exactly "employee absent from the template".
    template_pairs = {(t["id"], t["policy"]) for t in tpl["rows"]}
    missing = []
    for (eid, pol), val in plan["mapped"].items():
        if (eid, pol) in template_pairs or pd.isna(val):
            continue
        name = name_map.get(eid, "N/A")
        missing.append({"Employee ID": eid, "Employee Name": name, "Total Balance": val})
        exceptions.append({"Employee ID": eid, "Employee Name": name,
                           "Issue Category": "Missing in Uzio Template",
                           "ADP Balance": val})

    sheets = {"Policy Mapping": _policy_mapping_sheet(adp_df, tpl, mapping, auto,
                                                      plan["targets"])}
    status = (dict(zip(census_df["id"], census_df["status"]))
              if census_df is not None else {})
    termdt = (dict(zip(census_df["id"], census_df["termination date"]))
              if census_df is not None else {})

    if census_df is not None:
        rows = []
        for eid, bal in balance_map.items():
            st_val = str(status.get(eid, "")).strip()
            rows.append({
                "Employee ID": eid,
                "Employee Name": name_map.get(eid, "N/A"),
                "ADP Balance": bal,
                "UZIO Employment Status": st_val or "(not in census)",
                "Termination Date": termdt.get(eid, ""),
                "In Import Template": "Yes" if eid in template_ids else "No",
            })
        # Named columns: with nothing mapped `rows` is empty, and a bare
        # DataFrame([]) has no columns for the ranking below to read.
        df_status = pd.DataFrame(rows, columns=[
            "Employee ID", "Employee Name", "ADP Balance",
            "UZIO Employment Status", "Termination Date", "In Import Template"])
        # Terminated first — those are the rows to act on.
        df_status["_rank"] = df_status["UZIO Employment Status"].str.lower().map(
            lambda s: 0 if s.startswith("terminated") else (2 if s == "active" else 1))
        df_status = (df_status.sort_values(["_rank", "ADP Balance"], ascending=[True, False])
                     .drop(columns="_rank").reset_index(drop=True))
        sheets["Balance vs UZIO Status"] = df_status

        for _, r in df_status[df_status["UZIO Employment Status"]
                              .str.lower().str.startswith("terminated")].iterrows():
            exceptions.append({
                "Employee ID": r["Employee ID"], "Employee Name": r["Employee Name"],
                "Issue Category": "Terminated in UZIO but ADP sent a balance",
                "ADP Balance": r["ADP Balance"],
            })

    # Left out on purpose — each on the record, none silently.
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

    # "Missing in Uzio" and "ADP Grouped Data" are deliberately NOT emitted as
    # sheets: both were fully contained in "Balance vs UZIO Status". Grouped Data
    # is its first three columns, and Missing is it filtered to
    # `In Import Template = No`. The missing employees are still computed above,
    # because Exception Summary and the UI counters need them.
    sheets["Unassigned Policies"] = (pd.DataFrame(unassigned_rows) if unassigned_rows
                                     else pd.DataFrame({"Message": ["No unassigned policies found"]}))
    # Every exception carries the employee's UZIO status and termination date,
    # so an issue on someone already terminated can be told apart at a glance.
    # Unassigned-policy rows hold the template's raw ID, hence clean_id here.
    for e in exceptions:
        eid = clean_id(e["Employee ID"])
        e["Employment Status"] = str(status.get(eid, "")).strip() or "(not in census)"
        e["Termination Date"] = termdt.get(eid, "")
    sheets["Exception Summary"] = (pd.DataFrame(exceptions, columns=EXCEPTION_COLUMNS)
                                   if exceptions
                                   else pd.DataFrame({"Message": ["No exceptions found"]}))

    counts = {
        "missing": len(missing),
        "unassigned": len(unassigned_rows),
        "salaried": sum(1 for _, a, _ in plan["decisions"] if a == "salaried"),
        "blank_filled": sum(1 for _, a, _ in plan["decisions"] if a == "write_blank"),
        "not_imported": [(pol, int(g["id"].nunique()), _sum_money(g["balance"]))
                         for pol, g in left_out.groupby("policy")],
        "unmapped_uzio": [p for p in tpl["policies"] if p not in plan["targets"]],
    }
    return sheets, counts


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


def audit_workbook_bytes(sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, df in sheets.items():
        ws = wb.create_sheet(title=name[:31])
        for r in dataframe_to_rows(df, index=False, header=True):
            ws.append(r)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def run_tool(file_adp, file_uzio, file_census, mapping=None, include_salaried=False,
             include_blank_hourly=True):
    """Returns (filled_template_bytes, audit_bytes, stats) or (None, None, None).

    The census is required: the Balance vs UZIO Status sheet and the Exception
    Summary's Employment Status / Termination Date columns all come from it.

    `mapping` is {ADP policy: UZIO policy or DO_NOT_IMPORT}; None means the
    auto-mapping. `include_salaried` is the "Fill balances for Salaried
    employees too" checkbox.
    """
    if file_census is None:
        st.error("Please upload the UZIO Employee Census.")
        return None, None, None

    adp_df, err = read_adp_balances(file_adp)
    if err:
        st.error(err)
        return None, None, None

    census_df, err = read_census(file_census)
    if err:
        st.error(err)
        return None, None, None

    tpl, err = read_template_rows(file_uzio)
    if err:
        st.error(err)
        return None, None, None

    auto = auto_map([p for p, _, _ in policy_summary(adp_df)], tpl["policies"])
    if mapping is None:
        mapping = auto
    plan = plan_fill(tpl, adp_df, mapping, include_salaried, include_blank_hourly)

    wb_filled, filled, err = fill_import_template(file_uzio, plan["decisions"])
    if err:
        st.error(err)
        return None, None, None

    sheets, counts = build_audit_sheets(file_uzio, tpl, adp_df, census_df,
                                        plan, mapping, auto)

    buf = io.BytesIO()
    wb_filled.save(buf)

    stats = {
        "employees": int(adp_df["id"].nunique()),
        "filled": filled,
        "missing": counts["missing"],
        "unassigned": counts["unassigned"],
        "terminated": (int(sheets["Balance vs UZIO Status"]["UZIO Employment Status"]
                           .str.lower().str.startswith("terminated").sum())
                       if "Balance vs UZIO Status" in sheets else 0),
        "salaried": counts["salaried"],
        "blank_filled": counts["blank_filled"],
        "not_imported": counts["not_imported"],
        "unmapped_uzio": counts["unmapped_uzio"],
        "has_pay_type": tpl["has_pay_type"],
    }
    return buf.getvalue(), audit_workbook_bytes(sheets), stats


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
    include_blank_hourly = st.checkbox(
        "Fill blank Opening Balance for Hourly employees (assigns the policy in UZIO)",
        value=True, key=f"to_blank_{tag}",
        help="A blank Opening Balance means the policy is not assigned to that "
             "employee. Ticked, an Hourly employee's blank row is filled from ADP, "
             "which assigns the policy. Salaried blank rows are never filled.")
    if not ctx["has_pay_type"]:
        st.caption("This template has no Pay Type column, so nobody is treated as Salaried.")
    return mapping, include_salaried, include_blank_hourly


def _render_outcome(stats):
    """Green when something was written; red, with the reason, when nothing was."""
    if stats["blank_filled"]:
        st.info("**%d blank row(s) filled** — those employees will have the policy "
                "assigned in UZIO. They are listed in the audit report."
                % stats["blank_filled"])
    if stats["filled"]:
        st.success("Both files are ready — download them one at a time.")
        return
    reasons = []
    if stats["unassigned"]:
        reasons.append("%d template row(s) have a blank Opening Balance, so no policy "
                       "is assigned to them" % stats["unassigned"])
    if stats["salaried"]:
        reasons.append("%d Salaried row(s) were skipped" % stats["salaried"])
    if stats["unmapped_uzio"]:
        reasons.append("no ADP policy is mapped to "
                       + ", ".join("**%s**" % p for p in stats["unmapped_uzio"]))
    if stats["not_imported"]:
        reasons.append("these ADP policies are set to Do not import: "
                       + ", ".join("**%s**" % p for p, _, _ in stats["not_imported"]))
    if stats["missing"]:
        reasons.append("%d employee balance(s) have no matching row in the template"
                       % stats["missing"])
    st.error("**No balance was written — the filled template is the same as the one "
             "you uploaded.**\n\n"
             + ("\n".join("- %s" % r for r in reasons) if reasons
                else "- nothing in the ADP file matched this template"))


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


def render_ui():
    st.title(APP_TITLE)
    client_name = st.text_input("Client Name", value="Client", key="adp_timeoff_client")

    st.markdown("""
    **Upload**
    1. **ADP Time Off Balance Summary** (.xlsx)
    2. **Uzio Time Off Import Template** (.xlsx)
    3. **UZIO Employee Census** (.xlsx / .xlsm)

    All three files are required. Once the ADP file and the template are in,
    map each ADP policy to the UZIO policy its balance should go into.

    **You get two separate files**
    - `<Client>_Time off Import_filled.xlsx` — your template, unchanged except the
      filled Opening Balance column. Upload it to UZIO as-is.
    - `<Client>_Uzio_ADP_TimeOff_Audit_Report_<timestamp>.xlsx` — the audit only.

    The census gives the audit a **Balance vs UZIO Status** sheet showing every
    employee ADP sent a balance for, with their UZIO employment status and
    termination date — terminated employees first — and adds the same two
    columns to every row of the **Exception Summary**.
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        f_a = st.file_uploader("ADP Balance Summary", type=["xlsx"], key="at_a")
    with col2:
        f_u = st.file_uploader("Uzio Template", type=["xlsx"], key="at_u")
    with col3:
        f_c = st.file_uploader("UZIO Census", type=["xlsx", "xlsm"], key="at_c")

    mapping, include_salaried, include_blank_hourly = None, False, False
    if f_a is not None and f_u is not None:
        ctx = _mapping_context(f_a, f_u)
        if ctx["error"]:
            st.error(ctx["error"])
            return
        mapping, include_salaried, include_blank_hourly = _render_mapping(ctx)

    # st.download_button triggers a rerun of its own, so results computed inside
    # the Generate block would vanish the moment the first file is downloaded —
    # taking the second download button with them. Keep them in session_state and
    # render the buttons OUTSIDE that block.
    SKEY = "adp_timeoff_result"

    def _signature(*files):
        return tuple((f.name, getattr(f, "size", None)) if f is not None else None
                     for f in files)

    # The mapping and the checkbox are part of what produced a result, so
    # changing either discards it — a download always matches the screen.
    settings = (tuple(sorted(mapping.items())) if mapping else None,
                include_salaried, include_blank_hourly)
    sig = (_signature(f_a, f_u, f_c), settings)
    cached = st.session_state.get(SKEY)
    if cached and cached.get("signature") != sig:
        # Different uploads than the ones that produced these files — drop them
        # rather than let someone download the previous client's data.
        del st.session_state[SKEY]
        cached = None

    if st.button("Generate Files", key="run_timeoff_adp"):
        missing = [label for label, f in (("ADP Balance Summary", f_a),
                                          ("Uzio Template", f_u),
                                          ("UZIO Census", f_c)) if f is None]
        if missing:
            st.error("Please upload: " + ", ".join(missing) + ".")
            return
        try:
            with st.spinner("Processing..."):
                filled_bytes, audit_bytes, stats = run_tool(f_a, f_u, f_c, mapping,
                                                            include_salaried,
                                                            include_blank_hourly)
            if not filled_bytes:
                return
            st.session_state[SKEY] = {
                "signature": sig,
                "filled": filled_bytes,
                "audit": audit_bytes,
                "stats": stats,
                # Stamped once, so the filename does not change on every rerun.
                "ts": pd.Timestamp.now().strftime("%d_%m_%Y_%H%M"),
            }
            cached = st.session_state[SKEY]
        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.exception(e)
            return

    if not cached:
        return

    stats = cached["stats"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Employees in ADP", stats["employees"])
    c2.metric("Balances written", stats["filled"])
    c3.metric("Missing in UZIO", stats["missing"])
    c4.metric("Terminated in UZIO", stats["terminated"])
    _render_left_out(stats)

    _render_outcome(stats)
    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "⬇️ Time Off Import (filled)",
            data=cached["filled"],
            file_name=f"{client_name}_Time off Import_filled.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            key="to_dl_filled",
        )
    with d2:
        st.download_button(
            "⬇️ Audit Report",
            data=cached["audit"],
            file_name=(f"{client_name}_Uzio_ADP_TimeOff_Audit_Report_"
                       f"{cached['ts']}.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="to_dl_audit",
        )
