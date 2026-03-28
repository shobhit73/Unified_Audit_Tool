import pandas as pd
import io
import os
import sys

# Add the apps directory to path so we can import
sys.path.append(os.getcwd())

from apps.common.paycom_combined_audit import (
    read_uzio_master, 
    run_census_audit, 
    run_payment_audit, 
    run_emergency_audit,
    get_salaried_driver_exceptions,
    get_flsa_compliance_issues,
    get_active_missing_in_uzio,
    get_data_quality_issues,
    get_high_rate_anomalies,
    norm_id
)

def test_verification():
    u_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Custom Reports\Falcon\Falcon Logistics Master Custom Report.csv"
    p_path = r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\Sample Data\Sample Custom Reports\Falcon\Paycom_Falcon_Census_28th_March.xlsx"
    
    if not os.path.exists(u_path) or not os.path.exists(p_path):
        print("Missing sample files.")
        return

    print("Loading files...")
    with open(u_path, 'rb') as f:
        u_content = f.read()
    u_file = io.BytesIO(u_content)
    
    df_uzio = read_uzio_master(u_file)
    df_paycom = pd.read_excel(p_path, dtype=str)
    
    print("Running audits...")
    res_census = run_census_audit(df_uzio, df_paycom)
    
    print("Running anomaly extractions...")
    df_salaried_drivers = get_salaried_driver_exceptions(df_uzio, df_paycom)
    df_flsa_issues = get_flsa_compliance_issues(df_uzio)
    df_active_missing = get_active_missing_in_uzio(df_uzio, df_paycom)
    df_dq_issues = get_data_quality_issues(df_paycom)
    df_high_rates = get_high_rate_anomalies(df_paycom)
    
    print(f"Salaried Drivers: {len(df_salaried_drivers)}")
    print(f"FLSA Issues: {len(df_flsa_issues)}")
    print(f"Active Missing in Uzio: {len(df_active_missing)}")
    print(f"Data Quality Issues: {len(df_dq_issues)}")
    print(f"High Rate Anomalies: {len(df_high_rates)}")

    if not df_salaried_drivers.empty:
         print("\nSample Salaried Driver Exception:")
         print(df_salaried_drivers.head(2))

    if not df_active_missing.empty:
         print("\nSample Active Missing in Uzio:")
         print(df_active_missing.head(2))
         
    if not df_flsa_issues.empty:
         print("\nSample FLSA issues:")
         print(df_flsa_issues.head(2))

if __name__ == "__main__":
    test_verification()
