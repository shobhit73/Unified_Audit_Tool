"""Task 3 — row building, the zero filter, and the blocking validations."""
import io
import os
import sys

import pandas as pd

sys.path.insert(0, r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool")
import apps.adp.qualified_overtime as Q

CDC = r"C:\Users\rohit.kaushik\Downloads\CDC"
TEMPLATE = CDC + r"\Qualified_Overtime_Template_2026.xlsx"
PAYROLL = [CDC + r"\Payroll\Cleaned\Payroll History_Q3_cleaned.csv",
           CDC + r"\Payroll\Cleaned\PriorPayroll_03222026_06202026_06262026_cleaned.csv",
           CDC + r"\Payroll\Cleaned\PriorPayroll_12212025_03212026_03272026_cleaned.csv"]


class Upload(io.BytesIO):
    def __init__(self, path):
        super().__init__(open(path, "rb").read())
        self.name = os.path.basename(path)
        self.size = self.getbuffer().nbytes


ok = True


def check(label, got, want):
    global ok
    good = got == want
    ok = ok and good
    print("   %-46s %-24r %s" % (label, got, "OK" if good else "FAIL, want %r" % (want,)))


pay, _ = Q.read_payroll_files([Upload(p) for p in PAYROLL])
tpl, _ = Q.read_qot_template(Upload(TEMPLATE))
col, _ = Q.resolve_qot_column(pay)
res = Q.build_qot_rows(pay, tpl, col)

print("CDC, whole client:")
check("rows emitted", len(res["rows"]), 289)
check("employees emitted", res["employees_emitted"], 117)
check("employees dropped as zero", res["employees_dropped_zero"], 177)
check("total qot", round(res["total_qot"], 2), 13589.77)
check("overlaps", res["overlaps"], [])
check("missing dates", res["missing_dates"], [])
check("not in template", res["not_in_template"], [])
check("not blocked", Q.is_blocked(res), False)

r0 = res["rows"][0]
check("row keys", list(r0), Q.TEMPLATE_HEADERS)
check("dates verbatim", r0["Pay Date"], "03/27/2026")

print()
print("the three cases from the spec:")
by_emp = {}
for r in res["rows"]:
    by_emp.setdefault(r["Employee ID"], []).append(r)
# 11 paychecks, exactly one with a premium
check("14907Q48A rows", len(by_emp.get("14907Q48A", [])), 1)
check("14907Q48A premium", by_emp["14907Q48A"][0]["QOT Premium"], 36.34)
# 11 paychecks, ten with a premium
check("MY0KMI29H rows", len(by_emp.get("MY0KMI29H", [])), 10)
# no premium at all -> absent entirely
check("067PC9FLL absent", "067PC9FLL" in by_emp, False)

print()
print("synthetic blocking cases:")
tiny_tpl = pd.DataFrame([{"Employee ID": "E1", "First Name": "A", "Last Name": "B",
                          "Employment Status": "Active", "Period Start Date": "",
                          "Period End Date": "", "Pay Date": "", "QOT Premium": ""}])


def frame(rows):
    return pd.DataFrame([{Q.ADP_ID_COL: e, Q.ADP_START_COL: s, Q.ADP_END_COL: en,
                          Q.ADP_PAY_COL: p, Q.QOT_DEFAULT_COLUMN: v, "_file": f}
                         for e, s, en, p, v, f in rows])


overlap = frame([("E1", "01/01/2026", "03/31/2026", "04/03/2026", "10", "a.csv"),
                 ("E1", "03/01/2026", "03/07/2026", "03/13/2026", "5", "b.csv")])
r = Q.build_qot_rows(overlap, tiny_tpl, Q.QOT_DEFAULT_COLUMN)
check("overlap detected", len(r["overlaps"]), 1)
check("overlap blocks", Q.is_blocked(r), True)
check("overlap names both files",
      sorted([r["overlaps"][0]["File A"], r["overlaps"][0]["File B"]]), ["a.csv", "b.csv"])

same = frame([("E1", "01/01/2026", "01/07/2026", "01/09/2026", "10", "a.csv"),
              ("E1", "01/01/2026", "01/07/2026", "01/09/2026", "10", "b.csv")])
check("same period in two files blocks",
      Q.is_blocked(Q.build_qot_rows(same, tiny_tpl, Q.QOT_DEFAULT_COLUMN)), True)

partial = frame([("E1", "01/01/2026", "", "01/09/2026", "10", "a.csv")])
r = Q.build_qot_rows(partial, tiny_tpl, Q.QOT_DEFAULT_COLUMN)
check("missing one date detected", len(r["missing_dates"]), 1)
check("missing date blocks", Q.is_blocked(r), True)

negative = frame([("E1", "01/01/2026", "01/07/2026", "01/09/2026", "-4.50", "a.csv")])
check("negative premium kept",
      len(Q.build_qot_rows(negative, tiny_tpl, Q.QOT_DEFAULT_COLUMN)["rows"]), 1)

check("CDC pay years", res["pay_years"], [2026])
two_years = frame([("E1", "12/20/2025", "12/26/2025", "01/02/2026", "10", "a.csv"),
                   ("E1", "01/03/2026", "01/09/2026", "01/16/2026", "10", "a.csv"),
                   ("E1", "12/01/2024", "12/07/2024", "12/12/2024", "10", "a.csv")])
check("multiple pay years surfaced",
      Q.build_qot_rows(two_years, tiny_tpl, Q.QOT_DEFAULT_COLUMN)["pay_years"], [2024, 2026])
check("multiple pay years do NOT block",
      Q.is_blocked(Q.build_qot_rows(two_years, tiny_tpl, Q.QOT_DEFAULT_COLUMN)), False)

orphan = frame([("E9", "01/01/2026", "01/07/2026", "01/09/2026", "10", "a.csv")])
r = Q.build_qot_rows(orphan, tiny_tpl, Q.QOT_DEFAULT_COLUMN)
check("orphan not emitted", len(r["rows"]), 0)
check("orphan reported", len(r["not_in_template"]), 1)
check("orphan does not block", Q.is_blocked(r), False)

print()
print("TASK 3", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
