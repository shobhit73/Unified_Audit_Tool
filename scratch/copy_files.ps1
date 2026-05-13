$src = 'c:\Users\shobhit.sharma\Downloads\Deduction Tool'
$dst = 'c:\Users\shobhit.sharma\Downloads\Deduction Tool\implementors_repo'

# Create directories
New-Item -ItemType Directory -Force -Path "$dst\apps\adp"
New-Item -ItemType Directory -Force -Path "$dst\apps\paycom\assets"
New-Item -ItemType Directory -Force -Path "$dst\utils"
New-Item -ItemType Directory -Force -Path "$dst\audit_fast_api\core\census"

# Copy Apps
Copy-Item -Path "$src\apps\adp\census_audit.py" -Destination "$dst\apps\adp"
Copy-Item -Path "$src\apps\adp\census_generator.py" -Destination "$dst\apps\adp"
Copy-Item -Path "$src\apps\paycom\census_audit.py" -Destination "$dst\apps\paycom"
Copy-Item -Path "$src\apps\paycom\census_generator.py" -Destination "$dst\apps\paycom"

# Check for __init__.py in apps
if (Test-Path "$src\apps\__init__.py") { Copy-Item -Path "$src\apps\__init__.py" -Destination "$dst\apps" }
if (Test-Path "$src\apps\adp\__init__.py") { Copy-Item -Path "$src\apps\adp\__init__.py" -Destination "$dst\apps\adp" }
if (Test-Path "$src\apps\paycom\__init__.py") { Copy-Item -Path "$src\apps\paycom\__init__.py" -Destination "$dst\apps\paycom" }

# Copy Utils
Copy-Item -Path "$src\utils\__init__.py" -Destination "$dst\utils"
Copy-Item -Path "$src\utils\audit_utils.py" -Destination "$dst\utils"
Copy-Item -Path "$src\utils\ui_components.py" -Destination "$dst\utils"
Copy-Item -Path "$src\utils\preprocess_source_data.py" -Destination "$dst\utils"
if (Test-Path "$src\utils\job_title_mapper.py") { Copy-Item -Path "$src\utils\job_title_mapper.py" -Destination "$dst\utils" }

# Copy Core Logic
Copy-Item -Path "$src\audit_fast_api\core\census\__init__.py" -Destination "$dst\audit_fast_api\core\census"
Copy-Item -Path "$src\audit_fast_api\core\census\sanity_check.py" -Destination "$dst\audit_fast_api\core\census"
if (Test-Path "$src\audit_fast_api\__init__.py") { Copy-Item -Path "$src\audit_fast_api\__init__.py" -Destination "$dst\audit_fast_api" }
if (Test-Path "$src\audit_fast_api\core\__init__.py") { Copy-Item -Path "$src\audit_fast_api\core\__init__.py" -Destination "$dst\audit_fast_api\core" }

# Copy Assets
if (Test-Path "$src\apps\paycom\assets") { Copy-Item -Path "$src\apps\paycom\assets\*" -Destination "$dst\apps\paycom\assets" -Recurse -Force }

Write-Host 'Copy Completed!'
