import streamlit as st
import pandas as pd
import io
import re

APP_TITLE = "Paycom vs Uzio – Time Off Tool"

def clean_id(x):
    """Normalize Employee ID (remove .0, strip, remove leading zeros)."""
    if pd.isna(x): return ""
    s = str(x).strip()
    if s.endswith(".0"): s = s[:-2]
    # Remove leading zeros to match typically
    s = s.lstrip("0")
    return s

def run_tool(file_paycom, file_uzio):
    # 1. Read Paycom Report (Likely HTML disguised as XLS)
    try:
        # Try read_html first as it's common for Paycom 'xls'
        dfs = pd.read_html(file_paycom, header=0)
        if not dfs:
            st.error("No tables found in Paycom file.")
            return None
        df_p = dfs[0] # Assume main table is first
    except ValueError:
        # Fallback if actual Excel or CSV
        file_paycom.seek(0)
        try:
             df_p = pd.read_excel(file_paycom)
        except:
             file_paycom.seek(0)
             df_p = pd.read_csv(file_paycom)
    except Exception as e:
        st.error(f"Error reading Paycom file: {e}")
        return None

    # Normalize Paycom Columns
    # Look for 'Employee Code' and 'Net Available'
    p_cols = {c.strip(): c for c in df_p.columns}
    
    col_id_p = next((c for c in p_cols if "Employee Code" in c or "Employee ID" in c or "EECode" in c), None)
    col_bal_p = next((c for c in p_cols if "Net Available" in c), None)

    if not col_id_p or not col_bal_p:
        st.error(f"Could not find required columns in Paycom file. Found: {list(df_p.columns)}")
        return None

    # Create Lookup Map: CleanID -> Net Available
    # Filter out rows where Net Available is NaN/Blank if we want to preserve blanks?
    # Requirement: "Keep them as blank operating balance... dont fill anything"
    # So we only map values that exist.
    
    balance_map = {}
    for idx, row in df_p.iterrows():
        eid = clean_id(row[col_id_p])
        val = row[col_bal_p]
        
        if eid and pd.notna(val) and str(val).strip() != "":
            balance_map[eid] = val

    # 2. Read Uzio Template
    # "tab 2... row 4 header" -> sheet_name=1, header=3
    try:
        df_u = pd.read_excel(file_uzio, sheet_name=1, header=3)
    except Exception as e:
        st.error(f"Error reading Uzio Template: {e}")
        return None

    # Identify Uzio Columns
    u_cols = {c.strip(): c for c in df_u.columns}
    col_id_u = next((c for c in u_cols if "Employee ID" in c), None)
    # User said "Operating Balance", file usually says "Opening Balance". Check both.
    col_bal_u = next((c for c in u_cols if "Operating Balance" in c), None)
    if not col_bal_u:
        col_bal_u = next((c for c in u_cols if "Opening Balance" in c), None)

    if not col_id_u or not col_bal_u:
        # Fallback: maybe header is on different row? 
        # But for now assume structure is correct as per instructions.
        st.error(f"Could not find 'Employee ID' or 'Opening/Operating Balance' in Uzio Template. Found: {list(df_u.columns)}")
        return None

    # Future Columns
    col_future_app = next((c for c in p_cols if "Future Approved" in c), None)
    col_future_pend = next((c for c in p_cols if "Future Pending" in c), None)

    # 3. Process / Update
    
    # Trackers
    matched_paycom_ids = set()
    unassigned_policies_rows = [] # List of dicts (Uzio rows)

    # function to apply map
    def update_balance(row):
        # Rule: If existing Uzio Opening Balance is Blank/NaN -> Keep Blank (Policy Not Assigned)
        # If existing is 0.00 or any number -> Update with Paycom Value (Policy Assigned)
        
        current_val = row[col_bal_u]
        
        # Check if current value is "blank" (NaN or empty string)
        if pd.isna(current_val) or str(current_val).strip() == "":
            # Log as Unassigned Policy
            unassigned_policies_rows.append(row.to_dict())
            return current_val # Keep blank
            
        # Policy is assigned, try to find Paycom value
        eid = clean_id(row[col_id_u])
        if eid in balance_map:
            matched_paycom_ids.add(eid)
            return balance_map[eid] # Update with Paycom value
            
        return current_val # Keep original if no Paycom match

    df_u[col_bal_u] = df_u.apply(update_balance, axis=1)

    # --- Generate Additional Reports ---

    # 1. Missing in Uzio (Paycom IDs not in matched_paycom_ids)
    # We need to look at all Paycom rows where we *have* a Net Available but didn't match
    missing_in_uzio = []
    for idx, row in df_p.iterrows():
        eid = clean_id(row[col_id_p])
        # If valid ID and valid Balance, check if matched
        if eid and eid not in matched_paycom_ids:
            # Also check if it was worth matching (has balance)
            val = row[col_bal_p]
            if pd.notna(val) and str(val).strip() != "":
                missing_in_uzio.append(row)
    
    df_missing = pd.DataFrame(missing_in_uzio)

    # 2. Unassigned Policies (Already collected)
    df_unassigned = pd.DataFrame(unassigned_policies_rows)

    # 3. Future Time Off
    # Filter Paycom rows where Future Approved > 0 OR Future Pending > 0
    future_rows = []
    if col_future_app and col_future_pend:
        for idx, row in df_p.iterrows():
            try:
                fa = float(row[col_future_app]) if pd.notna(row[col_future_app]) else 0
                fp = float(row[col_future_pend]) if pd.notna(row[col_future_pend]) else 0
                if fa > 0 or fp > 0:
                    future_rows.append(row)
            except:
                pass # skip if non-numeric
    
    df_future = pd.DataFrame(future_rows)

    # 4. Output
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine='xlsxwriter') as writer:
        # Tab 1: Updated Template
        df_u.to_excel(writer, sheet_name='Time Off Details', index=False)
        
        # Tab 2: Missing in Uzio
        if not df_missing.empty:
            df_missing.to_excel(writer, sheet_name='Missing in Uzio', index=False)
        else:
            pd.DataFrame({'Message': ['All Paycom employees matched']}).to_excel(writer, sheet_name='Missing in Uzio', index=False)

        # Tab 3: Unassigned Policies
        if not df_unassigned.empty:
            df_unassigned.to_excel(writer, sheet_name='Unassigned Policies', index=False)
        else:
            pd.DataFrame({'Message': ['No unassigned policies found']}).to_excel(writer, sheet_name='Unassigned Policies', index=False)
            
        # Tab 4: Future Time Off
        if not df_future.empty:
            df_future.to_excel(writer, sheet_name='Future Time Off', index=False)
        else:
            pd.DataFrame({'Message': ['No future time off found']}).to_excel(writer, sheet_name='Future Time Off', index=False)
            
        # Tab 5: Paycom Raw Data
        df_p.to_excel(writer, sheet_name='Paycom Raw Data', index=False)
        
    return out.getvalue()

