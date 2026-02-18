
import streamlit as st
from datetime import datetime

from utils.withholding_core import (
    load_key_mapping_yml,
    load_filing_status_map_from_txt,
    run_withholding_audit
)

def render_ui():
    st.title("ADP ↔ UZIO Withholding Audit")
    st.markdown("""
    **Inputs**
    - **ADP Export** (CSV/XLSX) – wide format (one row per employee)
    - **UZIO Withholding Export** (CSV/XLSX) – long format with:
      `employee_id`, `withholding_field_key`, `withholding_field_value`
    - **Mapping** (XLSX) – must include columns:
      - `Uzio Columns`
      - `ADP Columns`
    """)

    payroll_file = st.file_uploader("Upload ADP File", type=["csv", "xlsx", "xls"], key="adp_payroll")
    uzio_file = st.file_uploader("Upload UZIO Withholding (Long) File", type=["csv", "xlsx", "xls"], key="adp_uzio")
    mapping_file = st.file_uploader("Upload Mapping File", type=["xlsx", "xls", "csv"], key="adp_mapping")

    client_name = st.text_input("Enter Client Name (for Report Filename)", value="Client_Name", key="adp_client")

    key_map_path = "key_mapping.yml"
    fs_map_path = "filing_status_code.txt"

    if payroll_file and uzio_file and mapping_file:
        # Column selectors
        import pandas as pd
        import io

        def read_any_bytes(b, name):
            if name.lower().endswith(".csv"):
                return pd.read_csv(io.BytesIO(b), dtype=str)
            return pd.read_excel(io.BytesIO(b), engine="openpyxl", dtype=str)

        payroll_df = read_any_bytes(payroll_file.getvalue(), payroll_file.name)
        uzio_df = read_any_bytes(uzio_file.getvalue(), uzio_file.name)

        payroll_cols = list(payroll_df.columns)
        uzio_cols = list(uzio_df.columns)

        st.subheader("Column Mapping")
        payroll_emp_col = st.selectbox("ADP Employee ID column", payroll_cols, index=payroll_cols.index("Associate ID") if "Associate ID" in payroll_cols else 0)
        uzio_emp_col = st.selectbox("UZIO employee_id column", uzio_cols, index=uzio_cols.index("employee_id") if "employee_id" in uzio_cols else 0)
        uzio_key_col = st.selectbox("UZIO withholding_field_key column", uzio_cols, index=uzio_cols.index("withholding_field_key") if "withholding_field_key" in uzio_cols else 0)
        uzio_val_col = st.selectbox("UZIO withholding_field_value column", uzio_cols, index=uzio_cols.index("withholding_field_value") if "withholding_field_value" in uzio_cols else 0)

        st.subheader("Active Employee Filter (optional)")
        active_flag_col = st.selectbox("Active flag/status column (optional)", ["(none)"] + payroll_cols, index=0)
        active_vals_text = st.text_input("Values treated as Active (comma-separated)", value="Active,A,1,True,Yes")

        if st.button("Run ADP ↔ UZIO Withholding Audit", type="primary"):
            with st.spinner("Processing..."):
                try:
                    key_label_map = load_key_mapping_yml(key_map_path)
                    filing_status_map = load_filing_status_map_from_txt(fs_map_path)

                    active_col = None if active_flag_col == "(none)" else active_flag_col
                    active_vals = [v.strip() for v in active_vals_text.split(",") if v.strip()]

                    report_bytes, metrics = run_withholding_audit(
                        payroll_bytes=payroll_file.getvalue(),
                        payroll_filename=payroll_file.name,
                        uzio_bytes=uzio_file.getvalue(),
                        uzio_filename=uzio_file.name,
                        mapping_bytes=mapping_file.getvalue(),
                        mapping_filename=mapping_file.name,
                        mapping_payroll_col_name="ADP Columns",
                        payroll_employee_id_col=payroll_emp_col,
                        uzio_employee_id_col=uzio_emp_col,
                        uzio_key_col=uzio_key_col,
                        uzio_value_col=uzio_val_col,
                        active_flag_col=active_col,
                        active_values=active_vals,
                        key_label_map=key_label_map,
                        filing_status_map=filing_status_map
                    )

                    st.success("Audit Completed Successfully!")
                    today_str = datetime.now().strftime("%b-%d-%Y")
                    clean_client = "".join([c if c.isalnum() or c in (' ', '_', '-') else '' for c in client_name]).strip().replace(" ", "_")
                    filename = f"{clean_client}_ADP_UZIO_Withholding_Report_{today_str}.xlsx"

                    st.download_button(
                        label="Download Report",
                        data=report_bytes,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    st.error(f"Error: {e}")
