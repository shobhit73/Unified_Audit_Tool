from __future__ import annotations

import io
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

try:
    import streamlit as st
except ModuleNotFoundError:  # allows import/testing without Streamlit installed
    st = None


# Supports both the dump typo `ups_company_contritbution` and the corrected spelling.
CONTRIBUTION_TABLE_REGEX = r"ups_company_contri(?:t)?bution"

INSERT_PATTERNS = {
    "deduction": re.compile(
        r"INSERT\s+INTO\s+ups_company_deduction\s*\((.*?)\)\s*VALUES\s*(.*?);",
        re.IGNORECASE | re.DOTALL,
    ),
    "earning": re.compile(
        r"INSERT\s+INTO\s+ups_company_earning_detail\s*\((.*?)\)\s*VALUES\s*(.*?);",
        re.IGNORECASE | re.DOTALL,
    ),
    "contribution": re.compile(
        rf"INSERT\s+INTO\s+{CONTRIBUTION_TABLE_REGEX}\s*\((.*?)\)\s*VALUES\s*(.*?);",
        re.IGNORECASE | re.DOTALL,
    ),
}

DEDUCTION_DEFAULT_FIELDS = [
    "master_ded_type_identifier",
    "deduction_type_name",
    "deduction_method",
    "w2_box",
    "w2_label",
    "deduction_code",
    "garnishment_type",
    "other_garnishment_type",
    "product_category_code",
    "sync_from_benefit",
    "plan_type",
]

DEDUCTION_FIELD_LABELS = {
    "master_ded_type_identifier": "Master Deduction Type ID",
    "deduction_type_name": "Deduction Type Name",
    "deduction_method": "Deduction Method",
    "w2_box": "W-2 Box",
    "w2_label": "W-2 Label",
    "deduction_code": "Deduction Code",
    "garnishment_type": "Garnishment Type",
    "other_garnishment_type": "Other Garnishment Type",
    "product_category_code": "Product Category Code",
    "sync_from_benefit": "Sync From Benefit",
    "plan_type": "Plan Type",
}

EARNING_DEFAULT_FIELDS = [
    "w2_box",
    "w2_label",
    "earning_code",
    "disposable",
    "part_of_other_earning",
    "subject_to_wc",
    "policy_identifier",
    "subject_to_federal_tax",
    "is_editable",
    "amount_multiplier",
    "include_in_overtime",
    "is_default",
    "frequently_used_x",
]

EARNING_FIELD_LABELS = {
    "w2_box": "W-2 Box",
    "w2_label": "W-2 Label",
    "earning_code": "Earning Code",
    "disposable": "Disposable",
    "part_of_other_earning": "Part of Other Earning",
    "subject_to_wc": "Subject to WC",
    "policy_identifier": "Policy Identifier",
    "subject_to_federal_tax": "Subject to Federal Tax",
    "is_editable": "Is Editable",
    "amount_multiplier": "Amount Multiplier",
    "include_in_overtime": "Include in Overtime",
    "is_default": "Is Default",
    "frequently_used_x": "Frequently Used",
}

CONTRIBUTION_DEFAULT_FIELDS = [
    "contritbution_method",
    "w2_box",
    "w2_label",
    "monthly_limit",
    "annual_limit",
    "applicable_s_corp",
    "link_contribution",
    "contribution_code",
]

CONTRIBUTION_FIELD_LABELS = {
    "contritbution_method": "Contribution Method",
    "w2_box": "W-2 Box",
    "w2_label": "W-2 Label",
    "monthly_limit": "Monthly Limit",
    "annual_limit": "Annual Limit",
    "applicable_s_corp": "Applicable S Corp",
    "link_contribution": "Link Contribution",
    "contribution_code": "Contribution Code",
}


# ----------------
# Generic helpers
# ----------------

def sql_token_to_python(token: str) -> Any:
    token = token.strip()
    if token == "":
        return None
    if token.upper() == "NULL":
        return None
    if token.startswith("'") and token.endswith("'"):
        return token[1:-1].replace("''", "'")
    if re.fullmatch(r"-?\d+", token):
        try:
            return int(token)
        except Exception:
            return token
    if re.fullmatch(r"-?\d+\.\d+", token):
        try:
            return float(token)
        except Exception:
            return token
    return token



def split_row_values(row_text: str) -> list[str]:
    values: list[str] = []
    current: list[str] = []
    in_quote = False
    i = 0
    while i < len(row_text):
        ch = row_text[i]
        if ch == "'":
            current.append(ch)
            if in_quote:
                if i + 1 < len(row_text) and row_text[i + 1] == "'":
                    current.append("'")
                    i += 1
                else:
                    in_quote = False
            else:
                in_quote = True
        elif ch == "," and not in_quote:
            values.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
        i += 1
    if current:
        values.append("".join(current).strip())
    return values



def extract_tuple_texts(values_block: str) -> list[str]:
    rows: list[str] = []
    current: list[str] = []
    depth = 0
    in_quote = False
    i = 0
    while i < len(values_block):
        ch = values_block[i]
        if ch == "'":
            if in_quote:
                if i + 1 < len(values_block) and values_block[i + 1] == "'":
                    current.append("''")
                    i += 1
                else:
                    current.append(ch)
                    in_quote = False
            else:
                current.append(ch)
                in_quote = True
        elif ch == "(" and not in_quote:
            if depth > 0:
                current.append(ch)
            depth += 1
        elif ch == ")" and not in_quote:
            depth -= 1
            if depth == 0:
                rows.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        else:
            if depth > 0:
                current.append(ch)
        i += 1
    return rows



def parse_insert_table(sql_text: str, source_name: str, kind: str) -> pd.DataFrame:
    pattern = INSERT_PATTERNS[kind]
    table_name = {
        "deduction": "ups_company_deduction",
        "earning": "ups_company_earning_detail",
        "contribution": "ups_company_contribution / ups_company_contritbution",
    }[kind]
    records: list[dict[str, Any]] = []

    for match in pattern.finditer(sql_text):
        columns_raw = match.group(1)
        values_block = match.group(2)
        columns = [c.strip().strip('"') for c in columns_raw.split(",")]
        tuple_texts = extract_tuple_texts(values_block)

        for row_text in tuple_texts:
            raw_values = split_row_values(row_text)
            if len(raw_values) != len(columns):
                raise ValueError(
                    f"Column/value count mismatch in {source_name} for {table_name}. "
                    f"Expected {len(columns)} values but found {len(raw_values)}."
                )
            row = {col: sql_token_to_python(val) for col, val in zip(columns, raw_values)}
            row["source_file"] = source_name
            row["record_type"] = kind
            records.append(row)

    if not records:
        raise ValueError(f"No INSERT INTO {table_name} statements found in {source_name}.")

    return pd.DataFrame(records)



