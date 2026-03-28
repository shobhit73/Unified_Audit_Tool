import sys
sys.stdout.reconfigure(encoding='utf-8')

def _strip_separators(val):
    return str(val).strip().replace('-', '').replace(' ', '')

def _strip_all(val):
    s = _strip_separators(val)
    return s.lstrip('0') or '0'

from collections import defaultdict

# Simulate source data with various edge cases
source_ids = [
    '024-86-3148',  # Hyphenated + leading zero
    '026-58-5829',  # Hyphenated + leading zero
    '015781731',    # Leading zero
    '809968086',    # Normal
    '01',           # Short with leading zero - Person A
    '001',          # Short with leading zero - Person B (COLLISION with 01)
    'AMXUG2HO',     # ADP alpha
]

# Build indexes
l2_index = defaultdict(set)
l3_index = defaultdict(set)
source_set = set(source_ids)
for sid in source_ids:
    l2_index[_strip_separators(sid)].add(sid)
    l3_index[_strip_all(sid)].add(sid)

# Test cases
test_cases = [
    ('024-86-3148', 'Exact match for hyphenated'),
    ('24863148',    'Without hyphens + leading zero'),
    ('026585829',   'Without hyphens + leading zero'),
    ('15781731',    'Without leading zero'),
    ('809968086',   'Exact match normal'),
    ('01',          'Exact match short'),
    ('001',         'Exact match short collision'),
    ('1',           'Stripped — should COLLIDE with 01 and 001'),
    ('AMXUG2HO',    'Exact match alpha'),
]

print("=" * 70)
print("3-LEVEL PROGRESSIVE MATCHING TEST")
print("=" * 70)

for user_id, desc in test_cases:
    result = "?"
    level = "?"
    details = ""
    
    # Level 1: Exact
    if user_id in source_set:
        result = "MATCHED"
        level = "L1-Exact"
    else:
        # Level 2: Strip hyphens/spaces
        l2_key = _strip_separators(user_id)
        l2_cands = l2_index.get(l2_key, set())
        if len(l2_cands) == 1:
            result = f"MATCHED → '{list(l2_cands)[0]}'"
            level = "L2-Hyphens"
        elif len(l2_cands) > 1:
            result = f"COLLISION"
            level = "L2-Hyphens"
            details = f" (conflicts: {sorted(l2_cands)})"
        else:
            # Level 3: Strip leading zeros
            l3_key = _strip_all(user_id)
            l3_cands = l3_index.get(l3_key, set())
            if len(l3_cands) == 1:
                result = f"MATCHED → '{list(l3_cands)[0]}'"
                level = "L3-Zeros"
            elif len(l3_cands) > 1:
                result = f"COLLISION"
                level = "L3-Zeros"
                details = f" (conflicts: {sorted(l3_cands)})"
            else:
                result = "NO MATCH"
                level = "—"

    print(f"\n  Input: '{user_id}' — {desc}")
    print(f"  → {result} [{level}]{details}")

print("\n" + "=" * 70)
print("ALL TESTS COMPLETE")
print("=" * 70)
