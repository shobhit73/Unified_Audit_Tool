import urllib.request
import zipfile
import os
import shutil

url = "https://github.com/shobhit73/Unified_Audit_Tool/archive/refs/heads/main.zip"
zip_path = "repo.zip"
extract_path = "tmp_git_pull"

print("Downloading repository...")
try:
    urllib.request.urlretrieve(url, zip_path)
except Exception as e:
    print("Failed with main, trying master...")
    url = "https://github.com/shobhit73/Unified_Audit_Tool/archive/refs/heads/master.zip"
    urllib.request.urlretrieve(url, zip_path)

print("Extracting...")
if os.path.exists(extract_path):
    shutil.rmtree(extract_path)
os.makedirs(extract_path, exist_ok=True)

with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall(extract_path)

print(f"Extracted to {extract_path}")
extracted_folders = os.listdir(extract_path)
print(f"Folders found: {extracted_folders}")
