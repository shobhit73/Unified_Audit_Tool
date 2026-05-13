"""Verify each guarded handler refuses wrong-vendor files and accepts right-vendor."""
import sys, asyncio, os
sys.path.insert(0, r"c:\Users\shobhit.sharma\Downloads\Deduction Tool\audit_fast_api")

import mcp_server

# Save fake files we can use as wrong-vendor inputs
WORK = r"C:\Users\shobhit.sharma\Desktop\Audit Files"
os.makedirs(WORK, exist_ok=True)

fake_uzio = os.path.join(WORK, "_test_fake_uzio.csv")
with open(fake_uzio, "wb") as f:
    f.write(b"Personal|SSN,Job|Employee ID,Job|Department,Job|Job Title\n123-45-6789,001,IT,Engineer\n")

fake_paycom = os.path.join(WORK, "_test_fake_paycom.csv")
with open(fake_paycom, "wb") as f:
    f.write(b"Employee_Code,SS_Number,DOL_Status,Department_Desc,Exempt_Status\n001,123-45-6789,Full-Time,IT,Yes\n")

real_adp = r"C:\Users\shobhit.sharma\Downloads\Carvan Prior Payroll Setup\Payroll_History_Q1_Consolidated.csv"


async def call(name, args):
    res = await mcp_server.handle_call_tool(name, args)
    return res[0].text if res else "<no response>"


async def main():
    print("=" * 70)
    print("TEST: each guarded tool rejects wrong-vendor and accepts right-vendor")
    print("=" * 70)

    cases = [
        # (handler, wrong-vendor file, expected_error_keyword)
        ("adp_prior_payroll_sanity", fake_uzio, "UZIO"),
        ("adp_prior_payroll_sanity", fake_paycom, "PAYCOM"),
        ("adp_census_sanity", fake_uzio, "UZIO"),
        ("adp_census_sanity", fake_paycom, "PAYCOM"),
        ("adp_census_generator", fake_uzio, "UZIO"),
        ("adp_prior_payroll_setup_helper", fake_uzio, "UZIO"),
        ("paycom_census_sanity", fake_uzio, "UZIO"),
        # Note: We don't have a fake ADP file; skip those.
    ]
    for handler, path, expected in cases:
        out = await call(handler, {"file_path": path})
        ok = expected in out
        flag = "OK " if ok else "FAIL"
        print(f"  [{flag}] {handler}({os.path.basename(path)}) -> contains '{expected}'")
        if not ok:
            print(f"        actual: {out[:200]}")

    # Real ADP file passes the guard
    print()
    print("Real ADP file should pass guard (we'll just call ask-mode of sanity):")
    out = await call("adp_prior_payroll_sanity", {"file_path": real_adp})
    if "detection_only" in out:
        print(f"  [OK ] adp_prior_payroll_sanity accepted the real ADP file (ask-mode summary returned)")
    else:
        print(f"  [FAIL] real ADP file got blocked or other error: {out[:300]}")

    # Cleanup
    os.remove(fake_uzio)
    os.remove(fake_paycom)


asyncio.run(main())