def detect_kinds(sql_text: str) -> list[str]:
    found: list[str] = []
    for kind, pattern in INSERT_PATTERNS.items():
        if pattern.search(sql_text):
            found.append(kind)
    return found



def file_alias(filename: str, kind: str) -> str:
    stem = Path(filename).stem
    if kind == "deduction":
        stem = re.sub(r"_ups_company_deduction.*$", "", stem, flags=re.IGNORECASE)
    elif kind == "earning":
        stem = re.sub(r"_?ups_company_earning_detail.*$", "", stem, flags=re.IGNORECASE)
        stem = re.sub(r"_?earning_final.*$", "", stem, flags=re.IGNORECASE)
    else:
        stem = re.sub(r"_ups_company_contri(?:t)?bution.*$", "", stem, flags=re.IGNORECASE)
        stem = re.sub(r"\(\d+\)$", "", stem).rstrip("_")
    return stem



def yes_no_blank(value: Any) -> str:
    if pd.isna(value) or value is None:
        return ""
    if str(value).strip() in {"1", "1.0"}:
        return "Yes"
    if str(value).strip() in {"0", "0.0"}:
        return "No"
    return str(value)



def method_ui(value: Any) -> str:
    mapping = {
        "FIXED_DOLLAR": "Fixed $",
        "PERCENT_OF_GROSS_PAY": "% of Gross Pay",
    }
    if pd.isna(value) or value is None:
        return ""
    return mapping.get(str(value), str(value))



def contribution_method_ui(value: Any) -> str:
    mapping = {
        "FIXED_AMOUNT": "Fixed $",
        "PERCENTAGE_OF_GROSS_PAY": "% of Gross Pay",
        "FORMULA": "Formula",
    }
    if pd.isna(value) or value is None:
        return ""
    return mapping.get(str(value), str(value))



def w2_box_ui(value: Any) -> str:
    if pd.isna(value) or value is None:
        return ""
    mapping = {"NOT_REQUIRED": "Not Required"}
    return mapping.get(str(value), str(value))



def schedule_ui(value: Any) -> str:
    if pd.isna(value) or value is None:
        return ""
    mapping = {"All": "Every Paycheck"}
    return mapping.get(str(value), str(value))



def amount_display(value: Any) -> Any:
    if pd.isna(value) or value is None:
        return ""
    return value



def most_common_non_null(values: Iterable[Any]) -> Any:
    filtered = [v for v in values if not pd.isna(v) and v is not None and str(v).strip() != ""]
    if not filtered:
        return None
    counts = Counter(filtered)
    return counts.most_common(1)[0][0]



def summarize_defaults(
    df: pd.DataFrame,
    group_key: str,
    candidate_fields: list[str],
) -> pd.DataFrame:
    summary_rows: list[dict[str, Any]] = []
    if group_key not in df.columns:
        return pd.DataFrame(summary_rows)

    for group_value, group in df.groupby(group_key, dropna=False):
        if pd.isna(group_value):
            continue
        result = {
            group_key: group_value,
            "master_group_row_count": len(group),
            "master_group_file_count": group["source_file"].nunique() if "source_file" in group.columns else 1,
        }
        for field in candidate_fields:
            if field not in group.columns:
                continue
            unique_values = [
                v for v in pd.Series(group[field]).dropna().tolist() if str(v).strip() != ""
            ]
            unique_set = list(dict.fromkeys(unique_values))
            result[f"{field}__unique_count"] = len(unique_set)
            result[f"{field}__canonical_value"] = unique_set[0] if len(unique_set) == 1 else None
        summary_rows.append(result)
    return pd.DataFrame(summary_rows)



def default_flags(
    row: pd.Series,
    summary_df: pd.DataFrame,
    group_key: str,
    candidate_fields: list[str],
    field_labels: dict[str, str],
    ui_renderers: dict[str, Callable[[Any], str]] | None = None,
) -> tuple[str, str, int, str]:
    group_value = row.get(group_key)
    if pd.isna(group_value) or summary_df.empty or group_value not in set(summary_df[group_key]):
        return "", "", 0, f"No {group_key} available"

    ui_renderers = ui_renderers or {}
    srow = summary_df.loc[summary_df[group_key] == group_value].iloc[0]
    flagged_labels: list[str] = []
    flagged_snapshot: list[str] = []
    if int(srow.get("master_group_row_count", 1)) == 1:
        basis = "Single-sample heuristic"
    else:
        basis = f"Consistent across {int(srow.get('master_group_row_count', 1))} row(s)"

    for field in candidate_fields:
        unique_count = srow.get(f"{field}__unique_count", 0)
        canonical_value = srow.get(f"{field}__canonical_value")
        if unique_count == 1 and canonical_value is not None:
            label = field_labels.get(field, field)
            flagged_labels.append(label)
            render_fn = ui_renderers.get(field)
            display_value = render_fn(canonical_value) if render_fn else canonical_value
            flagged_snapshot.append(f"{label}={display_value}")

    return ", ".join(flagged_labels), " | ".join(flagged_snapshot), len(flagged_labels), basis


# --------------------------
# Deduction-specific helpers
# --------------------------

def infer_master_list_name(df: pd.DataFrame) -> pd.Series:
    name_map: dict[Any, Any] = {}
    if "master_ded_identifier" not in df.columns:
        return df.get("display_name", pd.Series([""] * len(df)))

    for master_id, group in df.groupby("master_ded_identifier", dropna=False):
        if pd.isna(master_id):
            continue
        name_map[master_id] = most_common_non_null(group.get("display_name", []))

    return df["master_ded_identifier"].map(name_map).fillna(df.get("display_name", ""))



