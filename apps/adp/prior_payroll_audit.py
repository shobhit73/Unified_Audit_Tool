import streamlit as st
import pandas as pd
import io
import re
from utils.audit_utils import clean_money_val, norm_colname

def load_mapping(file, cat_name, adp_col, uzio_col):
    """Load a mapping file and return a list of mappings (ADP_Name, UZIO_Name)."""
    try:
        df = pd.read_excel(file)
        # Normalize headers to find columns
        df.columns = [norm_colname(c) for c in df.columns]
        
        # Finding the actual column names in the sheet
        actual_adp_col = next((c for c in df.columns if adp_col.lower() in c.lower()), None)
        actual_uzio_col = next((c for c in df.columns if uzio_col.lower() in c.lower()), None)
        
        if not actual_adp_col or not actual_uzio_col:
            st.warning(f"Could not find exact columns in {cat_name} mapping. Looking for '{adp_col}' and '{uzio_col}'. Available: {list(df.columns)}")
            return []
            
        mappings = []
        for _, row in df.iterrows():
            a_val = str(row[actual_adp_col]).strip()
            u_val = str(row[actual_uzio_col]).strip()
            if a_val and u_val and a_val.lower() != 'nan' and u_val.lower() != 'nan':
                mappings.append({
                    "Category": cat_name,
                    "ADP_Name": a_val,
                    "UZIO_Name": u_val
                })
        return mappings
    except Exception as e:
        st.error(f"Error loading {cat_name} mapping: {e}")
        return []

def find_header_and_data(file):
    """Find the correct header row and read the data, skipping metadata sheets."""
    with pd.ExcelFile(file) as xls:
        target_sheet = xls.sheet_names[0]
        
        # Skip "Report Criteria" or similar metadata sheets
        if len(xls.sheet_names) > 1 and "criteria" in xls.sheet_names[0].lower():
            target_sheet = xls.sheet_names[1]
        
        # Peek at first 50 rows to find header
        df_peek = pd.read_excel(xls, sheet_name=target_sheet, header=None, nrows=50)
        header_idx = 0
        for i, row in df_peek.iterrows():
            row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
            if "employee id" in row_str or "employee name" in row_str:
                header_idx = i
                break
                
        # Read the full sheet starting from the header row
        df = pd.read_excel(xls, sheet_name=target_sheet, header=header_idx)
        
        # Also get the row ABOVE the header (for Uzio's multi-row headers)
        header_top = None
        if header_idx > 0:
            header_top = df_peek.iloc[header_idx - 1].tolist()
            
        return df, header_top, target_sheet

def calculate_totals(df, header_top, column_names):
    """Sum up values for columns that match any of the provided names, handling multi-row headers."""
    total = 0.0
    found_cols = []
    
    # --- STRICT ROW FILTERING ---
    # Find the ID column (Associate ID or Employee ID)
    id_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["associate id", "employee id", "file #"])), None)
    
    if id_col:
        # Filter: Only rows where ID column is not null, not empty, and not "Total"
        df_clean = df[df[id_col].notna()].copy()
        df_clean[id_col] = df_clean[id_col].astype(str).str.strip()
        df_clean = df_clean[
            (df_clean[id_col] != "") & 
            (~df_clean[id_col].str.lower().str.contains("total|grand", na=False))
        ]
    else:
        # Fallback: Just filter out "Total" rows in the first column
        mask = df.iloc[:, 0].astype(str).str.lower().str.contains("total|grand", na=False)
        df_clean = df[~mask].copy()
    
    # Normalize current columns
    norm_cols_main = {norm_colname(c).lower(): i for i, c in enumerate(df.columns)}
    
    # Normalize top header columns if present
    norm_cols_top = {}
    if header_top:
        for i, c in enumerate(header_top):
            if pd.notna(c) and str(c).strip() != "":
                norm_cols_top[norm_colname(c).lower()] = i

    for name in column_names:
        n_name = norm_colname(name).lower()
        
        # 1. Check main header row (Direct match)
        if n_name in norm_cols_main:
            idx = norm_cols_main[n_name]
            col_name = df.columns[idx]
            total += df_clean[col_name].apply(clean_money_val).sum()
            found_cols.append(col_name)
        
        # 2. Check top header row (Group match - e.g. Earning or Tax category name)
        elif n_name in norm_cols_top:
            start_idx = norm_cols_top[n_name]
            # Find the end of this group (next non-null in top header)
            end_idx = len(df.columns)
            if header_top:
                for k in range(start_idx + 1, len(header_top)):
                    if pd.notna(header_top[k]) and str(header_top[k]).strip() != "":
                        end_idx = k
                        break
            
            # Sum columns within this range that look like 'Amounts'
            for k in range(start_idx, end_idx):
                main_h = str(df.columns[k]).lower()
                # Heuristic for sub-columns we want to sum:
                # Include 'Amount', 'Total', 'Current', 'EE', 'ER'
                # Exclude 'Wages', 'Hours', 'Rate', 'Basis'
                if any(x in main_h for x in ['amount', 'total', 'current', 'ee', 'er', 'tax']):
                    if not any(x in main_h for x in ['wages', 'hours', 'rate', 'basis']):
                        total += df_clean.iloc[:, k].apply(clean_money_val).sum()
                        found_cols.append(f"{df.columns[k]}")
            
    return total, found_cols

