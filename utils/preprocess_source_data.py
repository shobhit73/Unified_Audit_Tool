"""
Pre-processing auto-fix utility for Census Generators.
Applies opt-in corrections to source data AFTER sanity checks have been shown to the user.
The sanity check module (validate_source_data) is NOT modified.
"""
import re
import pandas as pd


def apply_auto_fixes(df, resolved_field_map):
    """
    Apply auto-corrections to the source DataFrame in-place.
    Returns a dict of DataFrames tracking what was changed (for soft flag display).

    Fixes applied:
      1. Blank FLSA Classification → filled based on Pay Type (Hourly→Non-Exempt, Salaried→Exempt)
      2. Blank Work Email → filled from Personal Email
      3. Zip code normalization → strip after '-', zero-pad to 5 digits

    Args:
        df: Source DataFrame (mutated in-place)
        resolved_field_map: Dict mapping standard field names to resolved column names

    Returns:
        dict with keys: 'flsa_fills', 'email_fallbacks', 'zip_corrections'
        Each value is a pd.DataFrame of corrections made.
    """
    flsa_fills = []
    email_fallbacks = []
    zip_corrections = []

    # Resolve column references
    emp_id_col = resolved_field_map.get('Employee ID')
    pay_type_col = resolved_field_map.get('Pay Type')
    flsa_col = resolved_field_map.get('FLSA Classification')
    work_email_col = resolved_field_map.get('Work Email')
    personal_email_col = resolved_field_map.get('Personal Email')
    zip_col = resolved_field_map.get('Zip')

    def get_emp_ref(row, idx):
        ref = f"Row {idx + 2}"
        if emp_id_col and emp_id_col in df.columns:
            eid = row.get(emp_id_col)
            if pd.notna(eid) and str(eid).strip():
                ref = str(eid).strip()
        return ref

    for idx, row in df.iterrows():
        emp_ref = get_emp_ref(row, idx)

        # --- FIX 1: Blank FLSA Classification → fill based on Pay Type ---
        if (flsa_col and flsa_col in df.columns
                and pay_type_col and pay_type_col in df.columns):
            flsa_val = row.get(flsa_col)
            pay_val = row.get(pay_type_col)

            flsa_is_blank = pd.isna(flsa_val) or str(flsa_val).strip() == ""
            pay_str = str(pay_val).strip().lower() if pd.notna(pay_val) and str(pay_val).strip() else ""

            if flsa_is_blank and pay_str:
                if "hourly" in pay_str or "hour" in pay_str:
                    df.at[idx, flsa_col] = "Non-Exempt"
                    flsa_fills.append({
                        'Employee ID': emp_ref,
                        'Pay Type': str(pay_val).strip(),
                        'Assigned FLSA': 'Non-Exempt'
                    })
                elif "salary" in pay_str or "salaried" in pay_str:
                    df.at[idx, flsa_col] = "Exempt"
                    flsa_fills.append({
                        'Employee ID': emp_ref,
                        'Pay Type': str(pay_val).strip(),
                        'Assigned FLSA': 'Exempt'
                    })

        # --- FIX 2: Blank Work Email → fill from Personal Email ---
        if work_email_col and work_email_col in df.columns:
            we_val = row.get(work_email_col)
            if pd.isna(we_val) or str(we_val).strip() == "":
                if personal_email_col and personal_email_col in df.columns:
                    pe_val = row.get(personal_email_col)
                    if pd.notna(pe_val) and str(pe_val).strip():
                        df.at[idx, work_email_col] = str(pe_val).strip()
                        email_fallbacks.append({
                            'Employee ID': emp_ref,
                            'Personal Email Used': str(pe_val).strip()
                        })

        # --- FIX 3: Zip Code Normalization ---
        if zip_col and zip_col in df.columns:
            zip_val = row.get(zip_col)
            if pd.notna(zip_val) and str(zip_val).strip():
                original_zip = str(zip_val).strip()

                # Step 1: Strip everything after '-'
                cleaned = original_zip.split('-')[0].strip()

                # Step 2: Remove any decimal part (e.g. '82913.0')
                cleaned = cleaned.split('.')[0].strip()

                # Step 3: Keep digits only
                digits_only = re.sub(r'[^0-9]', '', cleaned)

                # Step 4: Zero-pad to 5 digits if < 5 (keep as string!)
                if digits_only and len(digits_only) < 5:
                    digits_only = digits_only.zfill(5)

                # Only track if something changed
                if digits_only and digits_only != original_zip:
                    df.at[idx, zip_col] = digits_only
                    zip_corrections.append({
                        'Employee ID': emp_ref,
                        'Original Zip': original_zip,
                        'Corrected Zip': digits_only
                    })

    return {
        'flsa_fills': pd.DataFrame(flsa_fills),
        'email_fallbacks': pd.DataFrame(email_fallbacks),
        'zip_corrections': pd.DataFrame(zip_corrections),
    }
