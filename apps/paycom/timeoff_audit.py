import io
import re
import zlib

import openpyxl
import pandas as pd
import streamlit as st
from utils.file_io import read_table, read_report
from openpyxl.utils.dataframe import dataframe_to_rows

APP_TITLE = "Paycom vs Uzio – Time Off Tool"

# Both UZIO workbooks (Time Off Import, Employee Census) put their headers on
# row 4 with a title/notes block above.
UZIO_HEADER_ROW = 4

# Filled only when the Employee ID is not in the census: the census employees
# with the same first and last name, as "A09A (TERMINATED)". At Banda three
# such people were in the census under a different EECode (rehires).
POSSIBLE_MATCH = "Possible Census Match"

EXCEPTION_COLUMNS = ["Employee ID", "Employee Name", "Employment Status",
                     "Termination Date", POSSIBLE_MATCH, "Issue Category", "Paycom Balance"]

FUTURE_COLUMNS = ["Employee ID", "Employee Name", "Time-Off Type", "Mapped To",
                  "Available", "Future Approved", "Future Pending", "Net Available",
                  "Employment Status", "Termination Date", POSSIBLE_MATCH]

# The mapping dropdown's "leave this Paycom type out" choice.
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


def _exact(cols, name):
    """The column whose normalized header IS `name` — not merely contains it."""
    return next((c for c in cols if _norm_header(c) == name), None)


def _is_blank(v):
    return v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == ""


def _template_sheet(wb):
    """The template sheet: the first one whose row 4 carries an Employee ID header."""
    return next((s for s in wb.worksheets
                 if _find([s.cell(row=UZIO_HEADER_ROW, column=c).value
                           for c in range(1, s.max_column + 1)], "employee id")), None)


# ─────────────────────────────────────────────────────────────────────────────
# Paycom side
# ─────────────────────────────────────────────────────────────────────────────

def _numbers(series):
    """Paycom amounts as floats. Commas are dropped; blank or junk becomes NaN."""
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False).str.strip(),
                         errors="coerce")


def read_paycom_balances(file_paycom):
    """One row per employee per Paycom Time-Off Type, with its `Available` balance.

    `Available` is what the employee holds today. `Net Available` is
    Available − Future Approved − Future Pending, which the old tool wrote: at
    Banda that put −48.55 into a row whose real balance is 4.98, because 53.53
    hours of leave were already approved for later. The balance column is
    matched EXACTLY, so `Net Available` can never stand in for it.

    The Future columns and `Net Available` are kept for the Future Time Off
    sheet only; a blank or non-numeric future cell counts as 0.

    Returns (DataFrame[id, policy, balance, name, future_approved,
    future_pending, net_available, unit], error).
    """
    try:
        df = read_report(file_paycom, header=0, dtype=str)
    except Exception as e:
        return None, f"Error reading Paycom file: {e}"

    cols = list(df.columns)
    c_id = (_exact(cols, "eecode") or _find(cols, "employee code")
            or _find(cols, "employee id") or _find(cols, "eecode"))
    c_bal = _exact(cols, "available")
    if not c_id or not c_bal:
        return None, ("Could not find an `EECode` and an `Available` column in the "
                      f"Paycom file. Found: {[str(c) for c in cols]}")
    c_pol = _find(cols, "time-off type") or _find(cols, "time off type")
    c_name = _exact(cols, "employee") or _find(cols, "employee name")
    c_fa = _find(cols, "future approved")
    c_fp = _find(cols, "future pending")
    c_net = _exact(cols, "net available")
    c_unit = _find(cols, "unit of time")

    def col(c, default=""):
        return df[c] if c else pd.Series([default] * len(df), index=df.index)

    out = pd.DataFrame({
        "id": col(c_id).apply(clean_id),
        "policy": col(c_pol).fillna("").astype(str).str.strip().replace("", "(no policy name)"),
        "balance": _numbers(col(c_bal)),
        "name": col(c_name, "N/A").fillna("N/A").astype(str).str.strip(),
        "future_approved": _numbers(col(c_fa)).fillna(0.0),
        "future_pending": _numbers(col(c_fp)).fillna(0.0),
        "net_available": _numbers(col(c_net)),
        "unit": col(c_unit).fillna("").astype(str).str.strip(),
    })
    out = out[out["id"] != ""]
    if out.empty:
        return None, "No valid Employee IDs found in the Paycom file."

    # Paycom gives one row per employee and type; summing only guards against
    # the same pair appearing twice.
    out = (out.groupby(["id", "policy"])
              .agg(balance=("balance", _sum_money), name=("name", "first"),
                   future_approved=("future_approved", _sum_money),
                   future_pending=("future_pending", _sum_money),
                   net_available=("net_available", _sum_money),
                   unit=("unit", "first"))
              .reset_index())
    return out, None