def infer_deduction_type(row: pd.Series) -> str:
    name = str(row.get("display_name") or "").lower()
    ded_type_name = str(row.get("deduction_type_name") or "").strip()
    if ded_type_name:
        return ded_type_name

    garnishment_type = str(row.get("garnishment_type") or "").strip()
    if garnishment_type:
        return "Garnishment"

    if "roth" in name:
        return "Roth"
    if "loan" in name:
        return "Loan / Post-Tax"
    if "earned wage access" in name:
        return "Post-Tax / Advance"
    if "claim" in name or "reimbursement" in name:
        return "Post-Tax / Reimbursement"
    if "pre-tax" in name or "pretax" in name:
        return "Pre-Tax"
    if "post-tax" in name or "after-tax" in name or "after tax" in name:
        return "Post-Tax"

    w2_label = str(row.get("w2_label") or "").upper()
    display_name = str(row.get("display_name") or "")
    if display_name.upper() == "HSA":
        return "Pre-Tax"
    if w2_label == "D":
        return "Pre-Tax"
    if w2_label in {"AA", "BB", "EE"}:
        return "Roth"
    if str(row.get("deduction_code") or "").upper() == "HSA":
        return "Pre-Tax"

    return ""



def deduction_setup_notes(row: pd.Series) -> str:
    notes: list[str] = []
    derived_type = str(row.get("Derived Deduction Type") or "")
    if derived_type:
        notes.append(f"Type inferred as {derived_type}")
    if str(row.get("Garnishment Type") or ""):
        notes.append("Review garnishment order details")
    if str(row.get("Sync From Benefit") or "") == "Yes":
        notes.append("Likely benefit-linked deduction")
    if str(row.get("System Seeded") or "") == "Yes":
        notes.append("System-seeded row")
    if str(row.get("Arrears Applicable") or "") == "Yes":
        notes.append("Arrears enabled")
    return "; ".join(notes)




def deduction_ui_mapping_notes(row: pd.Series) -> str:
    notes: list[str] = []
    if str(row.get("Deduction Method (UI)") or ""):
        notes.append(f"Method UI shows {row['Deduction Method (UI)']}")
    if str(row.get("W-2 Box (UI)") or ""):
        notes.append(f"W-2 Box UI shows {row['W-2 Box (UI)']}")
    if str(row.get("Weekly Schedule") or "") == "Every Paycheck":
        notes.append("Weekly schedule maps from 'All'")
    if str(row.get("Biweekly Schedule") or "") == "Every Paycheck":
        notes.append("Biweekly schedule maps from 'All'")
    if str(row.get("Semimonthly Schedule") or "") == "Every Paycheck":
        notes.append("Semimonthly schedule maps from 'All'")
    if str(row.get("Arrears Applicable") or "") in {"Yes", "No"}:
        notes.append(f"Arrears radio shows {row['Arrears Applicable']}")
    return "; ".join(notes)



