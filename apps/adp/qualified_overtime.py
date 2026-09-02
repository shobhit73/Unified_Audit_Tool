import io
import os
import re

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