def _sum_money(series):
    """Total a set of 2-decimal money values back into a 2-decimal money value.

    `min_count=1` keeps an employee with no readable amounts at NaN rather than
    reporting a real 0.00 balance. Rounding clears float dust (3.62 + 24.42 -
    28.04 is 3.55e-15 in a float), and `+ 0.0` turns a -0.0 into 0.0 so a
    balance netting to zero is never written as "-0".
    """
    total = series.sum(min_count=1)
    return total if pd.isna(total) else round(total, 2) + 0.0


def policy_summary(paycom_df):
    """[(Paycom type, employees, total Available)] sorted by type name."""
    return [(pol, int(g["id"].nunique()), _sum_money(g["balance"]))
            for pol, g in paycom_df.groupby("policy")]


def non_hour_units(paycom_df):
    """[(type, unit, rows)] for every type reported in something other than hours.

    UZIO balances are hours, so a balance in days would be imported 8x too small.
    """
    u = paycom_df["unit"].fillna("").astype(str).str.strip()
    odd = paycom_df[(u != "") & ~u.str.lower().isin(["hours", "hour", "hrs", "hr"])]
    return [(pol, unit, len(g)) for (pol, unit), g in odd.groupby(["policy", "unit"])]


# ─────────────────────────────────────────────────────────────────────────────
# UZIO census
# ─────────────────────────────────────────────────────────────────────────────

def read_census(file_census):
    """Employee ID → employment status + termination date from a UZIO census.

    Returns (DataFrame[id, status, termination date, first, last], error).
    """
    if hasattr(file_census, "seek"):
        file_census.seek(0)
    try:
        book = read_table(file_census, sheet_name=None,
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
                "first": df[c_fn].fillna("") if c_fn else "",
                "last": df[c_ln].fillna("") if c_ln else "",
            })
            return out[out["id"] != ""].reset_index(drop=True), None

    return None, ("Could not find `Employee ID` and `Employment Status` columns "
                  f"on row {UZIO_HEADER_ROW} of any sheet in the census file.")


def _name_key(first, last):
    """(first word of the first name, last word of the last name), upper case.

    First word only, so a middle name or initial on one side does not block the
    match; last word only, so "DE LA CRUZ" and a template's "Juan De La Cruz"
    agree.
    """
    def words(s):
        return re.sub(r"[^A-Z' -]", " ", str(s or "").upper()).replace("-", " ").split()
    f, l = words(first), words(last)
    return (f[0], l[-1]) if f and l else None


def _split_name(name):
    """(first, last) from Paycom's "LAST, FIRST M" or the template's "First M Last"."""
    s = str(name or "").strip()
    if "," in s:
        last, first = s.split(",", 1)
        return first, last
    parts = s.split()
    return (parts[0], parts[-1]) if len(parts) >= 2 else ("", "")


def census_name_index(census_df):
    """{name key: ["A09A (TERMINATED)", ...]} over every census employee."""
    index = {}
    if census_df is None:
        return index
    for _, r in census_df.iterrows():
        key = _name_key(r["first"], r["last"])
        if key:
            label = f"{r['id']} ({str(r['status']).strip() or 'no status'})"
            index.setdefault(key, []).append(label)
    return index


