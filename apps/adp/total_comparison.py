import streamlit as st
import pandas as pd
import io
import re
from utils.audit_utils import clean_money_val, norm_colname

def load_mapping(file, cat_name, adp_col, uzio_col):
    """Load a mapping file and return a list of mappings (ADP_Name, UZIO_Name)."""
    try:
        file.seek(0)
        if str(file.name).lower().endswith('.csv'):
            df = pd.read_csv(file)
        else:
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

def find_header_and_data(file):
    """Find the correct header row and read the data, skipping metadata sheets."""
    file.seek(0)
    if str(file.name).lower().endswith('.csv'):
        file.seek(0)
        df_peek = pd.read_csv(file, header=None, nrows=50)
        header_idx = 0
        for i, row in df_peek.iterrows():
            row_str = " ".join([str(x).lower() for x in row if pd.notna(x)])
            if "employee id" in row_str or "employee name" in row_str:
                header_idx = i
                break
                
        file.seek(0)
        df = pd.read_csv(file, header=header_idx)
        
        header_top = None
        if header_idx > 0:
            header_top = df_peek.iloc[header_idx - 1].tolist()
            
        target_sheet = "Sheet1"
    else:
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

    # --- GRAND TOTAL ROW DETECTION ---
    # Sometimes ADP exports include a grand total at the very bottom but fail to clear
    # the last employee's ID from that row, messing up totals for that employee.
    if len(df) > 1:
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        shared_cols = 0
        for c in df.columns[:5]:
            v_last = str(last_row[c]).strip()
            v_prev = str(prev_row[c]).strip()
            if v_last and v_last == v_prev and v_last.lower() != 'nan':
                shared_cols += 1
                
        if shared_cols >= 1:
            for c in df.columns:
                try:
                    val_last = clean_money_val(last_row[c])
                    if val_last > 100:
                        sum_rest = sum(clean_money_val(x) for x in df[c].iloc[:-1])
                        if sum_rest > 0 and abs(val_last - sum_rest) < sum_rest * 0.05:
                            df = df.iloc[:-1]
                            break
                except:
                    continue
                    
    return df, header_top, target_sheet

def calculate_totals(df, header_top, column_names):
    """Sum up values for columns that match any of the provided names, handling multi-row headers."""
    found_cols = []
    emp_tots = {}
    emp_row_counts = {}
    
    # --- STRICT ROW FILTERING ---
    id_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["associate id", "employee id", "file #"])), None)
    # Prioritize 'pay date' / 'check date' before 'period end' to avoid using quarterly
    # period end dates instead of actual pay dates when both columns exist in the file.
    date_col = next((c for c in df.columns if any(x == str(c).lower().strip() for x in ["pay date", "check date"])), None)
    if date_col is None:
        date_col = next((c for c in df.columns if any(x in str(c).lower() for x in ["pay date", "period end", "check date"])), None)
    
    if id_col:
        df_clean = df[df[id_col].notna()].copy()
        df_clean[id_col] = df_clean[id_col].apply(normalize_id)
        df_clean = df_clean[
            (df_clean[id_col] != "Unknown") & 
            (~df_clean[id_col].str.lower().str.contains("total|grand", na=False))
        ]
    else:
        mask = df.iloc[:, 0].astype(str).str.lower().str.contains("total|grand", na=False)
        df_clean = df[~mask].copy()
    
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
        eid = row[id_col] if id_col else "Unknown"
        pay_date = format_pay_date(row[date_col]) if date_col else "Unknown"
        
        row_tot = sum(clean_money_val(row[c]) for c in set(cols_to_sum))
        
        key = (eid, pay_date)
        if key not in emp_tots:
            emp_tots[key] = 0.0
            emp_row_counts[key] = 0
        emp_tots[key] += row_tot
        emp_row_counts[key] += 1
            
    return sum(emp_tots.values()), found_cols, emp_tots, emp_row_counts

