import io
import os
import re

import openpyxl
import pandas as pd
import streamlit as st

APP_TITLE = "ADP - Qualified Overtime Wages"

# Prior payroll (ADP) column names.
ADP_ID_COL = "ASSOCIATE ID"
ADP_START_COL = "PERIOD BEGINNING DATE"
ADP_END_COL = "PERIOD ENDING DATE"
ADP_PAY_COL = "PAY DATE"
QOT_DEFAULT_COLUMN = "MEMO : $R-FDQOT"

ADP_REQUIRED_COLUMNS = [ADP_ID_COL, ADP_START_COL, ADP_END_COL, ADP_PAY_COL]


def _read_one(file):
    """Read an uploaded payroll file as strings. Returns (df, error)."""
    name = (getattr(file, "name", "") or "")
    file.seek(0)
    raw = file.read()
    buf = io.BytesIO(raw)
    try:
        if name.lower().endswith(".csv"):
            df = pd.read_csv(buf, dtype=str, low_memory=False)
        else:
            df = pd.read_excel(buf, dtype=str)
    except Exception as e:
        return None, "%s — could not be read: %s" % (name, e)
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in ADP_REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return None, "%s — missing column(s): %s" % (name, ", ".join(missing))
    df["_file"] = name
    return df, None


def read_payroll_files(files):
    """Concatenate the uploaded prior payroll files.

    Returns (DataFrame, errors). A file that cannot be read, or that lacks one
    of the four columns this module needs, is reported and left out rather than
    failing the whole run — the others still carry usable data.
    """
    frames, errors = [], []
    for f in files or []:
        df, err = _read_one(f)
        if err:
            errors.append(err)
        else:
            frames.append(df)
    if not frames:
        return pd.DataFrame(), errors
    out = pd.concat(frames, ignore_index=True)
    out[ADP_ID_COL] = out[ADP_ID_COL].fillna("").astype(str).str.strip()
    return out, errors


def memo_columns(df):
    """Every MEMO column the user could pick from, minus the roll-up total."""
    return sorted(c for c in df.columns
                  if str(c).strip().upper().startswith("MEMO")
                  and str(c).strip().upper() != "TOTAL MEMOS")


def resolve_qot_column(df, chosen=None):
    """Which column holds the qualified-overtime premium.

    `chosen` is the user's dropdown pick and always wins. Otherwise the ADP
    default is used when present. Returns (column_or_None, {file: present?}) so
    the UI can name the files that will be skipped.
    """
    col = chosen or (QOT_DEFAULT_COLUMN if QOT_DEFAULT_COLUMN in df.columns else None)
    per_file = {}
    if col and "_file" in df.columns:
        for name, g in df.groupby("_file"):
            per_file[name] = bool(g[col].notna().any()) if col in g.columns else False
    return col, per_file


# UZIO Qualified Overtime template. Headers sit on row 1 of "QOT Details";
# "Instructions" is a second sheet that must survive into the output untouched.
TEMPLATE_SHEET = "QOT Details"
TEMPLATE_HEADERS = ["Employee ID", "First Name", "Last Name", "Employment Status",
                    "Period Start Date", "Period End Date", "Pay Date", "QOT Premium"]


def read_qot_template(file):
    """Read the template's QOT Details sheet as strings. Returns (df, error)."""
    file.seek(0)
    try:
        book = pd.read_excel(io.BytesIO(file.read()), sheet_name=None, dtype=str)
    except Exception as e:
        return None, "Could not read the template: %s" % e
    if TEMPLATE_SHEET not in book:
        return None, ("The template has no `%s` sheet. Sheets found: %s."
                      % (TEMPLATE_SHEET, ", ".join(book) or "none"))
    df = book[TEMPLATE_SHEET].copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [h for h in TEMPLATE_HEADERS if h not in df.columns]
    if missing:
        return None, ("`%s` is missing column(s): %s."
                      % (TEMPLATE_SHEET, ", ".join(missing)))
    df = df[TEMPLATE_HEADERS].copy()
    df["Employee ID"] = df["Employee ID"].fillna("").astype(str).str.strip()
    df = df[df["Employee ID"] != ""].reset_index(drop=True)
    return df.fillna(""), None