# ─────────────────────────────────────────────────────────────────────────────
# UZIO template + the Paycom -> UZIO policy mapping
# ─────────────────────────────────────────────────────────────────────────────

def read_template_rows(file_uzio):
    """Every employee row of the UZIO Time Off Import template.

    Returns ({"sheet", "rows", "policies", "has_pay_type"}, error). Each row is
    {"row", "raw_id", "id", "name", "policy", "opening", "salaried"}; `row` is
    the Excel row number the filler writes back to, and `policies` lists the
    distinct Time Off Policy Names in template order.

    "Salaried" is the template's own Pay Type.
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


def auto_map(paycom_policies, uzio_policies):
    """Suggested Paycom -> UZIO policy mapping; the user can change every entry.

    Only PTO is guessed. A Paycom type named with the word PTO (or "Paid Time
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
            for a in paycom_policies}


def plan_fill(tpl, paycom_df, mapping, include_salaried, include_blank_hourly=True):
    """Decide what happens to every template row.

    Row (employee E, UZIO policy P) is written with the sum of E's balances
    across every Paycom type mapped to P. It is left exactly as it is when the
    template leaves it blank (policy not assigned), when nothing is mapped to
    P, when E has no balance in any type mapped to P, or when E is Salaried
    and `include_salaried` is off.

    `include_blank_hourly` (on by default) fills a BLANK row when the employee
    is Hourly and has a balance — a balance of 0.00 included. That ASSIGNS the
    policy in UZIO, so the screen says how many rows it filled and the audit
    names them. A Salaried blank row is never filled, whatever
    `include_salaried` says.

    Returns {"decisions": [(row, action, amount)], "mapped": {(E, P): amount},
             "emp_total": {E: amount}, "targets": {mapped UZIO policies}}.
    action is one of "write", "write_blank", "blank", "no_mapping",
    "no_balance", "salaried".
    """
    targets = {p for p in mapping.values() if p != DO_NOT_IMPORT}
    df = paycom_df.assign(uzio=paycom_df["policy"].map(lambda p: mapping.get(p, DO_NOT_IMPORT)))
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
    the rows `plan_fill` marked "write" / "write_blank" — same sheets, same
    formatting — so it can be uploaded to UZIO as-is.

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

