import re
import pandas as pd

def norm_digits_v2(x):
    """The updated norm_digits logic."""
    if x is None:
        return ""
    if isinstance(x, (float, int)):
        if pd.isna(x):
            return ""
        # Handle float like 123.0 -> '123'
        return str(int(x))
    # For strings, just remove non-digits. This preserves leading zeros like '00123'.
    return re.sub(r"\D", "", str(x))

def test_norm_digits():
    test_cases = [
        ("00123", "00123"),
        ("123", "123"),
        ("000000", "000000"),
        ("01-23 45", "012345"),
        (123, "123"),
        (123.0, "123"),
        (None, ""),
    ]
    
    for input_val, expected in test_cases:
        actual = norm_digits_v2(input_val)
        assert actual == expected, f"Failed for {input_val}: expected {expected}, got {actual}"
        print(f"Passed: {input_val} -> {actual}")

if __name__ == "__main__":
    test_norm_digits()
    print("\nAll tests passed! Leading zeros are preserved for strings.")