def run_comparison(adp_files, uzio_file, mappings):
    """Main logic to compare totals based on mappings."""
    try:
        # Load UZIO (smarter check for criteria sheet)
        df_uzio, uzio_top, uzio_sheet = find_header_and_data(uzio_file)
        
        # Load ADP files
        adp_data_list = []
        for adp_file in adp_files:
            df_adp, adp_top, adp_sheet = find_header_and_data(adp_file)
            adp_data_list.append((df_adp, adp_top, adp_sheet))
    except Exception as e:
        return None, f"Error reading payroll files: {e}"

    results = []
    
    # Group mappings by UZIO_Name
    unique_uzio_items = {}
    for m in mappings:
        u_name = m["UZIO_Name"]
        if u_name not in unique_uzio_items:
            unique_uzio_items[u_name] = {"Category": m["Category"], "ADP_Names": []}
        unique_uzio_items[u_name]["ADP_Names"].append(m["ADP_Name"])

    for u_name, data in unique_uzio_items.items():
        cat = data["Category"]
        adp_names = data["ADP_Names"]
        
        # Calculate ADP Total across all files
        adp_total = 0.0
        adp_cols = []
        for df_adp, adp_top, _ in adp_data_list:
            tot, cols = calculate_totals(df_adp, adp_top, adp_names)
            adp_total += tot
            for c in cols:
                if c not in adp_cols:
                    adp_cols.append(c)
        
        # Calculate UZIO Total
        uzio_total, uzio_cols = calculate_totals(df_uzio, uzio_top, [u_name])
        
        diff = uzio_total - adp_total
        status = "Match" if abs(diff) <= 0.02 else "Mismatch"
        
        results.append({
            "Category": cat,
            "UZIO Item": u_name,
            "ADP Total": round(adp_total, 2),
            "UZIO Total": round(uzio_total, 2),
            "Difference": round(diff, 2),
            "Status": status,
            "ADP Columns Found": ", ".join(adp_cols) if adp_cols else "None",
            "UZIO Columns Found": ", ".join(uzio_cols) if uzio_cols else "None"
        })

    df_results = pd.DataFrame(results)
    
    # Generate Excel Report
    out_buffer = io.BytesIO()
    with pd.ExcelWriter(out_buffer, engine='xlsxwriter') as writer:
        df_results.to_excel(writer, sheet_name="Full Comparison", index=False)
        df_mismatches = df_results[df_results["Status"] == "Mismatch"][["Category", "UZIO Item", "ADP Columns Found", "UZIO Columns Found", "ADP Total", "UZIO Total", "Difference"]]
        df_mismatches.to_excel(writer, sheet_name="Mismatches Only", index=False)
        
        for sheet_name in ["Full Comparison", "Mismatches Only"]:
            sheet = writer.sheets[sheet_name]
            curr_df = df_results if sheet_name == "Full Comparison" else df_mismatches
            for i, col in enumerate(curr_df.columns):
                column_len = max(curr_df[col].astype(str).map(len).max(), len(col)) + 2
                sheet.set_column(i, i, min(column_len, 50))

    return df_results, out_buffer.getvalue()

