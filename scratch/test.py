import sys
sys.path.append(r'c:\Users\shobhit.sharma\Downloads\Deduction Tool')
from audit_fast_api.core.adp.payment_audit import run_adp_payment_audit
with open(r'C:\Users\shobhit.sharma\Downloads\Hensen Brothers\Payment Method Uzio Hansan Brother 08th May.xlsx', 'rb') as f_u, open(r'C:\Users\shobhit.sharma\Downloads\Hensen Brothers\Direct Deposit Information.xlsx', 'rb') as f_a:
    res = run_adp_payment_audit(f_u.read(), f_a.read())
    print(res['Summary'])
    print("Missing in ADP:")
    missing = [r for r in res['Comparison_Detail'] if r['Status'] == 'Missing in ADP']
    if missing:
        print(missing[0])
