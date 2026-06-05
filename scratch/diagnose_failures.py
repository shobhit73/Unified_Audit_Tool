"""Diagnose the 3 stress-test failures with direct evidence."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.paycom.withholding_audit import _compare_amount, _compare_boolean, _parse_number

print("=== Failure 1: G2 'blank vs false' flagged as mismatch ===")
result = _compare_boolean("", "false")
print(f"  _compare_boolean('', 'false') = {result}")
print(f"  Interpretation: tool treats blank as 'unknown', not as 'false'")
print(f"  Result: flags as 'Blank vs Value' mismatch")
print()
print(f"  Compare with money side:")
result_money = _compare_amount("", "0")
print(f"  _compare_amount('', '0')      = {result_money}")
print(f"  -> money treats blank as 0 (matches 0). Inconsistent behavior across types.")

print()
print("=== Failure 2-3: G3 1-cent differences silently pass ===")
for uz_cents in ("999", "1000", "1001", "1005", "1006"):
    result = _compare_amount("10", uz_cents)
    diff_dollars = (float(uz_cents) / 100.0) - 10.0
    print(f"  _compare_amount('10', {uz_cents!r:>6s})  diff=${diff_dollars:+.3f}  -> match={result[0]}")
print()
print("  Tolerance check is `abs(diff) < 0.01` — exactly 1-cent diffs are caught,")
print("  but floating-point precision makes some 1-cent diffs evaluate to ~0.00999999")
print("  which IS < 0.01 -> treated as a match. Tolerance should be tighter.")