def build_audit_sheets(file_uzio, tpl, paycom_df, census_df, plan, mapping, auto):
    """Every audit view, as {sheet name: DataFrame}.

    An employee whose template row exists but has a BLANK balance is an
    unassigned policy, NOT missing from UZIO. Template rows are matched
    regardless of whether the balance is filled, and only genuinely absent IDs
    count as missing.

    An employee's "Paycom Balance" is the sum of their MAPPED types only; a
    type set to Do not import contributes nothing and is reported instead.
    """
    file_uzio.seek(0)
    df_u = pd.read_excel(file_uzio, sheet_name=tpl["sheet"],
                         header=UZIO_HEADER_ROW - 1)
    c_id = _find(df_u.columns, "employee id")
    c_bal = _find(df_u.columns, "opening balance") or _find(df_u.columns, "operating balance")
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

    balance_map = plan["emp_total"]                      # mapped types only
    name_map = paycom_df.groupby("id")["name"].first().to_dict()

    # A blank row we filled is no longer unassigned — we just assigned it.
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
                    "Paycom Balance": filled_blanks[(eid, policy)],
                })
                continue
            unassigned_rows.append(row.to_dict())
            exceptions.append({
                "Employee ID": str(row[c_id]) if pd.notna(row[c_id]) else "",
                "Employee Name": template_name(row),
                "Issue Category": "Unassigned Policy (Blank Balance)",
                "Paycom Balance": "",
            })

    # Missing = a mapped balance with no (employee, UZIO policy) row to go into.
    template_pairs = {(t["id"], t["policy"]) for t in tpl["rows"]}
    missing = []
    for (eid, pol), val in plan["mapped"].items():
        if (eid, pol) in template_pairs or pd.isna(val):
            continue
        name = name_map.get(eid, "N/A")
        missing.append({"Employee ID": eid, "Employee Name": name, "Total Balance": val})
        exceptions.append({"Employee ID": eid, "Employee Name": name,
                           "Issue Category": "Missing in Uzio Template",
                           "Paycom Balance": val})

    sheets = {"Policy Mapping": _policy_mapping_sheet(paycom_df, tpl, mapping, auto,
                                                      plan["targets"])}
    status = (dict(zip(census_df["id"], census_df["status"]))
              if census_df is not None else {})
    termdt = (dict(zip(census_df["id"], census_df["termination date"]))
              if census_df is not None else {})
    name_index = census_name_index(census_df)

    def possible_match(eid, name):
        """Census employees with this name — only when the ID itself is not there."""
        if census_df is None or eid in status:
            return ""
        return "; ".join(name_index.get(_name_key(*_split_name(name)), []))

    if census_df is not None:
        rows = []
        for eid, bal in balance_map.items():
            st_val = str(status.get(eid, "")).strip()
            rows.append({
                "Employee ID": eid,
                "Employee Name": name_map.get(eid, "N/A"),
                "Paycom Balance": bal,
                "UZIO Employment Status": st_val or "(not in census)",
                "Termination Date": termdt.get(eid, ""),
                POSSIBLE_MATCH: possible_match(eid, name_map.get(eid, "")),
                "In Import Template": "Yes" if eid in template_ids else "No",
            })
        df_status = pd.DataFrame(rows, columns=[
            "Employee ID", "Employee Name", "Paycom Balance",
            "UZIO Employment Status", "Termination Date", POSSIBLE_MATCH,
            "In Import Template"])
        # Terminated first — those are the rows to act on.
        df_status["_rank"] = df_status["UZIO Employment Status"].str.lower().map(
            lambda s: 0 if s.startswith("terminated") else (2 if s == "active" else 1))
        df_status = (df_status.sort_values(["_rank", "Paycom Balance"], ascending=[True, False])
                     .drop(columns="_rank").reset_index(drop=True))
        sheets["Balance vs UZIO Status"] = df_status

        for _, r in df_status[df_status["UZIO Employment Status"]
                              .str.lower().str.startswith("terminated")].iterrows():
            exceptions.append({
                "Employee ID": r["Employee ID"], "Employee Name": r["Employee Name"],
                "Issue Category": "Terminated in UZIO but Paycom sent a balance",
                "Paycom Balance": r["Paycom Balance"],
            })

    # Left out on purpose — each on the record, none silently.
    for t, action, amount in plan["decisions"]:
        if action == "salaried":
            exceptions.append({
                "Employee ID": str(t["raw_id"]), "Employee Name": t["name"],
                "Issue Category": f"Salaried — not filled ({t['policy']})",
                "Paycom Balance": amount,
            })
    left_out = paycom_df[(paycom_df["policy"].map(lambda p: mapping.get(p, DO_NOT_IMPORT))
                          == DO_NOT_IMPORT)
                         & paycom_df["balance"].notna() & (paycom_df["balance"] != 0)]
    for _, r in left_out.iterrows():
        exceptions.append({
            "Employee ID": r["id"], "Employee Name": r["name"],
            "Issue Category": f"Paycom policy not imported ({r['policy']})",
            "Paycom Balance": r["balance"],
        })

    sheets["Unassigned Policies"] = (pd.DataFrame(unassigned_rows) if unassigned_rows
                                     else pd.DataFrame({"Message": ["No unassigned policies found"]}))

    # Future leave Paycom already approved or has pending. Listed here only —
    # not in Exception Summary — so it can be checked against what is entered
    # in UZIO after go-live without being counted twice.
    future = paycom_df[(paycom_df["future_approved"] > 0) | (paycom_df["future_pending"] > 0)]
    sheets["Future Time Off"] = (pd.DataFrame([{
        "Employee ID": r["id"], "Employee Name": r["name"], "Time-Off Type": r["policy"],
        "Mapped To": mapping.get(r["policy"], DO_NOT_IMPORT),
        "Available": r["balance"], "Future Approved": r["future_approved"],
        "Future Pending": r["future_pending"], "Net Available": r["net_available"],
        "Employment Status": str(status.get(r["id"], "")).strip() or "(not in census)",
        "Termination Date": termdt.get(r["id"], ""),
        POSSIBLE_MATCH: possible_match(r["id"], r["name"]),
    } for _, r in future.iterrows()], columns=FUTURE_COLUMNS) if len(future)
        else pd.DataFrame({"Message": ["No future time off found"]}))

    # Every exception carries the employee's UZIO status and termination date.
    # Unassigned-policy rows hold the template's raw ID, hence clean_id here.
    for e in exceptions:
        eid = clean_id(e["Employee ID"])
        e["Employment Status"] = str(status.get(eid, "")).strip() or "(not in census)"
        e["Termination Date"] = termdt.get(eid, "")
        e[POSSIBLE_MATCH] = possible_match(eid, e["Employee Name"])
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
        "future": int(future["id"].nunique()),
    }
    return sheets, counts


