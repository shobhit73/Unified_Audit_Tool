"""Verify the filing-status loader is actually parsing the txt file."""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from apps.adp.withholding_audit import (
    load_filing_status_map, FILING_STATUS_MAP_FALLBACK,
    _resolve_filing_status_path,
)

path = _resolve_filing_status_path()
print(f"Resolved path: {path}")
print()

# Test 1: with the real file present, merged should equal fallback (already in sync).
load_filing_status_map.cache_clear()
fs1 = load_filing_status_map()
print(f"Test 1 (file present): merged size = {len(fs1)} (fallback = {len(FILING_STATUS_MAP_FALLBACK)})")

# Test 2: point env var at a small file with a NEW code we know isn't in the
# hardcoded dict. If the loader is doing its job, the new code shows up in
# the merged map.
fake = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8")
fake.write('TEST_NEW_CODE("Brand New Status"), ANOTHER_TEST("Second New One")')
fake.close()
os.environ["FILING_STATUS_CODE"] = fake.name
load_filing_status_map.cache_clear()
fs2 = load_filing_status_map()
print(f"Test 2 (env var to fake file): merged size = {len(fs2)}")
print(f"  TEST_NEW_CODE present?      {fs2.get('TEST_NEW_CODE')!r}")
print(f"  ANOTHER_TEST present?       {fs2.get('ANOTHER_TEST')!r}")
print(f"  Hardcoded FEDERAL_SINGLE still present (fallback merged)?  {fs2.get('FEDERAL_SINGLE')!r}")

# Test 3: env var to a non-existent path -> should fall back gracefully.
os.environ["FILING_STATUS_CODE"] = "C:/does/not/exist.txt"
load_filing_status_map.cache_clear()
fs3 = load_filing_status_map()
print(f"Test 3 (env var to nonexistent): merged size = {len(fs3)}  (should equal fallback {len(FILING_STATUS_MAP_FALLBACK)})")

# Cleanup
del os.environ["FILING_STATUS_CODE"]
os.unlink(fake.name)