def run_comparison(adp_files, uzio_file, mappings):
    """Main logic to compare totals based on mappings."""
    try:
        df_uzio, uzio_top, uzio_sheet = find_header_and_data(uzio_file)
        adp_data_list = []
        for adp_file in adp_files:
            df_adp, adp_top, adp_sheet = find_header_and_data(adp_file)
            adp_data_list.append((df_adp, adp_top, adp_sheet))
    except Exception as e:
        return None, f"Error reading payroll files: {e}"

    results = []
    employee_mismatches = []
    
    unique_uzio_items = {}
    for m in mappings:
        u_name = m["UZIO_Name"]
        if u_name not in unique_uzio_items:
            unique_uzio_items[u_name] = {"Category": m["Category"], "ADP_Names": []}
        unique_uzio_items[u_name]["ADP_Names"].append(m["ADP_Name"])

    for u_name, data in unique_uzio_items.items():
        cat = data["Category"]
        adp_names = data["ADP_Names"]
        
        adp_total = 0.0
        adp_cols = []
        adp_emp_detail = {}
        adp_emp_counts = {}
        for df_a, adp_t, _ in adp_data_list:
            tot, cols, emp_m, emp_c = calculate_totals(df_a, adp_t, adp_names)
            adp_total += tot
            for c in cols:
                if c not in adp_cols:
                    adp_cols.append(c)
            for (eid, p_date), v in emp_m.items():
                if eid not in adp_emp_detail: adp_emp_detail[eid] = {}
                adp_emp_detail[eid][p_date] = adp_emp_detail[eid].get(p_date, 0.0) + v
            for (eid, p_date), c_val in emp_c.items():
                if eid not in adp_emp_counts: adp_emp_counts[eid] = {}
                adp_emp_counts[eid][p_date] = adp_emp_counts[eid].get(p_date, 0) + c_val
        
        uzio_total, uzio_cols, uzio_emp_m, _ = calculate_totals(df_uzio, uzio_top, [u_name])
        uzio_emp_detail = {}
        for (eid, p_date), v in uzio_emp_m.items():
            if eid not in uzio_emp_detail: uzio_emp_detail[eid] = {}
            uzio_emp_detail[eid][p_date] = uzio_emp_detail[eid].get(p_date, 0.0) + v
        
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
        
        if status == "Mismatch":
            all_emp_ids = set(adp_emp_detail.keys()).union(set(uzio_emp_detail.keys()))
            for eid in all_emp_ids:
                if eid == "Unknown": continue
                
                emp_adp_total = sum(adp_emp_detail.get(eid, {}).values())
                emp_uzio_total = sum(uzio_emp_detail.get(eid, {}).values())
                
                if abs(emp_uzio_total - emp_adp_total) > 0.02:
                    adp_dates = adp_emp_detail.get(eid, {})
                    uzio_dates = uzio_emp_detail.get(eid, {})
                    all_dates = set(adp_dates.keys()).union(set(uzio_dates.keys()))
                    
                    for p_date in all_dates:
                        val_adp = adp_dates.get(p_date, 0.0)
                        val_uzio = uzio_dates.get(p_date, 0.0)
                        date_diff = val_uzio - val_adp
                        
                        if abs(date_diff) > 0.02:
                            multiple_entries = "Yes" if adp_emp_counts.get(eid, {}).get(p_date, 0) > 1 else "No"
                            employee_mismatches.append({
                                "Associate ID": eid,
                                "Pay Date": p_date,
                                "Category": cat,
                                "UZIO Item": u_name,
                                "ADP Amount": round(val_adp, 2),
                                "UZIO Amount": round(val_uzio, 2),
                                "Difference": round(date_diff, 2),
                                "Multiple ADP Entries on Same Date": multiple_entries
                            })

    df_results = pd.DataFrame(results)
    df_emp_mismatches = pd.DataFrame(employee_mismatches)
    
    out_buffer = io.BytesIO()
    with pd.ExcelWriter(out_buffer, engine='xlsxwriter') as writer:
        df_results.to_excel(writer, sheet_name="Full Comparison", index=False)
        df_mismatches = df_results[df_results["Status"] == "Mismatch"][["Category", "UZIO Item", "ADP Columns Found", "UZIO Columns Found", "ADP Total", "UZIO Total", "Difference"]]
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
                column_len = max(curr_df[col].astype(str).map(len).max(), len(col)) + 2
                sheet.set_column(i, i, min(column_len, 50))

    return df_results, out_buffer.getvalue()

