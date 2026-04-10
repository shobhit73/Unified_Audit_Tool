import shutil
import os

base_dir = r"c:\Users\rohit.kaushik\Downloads\Unified Audit Tool"
new_repo = os.path.join(base_dir, "tmp_git_pull", "Unified_Audit_Tool-main")

# Files to update from new repo
files_to_copy = [
    r"apps\adp\census_audit.py",
    r"apps\adp\prior_payroll_audit.py",
    r"apps\paycom\census_audit.py",
    r"docs\census.md"
]

for rel_path in files_to_copy:
    src = os.path.join(new_repo, rel_path)
    dst = os.path.join(base_dir, rel_path)
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        print(f"Copied: {rel_path}")

# Now for app.py, let's just see what the diff is
import difflib
with open(os.path.join(base_dir, "app.py"), "r") as f:
    local_app = f.readlines()
with open(os.path.join(new_repo, "app.py"), "r") as f:
    new_app = f.readlines()

print("\n--- Diff for app.py ---")
diff = difflib.unified_diff(local_app, new_app, fromfile='local_app', tofile='new_app', n=1)
for line in diff:
    print(line, end="")

