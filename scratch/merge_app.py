import os

base_dir = r"c:\Users\rohit.kaushik\Downloads\Unified Audit Tool"
new_repo = os.path.join(base_dir, "tmp_git_pull", "Unified_Audit_Tool-main")

with open(os.path.join(new_repo, "app.py"), "r") as f:
    new_app_lines = f.readlines()

output_lines = []
for line in new_app_lines:
    if '            "ADP - Prior Payroll Audit"' in line:
        output_lines.append(line.replace('\n', '') + ',\n')
        output_lines.append('            "ADP - Prior Payroll Audit Tool"\n')
    elif 'elif tool_option == "Paycom - Census Audit":' in line:
        output_lines.append('elif tool_option == "ADP - Prior Payroll Audit Tool":\n')
        output_lines.append('    from apps.adp import total_comparison\n')
        output_lines.append('    importlib.reload(total_comparison)\n')
        output_lines.append('    total_comparison.render_ui()\n\n')
        output_lines.append(line)
    else:
        output_lines.append(line)

with open(os.path.join(base_dir, "app.py"), "w") as f:
    f.writelines(output_lines)
    
print("Updated app.py with synced changes.")
