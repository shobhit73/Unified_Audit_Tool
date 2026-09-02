"""Task 2 — reading the UZIO Qualified Overtime template."""
import io
import os
import sys

import pandas as pd

sys.path.insert(0, r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool")
import apps.adp.qualified_overtime as Q

CDC = r"C:\Users\rohit.kaushik\Downloads\CDC"
TEMPLATE = CDC + r"\Qualified_Overtime_Template_2026.xlsx"


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
    print("   %-44s %-30r %s" % (label, got, "OK" if good else "FAIL, want %r" % (want,)))


tpl, err = Q.read_qot_template(Upload(TEMPLATE))
check("no error", err, None)
check("employees", len(tpl), 284)
check("headers", list(tpl.columns), Q.TEMPLATE_HEADERS)
check("ids are strings", isinstance(tpl["Employee ID"].iloc[0], str), True)
check("first id", tpl["Employee ID"].iloc[0], "067PC9FLL")
check("status values", sorted(tpl["Employment Status"].unique()), ["Active", "Terminated"])

# a workbook with no QOT Details sheet must be refused, not guessed at
bad = io.BytesIO()
pd.DataFrame({"a": [1]}).to_excel(bad, index=False, sheet_name="Something Else")
bad.seek(0)
bad.name = "bad.xlsx"
tpl2, err2 = Q.read_qot_template(bad)
check("bad workbook -> None", tpl2, None)
check("bad workbook -> error", isinstance(err2, str) and "QOT Details" in err2, True)

print()
print("TASK 2", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