def render_ui():
    st.title("ADP - Prior Payroll Audit Tool")
    st.markdown("""
    This tool compares the totals of payroll elements (Earnings, Deductions, Contributions, Taxes) 
    between ADP and UZIO reports based on provided mapping files.
    
    **Required Files**:
    1.  **ADP Prior Payroll File** (Excel)
    2.  **UZIO Prior Payroll Register File** (Excel)
    3.  **4 Mapping Files** (Earnings, Deductions, Contributions, Taxes)
    """)
    
    with st.expander("📁 Upload Payroll Reports", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            adp_files = st.file_uploader("Upload ADP Prior Payroll File(s)", type=["xlsx", "xls"], accept_multiple_files=True, key="tc_adp")
        with col2:
            uzio_file = st.file_uploader("Upload UZIO Prior Payroll Register", type=["xlsx", "xls"], key="tc_uzio")

    with st.expander("🗺️ Upload Mapping Files", expanded=True):
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            earn_file = st.file_uploader("Earnings Mapping File", type=["xlsx", "xls"], key="tc_m_earn")
            cont_file = st.file_uploader("Contributions Mapping File", type=["xlsx", "xls"], key="tc_m_cont")
        with m_col2:
            ded_file = st.file_uploader("Deductions Mapping File", type=["xlsx", "xls"], key="tc_m_ded")
            tax_file = st.file_uploader("Taxes Mapping File", type=["xlsx", "xls"], key="tc_m_tax")

    # Handle results persistence
    if "audit_results" not in st.session_state:
        st.session_state.audit_results = None
    if "audit_report" not in st.session_state:
        st.session_state.audit_report = None

    if adp_files and len(adp_files) > 0 and all([uzio_file, earn_file, cont_file, ded_file, tax_file]):
        if st.button("Run Total Comparison", type="primary"):
            with st.spinner("Processing files and calculating totals..."):
                # Load mappings
                all_mappings = []
                all_mappings.extend(load_mapping(earn_file, "Earnings", "Source Earning Code Name", "Uzio Earning Code Name"))
                all_mappings.extend(load_mapping(ded_file, "Deductions", "Source Deduction Code Name", "Uzio Deduction Code Name"))
                all_mappings.extend(load_mapping(cont_file, "Contributions", "Source Contribution Code Name", "Uzio Contribution Code Name"))
                # Tax mapping has different headers
                all_mappings.extend(load_mapping(tax_file, "Taxes", "Source Tax Code Name", "Uzio Tax Code Description"))

                if not all_mappings:
                    st.error("No mappings could be loaded from the mapping files. Please check the column headers.")
                    return

                res_df, report_data = run_comparison(adp_files, uzio_file, all_mappings)
                st.session_state.audit_results = res_df
                st.session_state.audit_report = report_data

        if st.session_state.audit_results is not None:
            results_df = st.session_state.audit_results
            report_data = st.session_state.audit_report
            
            st.success("Comparison completed!")
            
            # Display metrics
            matches = len(results_df[results_df["Status"] == "Match"])
            mismatches = len(results_df[results_df["Status"] == "Mismatch"])
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Items", len(results_df))
            m2.metric("Matches", matches)
            m3.metric("Mismatches", mismatches, delta=mismatches if mismatches > 0 else None, delta_color="inverse")
            
            # Display results table
            st.subheader("Comparison Results")
            
            # Color coding for status
            def color_status(val):
                color = 'green' if val == 'Match' else 'red'
                return f'color: {color}'
            
            st.dataframe(results_df.style.map(color_status, subset=['Status']), use_container_width=True)
            
            # Download button
            st.download_button(
                label="Download Full Comparison Report",
                data=report_data,
                file_name=f"Prior payroll audit report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="tc_download_v2"
            )

if __name__ == "__main__":
    st.set_page_config(page_title="Prior Payroll Audit Tool", layout="wide")
    render_ui()
