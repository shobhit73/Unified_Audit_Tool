import streamlit as st
import pandas as pd
import io
import re
import os
from utils.audit_utils import clean_money_val, norm_colname

def load_mapping(file, cat_name, source_col, uzio_col):
    """Load a mapping file and return a list of mappings (Source_Name, UZIO_Name)."""
    try:
        df = pd.read_excel(file)
        # Normalize headers to find columns
        df.columns = [norm_colname(c) for c in df.columns]
        
        # Finding the actual column names in the sheet
        actual_source_col = next((c for c in df.columns if source_col.lower() in c.lower()), None)
        actual_uzio_col = next((c for c in df.columns if uzio_col.lower() in c.lower()), None)
        
        if not actual_source_col or not actual_uzio_col:
            st.warning(f"Could not find exact columns in {cat_name} mapping. Looking for '{source_col}' and '{uzio_col}'. Available: {list(df.columns)}")
            return []
            
        mappings = []
        for _, row in df.iterrows():
            s_val = str(row[actual_source_col]).strip()
            u_val = str(row[actual_uzio_col]).strip()
            if s_val and u_val and s_val.lower() != 'nan' and u_val.lower() != 'nan':
                mappings.append({
                    "Category": cat_name,
                    "Source_Name": s_val,
                    "UZIO_Name": u_val
                })
        return mappings
    except Exception as e:
        st.error(f"Error loading {cat_name} mapping: {e}")
        return []

def format_pay_date(date_val):
    if pd.isna(date_val) or str(date_val).strip() in ["", "nan", "NaT"]:
        return "Unknown"
    try:
        dt = pd.to_datetime(date_val)
        return dt.strftime('%Y-%m-%d')
    except:
        return str(date_val).strip()

def normalize_id(id_val):
    """Strip hyphens, leading zeros, and whitespace from ID for matching."""
    if pd.isna(id_val):
        return "Unknown"
    s = str(id_val).replace('-', '').replace(' ', '').strip()
    return s.lstrip('0') if s else "Unknown"

def parse_paycom_filename_date(filename):
    """Extract the third date from Paycom filename: Priorpayroll_MMDDYYYY_MMDDYYYY_MMDDYYYY.xlsx"""
    # Look for any sequence of 8 digits that might be a date
    match = re.findall(r'(\d{8})', filename)
    if len(match) >= 3:
        d_str = match[2] # Third date
        try:
            return f"{d_str[4:]}-{d_str[:2]}-{d_str[2:4]}" # YYYY-MM-DD
        except:
            return "Unknown"
    # Fallback for 2-date pattern
    if len(match) >= 2:
        d_str = match[1]
        try:
            return f"{d_str[4:]}-{d_str[:2]}-{d_str[2:4]}"
        except:
            return "Unknown"
    # Fallback for 1-date pattern
    if len(match) >= 1:
        d_str = match[0]
        try:
            return f"{d_str[4:]}-{d_str[:2]}-{d_str[2:4]}"
        except:
            return "Unknown"
    return "Unknown"

def find_header_and_data_uzio(file):
    """Specific logic for Uzio reports (often multi-row headers)."""
    xls = pd.ExcelFile(file)
    target_sheet = xls.sheet_names[0]
    if len(xls.sheet_names) > 1 and "criteria" in xls.sheet_names[0].lower():
        target_sheet = xls.sheet_names[1]
    
    df_peek = pd.read_excel(xls, sheet_name=target_sheet, header=None, nrows=50)
    header_idx = 0
    for i, row in df_peek.iterrows():
        row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
        if "employee id" in row_str or "employee name" in row_str:
            header_idx = i
            break
            
    df = pd.read_excel(xls, sheet_name=target_sheet, header=header_idx)
    header_top = None
    if header_idx > 0:
        header_top = df_peek.iloc[header_idx - 1].tolist()
        
    return df, header_top, target_sheet

def find_header_and_data_paycom(file):
    """Specific logic for Paycom reports."""
    # Read first sheet
    xls = pd.ExcelFile(file)
    df_peek = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=None, nrows=10)
    
    # Try to find header row dynamically
    header_idx = 0
    for i, row in df_peek.iterrows():
        row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
        if any(kw in row_str for kw in ["ee code", "description", "earning", "amount", "row labels"]):
            header_idx = i
            break
            
    df = pd.read_excel(xls, sheet_name=xls.sheet_names[0], header=header_idx)
    return df, None, xls.sheet_names[0]

