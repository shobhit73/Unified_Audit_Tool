"""Analyze Travel Management Q1 to deduce per-deduction pre/post-tax behavior."""
import csv

path = r'C:/Users/shobhit.sharma/Downloads/Travel Management Prior Payroll Setup/Q1.csv'
with open(path, encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

print(f'Total rows: {len(rows)}')

def num(s):
    if s is None: return 0.0
    s = s.strip().replace(',', '').replace('$','')
    if s in ('','-','None'): return 0.0
    try: return float(s)
    except: return 0.0

ded_cols = [
    'VOLUNTARY DEDUCTION : 75-SUPPORT',
    'VOLUNTARY DEDUCTION : ADV-PAYADVANCE',
    'VOLUNTARY DEDUCTION : DEN-DENTAL',
    'VOLUNTARY DEDUCTION : IPY-TAPCHECK',
    'VOLUNTARY DEDUCTION : MED-MEDICAL',
    'VOLUNTARY DEDUCTION : REV-REVERSE/REISSU',
    'VOLUNTARY DEDUCTION : VIS-VISION',
]

# Strategy 1: rows with only ONE nonzero deduction => clean attribution
for ded in ded_cols:
    print(f'\n=== {ded} ===')
    isolated = []
    for r in rows:
        amt = num(r[ded])
        if amt <= 0: continue
        others = [num(r[d]) for d in ded_cols if d != ded]
        if any(o > 0 for o in others): continue
        gross = num(r['GROSS PAY'])
        fit_tx = num(r['FEDERAL INCOME - EMPLOYEE TAXABLE'])
        fica_tx = num(r['SOCIAL SECURITY - EMPLOYEE TAXABLE'])
        medi_tx = num(r['MEDICARE - EMPLOYEE TAXABLE'])
        sit_tx = num(r['WORKED IN STATE - EMPLOYEE TAXABLE'])
        isolated.append({
            'id': r['ASSOCIATE ID'], 'amt': amt, 'gross': gross,
            'd_fit': round(gross - fit_tx, 2),
            'd_fica': round(gross - fica_tx, 2),
            'd_medi': round(gross - medi_tx, 2),
            'd_sit': round(gross - sit_tx, 2),
        })
    print(f'  isolated rows: {len(isolated)}')
    for r in isolated[:5]:
        print(f'    {r}')
    if isolated:
        # Aggregate: how often does delta == amount?
        n = len(isolated)
        match = lambda fld: sum(1 for r in isolated if abs(r[fld] - r['amt']) <= 0.05)
        print(f'  d_fit  approx amt in {match("d_fit")}/{n}')
        print(f'  d_fica approx amt in {match("d_fica")}/{n}')
        print(f'  d_medi approx amt in {match("d_medi")}/{n}')
        print(f'  d_sit  approx amt in {match("d_sit")}/{n}')
        zero = lambda fld: sum(1 for r in isolated if abs(r[fld]) <= 0.05)
        print(f'  d_fit  == 0 in {zero("d_fit")}/{n}')
        print(f'  d_fica == 0 in {zero("d_fica")}/{n}')
        print(f'  d_medi == 0 in {zero("d_medi")}/{n}')
        print(f'  d_sit  == 0 in {zero("d_sit")}/{n}')

# Strategy 2: where multiple deductions exist, see if total deduction sum reconciles to delta
print('\n\n=== reconciling multi-deduction rows ===')
n_examined = 0
n_match_all_pretax = 0
n_match_zero = 0
for r in rows[:50]:
    nonzero = {d: num(r[d]) for d in ded_cols if num(r[d]) > 0}
    if len(nonzero) <= 1: continue
    gross = num(r['GROSS PAY'])
    fit_tx = num(r['FEDERAL INCOME - EMPLOYEE TAXABLE'])
    d_fit = round(gross - fit_tx, 2)
    print(f'  {r["ASSOCIATE ID"]}: gross={gross} d_fit={d_fit} sum_ded={sum(nonzero.values()):.2f} -> {nonzero}')
    n_examined += 1
    if n_examined >= 8: break
