"""Sanity-check that the client name field produces the expected filename."""
import sys, os, re
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import the module to confirm it parses cleanly.
import apps.paycom.prior_payroll_setup_helper as m
print("Module imports OK:", callable(m.render_ui))
print()

# Replicate the sanitization the UI does, then show each test input's filename.
test_cases = [
    "Chief Delivery",
    "Acme: West Coast",
    'Bob/Tom & "Co."',
    "",
    "   ",
    "Tab\there",
    "C:\\Bad\\Name",
]
print(f"  {'Input':<30s}  Output filename")
print(f"  {'-' * 30:<30s}  {'-' * 50}")
for inp in test_cases:
    raw = (inp or "").strip() or "Client"
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "", raw).strip() or "Client"
    fname = f"{safe}_Payroll_Setup_Helper.xlsx"
    print(f"  {inp!r:<30s}  {fname}")