def _policy_mapping_sheet(paycom_df, tpl, mapping, auto, targets):
    """Where each Paycom type went, plus every UZIO policy nothing went into."""
    rows = []
    for pol, n, total in policy_summary(paycom_df):
        target = mapping.get(pol, DO_NOT_IMPORT)
        rows.append({"Paycom Time-Off Type": pol, "Mapped To": target, "Employees": n,
                     "Total Paycom Available": total,
                     "Set By": "Auto" if target == auto.get(pol, DO_NOT_IMPORT) else "You"})
    for p in tpl["policies"]:
        if p not in targets:
            rows.append({"Paycom Time-Off Type": "(none)", "Mapped To": p, "Employees": "—",
                         "Total Paycom Available": "—", "Set By": "Not filled"})
    return pd.DataFrame(rows, columns=["Paycom Time-Off Type", "Mapped To", "Employees",
                                       "Total Paycom Available", "Set By"])


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


def run_tool(file_paycom, file_uzio, file_census, mapping=None, include_salaried=False,
             include_blank_hourly=True):
    """Returns (filled_template_bytes, audit_bytes, stats) or (None, None, None).

    All three files are required. `mapping` is {Paycom type: UZIO policy or
    DO_NOT_IMPORT}; None means the auto-mapping.
    """
    if file_census is None:
        st.error("Please upload the UZIO Employee Census.")
        return None, None, None

    paycom_df, err = read_paycom_balances(file_paycom)
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

    auto = auto_map([p for p, _, _ in policy_summary(paycom_df)], tpl["policies"])
    if mapping is None:
        mapping = auto
    plan = plan_fill(tpl, paycom_df, mapping, include_salaried, include_blank_hourly)

    wb_filled, filled, err = fill_import_template(file_uzio, plan["decisions"])
    if err:
        st.error(err)
        return None, None, None

    sheets, counts = build_audit_sheets(file_uzio, tpl, paycom_df, census_df,
                                        plan, mapping, auto)

    buf = io.BytesIO()
    wb_filled.save(buf)

    stats = {
        "employees": int(paycom_df["id"].nunique()),
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
        "future": counts["future"],
        "has_pay_type": tpl["has_pay_type"],
    }
    return buf.getvalue(), audit_workbook_bytes(sheets), stats


def _file_sig(f):
    return (f.name, getattr(f, "size", None)) if f is not None else None


