"""One-shot porter: build audit_fast_api/core/common/paycom_consolidated_audit.py
from the streamlit apps/common/paycom_combined_audit.py module."""

import os

src = open('apps/common/paycom_combined_audit.py', 'r', encoding='utf-8').read()
lines = src.split('\n')

helpers_start = next(i for i, ln in enumerate(lines) if ln.startswith('def norm_str'))
end = next(i for i, ln in enumerate(lines) if ln.startswith('def render_ui'))
helpers_block = '\n'.join(lines[helpers_start:end])

constants_start = next(i for i, ln in enumerate(lines) if ln.startswith('STATUS_MATCH ='))
constants_end = next(i for i in range(constants_start, len(lines)) if lines[i].startswith('def '))
constants_block = '\n'.join(lines[constants_start:constants_end])

header = '''"""Paycom Consolidated Audit (MCP core).

Pure-Python port of the Streamlit apps/common/paycom_combined_audit.py tool.
Runs Census + Payment + Emergency contact audits in one pass against the
Uzio Master CSV and a Paycom Census export, plus several anomaly checks
(salaried-driver exceptions, FLSA compliance, missing-employees-in-Uzio,
data quality, high-rate anomalies, duplicate SSNs).

The orchestrator run_paycom_consolidated_audit returns a dict-of-lists keyed
by sheet name, ready for save_results_to_excel to render.
"""

import io
import re
import pandas as pd
import numpy as np
from datetime import datetime, date

from utils.audit_utils import (
    norm_col, norm_colname, norm_blank, try_parse_date, clean_money_val,
    get_identity_match_map, norm_ssn_canonical, norm_id,
)


def _detect_duplicate_ssns_with_ids(df, id_col, ssn_col):
    """Return {ssn: [ids]} for SSNs that appear under more than one ID. Local copy
    matching the streamlit signature; the audit_fast_api utils' detect_duplicate_ssns
    has a (df, ssn_col) signature kept for the existing ADP census audit caller.
    """
    id_ssn_map = {}
    for _, row in df.iterrows():
        eid = norm_id(row.get(id_col, ""))
        ssn = norm_ssn_canonical(row.get(ssn_col, ""))
        if not ssn or not eid:
            continue
        id_ssn_map.setdefault(ssn, set()).add(eid)
    return {ssn: sorted(list(ids)) for ssn, ids in id_ssn_map.items() if len(ids) > 1}


'''

new_module = header + constants_block + '\n\n' + helpers_block

new_module = new_module.replace(
    "df_headers = pd.read_csv(io.StringIO(file.getvalue().decode('utf-8', errors='replace')), nrows=2, header=None)",
    "df_headers = pd.read_csv(io.StringIO(content.decode('utf-8', errors='replace')), nrows=2, header=None)"
)
new_module = new_module.replace(
    "    file.seek(0)\n    df = pd.read_csv(file, skiprows=2, header=None, dtype=str)",
    "    df = pd.read_csv(io.BytesIO(content), skiprows=2, header=None, dtype=str)"
)
new_module = new_module.replace("def read_uzio_master(file):", "def read_uzio_master(content):")

