import pandas as pd
import re

def _fix_zip(z):
    if pd.isna(z) or str(z).strip() == "": return ""
    import re
    # Trim after hyphen or decimal
    s = str(z).split('.')[0].split('-')[0]
    # Keep only digits
    s = re.sub(r'[^0-9]', '', s)
    if not s: return ""
    # Pad 4-digit to 5-digit
    if len(s) == 4: s = '0' + s
    # Truncate to 5
    return s[:5]

test_cases = [
    ("1234", "01234"),
    ("12345-6789", "12345"),
    ("1234.0", "01234"),
    ("0123", "00123"), # 4 characters including leading 0
    ("8881", "08881"),
    ("", ""),
    (None, ""),
    ("  ", ""),
    ("123456", "12345"),
    ("ABC1234", "01234"),
]

print("Running Zip Fix Logic Tests...")
passed = 0
for input_val, expected in test_cases:
    result = _fix_zip(input_val)
    if result == expected:
        print(f"✅ PASS: Input '{input_val}' -> Result '{result}'")
        passed += 1
    else:
        print(f"❌ FAIL: Input '{input_val}' -> Expected '{expected}', got '{result}'")

print(f"\nSummary: {passed}/{len(test_cases)} passed.")
