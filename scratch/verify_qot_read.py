"""Task 1 — payroll reading + QOT column resolution."""
import io
import os
import sys

sys.path.insert(0, r"C:\Users\rohit.kaushik\Downloads\Unified_Audit_Tool")
import apps.adp.qualified_overtime as Q

CDC = r"C:\Users\rohit.kaushik\Downloads\CDC"
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
    print("   %-46s %-28r %s" % (label, got, "OK" if good else "FAIL, want %r" % (want,)))


df, errors = Q.read_payroll_files([Upload(p) for p in PAYROLL])
check("rows", len(df), 1692)
check("errors", errors, [])
check("employees", df[Q.ADP_ID_COL].nunique(), 294)
check("_file column present", "_file" in df.columns, True)
check("id is string", isinstance(df[Q.ADP_ID_COL].iloc[0], str), True)

col, per_file = Q.resolve_qot_column(df)
check("resolved column", col, Q.QOT_DEFAULT_COLUMN)
check("all three files have it", sorted(per_file.values()), [True, True, True])

memos = Q.memo_columns(df)
check("TOTAL MEMOS excluded", "TOTAL MEMOS" in memos, False)
check("default column listed", Q.QOT_DEFAULT_COLUMN in memos, True)

# when the real column is absent, nothing is resolved and the caller must ask
stripped = df.drop(columns=[Q.QOT_DEFAULT_COLUMN])
col2, _ = Q.resolve_qot_column(stripped)
check("absent -> None", col2, None)
check("explicit choice honoured",
      Q.resolve_qot_column(stripped, chosen="MEMO : PTO-PAID TIME OFF")[0],
      "MEMO : PTO-PAID TIME OFF")

print()
print("TASK 1", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