def _money(v):
    """Parse a premium. Blank / unparseable -> None, which means 'no overtime'."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip().replace(",", "").replace("$", "")
    if s == "" or s.lower() in ("nan", "none"):
        return None
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def build_qot_rows(payroll_df, template_df, qot_col):
    """One output row per (employee, pay date) whose premium is non-zero.

    The filter is per ROW, not per employee: an employee keeps every pay period
    that carries a premium and disappears only when all of theirs are zero or
    blank. Rule 14 of the template ("omission does not delete") makes dropping
    the zero rows safe.

    Blank and 0 both mean "no qualified overtime". A NEGATIVE premium is kept —
    non-zero in either direction is real data.
    """
    empty = {"rows": [], "overlaps": [], "missing_dates": [], "not_in_template": [],
             "employees_emitted": 0, "employees_dropped_zero": 0, "total_qot": 0.0,
             "pay_years": []}
    if payroll_df.empty or qot_col not in payroll_df.columns:
        return empty

    df = payroll_df.copy()
    df["_qot"] = df[qot_col].apply(_money)
    all_employees = set(df[ADP_ID_COL]) - {""}
    kept = df[df["_qot"].notna() & (df["_qot"] != 0)].copy()

    names = template_df.set_index("Employee ID")[
        ["First Name", "Last Name", "Employment Status"]].to_dict("index")

    # `row_files` runs parallel to `rows` so the overlap report can name the file
    # each side came from. It cannot live inside the row dicts: those are keyed
    # strictly by TEMPLATE_HEADERS.
    rows, row_files, missing_dates, orphan = [], [], {}, {}
    for _, r in kept.iterrows():
        eid = r[ADP_ID_COL]
        start, end, pay = (str(r[c]).strip() if pd.notna(r[c]) else ""
                           for c in (ADP_START_COL, ADP_END_COL, ADP_PAY_COL))

        # Template rule 5: a row must carry all three dates or none. We always
        # write dates, so a row short of one is unusable and blocks the run.
        absent = [lbl for lbl, val in (("Period Start Date", start),
                                       ("Period End Date", end),
                                       ("Pay Date", pay)) if not val]
        if absent:
            missing_dates.setdefault((eid, pay), {
                "Employee ID": eid, "Pay Date": pay or "(blank)",
                "Missing": ", ".join(absent)})
            continue

        if eid not in names:
            # UZIO has no such employee to import against, so the row is left
            # out — but the money is real, so it is reported.
            o = orphan.setdefault(eid, {"Employee ID": eid, "Rows": 0, "Total QOT": 0.0})
            o["Rows"] += 1
            o["Total QOT"] = round(o["Total QOT"] + r["_qot"], 2)
            continue

        n = names[eid]
        rows.append({
            "Employee ID": eid,
            "First Name": n.get("First Name", ""),
            "Last Name": n.get("Last Name", ""),
            "Employment Status": n.get("Employment Status", ""),
            "Period Start Date": start,
            "Period End Date": end,
            "Pay Date": pay,
            "QOT Premium": r["_qot"],
        })
        row_files.append(str(r.get("_file", "")))

    order = sorted(range(len(rows)),
                   key=lambda i: (rows[i]["Employee ID"],
                                  pd.to_datetime(rows[i]["Pay Date"], errors="coerce")))
    rows = [rows[i] for i in order]
    row_files = [row_files[i] for i in order]

    emitted = {r["Employee ID"] for r in rows}
    pay_years = sorted({d.year for d in
                        pd.to_datetime([r["Pay Date"] for r in rows], errors="coerce")
                        if pd.notna(d)})
    return {
        "rows": rows,
        "overlaps": _find_overlaps(rows, row_files),
        "missing_dates": list(missing_dates.values()),
        "not_in_template": sorted(orphan.values(), key=lambda x: x["Employee ID"]),
        "employees_emitted": len(emitted),
        "employees_dropped_zero": len(all_employees - emitted - set(orphan)),
        "total_qot": round(sum(r["QOT Premium"] for r in rows), 2),
        "pay_years": pay_years,
    }


def _find_overlaps(rows, row_files):
    """Template rule 9: rows for the same employee must not overlap.

    UZIO rejects an import that contains overlapping periods, so this blocks
    rather than warns. Two copies of the same paycheck from two uploaded files
    produce identical periods and are caught here too — the tool cannot know
    which copy is authoritative, and picking one would be a guess.
    """
    by_emp = {}
    for r, src in zip(rows, row_files):
        by_emp.setdefault(r["Employee ID"], []).append((r, src))

    out = []
    for eid, group in by_emp.items():
        dated = []
        for r, src in group:
            s = pd.to_datetime(r["Period Start Date"], errors="coerce")
            e = pd.to_datetime(r["Period End Date"], errors="coerce")
            if pd.notna(s) and pd.notna(e):
                dated.append((s, e, r, src))
        dated.sort(key=lambda x: (x[0], x[1]))
        for i in range(1, len(dated)):
            _, pe, prev, prev_src = dated[i - 1]
            cs, _, cur, cur_src = dated[i]
            if cs <= pe:
                out.append({
                    "Employee ID": eid,
                    "Period A": "%s .. %s" % (prev["Period Start Date"], prev["Period End Date"]),
                    "File A": prev_src,
                    "Period B": "%s .. %s" % (cur["Period Start Date"], cur["Period End Date"]),
                    "File B": cur_src,
                })
    return out


def is_blocked(result):
    """Overlapping periods or a part-dated row make the file unimportable."""
    return bool(result["overlaps"] or result["missing_dates"])


def fill_qot_template(template_file, rows):
    """Write the rows into a copy of the uploaded template. Returns .xlsx bytes.

    Opened through openpyxl so the Instructions sheet and all formatting survive.
    The template's pre-filled rows are cleared first: left in place they would be
    DATELESS rows with a blank premium, and template rule 12 makes a dateless row
    the employee's cumulative total, replacing everything already imported for
    them. Only the rows this tool fills are written.
    """
    template_file.seek(0)
    wb = openpyxl.load_workbook(io.BytesIO(template_file.read()))
    ws = wb[TEMPLATE_SHEET]

    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row - 1)

    for i, r in enumerate(rows, start=2):
        for j, h in enumerate(TEMPLATE_HEADERS, start=1):
            ws.cell(row=i, column=j).value = r[h]

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def output_filename(client_name, template_file):
    """<Client>_<uploaded template's name>_filled.xlsx"""
    base = os.path.splitext(getattr(template_file, "name", "") or "template")[0]
    client = re.sub(r"\s+", " ", str(client_name or "Client")).strip() or "Client"
    return "%s_%s_filled.xlsx" % (client, base)
