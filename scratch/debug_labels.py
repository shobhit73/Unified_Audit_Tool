import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool")  # so load_key_mapping_yml finds it
from apps.adp.withholding_audit import load_key_mapping_yml, field_label

labels = load_key_mapping_yml()
print("Top-level keys (first 10):", list(labels.keys())[:10])
print("MA keys:", list(labels.get("MA", {}).keys()))
print()
print("field_label('SIT_TOTAL_ALLOWANCES', labels, 'MA') =>",
      repr(field_label("SIT_TOTAL_ALLOWANCES", labels, "MA")))
print("field_label('SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD', labels, 'MA') =>",
      repr(field_label("SIT_ADDL_WITHHOLDING_PER_PAY_PERIOD", labels, "MA")))
print("field_label('FIT_HIGHER_WITHHOLDING', labels, '') =>",
      repr(field_label("FIT_HIGHER_WITHHOLDING", labels, "")))
