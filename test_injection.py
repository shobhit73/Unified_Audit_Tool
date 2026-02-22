import pandas as pd
from utils.audit_utils import generate_uzio_template, inject_into_uzio_template

# Dummy exact standard fields mapped so vendor dataframe yields data
df_source = pd.DataFrame([{
    'Associate ID': 'TEST-123',
    'Legal First Name': 'John',
    'Legal Last Name': 'Doe',
    'Hire/Rehire Date': '2023-01-01',
    'Annual Salary': '50000',
    'Regular Pay Rate Description': 'Salary'
}])

vendor_map = {
    'Employee ID': 'Associate ID',
    'First Name': 'Legal First Name',
    'Last Name': 'Legal Last Name',
    'Hire Date': 'Hire/Rehire Date',
    'Annual Salary': 'Annual Salary',
    'Pay Type': 'Regular Pay Rate Description'
}

df_uzio = generate_uzio_template(df_source, vendor_map)
wb = inject_into_uzio_template(df_uzio, template_path="templates/Uzio_Census_Template.xlsm")
wb.save("test_output.xlsm")
print("Test generation successful! Created test_output.xlsm")
