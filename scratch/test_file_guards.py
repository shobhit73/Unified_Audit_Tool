"""Verify detect_vendor + require_vendor against real client files."""
import sys, os, io
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\audit_fast_api")
from utils.file_shape_guards import detect_vendor, require_vendor

cases = [
    ("Carvan Q1 ADP RAW xlsx",
     r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Prior Payroll Register Report_2026-05-02-10-15-34.xlsx"),
    ("Carvan Q1 ADP CSV",
     r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv"),
    ("Travel Mgmt ADP CSV",
     r"C:\Users\shobhit.sharma\Downloads\Travel Management Prior Payroll Setup\Q1.csv"),
    ("State Tax Code (lookup table, not vendor)",
     r"C:\Users\shobhit.sharma\Downloads\State Tax Code.csv"),
]

for label, p in cases:
    with open(p, "rb") as f:
        c = f.read()
    info = detect_vendor(c, os.path.basename(p))
    print(f"{label:50}  ->  vendor={info['vendor']:8}  evidence={info['evidence'][:3]}")

print("\n--- require_vendor demo ---")

# This should NOT raise (ADP file passed to ADP tool)
with open(r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv", "rb") as f:
    c = f.read()
info = require_vendor(c, "Payroll_History_Q1_Consolidated.csv", "adp", "adp_prior_payroll_sanity")
print(f"OK ADP-into-ADP tool: vendor={info['vendor']}")

# This SHOULD raise -- fake UZIO file passed to ADP tool
fake_uzio = b"Personal|SSN,Job|Employee ID,Job|Department\n123-45-6789,001,IT"
try:
    require_vendor(fake_uzio, "fake_uzio.csv", "adp", "adp_prior_payroll_sanity")
    print("UNEXPECTED: did not raise")
except ValueError as e:
    print(f"OK fake-UZIO blocked: {e}")

# This SHOULD also raise -- fake Paycom file passed to ADP tool
fake_paycom = b"Employee_Code,SS_Number,DOL_Status,Department_Desc\n001,123-45-6789,Full-Time,IT"
try:
    require_vendor(fake_paycom, "fake_paycom.csv", "adp", "adp_prior_payroll_sanity")
    print("UNEXPECTED: did not raise")
except ValueError as e:
    print(f"OK fake-Paycom blocked: {e}")