def calculate_totals_uzio(df, header_top, column_names):
    """Sum up values for Uzio columns (Wide format)."""
    found_cols = []
    emp_tots = {}
    
    # Header aliases for ID and Date
    id_aliases = ["employee id", "file #", "associate id", "ee code"]
    date_aliases = ["pay date", "check date", "period end"]
    
    id_col = next((c for c in df.columns if any(x in str(c).lower() for x in id_aliases)), None)
    date_col = next((c for c in df.columns if any(x in str(c).lower() for x in date_aliases)), None)
    
    if id_col:
        df_clean = df[df[id_col].notna()].copy()
        df_clean[id_col] = df_clean[id_col].apply(normalize_id)
        df_clean = df_clean[~df_clean[id_col].str.lower().str.contains("total|grand", na=False)]
    else:
        df_clean = df.copy()

    norm_cols_main = {norm_colname(c).lower(): i for i, c in enumerate(df.columns)}
    norm_cols_top = {}
    if header_top:
        for i, c in enumerate(header_top):
            if pd.notna(c) and str(c).strip() != "":
                norm_cols_top[norm_colname(c).lower()] = i

    cols_to_sum = []
    for name in column_names:
        n_name = norm_colname(name).lower()
        if n_name in norm_cols_main:
            idx = norm_cols_main[n_name]
            cols_to_sum.append(df.columns[idx])
            found_cols.append(df.columns[idx])
        elif n_name in norm_cols_top:
            start_idx = norm_cols_top[n_name]
            end_idx = len(df.columns)
            if header_top:
                for k in range(start_idx + 1, len(header_top)):
                    if pd.notna(header_top[k]) and str(header_top[k]).strip() != "":
                        end_idx = k
                        break
            for k in range(start_idx, end_idx):
                main_h = str(df.columns[k]).lower()
                if any(x in main_h for x in ['amount', 'total', 'current', 'ee', 'er', 'tax']):
                    if not any(x in main_h for x in ['wages', 'hours', 'rate', 'basis', 'taxable']):
                        cols_to_sum.append(df.columns[k])
                        found_cols.append(f"{df.columns[k]}")
                        
    for _, row in df_clean.iterrows():
        eid = row[id_col] if id_col else "Summary"
        pay_date = format_pay_date(row[date_col]) if date_col else "Unknown"
        row_tot = sum(clean_money_val(row[c]) for c in set(cols_to_sum))
        key = (eid, pay_date)
        emp_tots[key] = emp_tots.get(key, 0.0) + row_tot
            
    return sum(emp_tots.values()), found_cols, emp_tots

def calculate_totals_paycom(df, mapping_source_names, filename, uzio_item_name=""):
    """Sum up values for Paycom (Long format)."""
    found_items = set()
    emp_tots = {}
    
    # Flexible column detection
    id_aliases = ["ee code", "employee code", "file #", "clock #", "associate id"]
    desc_aliases = ["type description", "description", "earning/deduction/tax", "code description", "row labels"]
    amt_aliases = ["current amount", "amount", "total amount", "value", "sum of amount"]
    
    id_col = next((c for c in df.columns if any(x in str(c).lower() for x in id_aliases)), None)
    desc_col = next((c for c in df.columns if any(x in str(c).lower() for x in desc_aliases)), None)
    code_desc_col = next((c for c in df.columns if "code description" in str(c).lower()), None)
    
    # Prefer 'Current Amount' over 'Total Amount' if both are in aliases
    amt_col = next((c for c in df.columns if "current amount" in str(c).lower()), None)
    if not amt_col:
        amt_col = next((c for c in df.columns if any(x in str(c).lower() for x in amt_aliases)), None)
    
    if not all([desc_col, amt_col]):
        return 0.0, [], {}

    pay_date = parse_paycom_filename_date(filename)
    norm_mappings = [n.lower().strip() for n in mapping_source_names]
    
    for _, row in df.iterrows():
        raw_desc = str(row[desc_col]).strip()
        val_desc = raw_desc.lower()
        
        # Exact match based on mapping file
        if val_desc in norm_mappings:
            # Differentiate Employee vs Employer for Social Security and Medicare
            if "medicare" in val_desc or "social security" in val_desc or "ssc" in val_desc:
                if code_desc_col and pd.notna(row[code_desc_col]):
                    code_desc_val = str(row[code_desc_col]).strip().lower()
                    is_employer_tax = "employer" in uzio_item_name.lower() or "er " in uzio_item_name.lower()
                    
                    if is_employer_tax and "client side" not in code_desc_val:
                        continue
                    if not is_employer_tax and "w/h" not in code_desc_val:
                        continue

            eid = normalize_id(row[id_col]) if id_col else "Summary"
            amount = clean_money_val(row[amt_col])
            
            key = (eid, pay_date)
            emp_tots[key] = emp_tots.get(key, 0.0) + amount
            found_items.add(raw_desc)
            
    return sum(emp_tots.values()), list(found_items), emp_tots