def render_ui():
    st.title(APP_TITLE)
    st.markdown("""
    **Instructions**:
    1. Upload **Paycom TimeOff Summary Report** (.xls / HTML).
    2. Upload **Uzio Time Off Import Template** (.xlsx).
    
    **Logic**:
    - Matches employees by **Employee ID**.
    - Updates **Operating/Opening Balance** in Uzio with **Net Available** from Paycom.
    - **Blanks in Paycom** are ignored (Uzio value remains blank).
    """)

    col1, col2 = st.columns(2)
    with col1:
        f_p = st.file_uploader("Paycom TimeOff Report", type=["xls", "html", "xlsx"], key="pt_p")
    with col2:
        f_u = st.file_uploader("Uzio Template", type=["xlsx"], key="pt_u")

    if st.button("Generate Import File", key="run_timeoff"):
        if not f_u or not f_p:
            st.error("Please upload both files.")
            return
            
        try:
            with st.spinner("Processing..."):
                res = run_tool(f_p, f_u)
                
            if res:
                st.success("File Generated Successfully!")
                st.download_button(
                    "Download Uzio Import File",
                    data=res,
                    file_name="Uzio_TimeOff_Update.xlsx"
                )
        except Exception as e:
            st.error(f"An error occurred: {e}")
            st.exception(e)