orchestrator = '''


def run_paycom_consolidated_audit(uzio_content, paycom_content, paycom_filename="paycom.xlsx"):
    """End-to-end Paycom Consolidated Audit. Returns a dict-of-lists for save_results_to_excel.

    Sheets produced:
      - Summary, Duplicate_SSN_Check, Census_Audit, Payment_Audit, Emergency_Audit,
        Salaried_Drivers, FLSA_Issues, Active_Missing, Terminated_Missing,
        Data_Quality, High_Rate_Anomalies
    """
    df_uzio = read_uzio_master(uzio_content)
    name_lower = (paycom_filename or "").lower()
    if name_lower.endswith(".csv"):
        df_paycom = pd.read_csv(io.BytesIO(paycom_content), dtype=str)
    else:
        df_paycom = pd.read_excel(io.BytesIO(paycom_content), dtype=str)

    u_id_col = "Job|Employee ID"
    p_id_col = next((c for c in df_paycom.columns if "Employee_Code" in c), "Employee_Code")
    uzio_ssn_col = "Personal|SSN"
    paycom_ssn_col = next((c for c in df_paycom.columns if "SS_Number" in c or "SSN" in c), "SS_Number")

    df_uzio[u_id_col] = df_uzio[u_id_col].apply(norm_id)
    df_paycom[p_id_col] = df_paycom[p_id_col].apply(norm_id)

    uz_to_pc_id_map = get_identity_match_map(
        df_uzio, df_paycom,
        uzio_id_col=u_id_col, vendor_id_col=p_id_col,
        uzio_ssn_col=uzio_ssn_col, vendor_ssn_col=paycom_ssn_col,
    )

    df_uz_dupes = _detect_duplicate_ssns_with_ids(df_uzio, u_id_col, uzio_ssn_col)
    df_pc_dupes = _detect_duplicate_ssns_with_ids(df_paycom, p_id_col, paycom_ssn_col)
    dupe_rows = []
    for ssn, ids in df_uz_dupes.items():
        dupe_rows.append({"Source": "Uzio", "SSN": ssn, "IDs": ", ".join(ids), "Issue": "Duplicate SSN"})
    for ssn, ids in df_pc_dupes.items():
        dupe_rows.append({"Source": "Paycom", "SSN": ssn, "IDs": ", ".join(ids), "Issue": "Duplicate SSN"})

    res_census = run_census_audit(df_uzio, df_paycom, uz_to_pc_id_map=uz_to_pc_id_map)
    res_payment = run_payment_audit(df_uzio, df_paycom, uz_to_pc_id_map=uz_to_pc_id_map)
    res_emergency = run_emergency_audit(df_uzio, df_paycom, uz_to_pc_id_map=uz_to_pc_id_map)

    df_salaried_drivers = get_salaried_driver_exceptions(df_uzio, df_paycom)
    df_flsa_issues = get_flsa_compliance_issues(df_uzio)
    df_active_missing = get_active_missing_in_uzio(df_uzio, df_paycom)
    df_terminated_missing = get_terminated_missing_in_uzio(df_uzio, df_paycom)
    df_dq_issues = get_data_quality_issues(df_paycom)
    df_high_rates = get_high_rate_anomalies(df_paycom)

    uzio_ids = set(df_uzio[u_id_col].map(norm_id))
    pay_ids = set(df_paycom[p_id_col].map(norm_id))
    summary_rows = [
        {"Metric": "Employees in Uzio Master", "Value": len(uzio_ids)},
        {"Metric": "Employees in Paycom Export", "Value": len(pay_ids)},
        {"Metric": "Employees in Both", "Value": len(uzio_ids & pay_ids)},
        {"Metric": "Census Matches", "Value": int((res_census["Status"] == STATUS_MATCH).sum())},
        {"Metric": "Census Mismatches", "Value": int((res_census["Status"] == STATUS_MISMATCH).sum())},
        {"Metric": "Payment Matches", "Value": int((res_payment["Status"] == STATUS_MATCH).sum())},
        {"Metric": "Payment Mismatches", "Value": int((res_payment["Status"] == STATUS_MISMATCH).sum())},
        {"Metric": "Emergency Matches", "Value": int((res_emergency["Status"] == STATUS_MATCH).sum())},
        {"Metric": "Emergency Mismatches", "Value": int((res_emergency["Status"] == STATUS_MISMATCH).sum())},
        {"Metric": "Salaried Driver Exceptions", "Value": len(df_salaried_drivers)},
        {"Metric": "FLSA Compliance Issues", "Value": len(df_flsa_issues)},
        {"Metric": "Active Employees Missing in Uzio", "Value": len(df_active_missing)},
        {"Metric": "Terminated Employees Missing in Uzio", "Value": len(df_terminated_missing)},
        {"Metric": "Data Quality Issues (00/00/0000)", "Value": len(df_dq_issues)},
        {"Metric": "High Hourly Rate Anomalies (>$100)", "Value": len(df_high_rates)},
        {"Metric": "Duplicate SSN Warnings", "Value": len(dupe_rows)},
    ]

    def _records(df):
        return df.to_dict("records") if hasattr(df, "to_dict") else []

    return {
        "Summary": summary_rows,
        "Duplicate_SSN_Check": dupe_rows,
        "Census_Audit": _records(res_census),
        "Payment_Audit": _records(res_payment),
        "Emergency_Audit": _records(res_emergency),
        "Salaried_Drivers": _records(df_salaried_drivers),
        "FLSA_Issues": _records(df_flsa_issues),
        "Active_Missing": _records(df_active_missing),
        "Terminated_Missing": _records(df_terminated_missing),
        "Data_Quality": _records(df_dq_issues),
        "High_Rate_Anomalies": _records(df_high_rates),
    }
'''

new_module += orchestrator

out_path = 'audit_fast_api/core/common/paycom_consolidated_audit.py'
with open(out_path, 'w', encoding='utf-8') as f:
    f.write(new_module)
print(f'Wrote {out_path}, total {len(new_module.splitlines())} lines')