def run_comparison(paycom_files, uzio_file, mappings):
    """Main logic to compare totals based on mappings."""
    try:
        df_uzio, uzio_top, _ = find_header_and_data_uzio(uzio_file)
        paycom_data_list = []
        for p_file in paycom_files:
            df_p, _, _ = find_header_and_data_paycom(p_file)
            paycom_data_list.append((df_p, p_file.name))
    except Exception as e:
        return None, f"Error reading payroll files: {e}"

    results = []
    employee_mismatches = []
    
    unique_uzio_items = {}
    for m in mappings:
        u_name = m["UZIO_Name"]
        if u_name not in unique_uzio_items:
            unique_uzio_items[u_name] = {"Category": m["Category"], "Source_Names": []}
        unique_uzio_items[u_name]["Source_Names"].append(m["Source_Name"])

    for u_name, data in unique_uzio_items.items():
        cat = data["Category"]
        source_names = data["Source_Names"]
        
        paycom_total = 0.0
        paycom_items_found = []
        paycom_emp_detail = {} # (eid) -> {date: amount}
        
        for df_p, fname in paycom_data_list:
            tot, found, emp_m = calculate_totals_paycom(df_p, source_names, fname, u_name)
            paycom_total += tot
            for f in found:
                if f not in paycom_items_found: paycom_items_found.append(f)
            for (eid, p_date), v in emp_m.items():
                if eid not in paycom_emp_detail: paycom_emp_detail[eid] = {}
                paycom_emp_detail[eid][p_date] = paycom_emp_detail[eid].get(p_date, 0.0) + v
        
        uzio_total, uzio_cols, uzio_emp_m = calculate_totals_uzio(df_uzio, uzio_top, [u_name])
        uzio_emp_detail = {}
        for (eid, p_date), v in uzio_emp_m.items():
            if eid not in uzio_emp_detail: uzio_emp_detail[eid] = {}
            uzio_emp_detail[eid][p_date] = uzio_emp_detail[eid].get(p_date, 0.0) + v
        
        diff = uzio_total - paycom_total
        status = "Match" if abs(diff) <= 0.02 else "Mismatch"
        
        results.append({
            "Category": cat,
            "UZIO Item": u_name,
            "Paycom Total": round(paycom_total, 2),
            "UZIO Total": round(uzio_total, 2),
            "Difference": round(diff, 2),
            "Status": status,
            "Paycom Items Found": ", ".join(paycom_items_found) if paycom_items_found else "None",
            "UZIO Columns Found": ", ".join(uzio_cols) if uzio_cols else "None"
        })
        
        if status == "Mismatch":
            all_emp_ids = set(paycom_emp_detail.keys()).union(set(uzio_emp_detail.keys()))
            for eid in all_emp_ids:
                if eid == "Unknown": continue
                
                emp_p_total = sum(paycom_emp_detail.get(eid, {}).values())
                emp_u_total = sum(uzio_emp_detail.get(eid, {}).values())
                
                if abs(emp_u_total - emp_p_total) > 0.02:
                    p_dates = paycom_emp_detail.get(eid, {})
                    u_dates = uzio_emp_detail.get(eid, {})
                    all_dates = set(p_dates.keys()).union(set(u_dates.keys()))
                    
                    for p_date in all_dates:
                        val_p = p_dates.get(p_date, 0.0)
                        val_u = u_dates.get(p_date, 0.0)
                        date_diff = val_u - val_p
                        
                        if abs(date_diff) > 0.02:
                            employee_mismatches.append({
                                "Associate ID": eid,
                                "Pay Date": p_date,
                                "Category": cat,
                                "UZIO Item": u_name,
                                "Paycom Amount": round(val_p, 2),
                                "UZIO Amount": round(val_u, 2),
                                "Difference": round(date_diff, 2)
                            })

    df_results = pd.DataFrame(results)
    df_emp_mismatches = pd.DataFrame(employee_mismatches)
    
    out_buffer = io.BytesIO()
    with pd.ExcelWriter(out_buffer, engine='xlsxwriter') as writer:
        df_results.to_excel(writer, sheet_name="Full Comparison", index=False)
        df_mismatches = df_results[df_results["Status"] == "Mismatch"][["Category", "UZIO Item", "Paycom Items Found", "UZIO Columns Found", "Paycom Total", "UZIO Total", "Difference"]]
        df_mismatches.to_excel(writer, sheet_name="Mismatches Only", index=False)
        
        if not df_emp_mismatches.empty:
            df_emp_mismatches.to_excel(writer, sheet_name="Employee Mismatches", index=False)
            sheet_names = ["Full Comparison", "Mismatches Only", "Employee Mismatches"]
            dfs_to_format = [df_results, df_mismatches, df_emp_mismatches]
        else:
            sheet_names = ["Full Comparison", "Mismatches Only"]
            dfs_to_format = [df_results, df_mismatches]
            
        for sheet_name, curr_df in zip(sheet_names, dfs_to_format):
            sheet = writer.sheets[sheet_name]
            for i, col in enumerate(curr_df.columns):
                column_len = max(curr_df[col].astype(str).map(len).max() if not curr_df.empty else 10, len(col)) + 2
                sheet.set_column(i, i, min(column_len, 50))

    return df_results, out_buffer.getvalue()