# ---------------------------------------------------------------------------
# Auto-detect helper for bulk upload
# ---------------------------------------------------------------------------
def auto_detect_files(uploaded_files):
    """
    Given a list of uploaded files, auto-detect each file's role by inspecting
    column headers. Returns a dict with keys:
      'adp', 'uzio', 'earn', 'ded', 'cont', 'tax', 'unknown'
    """
    result = {
        'adp': [], 'uzio': None,
        'earn': None, 'ded': None, 'cont': None, 'tax': None,
        'unknown': []
    }

    for f in uploaded_files:
        f.seek(0)
        try:
            name = f.name.lower()
            if name.endswith('.csv'):
                df_peek = pd.read_csv(f, nrows=2, dtype=str)
            else:
                df_peek = pd.read_excel(f, nrows=2, dtype=str)
            cols = [str(c).lower().strip() for c in df_peek.columns]
            f.seek(0)
        except Exception:
            f.seek(0)
            result['unknown'].append(f)
            continue

        col_str = " | ".join(cols)

        if 'source tax code name' in col_str:
            result['tax'] = f
        elif 'source earning code name' in col_str:
            result['earn'] = f
        elif 'source deduction code name' in col_str:
            result['ded'] = f
        elif 'source contribution code name' in col_str:
            result['cont'] = f
        elif 'employee id' in col_str and (
            'regular wage' in col_str or
            ('first name' in col_str and 'gross pay' in col_str)
        ):
            result['uzio'] = f
        elif 'associate id' in col_str or 'regular earnings' in col_str:
            result['adp'].append(f)
        else:
            result['unknown'].append(f)

    return result

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def render_ui():
    st.title("ADP - Prior Payroll Audit Tool")
    st.markdown("""
    Compares the totals of payroll elements (Earnings, Deductions, Contributions, Taxes)
    between ADP and UZIO reports based on provided mapping files.
    """)

    # ── Upload mode toggle ──────────────────────────────────────────────────
    upload_mode = st.radio(
        "Upload Mode",
        ["📦 Bulk Upload (select all files at once)", "🗂️ Manual Upload (file by file)"],
        horizontal=True,
        key="tc_upload_mode"
    )

    adp_files = []
    uzio_file = earn_file = cont_file = ded_file = tax_file = None

    # ── BULK MODE ────────────────────────────────────────────────────────────
    if upload_mode.startswith("📦"):
        st.info(
            "Select **all** your files at once — ADP payroll file(s), UZIO register, "
            "and all 4 mapping files. The tool will automatically classify each file.",
            icon="💡"
        )
        bulk_files = st.file_uploader(
            "Drop all files here",
            type=["xlsx", "xls", "csv"],
            accept_multiple_files=True,
            key="tc_bulk"
        )
        if bulk_files:
            detected = auto_detect_files(bulk_files)
            adp_files = detected['adp']
            uzio_file = detected['uzio']
            earn_file = detected['earn']
            ded_file  = detected['ded']
            cont_file = detected['cont']
            tax_file  = detected['tax']

            st.markdown("#### Auto-detected file roles")
            summary_rows = []
            for f in adp_files:
                summary_rows.append({"File": f.name, "Detected As": "ADP Payroll"})
            if uzio_file:
                summary_rows.append({"File": uzio_file.name, "Detected As": "UZIO Register"})
            if earn_file:
                summary_rows.append({"File": earn_file.name, "Detected As": "Earnings Mapping"})
            if ded_file:
                summary_rows.append({"File": ded_file.name, "Detected As": "Deductions Mapping"})
            if cont_file:
                summary_rows.append({"File": cont_file.name, "Detected As": "Contributions Mapping"})
            if tax_file:
                summary_rows.append({"File": tax_file.name, "Detected As": "Taxes Mapping"})
            for f in detected['unknown']:
                summary_rows.append({"File": f.name, "Detected As": "Unknown - not used"})

            if summary_rows:
                role_df = pd.DataFrame(summary_rows)
                # Colour the Detected As column
                def _colour_role(val):
                    if "ADP" in val or "UZIO" in val or "Mapping" in val:
                        return "color: green"
                    return "color: orange"
                st.dataframe(
                    role_df.style.map(_colour_role, subset=["Detected As"]),
                    use_container_width=True, hide_index=True
                )

            missing = []
            if not adp_files: missing.append("ADP Payroll file")
            if not uzio_file: missing.append("UZIO Register")
            if not earn_file: missing.append("Earnings Mapping")
            if not ded_file:  missing.append("Deductions Mapping")
            if not cont_file: missing.append("Contributions Mapping")
            if not tax_file:  missing.append("Taxes Mapping")
            if missing:
                st.warning(f"Still missing: **{', '.join(missing)}**. Please add these files too.")

    # ── MANUAL MODE ──────────────────────────────────────────────────────────
    else:
        with st.expander("📁 Upload Payroll Reports", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                adp_files = st.file_uploader(
                    "Upload ADP Prior Payroll File(s)",
                    type=["xlsx", "xls", "csv"],
                    accept_multiple_files=True,
                    key="tc_adp"
                )
            with col2:
                uzio_file = st.file_uploader(
                    "Upload UZIO Prior Payroll Register",
                    type=["xlsx", "xls", "csv"],
                    key="tc_uzio"
                )

        with st.expander("🗺️ Upload Mapping Files", expanded=True):
            m_col1, m_col2 = st.columns(2)
            with m_col1:
                earn_file = st.file_uploader("Earnings Mapping File",      type=["xlsx", "xls", "csv"], key="tc_m_earn")
                cont_file = st.file_uploader("Contributions Mapping File", type=["xlsx", "xls", "csv"], key="tc_m_cont")
            with m_col2:
                ded_file  = st.file_uploader("Deductions Mapping File",    type=["xlsx", "xls", "csv"], key="tc_m_ded")
                tax_file  = st.file_uploader("Taxes Mapping File",         type=["xlsx", "xls", "csv"], key="tc_m_tax")

    # ── RUN AUDIT ────────────────────────────────────────────────────────────
    if "audit_results" not in st.session_state:
        st.session_state.audit_results = None
    if "audit_report" not in st.session_state:
        st.session_state.audit_report = None

    all_ready = (
        adp_files and len(adp_files) > 0 and
        all([uzio_file, earn_file, cont_file, ded_file, tax_file])
    )

    if all_ready:
        if st.button("Run Total Comparison", type="primary", use_container_width=True):
            with st.spinner("Processing files and calculating totals..."):
                all_mappings = []
                all_mappings.extend(load_mapping(earn_file, "Earnings",      "Source Earning Code Name",      "Uzio Earning Code Name"))
                all_mappings.extend(load_mapping(ded_file,  "Deductions",    "Source Deduction Code Name",    "Uzio Deduction Code Name"))
                all_mappings.extend(load_mapping(cont_file, "Contributions", "Source Contribution Code Name", "Uzio Contribution Code Name"))
                all_mappings.extend(load_mapping(tax_file,  "Taxes",         "Source Tax Code Name",          "Uzio Tax Code Description"))

                if not all_mappings:
                    st.error("No mappings could be loaded. Please check the mapping file column headers.")
                    return

                res_df, report_data = run_comparison(adp_files, uzio_file, all_mappings)
                if res_df is not None:
                    st.session_state.audit_results = res_df
                    st.session_state.audit_report  = report_data
                else:
                    st.error(f"Failed to generate results. Error: {report_data}")

    if st.session_state.audit_results is not None:
        results_df  = st.session_state.audit_results
        report_data = st.session_state.audit_report

        st.success("Comparison completed!")

        matches    = len(results_df[results_df["Status"] == "Match"])
        mismatches = len(results_df[results_df["Status"] == "Mismatch"])

        m1, m2, m3 = st.columns(3)
        m1.metric("Total Items", len(results_df))
        m2.metric("Matches",    matches)
        m3.metric("Mismatches", mismatches,
                  delta=mismatches if mismatches > 0 else None,
                  delta_color="inverse")

        st.subheader("Comparison Results")

        def color_status(val):
            return 'color: green' if val == 'Match' else 'color: red'

        st.dataframe(
            results_df.style.map(color_status, subset=['Status']),
            use_container_width=True
        )

        st.download_button(
            label="Download Full Comparison Report",
            data=report_data,
            file_name="Prior payroll audit report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="tc_download_v2",
            use_container_width=True
        )

if __name__ == "__main__":
    st.set_page_config(page_title="Total Comparison Tool", layout="wide")
    render_ui()
