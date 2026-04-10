import os
import filecmp
import shutil

base_dir = r"c:\Users\rohit.kaushik\Downloads\Unified Audit Tool"
new_repo = os.path.join(base_dir, "tmp_git_pull", "Unified_Audit_Tool-main")

# Let's compare files
def compare_dirs(dir1, dir2):
    dcmp = filecmp.dircmp(dir1, dir2)
    print(f"\n--- Comparing {dir1} and {dir2} ---")
    if dcmp.diff_files:
        print(f"Differing files: {dcmp.diff_files}")
    if dcmp.left_only:
        print(f"Only in local: {dcmp.left_only}")
    if dcmp.right_only:
        print(f"Only in new repo: {dcmp.right_only}")
    
    for sub in dcmp.common_dirs:
        if sub not in ['.git', '__pycache__', 'venv', '.devcontainer']:
            compare_dirs(os.path.join(dir1, sub), os.path.join(dir2, sub))

compare_dirs(base_dir, new_repo)