def render_ui():
    st.title("Paycom - Prior Payroll Audit Tool")
    st.markdown("""
    This tool compares the totals of payroll elements (Earnings, Deductions, Contributions, Taxes) 
    between Paycom and UZIO reports based on provided mapping files.
    
    **Required Files**:
    1.  **Paycom Prior Payroll File(s)** (Excel - format `Priorpayroll_MMDDYYYY_MMDDYYYY_MMDDYYYY.xlsx`)
    2.  **UZIO Prior Payroll Register File** (Excel)
    3.  **4 Mapping Files** (Earnings, Deductions, Contributions, Taxes)
    """)
    
    with st.expander("📁 Upload Payroll Reports", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            paycom_files = st.file_uploader("Upload Paycom Prior Payroll File(s)", type=["xlsx", "xls"], accept_multiple_files=True, key="pc_tc_paycom")
        with col2:
            uzio_file = st.file_uploader("Upload UZIO Prior Payroll Register", type=["xlsx", "xls"], key="pc_tc_uzio")

    with st.expander("🗺️ Upload Mapping Files", expanded=True):
        m_col1, m_col2 = st.columns(2)
        with m_col1:
            earn_file = st.file_uploader("Earnings Mapping File", type=["xlsx", "xls"], key="pc_tc_m_earn")
            cont_file = st.file_uploader("Contributions Mapping File", type=["xlsx", "xls"], key="pc_tc_m_cont")
        with m_col2:
            ded_file = st.file_uploader("Deductions Mapping File", type=["xlsx", "xls"], key="pc_tc_m_ded")
            tax_file = st.file_uploader("Taxes Mapping File", type=["xlsx", "xls"], key="pc_tc_m_tax")

    if "pc_audit_results" not in st.session_state:
        st.session_state.pc_audit_results = None
    if "pc_audit_report" not in st.session_state:
        st.session_state.pc_audit_report = None

    if paycom_files and len(paycom_files) > 0 and all([uzio_file, earn_file, cont_file, ded_file, tax_file]):
        if st.button("Run Total Comparison", type="primary"):
            with st.spinner("Processing files and calculating totals..."):
                all_mappings = []
                all_mappings.extend(load_mapping(earn_file, "Earnings", "Source Earning Code Name", "Uzio Earning Code Name"))
                all_mappings.extend(load_mapping(ded_file, "Deductions", "Source Deduction Code Name", "Uzio Deduction Code Name"))
                all_mappings.extend(load_mapping(cont_file, "Contributions", "Source Contribution Code Name", "Uzio Contribution Code Name"))
                all_mappings.extend(load_mapping(tax_file, "Taxes", "Source Tax Code Name", "Uzio Tax Code Description"))

                if not all_mappings:
                    st.error("No mappings could be loaded from the mapping files. Please check the column headers.")
                    return

                res_df, report_data = run_comparison(paycom_files, uzio_file, all_mappings)
                if res_df is not None:
                    st.session_state.pc_audit_results = res_df
                    st.session_state.pc_audit_report = report_data
                else:
                    st.error(f"Failed to generate results. Error: {report_data}")

        if st.session_state.pc_audit_results is not None:
            results_df = st.session_state.pc_audit_results
            report_data = st.session_state.pc_audit_report
            
            st.success("Comparison completed!")
            matches = len(results_df[results_df["Status"] == "Match"])
            mismatches = len(results_df[results_df["Status"] == "Mismatch"])
            
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Items", len(results_df))
            m2.metric("Matches", matches)
            m3.metric("Mismatches", mismatches, delta=mismatches if mismatches > 0 else None, delta_color="inverse")
            
            st.subheader("Comparison Results")
            def color_status(val):
                return 'color: green' if val == 'Match' else 'color: red'
            st.dataframe(results_df.style.map(color_status, subset=['Status']), use_container_width=True)
            
            st.download_button(
                label="Download Full Comparison Report",
                data=report_data,
                file_name=f"Paycom_prior_payroll_audit_report.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="pc_tc_download"
            )

if __name__ == "__main__":
    st.set_page_config(page_title="Paycom Total Comparison Tool", layout="wide")
    render_ui()