def build_deduction_master_table(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = raw_df.copy()
    df["Company"] = df["source_file"].map(lambda x: file_alias(x, "deduction"))
    df["Master Deduction List"] = infer_master_list_name(df)

    df["Deduction Method (UI)"] = df.get("deduction_method", "").map(method_ui)
    df["Amount Per Pay"] = df.get("amount_per_pay", "").map(amount_display)
    df["Amount %"] = df.get("amount_per_pay_percent", "").map(amount_display)
    df["W-2 Box (UI)"] = df.get("w2_box", "").map(w2_box_ui)
    df["W-2 Label"] = df.get("w2_label", "").fillna("")
    df["Sync From Benefit"] = df.get("sync_from_benefit", "").map(yes_no_blank)
    df["Auto Assign to Employee"] = df.get("auto_assign_to_ee", "").map(yes_no_blank)
    df["Weekly Schedule"] = df.get("schedule_for_weekly", "").map(schedule_ui)
    df["Biweekly Schedule"] = df.get("schedule_for_biweekly", "").map(schedule_ui)
    df["Semimonthly Schedule"] = df.get("schedule_for_semimonthly", "").map(schedule_ui)
    df["Arrears Applicable"] = df.get("arrears_applicable", "").map(yes_no_blank)
    df["System Seeded"] = df.get("system_seeded", "").map(yes_no_blank)
    df["Discarded"] = df.get("discarded", "").map(yes_no_blank)
    df["Deleted"] = df.get("deleted", "").map(yes_no_blank)
    df["Derived Deduction Type"] = df.apply(infer_deduction_type, axis=1)

    default_summary = summarize_defaults(df, "master_ded_identifier", DEDUCTION_DEFAULT_FIELDS)
    flagged = df.apply(
        lambda row: default_flags(
            row,
            default_summary,
            group_key="master_ded_identifier",
            candidate_fields=DEDUCTION_DEFAULT_FIELDS,
            field_labels=DEDUCTION_FIELD_LABELS,
            ui_renderers={
                "deduction_method": method_ui,
                "w2_box": w2_box_ui,
                "sync_from_benefit": yes_no_blank,
            },
        ),
        axis=1,
        result_type="expand",
    )
    flagged.columns = [
        "Likely Master-Default Fields",
        "Likely Master-Default Values Snapshot",
        "Master-Default Field Count",
        "Master-Default Basis",
    ]
    df = pd.concat([df, flagged], axis=1)

    df["Setup Notes"] = df.apply(deduction_setup_notes, axis=1)
    df["UI Mapping Notes"] = df.apply(deduction_ui_mapping_notes, axis=1)

    final_columns = [
        "Company",
        "source_file",
        "employer_org_ein",
        "Master Deduction List",
        "master_ded_identifier",
        "master_ded_type_identifier",
        "display_name",
        "Derived Deduction Type",
        "deduction_type_name",
        "Deduction Method (UI)",
        "Amount Per Pay",
        "Amount %",
        "W-2 Box (UI)",
        "W-2 Label",
        "deduction_code",
        "Sync From Benefit",
        "product_category_code",
        "garnishment_type",
        "other_garnishment_type",
        "Auto Assign to Employee",
        "Weekly Schedule",
        "Biweekly Schedule",
        "Semimonthly Schedule",
        "Arrears Applicable",
        "arrears_processing_method",
        "flat_arrears_amount",
        "assign_paycheck_limit",
        "paycheck_minimum",
        "paycheck_maximum",
        "deduction_priority_x",
        "plan_type",
        "plan_id",
        "deferral_limit_x",
        "System Seeded",
        "Discarded",
        "Deleted",
        "created_by",
        "created_date",
        "updated_by",
        "updated_date",
        "Likely Master-Default Fields",
        "Likely Master-Default Values Snapshot",
        "Master-Default Field Count",
        "Master-Default Basis",
        "Setup Notes",
        "UI Mapping Notes",
        "id",
        "identifier",
        "deduction_method",
        "amount_per_pay",
        "w2_box",
        "w2_label",
        "sync_from_benefit",
        "auto_assign_to_ee",
        "schedule_for_weekly",
        "schedule_for_biweekly",
        "schedule_for_semimonthly",
        "amount_per_pay_percent",
        "arrears_applicable",
        "system_seeded",
    ]
    final_columns = [c for c in final_columns if c in df.columns]
    final_df = df[final_columns].copy()

    rename_map = {
        "source_file": "Source File",
        "employer_org_ein": "Employer EIN",
        "master_ded_identifier": "Master Deduction ID",
        "master_ded_type_identifier": "Master Deduction Type ID",
        "display_name": "Company Deduction Name",
        "deduction_type_name": "Deduction Type Name",
        "deduction_code": "Deduction Code",
        "product_category_code": "Product Category Code",
        "garnishment_type": "Garnishment Type",
        "other_garnishment_type": "Other Garnishment Type",
        "arrears_processing_method": "Arrears Processing Method",
        "flat_arrears_amount": "Flat Arrears Amount",
        "assign_paycheck_limit": "Assign Paycheck Limit",
        "paycheck_minimum": "Paycheck Minimum",
        "paycheck_maximum": "Paycheck Maximum",
        "deduction_priority_x": "Deduction Priority",
        "plan_type": "Plan Type",
        "plan_id": "Plan ID",
        "deferral_limit_x": "Deferral Limit",
        "created_by": "Created By",
        "created_date": "Created Date",
        "updated_by": "Updated By",
        "updated_date": "Updated Date",
        "id": "Raw ID",
        "identifier": "Raw Identifier",
        "deduction_method": "Raw Deduction Method",
        "amount_per_pay": "Raw Amount Per Pay",
        "w2_box": "Raw W-2 Box",
        "w2_label": "Raw W-2 Label",
        "sync_from_benefit": "Raw Sync From Benefit",
        "auto_assign_to_ee": "Raw Auto Assign To EE",
        "schedule_for_weekly": "Raw Weekly Schedule",
        "schedule_for_biweekly": "Raw Biweekly Schedule",
        "schedule_for_semimonthly": "Raw Semimonthly Schedule",
        "amount_per_pay_percent": "Raw Amount %",
        "arrears_applicable": "Raw Arrears Applicable",
        "system_seeded": "Raw System Seeded",
    }
    final_df = final_df.rename(columns=rename_map)
    return final_df, default_summary


# -----------------------
# Earning-specific helpers
# -----------------------

def infer_master_earning_list(df: pd.DataFrame) -> pd.Series:
    name_map: dict[Any, Any] = {}
    if "earning_id" not in df.columns:
        return df.get("name", pd.Series([""] * len(df)))

    for earning_id, group in df.groupby("earning_id", dropna=False):
        if pd.isna(earning_id):
            continue
        name_map[earning_id] = most_common_non_null(group.get("name", []))

    return df["earning_id"].map(name_map).fillna(df.get("name", ""))



def infer_earning_type(row: pd.Series) -> str:
    name = str(row.get("name") or "").lower()
    code = str(row.get("earning_code") or "").upper()

    if "double overtime" in name:
        return "Double Overtime"
    if "overtime" in name or code in {"OT", "OTADJ"}:
        return "Overtime"
    if "retro" in name:
        return "Retro Pay"
    if "bonus" in name:
        return "Bonus"
    if "holiday" in name:
        return "Holiday / Premium"
    if "reimbursement" in name or code == "REIM":
        return "Reimbursement"
    if "pto balance payout" in name:
        return "PTO Payout"
    if "paid time off" in name or "unpaid" in name or name == "vto" or "time off" in name:
        return "Time Off / Leave"
    if "premium" in name:
        return "Premium"
    if "training" in name:
        return "Training"
    if "tuition" in name:
        return "Assistance / Informational"
    if "regular" in name:
        return "Regular Pay"
    if "station closure" in name:
        return "Special Pay"
    return "Other Earning"



def earning_setup_notes(row: pd.Series) -> str:
    notes: list[str] = []
    earning_type = str(row.get("Derived Earning Type") or "")
    if earning_type:
        notes.append(f"Type inferred as {earning_type}")
    if str(row.get("Include in Overtime") or "") == "Yes":
        notes.append("Included in overtime calculation")
    if str(row.get("Is Default") or "") == "Yes":
        notes.append("Default earning row")
    if str(row.get("Policy Linked") or "") == "Yes":
        notes.append("Linked to policy")
    if str(row.get("Linked Earning Present") or "") == "Yes":
        notes.append("Review linked earning relationship")
    if str(row.get("Is Editable") or "") == "No":
        notes.append("Likely locked/non-editable in UI")
    return "; ".join(notes)



def earning_ui_mapping_notes(row: pd.Series) -> str:
    notes: list[str] = []
    if str(row.get("W-2 Box") or ""):
        notes.append(f"W-2 Box UI shows {row['W-2 Box']}")
    if str(row.get("Include in Overtime") or "") in {"Yes", "No"}:
        notes.append(f"Include in overtime toggle shows {row['Include in Overtime']}")
    if str(row.get("Is Editable") or "") in {"Yes", "No"}:
        notes.append(f"Editable toggle shows {row['Is Editable']}")
    if str(row.get("Is Default") or "") == "Yes":
        notes.append("Default earning appears preconfigured")
    if str(row.get("Policy Linked") or "") == "Yes":
        notes.append("Policy selector is populated")
    return "; ".join(notes)



def build_earning_master_table(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = raw_df.copy()
    df["Company"] = df["source_file"].map(lambda x: file_alias(x, "earning"))
    df["Master Earning List"] = infer_master_earning_list(df)
    df["Derived Earning Type"] = df.apply(infer_earning_type, axis=1)

    df["W-2 Box"] = df.get("w2_box", "").map(w2_box_ui)
    df["W-2 Label"] = df.get("w2_label", "").fillna("")
    df["Disposable"] = df.get("disposable", "").map(yes_no_blank)
    df["Part of Other Earning"] = df.get("part_of_other_earning", "").map(yes_no_blank)
    df["Subject to WC"] = df.get("subject_to_wc", "").map(yes_no_blank)
    df["Subject to Federal Tax"] = df.get("subject_to_federal_tax", "").map(yes_no_blank)
    df["Is Editable"] = df.get("is_editable", "").map(yes_no_blank)
    df["Include in Overtime"] = df.get("include_in_overtime", "").map(yes_no_blank)
    df["Is Default"] = df.get("is_default", "").map(yes_no_blank)
    df["Frequently Used"] = df.get("frequently_used_x", "").map(yes_no_blank)
    df["Amount Multiplier"] = df.get("amount_multiplier", "").map(amount_display)
    df["Linked Earning Present"] = df.get("linked_earning", "").map(lambda x: "Yes" if pd.notna(x) and str(x).strip() else "No")
    df["Policy Linked"] = df.get("policy_identifier", "").map(lambda x: "Yes" if pd.notna(x) and str(x).strip() else "No")
    df["Deleted"] = df.get("deleted", "").map(yes_no_blank)

    default_summary = summarize_defaults(df, "earning_id", EARNING_DEFAULT_FIELDS)
    flagged = df.apply(
        lambda row: default_flags(
            row,
            default_summary,
            group_key="earning_id",
            candidate_fields=EARNING_DEFAULT_FIELDS,
            field_labels=EARNING_FIELD_LABELS,
            ui_renderers={
                "w2_box": w2_box_ui,
                "disposable": yes_no_blank,
                "part_of_other_earning": yes_no_blank,
                "subject_to_wc": yes_no_blank,
                "subject_to_federal_tax": yes_no_blank,
                "is_editable": yes_no_blank,
                "include_in_overtime": yes_no_blank,
                "is_default": yes_no_blank,
                "frequently_used_x": yes_no_blank,
            },
        ),
        axis=1,
        result_type="expand",
    )
    flagged.columns = [
        "Likely Master-Default Fields",
        "Likely Master-Default Values Snapshot",
        "Master-Default Field Count",
        "Master-Default Basis",
    ]
    df = pd.concat([df, flagged], axis=1)

    df["Setup Notes"] = df.apply(earning_setup_notes, axis=1)
    df["UI Mapping Notes"] = df.apply(earning_ui_mapping_notes, axis=1)

    final_columns = [
        "Company",
        "source_file",
        "employer_org_ein",
        "Master Earning List",
        "earning_id",
        "name",
        "Derived Earning Type",
        "earning_code",
        "W-2 Box",
        "W-2 Label",
        "Disposable",
        "Part of Other Earning",
        "Subject to WC",
        "Subject to Federal Tax",
        "Is Editable",
        "Amount Multiplier",
        "Include in Overtime",
        "Policy Linked",
        "policy_identifier",
        "Linked Earning Present",
        "linked_earning",
        "Is Default",
        "Frequently Used",
        "display_order",
        "Deleted",
        "created_by",
        "created_date",
        "updated_by",
        "updated_date",
        "Likely Master-Default Fields",
        "Likely Master-Default Values Snapshot",
        "Master-Default Field Count",
        "Master-Default Basis",
        "Setup Notes",
        "UI Mapping Notes",
        "id",
        "earning_identifier",
        "w2_box",
        "w2_label",
        "disposable",
        "part_of_other_earning",
        "subject_to_wc",
        "subject_to_federal_tax",
        "is_editable",
        "amount_multiplier",
        "include_in_overtime",
        "is_default",
        "frequently_used_x",
    ]
    final_columns = [c for c in final_columns if c in df.columns]
    final_df = df[final_columns].copy()

    rename_map = {
        "source_file": "Source File",
        "employer_org_ein": "Employer EIN",
        "earning_id": "Master Earning ID",
        "name": "Company Earning Name",
        "earning_code": "Earning Code",
        "policy_identifier": "Policy Identifier",
        "linked_earning": "Linked Earning Identifier",
        "display_order": "Display Order",
        "created_by": "Created By",
        "created_date": "Created Date",
        "updated_by": "Updated By",
        "updated_date": "Updated Date",
        "id": "Raw ID",
        "earning_identifier": "Raw Earning Identifier",
        "w2_box": "Raw W-2 Box",
        "w2_label": "Raw W-2 Label",
        "disposable": "Raw Disposable",
        "part_of_other_earning": "Raw Part of Other Earning",
        "subject_to_wc": "Raw Subject to WC",
        "subject_to_federal_tax": "Raw Subject to Federal Tax",
        "is_editable": "Raw Is Editable",
        "amount_multiplier": "Raw Amount Multiplier",
        "include_in_overtime": "Raw Include in Overtime",
        "is_default": "Raw Is Default",
        "frequently_used_x": "Raw Frequently Used",
    }
    final_df = final_df.rename(columns=rename_map)
    return final_df, default_summary


# ----------------------------
# Contribution-specific helpers
# ----------------------------

def infer_master_contribution_list(df: pd.DataFrame) -> pd.Series:
    name_map: dict[Any, Any] = {}
    if "contribution_code" not in df.columns:
        return df.get("name", pd.Series([""] * len(df)))

    for contribution_code, group in df.groupby("contribution_code", dropna=False):
        if pd.isna(contribution_code):
            continue
        name_map[contribution_code] = most_common_non_null(group.get("name", []))

    return df["contribution_code"].map(name_map).fillna(df.get("name", ""))



def infer_contribution_type(row: pd.Series) -> str:
    name = str(row.get("name") or "").lower()
    method = str(row.get("contritbution_method") or "").upper()
    code = str(row.get("contribution_code") or "").upper()

    if "roth" in name and "match" in name:
        return "Roth Match"
    if ("401k" in name or code.startswith("K4P")) and "match" in name:
        return "Retirement Match"
    if "hsa" in name:
        return "HSA Employer Contribution"
    if "medical" in name and "memo" in name:
        return "Benefit Employer Memo"
    if "memo" in name:
        return "Employer Memo / Informational"
    if method == "FORMULA":
        return "Formula-Based Contribution"
    if method == "PERCENTAGE_OF_GROSS_PAY":
        return "% of Gross Pay Contribution"
    if method == "FIXED_AMOUNT":
        return "Fixed Amount Contribution"
    return "Employer Contribution"



def build_linked_deduction_lookup(deduction_raw_df: pd.DataFrame | None) -> pd.DataFrame:
    if deduction_raw_df is None or deduction_raw_df.empty:
        return pd.DataFrame(columns=[
            "employer_org_ein",
            "company_deduction_id",
            "linked_deduction_name",
            "linked_master_deduction_list",
            "linked_master_deduction_id",
        ])

    ddf = deduction_raw_df.copy()
    ddf["linked_master_deduction_list"] = infer_master_list_name(ddf)
    cols = [c for c in ["employer_org_ein", "id", "display_name", "linked_master_deduction_list", "master_ded_identifier"] if c in ddf.columns]
    ddf = ddf[cols].copy()
    ddf = ddf.rename(columns={
        "id": "company_deduction_id",
        "display_name": "linked_deduction_name",
        "master_ded_identifier": "linked_master_deduction_id",
    })
    ddf = ddf.drop_duplicates(subset=[c for c in ["employer_org_ein", "company_deduction_id"] if c in ddf.columns])
    return ddf



def contribution_setup_notes(row: pd.Series) -> str:
    notes: list[str] = []
    derived_type = str(row.get("Derived Contribution Type") or "")
    if derived_type:
        notes.append(f"Type inferred as {derived_type}")
    if str(row.get("Contribution Method") or "") == "Formula":
        notes.append("Formula-based contribution")
    if str(row.get("Link Contribution") or "") == "Yes":
        notes.append("Linked contribution enabled")
    if str(row.get("Applicable S Corp") or "") == "Yes":
        notes.append("S corp applicable")
    if str(row.get("Linked Deduction Name") or ""):
        notes.append(f"Linked to deduction {row['Linked Deduction Name']}")
    return "; ".join(notes)



def contribution_ui_mapping_notes(row: pd.Series) -> str:
    notes: list[str] = []
    if str(row.get("Contribution Method") or ""):
        notes.append(f"Method UI shows {row['Contribution Method']}")
    if str(row.get("W-2 Box") or ""):
        notes.append(f"W-2 Box UI shows {row['W-2 Box']}")
    if str(row.get("Link Contribution") or "") in {"Yes", "No"}:
        notes.append(f"Link contribution toggle shows {row['Link Contribution']}")
    if str(row.get("Applicable S Corp") or "") in {"Yes", "No"}:
        notes.append(f"Applicable S corp toggle shows {row['Applicable S Corp']}")
    return "; ".join(notes)



def build_contribution_master_table(
    raw_df: pd.DataFrame,
    deduction_raw_df: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = raw_df.copy()
    df["Company"] = df["source_file"].map(lambda x: file_alias(x, "contribution"))
    df["Master Contribution List"] = infer_master_contribution_list(df)
    df["Derived Contribution Type"] = df.apply(infer_contribution_type, axis=1)

    df["Contribution Method"] = df.get("contritbution_method", "").map(contribution_method_ui)
    df["Contribution Value"] = df.get("contritbution_value", "").map(amount_display)
    df["Contribution %"] = df.get("contritbution_percent_value", "").map(amount_display)
    df["Monthly Limit"] = df.get("monthly_limit", "").map(amount_display)
    df["Annual Limit"] = df.get("annual_limit", "").map(amount_display)
    df["W-2 Box"] = df.get("w2_box", "").map(w2_box_ui)
    df["W-2 Label"] = df.get("w2_label", "").fillna("")
    df["Auto Assign to Employee"] = df.get("auto_assign_to_ee", "").map(yes_no_blank)
    df["Applicable S Corp"] = df.get("applicable_s_corp", "").map(yes_no_blank)
    df["Link Contribution"] = df.get("link_contribution", "").map(yes_no_blank)
    df["Discarded"] = df.get("discarded", "").map(yes_no_blank)
    df["Deleted"] = df.get("deleted", "").map(yes_no_blank)

    linked_lookup = build_linked_deduction_lookup(deduction_raw_df)
    if not linked_lookup.empty and {"employer_org_ein", "company_deduction_id"}.issubset(df.columns):
        df = df.merge(linked_lookup, on=["employer_org_ein", "company_deduction_id"], how="left")
    else:
        df["linked_deduction_name"] = ""
        df["linked_master_deduction_list"] = ""
        df["linked_master_deduction_id"] = ""

    default_summary = summarize_defaults(df, "contribution_code", CONTRIBUTION_DEFAULT_FIELDS)
    flagged = df.apply(
        lambda row: default_flags(
            row,
            default_summary,
            group_key="contribution_code",
            candidate_fields=CONTRIBUTION_DEFAULT_FIELDS,
            field_labels=CONTRIBUTION_FIELD_LABELS,
            ui_renderers={
                "contritbution_method": contribution_method_ui,
                "w2_box": w2_box_ui,
                "applicable_s_corp": yes_no_blank,
                "link_contribution": yes_no_blank,
            },
        ),
        axis=1,
        result_type="expand",
    )
    flagged.columns = [
        "Likely Master-Default Fields",
        "Likely Master-Default Values Snapshot",
        "Master-Default Field Count",
        "Master-Default Basis",
    ]
    df = pd.concat([df, flagged], axis=1)

    df["Setup Notes"] = df.apply(contribution_setup_notes, axis=1)
    df["UI Mapping Notes"] = df.apply(contribution_ui_mapping_notes, axis=1)

    final_columns = [
        "Company",
        "source_file",
        "employer_org_ein",
        "Master Contribution List",
        "contribution_code",
        "name",
        "Derived Contribution Type",
        "Contribution Method",
        "Contribution Value",
        "Contribution %",
        "Monthly Limit",
        "Annual Limit",
        "W-2 Box",
        "W-2 Label",
        "company_deduction_id",
        "linked_deduction_name",
        "linked_master_deduction_list",
        "linked_master_deduction_id",
        "Auto Assign to Employee",
        "Applicable S Corp",
        "Link Contribution",
        "Discarded",
        "Deleted",
        "created_by",
        "created_date",
        "updated_by",
        "updated_date",
        "Likely Master-Default Fields",
        "Likely Master-Default Values Snapshot",
        "Master-Default Field Count",
        "Master-Default Basis",
        "Setup Notes",
        "UI Mapping Notes",
        "id",
        "contribution_identifier",
        "contritbution_method",
        "contritbution_value",
        "monthly_limit",
        "annual_limit",
        "w2_box",
        "w2_label",
        "auto_assign_to_ee",
        "contritbution_percent_value",
        "applicable_s_corp",
        "link_contribution",
    ]
    final_columns = [c for c in final_columns if c in df.columns]
    final_df = df[final_columns].copy()

    rename_map = {
        "source_file": "Source File",
        "employer_org_ein": "Employer EIN",
        "contribution_code": "Master Contribution Code",
        "name": "Company Contribution Name",
        "company_deduction_id": "Linked Company Deduction ID",
        "linked_deduction_name": "Linked Deduction Name",
        "linked_master_deduction_list": "Linked Master Deduction List",
        "linked_master_deduction_id": "Linked Master Deduction ID",
        "created_by": "Created By",
        "created_date": "Created Date",
        "updated_by": "Updated By",
        "updated_date": "Updated Date",
        "id": "Raw ID",
        "contribution_identifier": "Raw Contribution Identifier",
        "contritbution_method": "Raw Contribution Method",
        "contritbution_value": "Raw Contribution Value",
        "monthly_limit": "Raw Monthly Limit",
        "annual_limit": "Raw Annual Limit",
        "w2_box": "Raw W-2 Box",
        "w2_label": "Raw W-2 Label",
        "auto_assign_to_ee": "Raw Auto Assign To EE",
        "contritbution_percent_value": "Raw Contribution %",
        "applicable_s_corp": "Raw Applicable S Corp",
        "link_contribution": "Raw Link Contribution",
    }
    final_df = final_df.rename(columns=rename_map)
    return final_df, default_summary


# -----------------------
# Output / app helpers
# -----------------------

def safe_sheet_name(prefix: str, name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9_]+", "_", Path(name).stem)
    sheet = f"{prefix}_{base}" if prefix else base
    return sheet[:31] or "Sheet1"



def to_excel_bytes(outputs: dict[str, dict[str, pd.DataFrame]]) -> bytes:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        if "deduction" in outputs:
            outputs["deduction"]["master"].to_excel(writer, sheet_name="Deductions_Master", index=False)
            outputs["deduction"]["raw"].to_excel(writer, sheet_name="Deduction_Raw_SQL", index=False)
            outputs["deduction"]["summary"].to_excel(writer, sheet_name="Deduction_Defaults", index=False)
            for source_name, group in outputs["deduction"]["master"].groupby("Source File"):
                group.to_excel(writer, sheet_name=safe_sheet_name("D", source_name), index=False)

        if "earning" in outputs:
            outputs["earning"]["master"].to_excel(writer, sheet_name="Earnings_Master", index=False)
            outputs["earning"]["raw"].to_excel(writer, sheet_name="Earning_Raw_SQL", index=False)
            outputs["earning"]["summary"].to_excel(writer, sheet_name="Earning_Defaults", index=False)
            for source_name, group in outputs["earning"]["master"].groupby("Source File"):
                group.to_excel(writer, sheet_name=safe_sheet_name("E", source_name), index=False)

        if "contribution" in outputs:
            outputs["contribution"]["master"].to_excel(writer, sheet_name="Contributions_Master", index=False)
            outputs["contribution"]["raw"].to_excel(writer, sheet_name="Contribution_Raw_SQL", index=False)
            outputs["contribution"]["summary"].to_excel(writer, sheet_name="Contribution_Defaults", index=False)
            for source_name, group in outputs["contribution"]["master"].groupby("Source File"):
                group.to_excel(writer, sheet_name=safe_sheet_name("C", source_name), index=False)
    output.seek(0)
    return output.getvalue()



def parse_uploaded_files(uploaded_files: list[Any]) -> dict[str, pd.DataFrame]:
    parsed: dict[str, list[pd.DataFrame]] = {"deduction": [], "earning": [], "contribution": []}
    unsupported_files: list[str] = []

    for file in uploaded_files:
        sql_text = file.read().decode("utf-8", errors="ignore")
        found_kinds = detect_kinds(sql_text)
        if not found_kinds:
            unsupported_files.append(file.name)
            continue
        for kind in found_kinds:
            parsed[kind].append(parse_insert_table(sql_text, file.name, kind))

    if unsupported_files:
        raise ValueError(
            "Unsupported SQL file(s): " + ", ".join(unsupported_files) + ". "
            "Only ups_company_deduction, ups_company_earning_detail, and ups_company_contribution/contritbution INSERT dumps are supported."
        )

    result: dict[str, pd.DataFrame] = {}
    for kind, frames in parsed.items():
        if frames:
            result[kind] = pd.concat(frames, ignore_index=True)
    if not result:
        raise ValueError("No supported INSERT statements found in uploaded files.")
    return result



def build_outputs(parsed: dict[str, pd.DataFrame]) -> dict[str, dict[str, pd.DataFrame]]:
    outputs: dict[str, dict[str, pd.DataFrame]] = {}
    if "deduction" in parsed:
        master_df, summary_df = build_deduction_master_table(parsed["deduction"])
        outputs["deduction"] = {
            "raw": parsed["deduction"],
            "master": master_df,
            "summary": summary_df,
        }
    if "earning" in parsed:
        master_df, summary_df = build_earning_master_table(parsed["earning"])
        outputs["earning"] = {
            "raw": parsed["earning"],
            "master": master_df,
            "summary": summary_df,
        }
    if "contribution" in parsed:
        deduction_raw_df = parsed.get("deduction")
        master_df, summary_df = build_contribution_master_table(parsed["contribution"], deduction_raw_df)
        outputs["contribution"] = {
            "raw": parsed["contribution"],
            "master": master_df,
            "summary": summary_df,
        }
    return outputs



def render_dataset_section(kind: str, payload: dict[str, pd.DataFrame], client_name: str = "") -> None:
    master_df = payload["master"]
    raw_df = payload["raw"]
    summary_df = payload["summary"]

    title_map = {
        "deduction": "Deductions",
        "earning": "Earnings",
        "contribution": "Contributions",
    }
    title = title_map[kind]
    st.subheader(f"{title} master table")

    c1, c2, c3 = st.columns(3)
    c1.metric("Files", master_df["Source File"].nunique() if "Source File" in master_df.columns else 0)
    c2.metric("Rows", len(master_df))

    if kind == "deduction":
        c3.metric("Master IDs", master_df["Master Deduction ID"].nunique(dropna=True) if "Master Deduction ID" in master_df.columns else 0)
        preview_cols = [
            c for c in [
                "Company",
                "Employer EIN",
                "Master Deduction List",
                "Master Deduction ID",
                "Company Deduction Name",
                "Derived Deduction Type",
                "Deduction Method (UI)",
                "W-2 Box (UI)",
                "Deduction Code",
                "Sync From Benefit",
                "Auto Assign to Employee",
                "Weekly Schedule",
                "Biweekly Schedule",
                "Semimonthly Schedule",
                "Arrears Applicable",
                "Likely Master-Default Fields",
            ] if c in master_df.columns
        ]
        csv_name = "ups_company_deduction_master_table.csv"
        excel_name = "ups_company_deduction_master_table.xlsx"
        summary_label = "Likely default summary by master_ded_identifier"
    elif kind == "earning":
        c3.metric("Master IDs", master_df["Master Earning ID"].nunique(dropna=True) if "Master Earning ID" in master_df.columns else 0)
        preview_cols = [
            c for c in [
                "Company",
                "Employer EIN",
                "Master Earning List",
                "Master Earning ID",
                "Company Earning Name",
                "Derived Earning Type",
                "Earning Code",
                "W-2 Box",
                "Disposable",
                "Subject to WC",
                "Is Editable",
                "Include in Overtime",
                "Policy Linked",
                "Linked Earning Present",
                "Is Default",
                "Likely Master-Default Fields",
            ] if c in master_df.columns
        ]
        csv_name = "ups_company_earning_master_table.csv"
        excel_name = "ups_company_earning_master_table.xlsx"
        summary_label = "Likely default summary by earning_id"
    else:
        c3.metric("Master Codes", master_df["Master Contribution Code"].nunique(dropna=True) if "Master Contribution Code" in master_df.columns else 0)
        preview_cols = [
            c for c in [
                "Company",
                "Employer EIN",
                "Master Contribution List",
                "Master Contribution Code",
                "Company Contribution Name",
                "Derived Contribution Type",
                "Contribution Method",
                "Contribution Value",
                "Contribution %",
                "Linked Deduction Name",
                "Applicable S Corp",
                "Link Contribution",
                "Likely Master-Default Fields",
            ] if c in master_df.columns
        ]
        csv_name = "ups_company_contribution_master_table.csv"
        excel_name = "ups_company_contribution_master_table.xlsx"
        summary_label = "Likely default summary by contribution_code"

    if "Client Name" in master_df.columns:
        preview_cols.insert(0, "Client Name")

    st.dataframe(master_df[preview_cols], use_container_width=True, height=500)

    csv_bytes = master_df.to_csv(index=False).encode("utf-8")
    excel_bytes = to_excel_bytes({kind: payload})
    d1, d2 = st.columns(2)
    
    file_prefix = f"{client_name.replace(' ', '_').lower()}_" if client_name else ""
    csv_name = f"{file_prefix}{csv_name}"
    excel_name = f"{file_prefix}{excel_name}"
    
    d1.download_button(
        f"Download {title.lower()} master table (CSV)",
        data=csv_bytes,
        file_name=csv_name,
        mime="text/csv",
        key=f"csv_{kind}",
    )
    d2.download_button(
        f"Download {title.lower()} workbook (Excel)",
        data=excel_bytes,
        file_name=excel_name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"xlsx_{kind}",
    )

    with st.expander(f"Raw parsed {title.lower()} SQL rows"):
        st.dataframe(raw_df, use_container_width=True, height=350)

    with st.expander(summary_label):
        st.dataframe(summary_df, use_container_width=True, height=350)



def render_ui() -> None:
    if st is None:
        raise ModuleNotFoundError("streamlit is required to run this app")

    st.title("UPS Company Deduction / Earning / Contribution → Master Table")
    st.caption(
        "Upload separate SQL dump files for Deductions, Earnings, and Contributions. "
        "The app supports merging them into a master table."
    )
    
    st.markdown("### Client Configuration")
    client_name = st.text_input("Client Name", placeholder="Enter Client Name (e.g., Acme Corp)").strip()
    
    st.markdown("### Upload Files")
    col1, col2, col3 = st.columns(3)
    with col1:
        ded_files = st.file_uploader("Upload Deduction SQL(s)", type=["sql"], accept_multiple_files=True, key="ded")
    with col2:
        earn_files = st.file_uploader("Upload Earning SQL(s)", type=["sql"], accept_multiple_files=True, key="earn")
    with col3:
        cont_files = st.file_uploader("Upload Contribution SQL(s)", type=["sql"], accept_multiple_files=True, key="cont")
    
    all_uploaded = (ded_files or []) + (earn_files or []) + (cont_files or [])

    if not all_uploaded:
        st.info("Upload at least one .sql file.")
        return

    st.markdown("---")
    if st.button("Run Processing", type="primary"):
        try:
            parsed = parse_uploaded_files(all_uploaded)
            outputs = build_outputs(parsed)
            
            # Incorporate Client Name
            if client_name:
                for kind in outputs:
                    if "master" in outputs[kind]:
                        outputs[kind]["master"].insert(0, "Client Name", client_name)

            total_rows = sum(len(payload["master"]) for payload in outputs.values())
            type_labels = ", ".join(sorted(outputs.keys()))
            st.success(f"Processed files. Detected: {type_labels}. Built {total_rows} total row(s).")
            
            st.subheader("Downloads")
            combined_excel_name = f"{client_name.replace(' ', '_').lower()}_ups_company_master_tables.xlsx" if client_name else "ups_company_master_tables.xlsx"

            combined_excel_bytes = to_excel_bytes(outputs)
            st.download_button(
                "Download combined workbook (Excel)",
                data=combined_excel_bytes,
                file_name=combined_excel_name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="combined_workbook",
            )

            ordered_kinds = [k for k in ["deduction", "earning", "contribution"] if k in outputs]
            if len(ordered_kinds) == 1:
                only_kind = ordered_kinds[0]
                render_dataset_section(only_kind, outputs[only_kind], client_name)
            else:
                tab_titles = [
                    {"deduction": "Deductions", "earning": "Earnings", "contribution": "Contributions"}[k]
                    for k in ordered_kinds
                ]
                tabs = st.tabs(tab_titles)
                for tab, kind in zip(tabs, ordered_kinds):
                    with tab:
                        render_dataset_section(kind, outputs[kind], client_name)

        except Exception as exc:
            st.error(str(exc))


if __name__ == "__main__":
    render_ui()