def _mapping_context(f_p, f_u):
    """Parse the Paycom report and the template once per upload pair (cached)."""
    key = (_file_sig(f_p), _file_sig(f_u))
    ctx = st.session_state.get("paycom_timeoff_ctx")
    if ctx and ctx["key"] == key:
        return ctx
    with st.spinner("Reading policies..."):
        paycom_df, err = read_paycom_balances(f_p)
        tpl = None
        if not err:
            tpl, err = read_template_rows(f_u)
    if err:
        ctx = {"key": key, "error": err}
    else:
        summary = policy_summary(paycom_df)
        ctx = {"key": key, "error": None, "summary": summary,
               "uzio": tpl["policies"], "has_pay_type": tpl["has_pay_type"],
               "units": non_hour_units(paycom_df),
               "auto": auto_map([p for p, _, _ in summary], tpl["policies"])}
    st.session_state["paycom_timeoff_ctx"] = ctx
    return ctx


def _render_mapping(ctx):
    """One dropdown per Paycom Time-Off Type plus the two checkboxes."""
    st.subheader("Policy Mapping")
    st.caption(
        "Pick the UZIO policy each Paycom Time-Off Type's **Available** balance goes "
        "into. PTO is pre-selected; everything else starts on Do not import, because "
        "a wrong guess would move hours into the wrong policy. Types mapped to the "
        "same UZIO policy are added together. A UZIO policy nothing is mapped to is "
        "left exactly as the template has it."
    )
    if ctx["units"]:
        st.warning("**Not in hours:** UZIO balances are hours, but Paycom reports "
                   + ", ".join(f"**{pol}** in {unit} ({n} row(s))"
                               for pol, unit, n in ctx["units"])
                   + ". Check those balances before importing.")
    # Widget keys carry the upload pair, so a new client starts from its own
    # auto-mapping instead of inheriting the previous client's choices.
    tag = zlib.crc32(repr(ctx["key"]).encode())
    options = [DO_NOT_IMPORT] + ctx["uzio"]
    mapping = {}
    for i, (pol, n, total) in enumerate(ctx["summary"]):
        shown = "—" if pd.isna(total) else "%.2f" % total
        default = ctx["auto"].get(pol, DO_NOT_IMPORT)
        mapping[pol] = st.selectbox(
            f"**{pol}** · {n} employee(s) · {shown} available",
            options, index=options.index(default), key=f"pto_pol_{tag}_{i}")
    include_salaried = st.checkbox(
        "Fill balances for Salaried employees too", value=False, key=f"pto_sal_{tag}",
        help="Unticked, rows whose Pay Type is Salaried are left exactly as the "
             "template has them.")
    include_blank_hourly = st.checkbox(
        "Fill blank Opening Balance for Hourly employees (assigns the policy in UZIO)",
        value=True, key=f"pto_blank_{tag}",
        help="A blank Opening Balance means the policy is not assigned to that "
             "employee. Ticked, an Hourly employee's blank row is filled from Paycom, "
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
    if stats["future"]:
        st.info("**%d employee(s) have future time off in Paycom** — see the "
                "Future Time Off sheet in the audit report." % stats["future"])
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
        reasons.append("no Paycom Time-Off Type is mapped to "
                       + ", ".join("**%s**" % p for p in stats["unmapped_uzio"]))
    if stats["not_imported"]:
        reasons.append("these Paycom Time-Off Types are set to Do not import: "
                       + ", ".join("**%s**" % p for p, _, _ in stats["not_imported"]))
    if stats["missing"]:
        reasons.append("%d employee balance(s) have no matching row in the template"
                       % stats["missing"])
    st.error("**No balance was written — the filled template is the same as the one "
             "you uploaded.**\n\n"
             + ("\n".join("- %s" % r for r in reasons) if reasons
                else "- nothing in the Paycom file matched this template"))


def _render_left_out(stats):
    """Everything deliberately not written — no silent omissions."""
    notes = []
    if stats["salaried"]:
        notes.append(f"{stats['salaried']} Salaried row(s) left as the template has them — "
                     "tick **Fill balances for Salaried employees too** to fill them.")
    for pol, n, total in stats["not_imported"]:
        notes.append(f"Paycom Time-Off Type **{pol}** not imported — {n} employee(s), "
                     f"{total:.2f} total.")
    if stats["unmapped_uzio"]:
        notes.append("No Paycom Time-Off Type mapped, so not filled: "
                     + ", ".join(f"**{p}**" for p in stats["unmapped_uzio"]) + ".")
    if notes:
        st.warning("**Left out on purpose — also listed in the audit report:**\n\n"
                   + "\n".join(f"- {n}" for n in notes))


def render_ui():
    st.title(APP_TITLE)
    client_name = st.text_input("Client Name", value="Client", key="paycom_timeoff_client")

    st.markdown("""
    **Upload**
    1. **Paycom TimeOff Summary Report** (.xlsx / .xls / HTML / .csv)
    2. **Uzio Time Off Import Template** (.xlsx)
    3. **UZIO Employee Census** (.xlsx / .xlsm / .csv)

    All three files are required. Once the Paycom report and the template are in,
    map each Paycom Time-Off Type to the UZIO policy its balance should go into.
    The balance imported is Paycom's **Available** column (not Net Available).

    **You get two separate files**
    - `<Client>_Time off Import_filled.xlsx` — your template, unchanged except the
      filled Opening Balance column. Upload it to UZIO as-is.
    - `<Client>_Uzio_Paycom_TimeOff_Audit_Report_<timestamp>.xlsx` — the audit only,
      including a **Future Time Off** sheet for leave Paycom has already approved or
      has pending.
    """)

    col1, col2, col3 = st.columns(3)
    with col1:
        f_p = st.file_uploader("Paycom TimeOff Report", type=["xlsx", "xls", "html", "csv"],
                               key="pt_p")
    with col2:
        f_u = st.file_uploader("Uzio Template", type=["xlsx"], key="pt_u")
    with col3:
        f_c = st.file_uploader("UZIO Census", type=["xlsx", "xlsm", "csv"], key="pt_c")

    mapping, include_salaried, include_blank_hourly = None, False, False
    if f_p is not None and f_u is not None:
        ctx = _mapping_context(f_p, f_u)
        if ctx["error"]:
            st.error(ctx["error"])
            return
        mapping, include_salaried, include_blank_hourly = _render_mapping(ctx)

    # st.download_button triggers a rerun of its own, so results computed inside
    # the Generate block would vanish the moment the first file is downloaded —
    # taking the second download button with them. Keep them in session_state and
    # render the buttons OUTSIDE that block.
    SKEY = "paycom_timeoff_result"

    def _signature(*files):
        return tuple((f.name, getattr(f, "size", None)) if f is not None else None
                     for f in files)

    # The mapping and the checkboxes are part of what produced a result, so
    # changing any of them discards it — a download always matches the screen.
    settings = (tuple(sorted(mapping.items())) if mapping else None,
                include_salaried, include_blank_hourly)
    sig = (_signature(f_p, f_u, f_c), settings)
    cached = st.session_state.get(SKEY)
    if cached and cached.get("signature") != sig:
        del st.session_state[SKEY]
        cached = None

    if st.button("Generate Files", key="run_timeoff_paycom"):
        missing = [label for label, f in (("Paycom TimeOff Report", f_p),
                                          ("Uzio Template", f_u),
                                          ("UZIO Census", f_c)) if f is None]
        if missing:
            st.error("Please upload: " + ", ".join(missing) + ".")
            return
        try:
            with st.spinner("Processing..."):
                filled_bytes, audit_bytes, stats = run_tool(f_p, f_u, f_c, mapping,
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
    c1.metric("Employees in Paycom", stats["employees"])
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
            key="pto_dl_filled",
        )
    with d2:
        st.download_button(
            "⬇️ Audit Report",
            data=cached["audit"],
            file_name=(f"{client_name}_Uzio_Paycom_TimeOff_Audit_Report_"
                       f"{cached['ts']}.xlsx"),
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="pto_dl_audit",
        )


# Streamlit UI
if __name__ == "__main__":
    render_ui()
