import yaml
with open(r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool\key_mapping.yml", "r", encoding="utf-8") as f:
    data = yaml.safe_load(f)
for state in ("MA", "IL", "NJ", "CA", "FED"):
    bucket = data["withholding_es"]["mappings"].get(state, {})
    print(f"--- {state} ({len(bucket)} entries) ---")
    for k, meta in bucket.items():
        if isinstance(meta, dict):
            print(f"  {k}  =>  {meta.get('label','')}")
    print()
